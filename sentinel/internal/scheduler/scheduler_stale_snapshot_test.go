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

func makeCheck(mid int64, at string, ok int) store.Check {
	return store.Check{MonitorID: mid, CheckedAt: at, Ok: ok}
}

func openIncidentCount(t *testing.T, st *store.Store, mid int64) int {
	t.Helper()
	incs, err := st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents: %v", err)
	}
	n := 0
	for _, in := range incs {
		if !in.EndedAt.Valid {
			n++
		}
	}
	return n
}

func TestTickStaleSnapshot_NoDuplicateRecovered(t *testing.T) {
	var up atomic.Bool
	up.Store(true)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if up.Load() {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)

	st := newTestStore(t)
	m := failingMonitor("stale-dup")
	m.Target = srv.URL
	mid, err := st.CreateMonitor(m)
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	oldAt := time.Now().Add(-120 * time.Second).UTC().Format(time.RFC3339)
	if _, _, err := st.OpenIncident(mid, oldAt, "boom"); err != nil {
		t.Fatalf("OpenIncident: %v", err)
	}
	if _, err := st.InsertCheck(makeCheck(mid, oldAt, 0)); err != nil {
		t.Fatalf("InsertCheck: %v", err)
	}

	var (
		cntMu       sync.Mutex
		down, recov int
	)
	notifyFn := func(_ store.Monitor, event, _, _, _, _ string) {
		cntMu.Lock()
		switch event {
		case "down":
			down++
		case "recovered":
			recov++
		}
		cntMu.Unlock()
	}

	sched := New(st, notifyFn, 1, 3600, 0)

	sched.sem <- struct{}{}
	go sched.tick(context.Background())

	waitFn := func(want bool) {
		t.Helper()
		deadline := time.Now().Add(5 * time.Second)
		for time.Now().Before(deadline) {
			sched.mu.Lock()
			got := sched.inflight[mid]
			sched.mu.Unlock()
			if got == want {
				return
			}
			time.Sleep(2 * time.Millisecond)
		}
		t.Fatalf("等待 inflight[%d]==%v 超时", mid, want)
	}
	waitFn(true)

	up.Store(true)
	if _, err := sched.CheckNow(context.Background(), mid, 0); err != nil {
		t.Fatalf("CheckNow: %v", err)
	}

	<-sched.sem
	waitFn(false)

	cntMu.Lock()
	gotDown, gotRecov := down, recov
	cntMu.Unlock()

	if gotRecov != 1 {
		t.Fatalf("recov = %d, want 1", gotRecov)
	}
	if gotDown != 0 {
		t.Fatalf("down = %d, want 0", gotDown)
	}
	if n := openIncidentCount(t, st, mid); n != 0 {
		t.Fatalf("openIncidentCount = %d, want 0", n)
	}
}

func TestTickStaleSnapshot_NoMissedOpen(t *testing.T) {
	var up atomic.Bool
	up.Store(true)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if up.Load() {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)

	st := newTestStore(t)
	m := failingMonitor("stale-miss")
	m.Target = srv.URL
	mid, err := st.CreateMonitor(m)
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	oldAt := time.Now().Add(-120 * time.Second).UTC().Format(time.RFC3339)
	if _, err := st.InsertCheck(makeCheck(mid, oldAt, 0)); err != nil {
		t.Fatalf("InsertCheck: %v", err)
	}

	var (
		cntMu       sync.Mutex
		down, recov int
	)
	notifyFn := func(_ store.Monitor, event, _, _, _, _ string) {
		cntMu.Lock()
		switch event {
		case "down":
			down++
		case "recovered":
			recov++
		}
		cntMu.Unlock()
	}

	sched := New(st, notifyFn, 1, 3600, 0)

	sched.sem <- struct{}{}
	go sched.tick(context.Background())

	waitFn := func(want bool) {
		t.Helper()
		deadline := time.Now().Add(5 * time.Second)
		for time.Now().Before(deadline) {
			sched.mu.Lock()
			got := sched.inflight[mid]
			sched.mu.Unlock()
			if got == want {
				return
			}
			time.Sleep(2 * time.Millisecond)
		}
		t.Fatalf("等待 inflight[%d]==%v 超时", mid, want)
	}
	waitFn(true)

	if _, err := st.InsertCheck(makeCheck(mid, time.Now().UTC().Format(time.RFC3339), 1)); err != nil {
		t.Fatalf("InsertCheck: %v", err)
	}

	up.Store(false)
	<-sched.sem
	waitFn(false)

	cntMu.Lock()
	gotDown, gotRecov := down, recov
	cntMu.Unlock()

	if gotDown != 1 {
		t.Fatalf("down = %d, want 1", gotDown)
	}
	if gotRecov != 0 {
		t.Fatalf("recov = %d, want 0", gotRecov)
	}
	if n := openIncidentCount(t, st, mid); n != 1 {
		t.Fatalf("openIncidentCount = %d, want 1", n)
	}
}
