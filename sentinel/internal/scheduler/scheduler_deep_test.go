package scheduler

import (
	"context"
	"sync"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

type notifyCall struct {
	event  string
	errMsg string
	target string
}

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := store.New(d)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant failed: %v", err)
	}
	return st
}

func newMonitor(t *testing.T, st *store.Store, name string, enabled int) store.Monitor {
	t.Helper()
	id, err := st.CreateMonitor(store.Monitor{
		Name:           name,
		Kind:           "http",
		Target:         "http://example.invalid/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        enabled,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}
	m, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("GetMonitor failed: %v", err)
	}
	return m
}

func TestNew_Defaults(t *testing.T) {
	st := newTestStore(t)
	s := New(st, nil, 0, 0, -1)
	if cap(s.sem) != 10 {
		t.Fatalf("expected cap(s.sem)==10, got %d", cap(s.sem))
	}
	if s.tickSec != 5 {
		t.Fatalf("expected tickSec==5, got %d", s.tickSec)
	}
	if s.maxRetries != 0 {
		t.Fatalf("expected maxRetries==0, got %d", s.maxRetries)
	}
}

func TestNew_CustomValues(t *testing.T) {
	st := newTestStore(t)
	fn := func(m store.Monitor, event, name, target, at, errMsg string) {}
	s := New(st, fn, 3, 7, 2)
	if cap(s.sem) != 3 {
		t.Fatalf("expected cap(s.sem)==3, got %d", cap(s.sem))
	}
	if s.tickSec != 7 {
		t.Fatalf("expected tickSec==7, got %d", s.tickSec)
	}
	if s.maxRetries != 2 {
		t.Fatalf("expected maxRetries==2, got %d", s.maxRetries)
	}
}

func TestRecord_FirstFailureOpensIncident(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "first-fail", 1)

	var mu sync.Mutex
	var calls []notifyCall
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		calls = append(calls, notifyCall{event: event, errMsg: errMsg, target: target})
		mu.Unlock()
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 0, LatencyMs: 1, Error: "boom"}, false, false)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 1 {
		t.Fatalf("expected 1 open incident, got %d", len(incidents))
	}

	mu.Lock()
	defer mu.Unlock()
	if len(calls) != 1 {
		t.Fatalf("expected notify called once, got %d", len(calls))
	}
	if calls[0].event != "down" {
		t.Fatalf("expected event down, got %q", calls[0].event)
	}
	if calls[0].errMsg != "boom" {
		t.Fatalf("expected errMsg boom, got %q", calls[0].errMsg)
	}
	if calls[0].target != m.Target {
		t.Fatalf("expected target %q, got %q", m.Target, calls[0].target)
	}
}

func TestRecord_RepeatFailureNoDuplicate(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "repeat-fail", 1)

	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := st.OpenIncident(m.ID, now, "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	later := time.Now().UTC().Add(time.Minute).Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: later, Ok: 0, Error: "still down"}, false, true)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 1 {
		t.Fatalf("expected 1 open incident, got %d", len(incidents))
	}
	if notified != 0 {
		t.Fatalf("expected no notify, got %d", notified)
	}
}

func TestRecord_FailureAfterSuccess(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "fail-after-success", 1)

	notified := 0
	var lastEvent string
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
		lastEvent = event
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 0, Error: "down now"}, true, true)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 1 {
		t.Fatalf("expected 1 open incident, got %d", len(incidents))
	}
	if notified != 1 {
		t.Fatalf("expected notify once, got %d", notified)
	}
	if lastEvent != "down" {
		t.Fatalf("expected event down, got %q", lastEvent)
	}
}

func TestRecord_RecoverClosesIncident(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "recover", 1)

	startedAt := time.Now().UTC().Add(-5 * time.Minute).Format(time.RFC3339)
	if _, err := st.OpenIncident(m.ID, startedAt, "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	var mu sync.Mutex
	var calls []notifyCall
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		calls = append(calls, notifyCall{event: event, errMsg: errMsg})
		mu.Unlock()
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 1, LatencyMs: 3}, false, true)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 0 {
		t.Fatalf("expected 0 open incidents, got %d", len(incidents))
	}

	mu.Lock()
	defer mu.Unlock()
	if len(calls) != 1 {
		t.Fatalf("expected notify once, got %d", len(calls))
	}
	if calls[0].event != "recovered" {
		t.Fatalf("expected event recovered, got %q", calls[0].event)
	}
	if calls[0].errMsg != "" {
		t.Fatalf("expected empty errMsg, got %q", calls[0].errMsg)
	}
}

func TestRecord_SuccessNoHistory(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "success-nohistory", 1)

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 1, LatencyMs: 2}, false, false)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 0 {
		t.Fatalf("expected 0 open incidents, got %d", len(incidents))
	}
	if notified != 0 {
		t.Fatalf("expected no notify, got %d", notified)
	}
}

func TestRecord_NilNotifyNoPanic(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "nil-notify", 1)
	s := New(st, nil, 1, 1, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 0, Error: "boom"}, false, false)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 1 {
		t.Fatalf("expected 1 open incident, got %d", len(incidents))
	}
}

func TestTick_SkipsDisabled(t *testing.T) {
	st := newTestStore(t)
	_ = newMonitor(t, st, "disabled", 0)

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	s.tick(context.Background())

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 0 {
		t.Fatalf("expected 0 open incidents, got %d", len(incidents))
	}
	if notified != 0 {
		t.Fatalf("expected no notify, got %d", notified)
	}
}

func TestTick_NoMonitors(t *testing.T) {
	st := newTestStore(t)

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	s.tick(context.Background())

	if notified != 0 {
		t.Fatalf("expected no notify, got %d", notified)
	}
}

func TestCheckNow_UnknownMonitor(t *testing.T) {
	st := newTestStore(t)
	s := New(st, nil, 2, 5, 0)

	if _, err := s.CheckNow(999999, 0); err == nil {
		t.Fatalf("expected error for unknown monitor, got nil")
	}
}

func TestRecord_SilenceSuppressesNotify(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "silenced", 1)

	startsAt := time.Now().UTC().Add(-1 * time.Hour).Format(time.RFC3339)
	endsAt := time.Now().UTC().Add(1 * time.Hour).Format(time.RFC3339)
	if _, err := st.CreateSilence(store.Silence{
		MonitorID: m.ID,
		NameMatch: "",
		StartsAt:  startsAt,
		EndsAt:    endsAt,
		Reason:    "maintenance",
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}); err != nil {
		t.Fatalf("CreateSilence failed: %v", err)
	}

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 0, Error: "boom"}, false, false)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 1 {
		t.Fatalf("expected 1 open incident, got %d", len(incidents))
	}
	if notified != 0 {
		t.Fatalf("expected notify suppressed, got %d", notified)
	}
}
