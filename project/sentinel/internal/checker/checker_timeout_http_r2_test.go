package checker

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_CheckHTTPTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(3 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     1,
		ExpectedStatus: 200,
	}

	start := time.Now()
	c := Check(m)
	elapsed := time.Since(start).Milliseconds()

	if c.Ok != 0 {
		t.Fatalf("expected Ok==0 on timeout, got %d (error=%q)", c.Ok, c.Error)
	}
	if c.LatencyMs < 900 {
		t.Fatalf("expected LatencyMs >= 900, got %d", c.LatencyMs)
	}
	if c.LatencyMs >= 4500 {
		t.Fatalf("expected LatencyMs < 4500, got %d", c.LatencyMs)
	}
	if elapsed >= 4500 {
		t.Fatalf("expected elapsed < 4500ms, got %dms", elapsed)
	}
	if c.Error == "" {
		t.Fatal("expected non-empty Error on timeout")
	}
}

func TestR2_CheckHTTPNoTimeoutFast(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		TimeoutSec:     1,
		ExpectedStatus: 200,
	}

	c := Check(m)

	if c.Ok != 1 {
		t.Fatalf("expected Ok==1 on fast response, got %d (error=%q)", c.Ok, c.Error)
	}
	if c.LatencyMs >= 2000 {
		t.Fatalf("expected LatencyMs < 2000, got %d", c.LatencyMs)
	}
}
