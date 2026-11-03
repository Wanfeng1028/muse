package scheduler

import (
	"context"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_TickSkipsDisabled(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(store.Monitor{
		Name:           "tickm",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     2,
		IntervalSec:    60,
		Enabled:        0,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	s := New(st, nil, 10, 60, 0)
	s.tick(context.Background())

	time.Sleep(1500 * time.Millisecond)

	last, err := st.LastCheck(mid)
	if err != nil {
		t.Fatalf("LastCheck: %v", err)
	}
	if last != nil {
		t.Fatalf("disabled monitor should not be scheduled, got check: %+v", last)
	}
}

func TestR2_TickSchedulesUnchecked(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(store.Monitor{
		Name:           "tickm2",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     2,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	s := New(st, nil, 10, 60, 0)
	s.tick(context.Background())

	deadline := time.Now().Add(5 * time.Second)
	var last *store.Check
	for time.Now().Before(deadline) {
		l, err := st.LastCheck(mid)
		if err != nil {
			t.Fatalf("LastCheck: %v", err)
		}
		if l != nil {
			last = l
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if last == nil {
		t.Fatal("expected check to be recorded within 5 seconds")
	}
}
