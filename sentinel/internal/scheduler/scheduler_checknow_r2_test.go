package scheduler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"sentinel/internal/store"
)

func TestR2_CheckNowDownOpensIncident(t *testing.T) {
	st := newTestStore(t)

	var mu sync.Mutex
	events := make([]string, 0, 2)
	notifyFn := func(m store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, event)
	}

	s := New(st, notifyFn, 10, 5, 0)
	m := newMonitor(t, st, "cn1", 1)

	c, err := s.CheckNow(context.Background(), m.ID, 0)
	if err != nil {
		t.Fatalf("CheckNow returned error: %v", err)
	}
	if c.Ok != 0 {
		t.Fatalf("expected failed check, got Ok=%d", c.Ok)
	}
	if c.MonitorID != m.ID {
		t.Fatalf("expected MonitorID %d, got %d", m.ID, c.MonitorID)
	}

	last, err := st.LastCheck(m.ID)
	if err != nil {
		t.Fatalf("LastCheck returned error: %v", err)
	}
	if last == nil {
		t.Fatal("expected stored last check, got nil")
	}
	if last.Ok != 0 {
		t.Fatalf("expected stored failed check, got Ok=%d", last.Ok)
	}

	mu.Lock()
	gotEvents := append([]string(nil), events...)
	mu.Unlock()

	if len(gotEvents) != 1 || gotEvents[0] != "down" {
		t.Fatalf("expected exactly one down event, got %v", gotEvents)
	}
}

func TestR2_CheckNowRecoveredAfterDown(t *testing.T) {
	st := newTestStore(t)

	var mu sync.Mutex
	events := make([]string, 0, 2)
	notifyFn := func(m store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, event)
	}

	s := New(st, notifyFn, 10, 5, 0)
	m := newMonitor(t, st, "cn1", 1)

	c1, err := s.CheckNow(context.Background(), m.ID, 0)
	if err != nil {
		t.Fatalf("initial CheckNow returned error: %v", err)
	}
	if c1.Ok != 0 {
		t.Fatalf("expected initial failed check, got Ok=%d", c1.Ok)
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	updated, err := st.GetMonitor(m.ID)
	if err != nil {
		t.Fatalf("GetMonitor returned error: %v", err)
	}
	updated.Target = srv.URL
	if err := st.UpdateMonitor(m.ID, updated); err != nil {
		t.Fatalf("UpdateMonitor returned error: %v", err)
	}

	c2, err := s.CheckNow(context.Background(), m.ID, 0)
	if err != nil {
		t.Fatalf("recovery CheckNow returned error: %v", err)
	}
	if c2.Ok != 1 {
		t.Fatalf("expected recovered check, got Ok=%d", c2.Ok)
	}

	mu.Lock()
	gotEvents := append([]string(nil), events...)
	mu.Unlock()

	if len(gotEvents) != 2 || gotEvents[0] != "down" || gotEvents[1] != "recovered" {
		t.Fatalf("expected down then recovered events, got %v", gotEvents)
	}
}
