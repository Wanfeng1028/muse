package scheduler

import (
	"sync"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_RecordUpUpSilent(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "m2", 1)

	var mu sync.Mutex
	notifyCount := 0
	notifyFn := func(_ store.Monitor, _, _, _, _, _ string) {
		mu.Lock()
		notifyCount++
		mu.Unlock()
	}

	s := New(st, notifyFn, 10, 5, 0)

	c := store.Check{
		MonitorID: m.ID,
		Ok:        1,
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}

	s.record(m, c, true, true)

	mu.Lock()
	got := notifyCount
	mu.Unlock()
	if got != 0 {
		t.Fatalf("expected 0 notify calls, got %d", got)
	}

	if _, err := st.OpenIncidentStartedAt(m.ID); err == nil {
		t.Fatal("expected OpenIncidentStartedAt to return error when no incident exists")
	}
}

func TestR2_RecordUpAfterDownWithNoPrevSilent(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "m2", 1)

	var mu sync.Mutex
	notifyCount := 0
	notifyFn := func(_ store.Monitor, _, _, _, _, _ string) {
		mu.Lock()
		notifyCount++
		mu.Unlock()
	}

	s := New(st, notifyFn, 10, 5, 0)

	c := store.Check{
		MonitorID: m.ID,
		Ok:        1,
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}

	s.record(m, c, false, false)

	mu.Lock()
	got := notifyCount
	mu.Unlock()
	if got != 0 {
		t.Fatalf("expected 0 notify calls, got %d", got)
	}
}

func TestR2_RecordDownAfterUpOpens(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "m2", 1)

	var mu sync.Mutex
	var events []string
	notifyFn := func(_ store.Monitor, event, _, _, _, _ string) {
		mu.Lock()
		events = append(events, event)
		mu.Unlock()
	}

	s := New(st, notifyFn, 10, 5, 0)

	downCheck := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
		Error:     "connection refused",
	}

	s.record(m, downCheck, true, true)

	mu.Lock()
	defer mu.Unlock()
	if len(events) != 1 {
		t.Fatalf("expected 1 notify call, got %d", len(events))
	}
	if events[0] != "down" {
		t.Fatalf("expected event %q, got %q", "down", events[0])
	}

	if _, err := st.OpenIncidentStartedAt(m.ID); err != nil {
		t.Fatalf("expected incident to exist, got error: %v", err)
	}
}
