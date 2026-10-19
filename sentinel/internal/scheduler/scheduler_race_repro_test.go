package scheduler

import (
	"context"
	"sync"
	"testing"

	"sentinel/internal/store"
)

func TestManualAndTickConcurrent_DuplicateOpenIncident(t *testing.T) {
	st := newTestStore(t)

	m := store.Monitor{
		Name:           "race-down",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}
	id, err := st.CreateMonitor(m)
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}
	m.ID = id

	var mu sync.Mutex
	downCalls := 0
	notifyFn := func(mm store.Monitor, event, name, target, at, errMsg string) {
		if event == "down" {
			mu.Lock()
			downCalls++
			mu.Unlock()
		}
	}

	sched := New(st, notifyFn, 10, 1, 0)

	start := make(chan struct{})
	var wg sync.WaitGroup

	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			_, _ = sched.CheckNow(context.Background(), m.ID, 0)
		}()
	}
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			sched.runOne(context.Background(), m, false, false)
		}()
	}

	close(start)
	wg.Wait()

	incidents, err := st.ListIncidents(m.ID, 100)
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
		t.Fatalf("open incident 数量 = %d，期望 1：并发竞态导致重复 open", openCount)
	}

	mu.Lock()
	got := downCalls
	mu.Unlock()
	if got != 1 {
		t.Fatalf("down 通知次数 = %d，期望 1：重复 open 导致重复告警", got)
	}
}
