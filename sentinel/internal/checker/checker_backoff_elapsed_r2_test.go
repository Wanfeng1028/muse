package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_CheckWithRetryBackoffElapsed(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	addr := ln.Addr().String()
	if err := ln.Close(); err != nil {
		t.Fatalf("close listener: %v", err)
	}

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}

	start := time.Now()
	c, retries := CheckWithRetry(m, 2)
	elapsed := time.Since(start)

	if retries != 2 {
		t.Fatalf("retries = %d, want 2", retries)
	}
	if elapsed < 1400*time.Millisecond {
		t.Fatalf("elapsed = %v, want >= 1400ms", elapsed)
	}
	if elapsed >= 8*time.Second {
		t.Fatalf("elapsed = %v, want < 8s", elapsed)
	}
	if c.Ok != 0 {
		t.Fatalf("c.Ok = %d, want 0", c.Ok)
	}
}

func TestR2_CheckWithRetrySingleAttempt(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	addr := ln.Addr().String()
	if err := ln.Close(); err != nil {
		t.Fatalf("close listener: %v", err)
	}

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}

	start := time.Now()
	c, retries := CheckWithRetry(m, 0)
	elapsed := time.Since(start)

	if retries != 0 {
		t.Fatalf("retries = %d, want 0", retries)
	}
	if elapsed >= 3*time.Second {
		t.Fatalf("elapsed = %v, want < 3s", elapsed)
	}
	if c.Ok != 0 {
		t.Fatalf("c.Ok = %d, want 0", c.Ok)
	}
}

func TestR2_CheckWithRetrySuccessNoRetry(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
	}

	c, retries := CheckWithRetry(m, 3)

	if retries != 0 {
		t.Fatalf("retries = %d, want 0", retries)
	}
	if c.Ok != 1 {
		t.Fatalf("c.Ok = %d, want 1 (error=%q)", c.Ok, c.Error)
	}
}
