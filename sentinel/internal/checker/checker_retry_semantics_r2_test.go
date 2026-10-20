package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

func TestR2_CheckWithRetryNoRetryOnStatusMismatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
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
		t.Fatalf("expected retries == 0 when status code present, got %d", retries)
	}
	if c.Ok != 0 {
		t.Fatalf("expected Ok == 0, got %d", c.Ok)
	}
	if !c.StatusCode.Valid {
		t.Fatalf("expected StatusCode.Valid to be true")
	}
	if c.StatusCode.Int64 != 500 {
		t.Fatalf("expected StatusCode == 500, got %d", c.StatusCode.Int64)
	}
}

func TestR2_CheckWithRetryNegativeMaxRetries(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to allocate listener: %v", err)
	}
	addr := ln.Addr().String()
	_ = ln.Close()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}

	c, retries := CheckWithRetry(m, -5)

	if retries != 0 {
		t.Fatalf("expected retries == 0 with negative maxRetries, got %d", retries)
	}
	if c.Ok != 0 {
		t.Fatalf("expected Ok == 0 for unreachable TCP target, got %d", c.Ok)
	}
}

func TestR2_CheckWithRetryTCPNoRetryOnSuccess(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer ln.Close()

	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			_ = conn.Close()
		}
	}()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}

	c, retries := CheckWithRetry(m, 3)

	if retries != 0 {
		t.Fatalf("expected retries == 0 on TCP success, got %d", retries)
	}
	if c.Ok != 1 {
		t.Fatalf("expected Ok == 1 on TCP success, got %d", c.Ok)
	}
}
