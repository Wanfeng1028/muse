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

func TestConcurrentRecover_SingleRecoveredNotify(t *testing.T) {
	st := newTestStore(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	defer srv.Close()

	m := store.Monitor{
		Name:           "dedupe-recover",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}
	mid, err := st.CreateMonitor(m)
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	m.ID = mid

	var mu sync.Mutex
	var downCount, recoveredCount int
	notifyFn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		mu.Lock()
		defer mu.Unlock()
		switch event {
		case "down":
			downCount++
		case "recovered":
			recoveredCount++
		}
	}

	sched := New(st, notifyFn, 10, 60, 0)
	ctx := context.Background()

	if _, err := sched.CheckNow(ctx, mid, 0); err != nil {
		t.Fatalf("CheckNow: %v", err)
	}
	mu.Lock()
	if downCount != 1 {
		t.Fatalf("expected downCount=1, got %d", downCount)
	}
	mu.Unlock()

	incs, err := st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents: %v", err)
	}
	openCount := 0
	for _, inc := range incs {
		if !inc.EndedAt.Valid {
			openCount++
		}
	}
	if openCount != 1 {
		t.Fatalf("expected 1 open incident, got %d", openCount)
	}

	m.Target = srv.URL + "/health"
	st.UpdateMonitor(mid, m)

	start := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			<-start
			sched.CheckNow(ctx, mid, 0)
			wg.Done()
		}()
	}
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			<-start
			sched.runOne(ctx, m, false, true)
			wg.Done()
		}()
	}
	close(start)
	wg.Wait()

	mu.Lock()
	if recoveredCount != 1 {
		t.Fatalf("expected recoveredCount=1, got %d", recoveredCount)
	}
	if downCount != 1 {
		t.Fatalf("expected downCount=1, got %d", downCount)
	}
	mu.Unlock()

	incs, err = st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents: %v", err)
	}
	if len(incs) != 1 {
		t.Fatalf("expected 1 incident, got %d", len(incs))
	}
	if !incs[0].EndedAt.Valid {
		t.Fatal("expected EndedAt.Valid=true")
	}
	if !incs[0].DowntimeSec.Valid {
		t.Fatal("expected DowntimeSec.Valid=true")
	}
}

func TestCloseOpenIncident_ReturnsClosedFlag(t *testing.T) {
	st := newTestStore(t)

	m := store.Monitor{
		Name:           "close-flag",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}
	mid, _ := st.CreateMonitor(m)

	t1 := time.Now().Add(-2 * time.Minute).Format(time.RFC3339)
	t2 := time.Now().Add(-time.Minute).Format(time.RFC3339)
	t3 := time.Now().Format(time.RFC3339)

	_, created, err := st.OpenIncident(mid, t1, "boom")
	if err != nil {
		t.Fatalf("OpenIncident: %v", err)
	}
	if !created {
		t.Fatal("expected created=true")
	}

	closed, err := st.CloseOpenIncident(mid, t2, 60)
	if err != nil {
		t.Fatalf("CloseOpenIncident: %v", err)
	}
	if !closed {
		t.Fatal("expected closed=true")
	}

	closed2, err := st.CloseOpenIncident(mid, t3, 60)
	if err != nil {
		t.Fatalf("CloseOpenIncident second: %v", err)
	}
	if closed2 {
		t.Fatal("expected closed2=false")
	}
}
