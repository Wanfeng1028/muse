package scheduler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

func newCtxTestStore(t *testing.T) *store.Store {
	t.Helper()
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	t.Cleanup(func() { _ = d.Close() })
	st := store.New(d)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant failed: %v", err)
	}
	return st
}

func TestSchedulerCheckNow_CtxCancel(t *testing.T) {
	release := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-time.After(3 * time.Second):
		case <-release:
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	defer close(release)

	st := newCtxTestStore(t)

	now := time.Now().UTC().Format(time.RFC3339)
	m := store.Monitor{
		Name:           "ctx-cancel",
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	id, err := st.CreateMonitor(m)
	if err != nil {
		t.Fatalf("CreateMonitor 失败: %v", err)
	}

	s := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {}, 1, 60, 0)

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(200 * time.Millisecond)
		cancel()
	}()

	done := make(chan struct{})
	go func() {
		defer close(done)
		_, _ = s.CheckNow(ctx, id, 0)
	}()

	select {
	case <-done:
	case <-time.After(2500 * time.Millisecond):
		t.Fatalf("CheckNow 未在 2.5s 内返回")
	}
}
