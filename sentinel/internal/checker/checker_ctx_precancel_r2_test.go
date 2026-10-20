package checker

import (
	"context"
	"net"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_CheckWithRetryCtxPreCanceled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	m := store.Monitor{
		Kind:       "http",
		Target:     "http://127.0.0.1:1/",
		TimeoutSec: 2,
	}

	start := time.Now()
	c, retries := CheckWithRetryCtx(ctx, m, 3)
	elapsed := time.Since(start)

	if c.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d", c.Ok)
	}
	if !strings.Contains(c.Error, "context") {
		t.Fatalf("expected error containing context, got %q", c.Error)
	}
	if retries != 0 {
		t.Fatalf("expected retries=0, got %d", retries)
	}
	if elapsed >= 2*time.Second {
		t.Fatalf("expected elapsed < 2s, got %v", elapsed)
	}
}

func TestR2_CheckWithRetryCtxCancelDuringBackoff(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to allocate listener: %v", err)
	}
	addr := ln.Addr().String()
	if cerr := ln.Close(); cerr != nil {
		t.Fatalf("failed to close listener: %v", cerr)
	}

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	timer := time.AfterFunc(300*time.Millisecond, cancel)
	defer timer.Stop()

	start := time.Now()
	c, retries := CheckWithRetryCtx(ctx, m, 6)
	elapsed := time.Since(start)

	if c.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d", c.Ok)
	}
	if retries >= 6 {
		t.Fatalf("expected retries < 6, got %d", retries)
	}
	if elapsed >= 6*time.Second {
		t.Fatalf("expected elapsed < 6s, got %v", elapsed)
	}
}
