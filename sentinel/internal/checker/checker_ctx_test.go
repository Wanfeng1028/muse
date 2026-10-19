package checker

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestCheckWithRetryCtx_CancelMidFlight(t *testing.T) {
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

	m := store.Monitor{
		ID:          1,
		Name:        "mid-flight",
		Kind:        "http",
		Target:      srv.URL,
		Method:      http.MethodGet,
		TimeoutSec:  10,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	}

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()

	start := time.Now()
	c, _ := CheckWithRetryCtx(ctx, m, 0)
	elapsed := time.Since(start)

	if elapsed >= 2500*time.Millisecond {
		t.Fatalf("CheckWithRetryCtx 未在 2.5s 内返回，耗时 %v", elapsed)
	}
	if elapsed < 100*time.Millisecond {
		t.Fatalf("CheckWithRetryCtx 返回过快（<100ms），可能未真正发起请求，耗时 %v", elapsed)
	}
	if c.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, err=%q", c.Ok, c.Error)
	}
}

func TestCheckWithRetryCtx_BackoffInterrupted(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	// 立即关闭，后续请求触发 transport 错误（无状态码），进入重试退避。
	srv.Close()

	m := store.Monitor{
		ID:          2,
		Name:        "backoff",
		Kind:        "http",
		Target:      srv.URL,
		Method:      http.MethodGet,
		TimeoutSec:  10,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	}

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(200 * time.Millisecond)
		cancel()
	}()

	start := time.Now()
	c, retries := CheckWithRetryCtx(ctx, m, 5)
	elapsed := time.Since(start)

	if elapsed >= 5*time.Second {
		t.Fatalf("退避未被 ctx 中断，耗时 %v", elapsed)
	}
	if retries >= 5 {
		t.Fatalf("期望重试次数 <5（被中断），实际 retries=%d", retries)
	}
	if c.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, err=%q", c.Ok, c.Error)
	}
}

func TestCheckWithRetryCtx_SuccessUnaffected(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		ID:             3,
		Name:           "success",
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}

	c, retries := CheckWithRetryCtx(context.Background(), m, 3)
	if c.Ok != 1 {
		t.Fatalf("期望 Ok=1，实际 Ok=%d, err=%q", c.Ok, c.Error)
	}
	if retries != 0 {
		t.Fatalf("期望 retries=0，实际 retries=%d", retries)
	}
}
