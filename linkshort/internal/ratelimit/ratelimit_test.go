package ratelimit

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
)

func okHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}
}

func doReq(h http.Handler, req *http.Request) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestAllowsWithinBurst(t *testing.T) {
	l := New(10, 5, true)
	h := l.Middleware(okHandler())

	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.RemoteAddr = "10.0.0.1:1234"
		rec := doReq(h, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("request %d status = %d, want 200", i+1, rec.Code)
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.RemoteAddr = "10.0.0.1:1234"
	rec := doReq(h, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("6th request status = %d, want 429", rec.Code)
	}
}

func TestRetryAfterHeader(t *testing.T) {
	l := New(1, 1, true)
	h := l.Middleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.RemoteAddr = "10.0.0.2:1234"
	if rec := doReq(h, req); rec.Code != http.StatusOK {
		t.Fatalf("first request status = %d, want 200", rec.Code)
	}

	req = httptest.NewRequest(http.MethodGet, "/x", nil)
	req.RemoteAddr = "10.0.0.2:1234"
	rec := doReq(h, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("second request status = %d, want 429", rec.Code)
	}
	if rec.Header().Get("Retry-After") == "" {
		t.Fatalf("429 response missing Retry-After header")
	}
	if !strings.Contains(rec.Body.String(), "rate limit exceeded") {
		t.Fatalf("429 body = %q, want to contain %q", rec.Body.String(), "rate limit exceeded")
	}
}

func TestExemptPaths(t *testing.T) {
	l := New(1, 1, true)
	r := chi.NewRouter()
	r.Use(l.Middleware)
	r.Get("/metrics", okHandler())
	r.Get("/api/health", okHandler())
	r.Get("/api/readyz", okHandler())
	r.Get("/limited", okHandler())

	// Drain the bucket on a limited path.
	req := httptest.NewRequest(http.MethodGet, "/limited", nil)
	req.RemoteAddr = "10.0.0.3:1234"
	if rec := doReq(r, req); rec.Code != http.StatusOK {
		t.Fatalf("first limited request status = %d, want 200", rec.Code)
	}
	req = httptest.NewRequest(http.MethodGet, "/limited", nil)
	req.RemoteAddr = "10.0.0.3:1234"
	if rec := doReq(r, req); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("second limited request status = %d, want 429", rec.Code)
	}

	for _, path := range []string{"/metrics", "/api/health", "/api/readyz"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.RemoteAddr = "10.0.0.3:1234"
		rec := doReq(r, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("exempt path %s status = %d, want 200", path, rec.Code)
		}
	}
}

func TestDisabled(t *testing.T) {
	l := New(1, 1, false)
	h := l.Middleware(okHandler())

	for i := 0; i < 100; i++ {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.RemoteAddr = "10.0.0.4:1234"
		rec := doReq(h, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("request %d status = %d, want 200 (disabled)", i+1, rec.Code)
		}
	}
}

func TestPerKeyIsolation(t *testing.T) {
	l := New(10, 2, true)
	h := l.Middleware(okHandler())

	mk := func(key string) *http.Request {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.RemoteAddr = "10.0.0.5:1234"
		req.Header.Set("X-API-Key", key)
		return req
	}

	for i := 0; i < 2; i++ {
		if rec := doReq(h, mk("A")); rec.Code != http.StatusOK {
			t.Fatalf("key A request %d status = %d, want 200", i+1, rec.Code)
		}
	}
	if rec := doReq(h, mk("A")); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("key A 3rd request status = %d, want 429", rec.Code)
	}

	for i := 0; i < 2; i++ {
		if rec := doReq(h, mk("B")); rec.Code != http.StatusOK {
			t.Fatalf("key B request %d status = %d, want 200", i+1, rec.Code)
		}
	}
}

func TestRefillOverTime(t *testing.T) {
	l := New(10, 1, true)
	h := l.Middleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.RemoteAddr = "10.0.0.6:1234"
	if rec := doReq(h, req); rec.Code != http.StatusOK {
		t.Fatalf("first request status = %d, want 200", rec.Code)
	}

	req = httptest.NewRequest(http.MethodGet, "/x", nil)
	req.RemoteAddr = "10.0.0.6:1234"
	if rec := doReq(h, req); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("second request status = %d, want 429", rec.Code)
	}

	time.Sleep(300 * time.Millisecond)

	req = httptest.NewRequest(http.MethodGet, "/x", nil)
	req.RemoteAddr = "10.0.0.6:1234"
	if rec := doReq(h, req); rec.Code != http.StatusOK {
		t.Fatalf("post-refill request status = %d, want 200", rec.Code)
	}
}
