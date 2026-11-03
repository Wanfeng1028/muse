package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestR2_AuthPrefixWhitelistPublic(t *testing.T) {
	st := newTestStore(t)
	auth := NewAuth(st)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	h := auth.Middleware(
		[]string{
			"/healthz",
			"/readyz",
			"/api/healthz",
			"/api/readyz",
			"/api/health",
			"/",
			"/monitors",
			"/incidents",
			"/profile",
			"/deliveries",
		},
		[]string{
			"/api/status/",
			"/status/",
			"/static/",
		},
	)(next)

	paths := []string{
		"/status/my-page",
		"/api/status/my-page/subscribe",
		"/static/app.js",
	}

	for _, p := range paths {
		req := httptest.NewRequest("GET", p, nil)
		rr := httptest.NewRecorder()

		h.ServeHTTP(rr, req)

		if rr.Code != http.StatusOK {
			t.Fatalf("path %q: expected status %d, got %d", p, http.StatusOK, rr.Code)
		}
	}
}
