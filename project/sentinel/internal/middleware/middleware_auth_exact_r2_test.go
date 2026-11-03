package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestR2_AuthExactWhitelist(t *testing.T) {
	st := newTestStore(t)
	auth := NewAuth(st)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	exact := []string{
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
	}
	prefixes := []string{
		"/api/status/",
		"/status/",
		"/static/",
	}

	h := auth.Middleware(exact, prefixes)(next)

	cases := []struct {
		name       string
		target     string
		wantStatus int
	}{
		{
			name:       "exact hit bypasses auth",
			target:     "/api/healthz",
			wantStatus: http.StatusOK,
		},
		{
			name:       "prefix requires trailing slash",
			target:     "/api/status",
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "exact entry does not match with trailing slash",
			target:     "/api/healthz/",
			wantStatus: http.StatusUnauthorized,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tc.target, nil)
			rec := httptest.NewRecorder()

			h.ServeHTTP(rec, req)

			if rec.Code != tc.wantStatus {
				t.Fatalf("path %q: got status %d, want %d", tc.target, rec.Code, tc.wantStatus)
			}
		})
	}
}
