package ratelimit

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

func TestMiddleware_KeyIsolationByUser(t *testing.T) {
	var now time.Time
	now = time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	lim := New(cfg)
	lim.SetNowFunc(func() time.Time { return now })

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	userOf := func(r *http.Request) string { return r.Header.Get("X-User") }
	h := lim.Middleware(userOf, next)

	do := func(user string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.Header.Set(headerXForwardedFor, "9.9.9.9")
		req.Header.Set("X-User", user)
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec
	}

	if rec := do("a"); rec.Code != http.StatusOK {
		t.Fatalf("user a first: code = %d, want 200", rec.Code)
	}
	if rec := do("a"); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("user a second: code = %d, want 429", rec.Code)
	}
	if rec := do("b"); rec.Code != http.StatusOK {
		t.Fatalf("user b first: code = %d, want 200", rec.Code)
	}
}

func TestMiddleware_UnknownMethodIsWrite(t *testing.T) {
	var now time.Time
	now = time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	cfg := Config{Enabled: true, RPS: 10, Burst: 10, WriteRPS: 10, WriteBurst: 1}
	lim := New(cfg)
	lim.SetNowFunc(func() time.Time { return now })

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := lim.Middleware(nil, next)

	do := func() *httptest.ResponseRecorder {
		req := httptest.NewRequest("BREW", "/", nil)
		req.RemoteAddr = "6.6.6.6:2222"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec
	}

	if rec := do(); rec.Code != http.StatusOK {
		t.Fatalf("BREW first: code = %d, want 200", rec.Code)
	}
	if rec := do(); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("BREW second: code = %d, want 429", rec.Code)
	}
}

func TestClientIP_Priority(t *testing.T) {
	var now time.Time
	now = time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	lim := New(cfg)
	lim.SetNowFunc(func() time.Time { return now })

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := lim.Middleware(nil, next)

	req1 := httptest.NewRequest(http.MethodGet, "/", nil)
	req1.Header.Set(headerXForwardedFor, "10.0.0.1, 10.0.0.2")
	rec1 := httptest.NewRecorder()
	h.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("req1: code = %d, want 200", rec1.Code)
	}

	req2 := httptest.NewRequest(http.MethodGet, "/", nil)
	req2.Header.Set(headerXForwardedFor, "10.0.0.1")
	rec2 := httptest.NewRecorder()
	h.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("req2: code = %d, want 429", rec2.Code)
	}

	req3 := httptest.NewRequest(http.MethodGet, "/", nil)
	req3.Header.Set(headerXRealIP, "10.0.0.7")
	rec3 := httptest.NewRecorder()
	h.ServeHTTP(rec3, req3)
	if rec3.Code != http.StatusOK {
		t.Fatalf("req3: code = %d, want 200", rec3.Code)
	}
}

func TestSetNowFunc_NilIgnored(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	lim := New(cfg)
	lim.SetNowFunc(nil)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := lim.Middleware(nil, next)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.RemoteAddr = "11.11.11.11:5555"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("code = %d, want 200", rec.Code)
	}
}

func TestConcurrentAllow_NoRace(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1000, Burst: 1000, WriteRPS: 1000, WriteBurst: 1000}
	lim := New(cfg)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := lim.Middleware(nil, next)

	const goroutines = 20
	const perGoroutine = 50

	var wg sync.WaitGroup
	var mu sync.Mutex
	failures := 0

	wg.Add(goroutines)
	for g := 0; g < goroutines; g++ {
		go func() {
			defer wg.Done()
			for i := 0; i < perGoroutine; i++ {
				req := httptest.NewRequest(http.MethodGet, "/", nil)
				req.RemoteAddr = "12.12.12.12:6666"
				rec := httptest.NewRecorder()
				h.ServeHTTP(rec, req)
				if rec.Code != http.StatusOK {
					mu.Lock()
					failures++
					mu.Unlock()
				}
			}
		}()
	}
	wg.Wait()

	if failures != 0 {
		t.Fatalf("got %d non-200 responses, want 0", failures)
	}
}

var _ = fmt.Sprintf
