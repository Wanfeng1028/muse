package scheduler

import (
	"sync"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_NotifyDownDedup(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "dd1", 1)

	var mu sync.Mutex
	events := make([]string, 0, 4)
	notifyFn := func(_ store.Monitor, event, _, _, _, _ string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, event)
	}
	countEvent := func(want string) int {
		mu.Lock()
		defer mu.Unlock()
		n := 0
		for _, got := range events {
			if got == want {
				n++
			}
		}
		return n
	}

	s := New(st, notifyFn, 10, 5, 0)
	down := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom",
		CheckedAt: time.Now().UTC().Add(-2 * time.Second).Format(time.RFC3339),
	}

	s.record(m, down, true, true)
	s.record(m, down, false, true)
	s.record(m, down, false, true)

	if got := countEvent("down"); got != 1 {
		t.Fatalf("down notifications = %d, want 1", got)
	}
}

func TestR2_NotifyRecoveredOnce(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "rec1", 1)

	var mu sync.Mutex
	events := make([]string, 0, 4)
	notifyFn := func(_ store.Monitor, event, _, _, _, _ string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, event)
	}
	countEvent := func(want string) int {
		mu.Lock()
		defer mu.Unlock()
		n := 0
		for _, got := range events {
			if got == want {
				n++
			}
		}
		return n
	}

	s := New(st, notifyFn, 10, 5, 0)
	down := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom",
		CheckedAt: time.Now().UTC().Add(-2 * time.Second).Format(time.RFC3339),
	}
	upCheck := store.Check{
		MonitorID: m.ID,
		Ok:        1,
		CheckedAt: time.Now().UTC().Add(-1 * time.Second).Format(time.RFC3339),
	}
	upCheck2 := store.Check{
		MonitorID: m.ID,
		Ok:        1,
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}

	s.record(m, down, true, true)
	s.record(m, upCheck, false, true)
	s.record(m, upCheck2, true, true)

	if got := countEvent("recovered"); got != 1 {
		t.Fatalf("recovered notifications = %d, want 1", got)
	}
}

func TestR2_NotifySecondDownAfterRecover(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "down2", 1)

	var mu sync.Mutex
	events := make([]string, 0, 4)
	notifyFn := func(_ store.Monitor, event, _, _, _, _ string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, event)
	}
	countEvent := func(want string) int {
		mu.Lock()
		defer mu.Unlock()
		n := 0
		for _, got := range events {
			if got == want {
				n++
			}
		}
		return n
	}

	s := New(st, notifyFn, 10, 5, 0)
	down1 := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom",
		CheckedAt: time.Now().UTC().Add(-2 * time.Second).Format(time.RFC3339),
	}
	upCheck := store.Check{
		MonitorID: m.ID,
		Ok:        1,
		CheckedAt: time.Now().UTC().Add(-1 * time.Second).Format(time.RFC3339),
	}
	down2 := store.Check{
		MonitorID: m.ID,
		Ok:        0,
		Error:     "boom2",
		CheckedAt: time.Now().UTC().Format(time.RFC3339),
	}

	s.record(m, down1, true, true)
	s.record(m, upCheck, false, true)
	s.record(m, down2, true, true)

	if got := countEvent("down"); got != 2 {
		t.Fatalf("down notifications = %d, want 2", got)
	}
}
