package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

func TestR2_CheckTCPRefusedFast(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen failed: %v", err)
	}
	addr := ln.Addr().String()
	if err := ln.Close(); err != nil {
		t.Fatalf("close listener failed: %v", err)
	}

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}

	c := Check(m)

	if c.Ok != 0 {
		t.Fatalf("expected Ok=0 for refused connection, got %d (error=%q)", c.Ok, c.Error)
	}
	if c.Error == "" {
		t.Fatalf("expected non-empty Error for refused connection")
	}
	if c.LatencyMs >= 3000 {
		t.Fatalf("expected refused connection to fail fast, latency=%dms", c.LatencyMs)
	}
}

func TestR2_CheckTCPKindCaseInsensitive(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen failed: %v", err)
	}
	defer ln.Close()

	accepted := make(chan struct{})
	go func() {
		conn, aerr := ln.Accept()
		if aerr == nil {
			_ = conn.Close()
		}
		close(accepted)
	}()

	m := store.Monitor{
		Kind:       "TCP",
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}

	c := Check(m)

	if c.Ok != 1 {
		t.Fatalf("expected Ok=1 for reachable TCP target with kind TCP, got %d (error=%q)", c.Ok, c.Error)
	}

	<-accepted
}

func TestR2_CheckTimeoutDefault(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     0,
		ExpectedStatus: 200,
	}

	c := Check(m)

	if c.Ok != 1 {
		t.Fatalf("expected Ok=1 with default timeout, got %d (error=%q)", c.Ok, c.Error)
	}
	if c.LatencyMs >= 2000 {
		t.Fatalf("expected fast response under default timeout, latency=%dms", c.LatencyMs)
	}
}
