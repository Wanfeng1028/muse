package scheduler

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"sentinel/internal/escalation"
	"sentinel/internal/store"
)

func deep2NewStore(t *testing.T) *store.Store {
	t.Helper()
	return newTestStore(t)
}

func deep2NewMonitor(t *testing.T, st *store.Store, name string, enabled int) store.Monitor {
	t.Helper()
	return newMonitor(t, st, name, enabled)
}

func TestDeep2_CheckNow_KnownMonitorNoLastCheck(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "checknow-nolast", 1)

	var mu sync.Mutex
	var events []string
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		events = append(events, event)
		mu.Unlock()
	}
	s := New(st, fn, 2, 5, 0)

	c, err := s.CheckNow(m.ID, 0)
	if err != nil {
		t.Fatalf("CheckNow failed: %v", err)
	}
	if c.MonitorID != m.ID {
		t.Fatalf("expected check MonitorID %d, got %d", m.ID, c.MonitorID)
	}
	if c.CheckedAt == "" {
		t.Fatalf("expected non-empty CheckedAt")
	}
	if _, perr := time.Parse(time.RFC3339, c.CheckedAt); perr != nil {
		t.Fatalf("CheckedAt not RFC3339: %v", perr)
	}

	last, err := st.LastCheck(m.ID)
	if err != nil {
		t.Fatalf("LastCheck failed: %v", err)
	}
	if last == nil {
		t.Fatalf("expected persisted last check, got nil")
	}
	// 这是该 monitor 持久化的第一条 check 记录, ID 从 1 开始。
	if last.ID != 1 {
		t.Fatalf("expected persisted check ID 1, got %d", last.ID)
	}
}

func TestDeep2_CheckNow_SecondCallHasHistory(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "checknow-history", 1)

	s := New(st, nil, 2, 5, 0)

	if _, err := s.CheckNow(m.ID, 0); err != nil {
		t.Fatalf("first CheckNow failed: %v", err)
	}
	if _, err := s.CheckNow(m.ID, 0); err != nil {
		t.Fatalf("second CheckNow failed: %v", err)
	}

	checks, err := st.ListChecks(m.ID, 100)
	if err != nil {
		t.Fatalf("ListChecks failed: %v", err)
	}
	if len(checks) < 2 {
		t.Fatalf("expected at least 2 checks, got %d", len(checks))
	}
}

func TestDeep2_Tick_RespectsInflightGuard(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "inflight", 1)

	s := New(st, nil, 4, 5, 0)

	s.mu.Lock()
	s.inflight[m.ID] = true
	s.mu.Unlock()

	s.tick(context.Background())

	s.mu.Lock()
	still := s.inflight[m.ID]
	s.mu.Unlock()
	if !still {
		t.Fatalf("expected inflight entry preserved for %d", m.ID)
	}

	checks, err := st.ListChecks(m.ID, 10)
	if err != nil {
		t.Fatalf("ListChecks failed: %v", err)
	}
	if len(checks) != 0 {
		t.Fatalf("expected no checks while inflight, got %d", len(checks))
	}
}

func TestDeep2_Tick_ReleasesInflightAfterRun(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "inflight-release", 1)

	s := New(st, nil, 4, 5, 0)

	s.tick(context.Background())

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		busy := s.inflight[m.ID]
		s.mu.Unlock()
		if !busy {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("inflight entry for %d was never released", m.ID)
}

func TestDeep2_New_NegativeConcurrencyDefaultsToTen(t *testing.T) {
	st := deep2NewStore(t)
	s := New(st, nil, -7, 3, 1)
	if cap(s.sem) != 10 {
		t.Fatalf("expected default concurrency 10, got %d", cap(s.sem))
	}
	if s.tickSec != 3 {
		t.Fatalf("expected tickSec 3, got %d", s.tickSec)
	}
	if s.maxRetries != 1 {
		t.Fatalf("expected maxRetries 1, got %d", s.maxRetries)
	}
}

func TestDeep2_New_NegativeTickDefaultsToFive(t *testing.T) {
	st := deep2NewStore(t)
	s := New(st, nil, 2, -1, 0)
	if s.tickSec != 5 {
		t.Fatalf("expected default tickSec 5, got %d", s.tickSec)
	}
}

func TestDeep2_Start_ExitsOnContextCancel(t *testing.T) {
	st := deep2NewStore(t)
	_ = deep2NewMonitor(t, st, "start-cancel", 0)

	s := New(st, nil, 2, 1, 0)

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan struct{})
	go func() {
		s.Start(ctx)
		close(done)
	}()

	time.Sleep(50 * time.Millisecond)
	cancel()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatalf("Start did not return after context cancel")
	}
}

func TestDeep2_Record_ZeroSecsWhenRecoverBeforeStart(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "recover-negsecs", 1)

	startedAt := time.Now().UTC().Add(30 * time.Minute).Format(time.RFC3339)
	if _, err := st.OpenIncident(m.ID, startedAt, "future-start"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 1}, false, true)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 0 {
		t.Fatalf("expected 0 open incidents, got %d", len(incidents))
	}
	if notified != 1 {
		t.Fatalf("expected notify once, got %d", notified)
	}
}

func TestDeep2_Record_SuccessNoNotifyWithoutPrevFailure(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "success-prevok", 1)

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	s.record(m, store.Check{MonitorID: m.ID, CheckedAt: now, Ok: 1}, true, true)

	incidents, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("ListOpenIncidents failed: %v", err)
	}
	if len(incidents) != 0 {
		t.Fatalf("expected 0 open incidents, got %d", len(incidents))
	}
	if notified != 0 {
		t.Fatalf("expected no notify on steady success, got %d", notified)
	}
}

