package scheduler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_SchedulerConcurrencyCap(t *testing.T) {
	var inFlight atomic.Int32
	var maxInFlight atomic.Int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		current := inFlight.Add(1)
		for {
			old := maxInFlight.Load()
			if current <= old || maxInFlight.CompareAndSwap(old, current) {
				break
			}
		}
		time.Sleep(200 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
		inFlight.Add(-1)
	}))
	defer server.Close()

	st := newTestStore(t)

	monitors := make([]store.Monitor, 0, 5)
	names := []string{"cap-1", "cap-2", "cap-3", "cap-4", "cap-5"}
	for _, name := range names {
		m := newMonitor(t, st, name, 1)
		m.Kind = "http"
		m.Method = http.MethodGet
		m.Target = server.URL
		m.ExpectedStatus = http.StatusOK
		m.TimeoutSec = 5
		m.IntervalSec = 60
		m.Enabled = 1
		m.TenantID = 1
		monitors = append(monitors, m)
	}

	s := New(st, nil, 2, 60, 0)

	var wg sync.WaitGroup
	for _, m := range monitors {
		m := m
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.runOne(context.Background(), m, true, true)
		}()
	}

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for scheduler checks to finish")
	}

	if got := maxInFlight.Load(); got > 2 {
		t.Fatalf("max in-flight = %d, want <= 2", got)
	}

	for _, m := range monitors {
		last, err := st.LastCheck(m.ID)
		if err != nil {
			t.Fatalf("LastCheck for monitor %d returned error: %v", m.ID, err)
		}
		if last == nil {
			t.Fatalf("LastCheck for monitor %d returned nil", m.ID)
		}
		if last.Ok != 1 {
			t.Fatalf("LastCheck for monitor %d has Ok = %d, want 1", m.ID, last.Ok)
		}
	}
}

func TestR2_SchedulerConcurrencyOneIsSerial(t *testing.T) {
	var inFlight atomic.Int32
	var maxInFlight atomic.Int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		current := inFlight.Add(1)
		for {
			old := maxInFlight.Load()
			if current <= old || maxInFlight.CompareAndSwap(old, current) {
				break
			}
		}
		time.Sleep(200 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
		inFlight.Add(-1)
	}))
	defer server.Close()

	st := newTestStore(t)

	monitors := make([]store.Monitor, 0, 5)
	names := []string{"serial-1", "serial-2", "serial-3", "serial-4", "serial-5"}
	for _, name := range names {
		m := newMonitor(t, st, name, 1)
		m.Kind = "http"
		m.Method = http.MethodGet
		m.Target = server.URL
		m.ExpectedStatus = http.StatusOK
		m.TimeoutSec = 5
		m.IntervalSec = 60
		m.Enabled = 1
		m.TenantID = 1
		monitors = append(monitors, m)
	}

	s := New(st, nil, 1, 60, 0)

	var wg sync.WaitGroup
	for _, m := range monitors {
		m := m
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.runOne(context.Background(), m, true, true)
		}()
	}

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for scheduler checks to finish")
	}

	if got := maxInFlight.Load(); got != 1 {
		t.Fatalf("max in-flight = %d, want 1", got)
	}

	for _, m := range monitors {
		last, err := st.LastCheck(m.ID)
		if err != nil {
			t.Fatalf("LastCheck for monitor %d returned error: %v", m.ID, err)
		}
		if last == nil {
			t.Fatalf("LastCheck for monitor %d returned nil", m.ID)
		}
		if last.Ok != 1 {
			t.Fatalf("LastCheck for monitor %d has Ok = %d, want 1", m.ID, last.Ok)
		}
	}
}
