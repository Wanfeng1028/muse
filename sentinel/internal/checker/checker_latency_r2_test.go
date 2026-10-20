package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_CheckLatencyReflectsServerDelay(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(300 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         ts.URL,
		TimeoutSec:     5,
		ExpectedStatus: http.StatusOK,
	}

	c := Check(m)
	if c.Ok != 1 {
		t.Fatalf("Check() Ok = %d, Error = %q, want Ok = 1", c.Ok, c.Error)
	}
	if c.LatencyMs < 250 {
		t.Fatalf("Check() LatencyMs = %d, want >= 250", c.LatencyMs)
	}
	if c.LatencyMs >= 3000 {
		t.Fatalf("Check() LatencyMs = %d, want < 3000", c.LatencyMs)
	}
}

func TestR2_CheckLatencyFast(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         ts.URL,
		TimeoutSec:     5,
		ExpectedStatus: 200,
	}

	c := Check(m)
	if c.Ok != 1 {
		t.Fatalf("Check() Ok = %d, Error = %q, want Ok = 1", c.Ok, c.Error)
	}
	if c.LatencyMs < 0 {
		t.Fatalf("Check() LatencyMs = %d, want >= 0", c.LatencyMs)
	}
	if c.LatencyMs >= 2000 {
		t.Fatalf("Check() LatencyMs = %d, want < 2000", c.LatencyMs)
	}
}

func TestR2_CheckTCPLatencyOnFailure(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("net.Listen() error = %v", err)
	}
	target := ln.Addr().String()
	if err := ln.Close(); err != nil {
		t.Fatalf("listener Close() error = %v", err)
	}

	m := store.Monitor{
		Kind:       "tcp",
		Target:     target,
		TimeoutSec: 2,
	}

	c := Check(m)
	if c.Ok != 0 {
		t.Fatalf("Check() Ok = %d, Error = %q, want Ok = 0", c.Ok, c.Error)
	}
	if c.LatencyMs < 0 {
		t.Fatalf("Check() LatencyMs = %d, want >= 0", c.LatencyMs)
	}
}