func TestDeep2_SetEscalation_EmptyDisables(t *testing.T) {
	st := deep2NewStore(t)
	s := New(st, nil, 2, 5, 0)

	policy := []escalation.Level{
		{AfterMinutes: 5, Channels: []string{"email"}},
	}
	s.SetEscalation(policy)

	s.mu.Lock()
	got := len(s.escalation)
	s.mu.Unlock()
	if got != 1 {
		t.Fatalf("expected escalation len 1, got %d", got)
	}

	s.SetEscalation(nil)

	s.mu.Lock()
	got = len(s.escalation)
	s.mu.Unlock()
	if got != 0 {
		t.Fatalf("expected escalation len 0 after nil, got %d", got)
	}
}

func TestDeep2_CheckEscalations_NoPolicyNoop(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "esc-noop", 1)

	startedAt := time.Now().UTC().Add(-30 * time.Minute).Format(time.RFC3339)
	if _, err := st.OpenIncident(m.ID, startedAt, "down"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	s.checkEscalations()

	if notified != 0 {
		t.Fatalf("expected no notify with empty policy, got %d", notified)
	}
}

func TestDeep2_CheckEscalations_TriggersDueLevel(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "esc-due", 1)

	startedAt := time.Now().UTC().Add(-30 * time.Minute).Format(time.RFC3339)
	if _, err := st.OpenIncident(m.ID, startedAt, "down-long"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	var mu sync.Mutex
	var events []string
	var errMsgs []string
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		events = append(events, event)
		errMsgs = append(errMsgs, errMsg)
		mu.Unlock()
	}
	s := New(st, fn, 2, 5, 0)
	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 10, Channels: []string{"email"}},
	})

	s.checkEscalations()

	mu.Lock()
	defer mu.Unlock()
	if len(events) != 1 {
		t.Fatalf("expected 1 escalation notify, got %d", len(events))
	}
	if events[0] != "escalated" {
		t.Fatalf("expected event escalated, got %q", events[0])
	}
	if errMsgs[0] == "" {
		t.Fatalf("expected non-empty escalation errMsg")
	}
}

func TestDeep2_CheckEscalations_Idempotent(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "esc-idem", 1)

	startedAt := time.Now().UTC().Add(-30 * time.Minute).Format(time.RFC3339)
	if _, err := st.OpenIncident(m.ID, startedAt, "down-long"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	var count int64
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		atomic.AddInt64(&count, 1)
	}
	s := New(st, fn, 2, 5, 0)
	s.SetEscalation([]escalation.Level{
		{AfterMinutes: 10, Channels: []string{"email"}},
	})

	s.checkEscalations()
	s.checkEscalations()
	s.checkEscalations()

	if got := atomic.LoadInt64(&count); got != 1 {
		t.Fatalf("expected exactly 1 escalation notify across repeated scans, got %d", got)
	}
}

func TestDeep2_NotifyUnlessSilenced_NoActiveWindow(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "silence-inactive", 1)

	startsAt := time.Now().UTC().Add(-2 * time.Hour).Format(time.RFC3339)
	endsAt := time.Now().UTC().Add(-1 * time.Hour).Format(time.RFC3339)
	if _, err := st.CreateSilence(store.Silence{
		MonitorID: m.ID,
		StartsAt:  startsAt,
		EndsAt:    endsAt,
		Reason:    "expired",
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}); err != nil {
		t.Fatalf("CreateSilence failed: %v", err)
	}

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	s.notifyUnlessSilenced(m, "down", m.Name, m.Target, time.Now().UTC().Format(time.RFC3339), "boom")

	if notified != 1 {
		t.Fatalf("expected notify when silence window expired, got %d", notified)
	}
}

func TestDeep2_Tick_MonitorNotDueSkipped(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "not-due", 1)

	recent := time.Now().UTC().Add(-1 * time.Second).Format(time.RFC3339)
	if _, err := st.InsertCheck(store.Check{
		MonitorID: m.ID,
		CheckedAt: recent,
		Ok:        1,
		LatencyMs: 1,
	}); err != nil {
		t.Fatalf("InsertCheck failed: %v", err)
	}

	notified := 0
	fn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}
	s := New(st, fn, 2, 5, 0)

	s.tick(context.Background())

	checks, err := st.ListChecks(m.ID, 100)
	if err != nil {
		t.Fatalf("ListChecks failed: %v", err)
	}
	if len(checks) != 1 {
		t.Fatalf("expected tick to skip not-due monitor, checks=%d", len(checks))
	}
	if notified != 0 {
		t.Fatalf("expected no notify, got %d", notified)
	}
}

func TestDeep2_Tick_BadCheckedAtIsTreatedDue(t *testing.T) {
	st := deep2NewStore(t)
	m := deep2NewMonitor(t, st, "bad-timestamp", 1)

	if _, err := st.InsertCheck(store.Check{
		MonitorID: m.ID,
		CheckedAt: "not-a-rfc3339-timestamp",
		Ok:        1,
		LatencyMs: 1,
	}); err != nil {
		t.Fatalf("InsertCheck failed: %v", err)
	}

	s := New(st, nil, 4, 5, 0)

	s.tick(context.Background())

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		checks, err := st.ListChecks(m.ID, 100)
		if err != nil {
			t.Fatalf("ListChecks failed: %v", err)
		}
		if len(checks) >= 2 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("expected tick to re-check monitor with unparsable CheckedAt")
}
