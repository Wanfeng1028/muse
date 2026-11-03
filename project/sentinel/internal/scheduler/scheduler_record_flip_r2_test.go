package scheduler

import (
	"sync"
	"testing"
	"time"

	"sentinel/internal/store"
)

type r2RecordNotification struct {
	monitor store.Monitor
	event   string
	name    string
	target  string
	at      string
	errMsg  string
}

func TestR2_RecordFirstDownOpensIncident(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "m1", 1)

	var mu sync.Mutex
	var events []r2RecordNotification
	notifyFn := func(monitor store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, r2RecordNotification{
			monitor: monitor,
			event:   event,
			name:    name,
			target:  target,
			at:      at,
			errMsg:  errMsg,
		})
	}

	s := New(st, notifyFn, 10, 5, 0)

	c := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom",
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}

	s.record(m, c, false, false)

	mu.Lock()
	gotCount := len(events)
	var got r2RecordNotification
	if gotCount == 1 {
		got = events[0]
	}
	mu.Unlock()

	if gotCount != 1 {
		t.Fatalf("notify count = %d, want 1", gotCount)
	}
	if got.event != "down" {
		t.Fatalf("notify event = %q, want %q", got.event, "down")
	}
	if got.name != m.Name {
		t.Fatalf("notify name = %q, want %q", got.name, m.Name)
	}
	if got.target != m.Target {
		t.Fatalf("notify target = %q, want %q", got.target, m.Target)
	}
	if got.errMsg != "boom" {
		t.Fatalf("notify errMsg = %q, want %q", got.errMsg, "boom")
	}

	startedAt, err := st.OpenIncidentStartedAt(m.ID)
	if err != nil {
		t.Fatalf("OpenIncidentStartedAt returned error: %v", err)
	}
	if startedAt == "" {
		t.Fatal("OpenIncidentStartedAt returned empty startedAt")
	}
}

func TestR2_RecordDownDownNoDuplicate(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "m1", 1)

	var mu sync.Mutex
	var events []r2RecordNotification
	notifyFn := func(monitor store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, r2RecordNotification{
			monitor: monitor,
			event:   event,
			name:    name,
			target:  target,
			at:      at,
			errMsg:  errMsg,
		})
	}

	s := New(st, notifyFn, 10, 5, 0)

	c := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom",
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}

	s.record(m, c, false, false)
	s.record(m, c, false, true)

	mu.Lock()
	gotCount := len(events)
	mu.Unlock()

	if gotCount != 1 {
		t.Fatalf("notify count = %d, want 1", gotCount)
	}

	verifyAt := time.Now().UTC().Format(time.RFC3339)
	_, created, err := st.OpenIncident(m.ID, verifyAt, "boom")
	if err != nil {
		t.Fatalf("OpenIncident returned error: %v", err)
	}
	if created {
		t.Fatal("OpenIncident created a duplicate open incident")
	}

	startedAt, err := st.OpenIncidentStartedAt(m.ID)
	if err != nil {
		t.Fatalf("OpenIncidentStartedAt returned error: %v", err)
	}
	if startedAt == "" {
		t.Fatal("OpenIncidentStartedAt returned empty startedAt")
	}
}

func TestR2_RecordRecoverClosesIncident(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "m1", 1)

	var mu sync.Mutex
	var events []r2RecordNotification
	notifyFn := func(monitor store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, r2RecordNotification{
			monitor: monitor,
			event:   event,
			name:    name,
			target:  target,
			at:      at,
			errMsg:  errMsg,
		})
	}

	s := New(st, notifyFn, 10, 5, 0)

	downCheck := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom",
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}
	s.record(m, downCheck, false, false)

	upCheck := store.Check{
		MonitorID: m.ID,
		Ok:        1,
		CheckedAt: time.Now().Add(2 * time.Second).UTC().Format(time.RFC3339),
	}
	s.record(m, upCheck, false, true)

	mu.Lock()
	gotCount := len(events)
	var recovered r2RecordNotification
	if gotCount == 2 {
		recovered = events[1]
	}
	mu.Unlock()

	if gotCount != 2 {
		t.Fatalf("notify count = %d, want 2", gotCount)
	}
	if recovered.event != "recovered" {
		t.Fatalf("notify event = %q, want %q", recovered.event, "recovered")
	}
	if recovered.name != m.Name {
		t.Fatalf("notify name = %q, want %q", recovered.name, m.Name)
	}
	if recovered.target != m.Target {
		t.Fatalf("notify target = %q, want %q", recovered.target, m.Target)
	}
	if recovered.errMsg != "" {
		t.Fatalf("notify errMsg = %q, want empty", recovered.errMsg)
	}

	if _, err := st.OpenIncidentStartedAt(m.ID); err == nil {
		t.Fatal("OpenIncidentStartedAt returned nil error, want open incident to be closed")
	}
}
