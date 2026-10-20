package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestR2_AuthProtectedNeedsToken(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateUser(1, "u", sha256Hex(t, "s3cret")); err != nil {
		t.Fatalf("CreateUser returned error: %v", err)
	}

	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	auth := NewAuth(st)
	h := auth.Middleware([]string{"/api/healthz"}, []string{"/api/status/"})(next)

	cases := []struct {
		name         string
		authorization string
		wantStatus   int
	}{
		{name: "missing token", authorization: "", wantStatus: http.StatusUnauthorized},
		{name: "wrong token", authorization: "Bearer wrong", wantStatus: http.StatusUnauthorized},
		{name: "valid token", authorization: "Bearer s3cret", wantStatus: http.StatusOK},
		{name: "lowercase bearer scheme", authorization: "bearer s3cret", wantStatus: http.StatusOK},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, "/api/monitors", nil)
			if tc.authorization != "" {
				req.Header.Set("Authorization", tc.authorization)
			}

			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, req)

			if rec.Code != tc.wantStatus {
				t.Fatalf("status = %d, want %d", rec.Code, tc.wantStatus)
			}
			if tc.wantStatus == http.StatusOK {
				if got := rec.Body.String(); got != "ok" {
					t.Fatalf("body = %q, want %q", got, "ok")
				}
			}
		})
	}
}
