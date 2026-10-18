package scheduler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"sentinel/internal/store"
)

func failingMonitor(name string) store.Monitor {
	return store.Monitor{
		Name:           name,
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}
}

func TestCheckNow_SequentialDown_SingleOpen(t *testing.T) {
	st := newTestStore(t)

	var mu sync.Mutex
	downCount := 0
	notifyFn := func(m store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		if event == "down" {
			downCount++
		}
	}

	sched := New(st, notifyFn, 4, 60, 3)

	mid, err := st.CreateMonitor(failingMonitor("seq-down"))
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	for i := 0; i < 5; i++ {
		sched.CheckNow(mid, 0)
	}

	incidents, err := st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents failed: %v", err)
	}
	openCount := 0
	for _, inc := range incidents {
		if !inc.EndedAt.Valid {
			openCount++
		}
	}
	if openCount != 1 {
		t.Fatalf("open incidents count: got %d want 1", openCount)
	}

	mu.Lock()
	got := downCount
	mu.Unlock()
	if got != 1 {
		t.Fatalf("down notifications: got %d want 1", got)
	}
}

func TestDownRecoverDown_ReopensNewIncident(t *testing.T) {
	st := newTestStore(t)

	var mu sync.Mutex
	downCount := 0
	recoveredCount := 0
	notifyFn := func(m store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		switch event {
		case "down":
			downCount++
		case "recovered":
			recoveredCount++
		}
	}

	sched := New(st, notifyFn, 4, 60, 3)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	mid, err := st.CreateMonitor(failingMonitor("down-recover-down"))
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	sched.CheckNow(mid, 0)

	okMon := store.Monitor{
		Name:           "down-recover-down",
		Kind:           "http",
		Target:         srv.URL + "/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}
	if err := st.UpdateMonitor(mid, okMon); err != nil {
		t.Fatalf("UpdateMonitor to success failed: %v", err)
	}
	sched.CheckNow(mid, 0)

	if err := st.UpdateMonitor(mid, failingMonitor("down-recover-down")); err != nil {
		t.Fatalf("UpdateMonitor to failure failed: %v", err)
	}
	sched.CheckNow(mid, 0)

	incidents, err := st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents failed: %v", err)
	}
	if len(incidents) != 2 {
		t.Fatalf("incidents count: got %d want 2", len(incidents))
	}

	var openCount int
	var closedCount int
	var openID int64
	for _, inc := range incidents {
		if inc.EndedAt.Valid {
			closedCount++
		} else {
			openCount++
			openID = inc.ID
		}
	}
	if openCount != 1 {
		t.Fatalf("open incidents count: got %d want 1", openCount)
	}
	if closedCount != 1 {
		t.Fatalf("closed incidents count: got %d want 1", closedCount)
	}
	if openID == 0 {
		t.Fatalf("open incident id is zero")
	}
	var maxClosedID int64
	for _, inc := range incidents {
		if inc.EndedAt.Valid && inc.ID > maxClosedID {
			maxClosedID = inc.ID
		}
	}
	if openID <= maxClosedID {
		t.Fatalf("open incident id %d not newer than closed id %d", openID, maxClosedID)
	}

	mu.Lock()
	gotDown := downCount
	gotRecovered := recoveredCount
	mu.Unlock()
	if gotDown != 2 {
		t.Fatalf("down notifications: got %d want 2", gotDown)
	}
	if gotRecovered != 1 {
		t.Fatalf("recovered notifications: got %d want 1", gotRecovered)
	}
}

func TestManualTickInterleaved_NoDuplicate(t *testing.T) {
	st := newTestStore(t)

	notifyFn := func(m store.Monitor, event, name, target, at, errMsg string) {}

	sched := New(st, notifyFn, 16, 60, 3)

	mid, err := st.CreateMonitor(failingMonitor("interleaved"))
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	m, err := st.GetMonitor(mid)
	if err != nil {
		t.Fatalf("GetMonitor failed: %v", err)
	}

	const manualN = 10
	const tickN = 10

	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(manualN + tickN)

	ctx := context.Background()

	for i := 0; i < manualN; i++ {
		go func() {
			defer wg.Done()
			<-start
			sched.CheckNow(mid, 0)
		}()
	}
	for i := 0; i < tickN; i++ {
		go func() {
			defer wg.Done()
			<-start
			sched.runOne(ctx, m, true, true)
		}()
	}

	close(start)
	wg.Wait()

	deadline := time.Now().Add(5 * time.Second)
	for {
		incidents, err := st.ListIncidents(mid, 100)
		if err != nil {
			t.Fatalf("ListIncidents failed: %v", err)
		}
		openCount := 0
		for _, inc := range incidents {
			if !inc.EndedAt.Valid {
				openCount++
			}
		}
		if openCount == 1 {
			break
		}
		if openCount > 1 {
			t.Fatalf("open incidents count: got %d want 1", openCount)
		}
		if time.Now().After(deadline) {
			t.Fatalf("open incidents count: got %d want 1 (timed out waiting)", openCount)
		}
		time.Sleep(10 * time.Millisecond)
	}
}
