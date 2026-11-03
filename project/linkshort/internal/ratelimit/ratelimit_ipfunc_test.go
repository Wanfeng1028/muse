package ratelimit

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestIPFuncHonored(t *testing.T) {
	l := New(100, 2, true)
	l.IPFunc = func(r *http.Request) string { return "9.9.9.9" }
	h := l.Middleware(okHandler())

	req1 := httptest.NewRequest(http.MethodGet, "/", nil)
	req1.RemoteAddr = "10.0.0.1:1111"
	w1 := httptest.NewRecorder()
	h.ServeHTTP(w1, req1)
	if w1.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w1.Code)
	}

	req2 := httptest.NewRequest(http.MethodGet, "/", nil)
	req2.RemoteAddr = "10.0.0.2:2222"
	w2 := httptest.NewRecorder()
	h.ServeHTTP(w2, req2)
	if w2.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w2.Code)
	}

	req3 := httptest.NewRequest(http.MethodGet, "/", nil)
	req3.RemoteAddr = "10.0.0.3:3333"
	w3 := httptest.NewRecorder()
	h.ServeHTTP(w3, req3)
	if w3.Code != http.StatusTooManyRequests {
		t.Fatalf("expected 429, got %d", w3.Code)
	}
}

func TestDefaultIgnoresSpoofedXFF(t *testing.T) {
	l := New(100, 2, true)
	h := l.Middleware(okHandler())

	xffs := []string{"1.1.1.1", "2.2.2.2", "3.3.3.3"}
	for i, xff := range xffs {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.RemoteAddr = "10.0.0.1:1234"
		req.Header.Set("X-Forwarded-For", xff)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		if i < 2 {
			if w.Code != http.StatusOK {
				t.Fatalf("request %d: expected 200, got %d", i+1, w.Code)
			}
		} else {
			if w.Code != http.StatusTooManyRequests {
				t.Fatalf("request %d: expected 429, got %d", i+1, w.Code)
			}
		}
	}
}

func TestIPFuncNilFallsBack(t *testing.T) {
	l := New(100, 100, true)
	l.IPFunc = nil
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.RemoteAddr = "10.9.8.7:5555"
	ip := l.ipOf(req)
	if ip != "10.9.8.7" {
		t.Fatalf("expected ip 10.9.8.7, got %s", ip)
	}
}
