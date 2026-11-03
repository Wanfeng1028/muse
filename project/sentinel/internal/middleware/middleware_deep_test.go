package middleware

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"sentinel/internal/db"
	applog "sentinel/internal/log"
	"sentinel/internal/store"
)

func sha256Hex(t *testing.T, s string) string {
	t.Helper()
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	path := filepath.Join(t.TempDir(), "sentinel-test.db")
	sqlDB, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := store.New(sqlDB)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant failed: %v", err)
	}
	return st
}

func TestRequestID_Passthrough(t *testing.T) {
	var gotID string
	handler := RequestID(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotID = applog.RequestIDFrom(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Request-ID", "req-42")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if got := rec.Header().Get("X-Request-ID"); got != "req-42" {
		t.Fatalf("response X-Request-ID = %q, want %q", got, "req-42")
	}
	if gotID != "req-42" {
		t.Fatalf("downstream request id = %q, want %q", gotID, "req-42")
	}
}

func TestRequestID_Generated(t *testing.T) {
	var gotID string
	handler := RequestID(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotID = applog.RequestIDFrom(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	respID := rec.Header().Get("X-Request-ID")
	if respID == "" {
		t.Fatalf("generated request id is empty")
	}
	if len(respID) != 32 {
		t.Fatalf("generated request id length = %d, want 32", len(respID))
	}
	for i := 0; i < len(respID); i++ {
		c := respID[i]
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			t.Fatalf("generated request id contains non-hex char %q at %d", c, i)
		}
	}
	if gotID != respID {
		t.Fatalf("downstream id = %q, response header = %q, want equal", gotID, respID)
	}
}

func TestRequestID_TrimsSpaces(t *testing.T) {
	handler := RequestID(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Request-ID", "  spaced  ")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if got := rec.Header().Get("X-Request-ID"); got != "spaced" {
		t.Fatalf("response X-Request-ID = %q, want %q", got, "spaced")
	}
}

func TestUserFrom_NilContext(t *testing.T) {
	if u := UserFrom(nil); u != nil {
		t.Fatalf("UserFrom(nil) = %v, want nil", u)
	}
	if id := TenantIDFrom(nil); id != 0 {
		t.Fatalf("TenantIDFrom(nil) = %d, want 0", id)
	}
}

func TestUserFrom_WrongType(t *testing.T) {
	ctx := context.WithValue(context.Background(), userKey, "not-a-user")
	if u := UserFrom(ctx); u != nil {
		t.Fatalf("UserFrom with wrong type = %v, want nil", u)
	}
	if id := TenantIDFrom(ctx); id != 0 {
		t.Fatalf("TenantIDFrom with wrong type = %d, want 0", id)
	}
}

func TestAuth_ExactWhitelist(t *testing.T) {
	st := newTestStore(t)
	a := NewAuth(st)
	mw := a.Middleware([]string{"/healthz"}, nil)

	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !called {
		t.Fatalf("downstream handler was not called for whitelisted path")
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("whitelisted status = %d, want %d", rec.Code, http.StatusOK)
	}

	called = false
	req2 := httptest.NewRequest(http.MethodGet, "/api/x", nil)
	rec2 := httptest.NewRecorder()
	handler.ServeHTTP(rec2, req2)

	if called {
		t.Fatalf("downstream handler was called for non-whitelisted path")
	}
	if rec2.Code != http.StatusUnauthorized {
		t.Fatalf("non-whitelisted status = %d, want %d", rec2.Code, http.StatusUnauthorized)
	}
}

func TestAuth_PrefixWhitelist(t *testing.T) {
	st := newTestStore(t)
	a := NewAuth(st)
	mw := a.Middleware(nil, []string{"/api/status/"})

	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/status/abc", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !called {
		t.Fatalf("downstream handler was not called for prefix-whitelisted path")
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("prefix-whitelisted status = %d, want %d", rec.Code, http.StatusOK)
	}

	called = false
	req2 := httptest.NewRequest(http.MethodGet, "/api/statusx", nil)
	rec2 := httptest.NewRecorder()
	handler.ServeHTTP(rec2, req2)

	if called {
		t.Fatalf("downstream handler was called for non-prefix-whitelisted path")
	}
	if rec2.Code != http.StatusUnauthorized {
		t.Fatalf("non-prefix-whitelisted status = %d, want %d", rec2.Code, http.StatusUnauthorized)
	}
}

func TestAuth_ValidToken(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateUser(1, "alice", sha256Hex(t, "good-token-1")); err != nil {
		t.Fatalf("CreateUser failed: %v", err)
	}
	a := NewAuth(st)
	mw := a.Middleware(nil, nil)

	var gotName string
	var gotTenant int64
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		u := UserFrom(r.Context())
		if u != nil {
			gotName = u.Name
		}
		gotTenant = TenantIDFrom(r.Context())
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	req.Header.Set("Authorization", "Bearer good-token-1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if gotName != "alice" {
		t.Fatalf("downstream user name = %q, want %q", gotName, "alice")
	}
	if gotTenant != 1 {
		t.Fatalf("downstream tenant id = %d, want 1", gotTenant)
	}
}

func TestAuth_WrongToken(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateUser(1, "alice", sha256Hex(t, "good-token-1")); err != nil {
		t.Fatalf("CreateUser failed: %v", err)
	}
	a := NewAuth(st)
	mw := a.Middleware(nil, nil)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	req.Header.Set("Authorization", "Bearer wrong-token")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusUnauthorized)
	}
	ct := rec.Header().Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Fatalf("Content-Type = %q, want contains application/json", ct)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to unmarshal body %q: %v", rec.Body.String(), err)
	}
	if body["error"] != "未授权" {
		t.Fatalf("body error = %q, want %q", body["error"], "未授权")
	}
}

func TestAuth_MissingHeader(t *testing.T) {
	st := newTestStore(t)
	a := NewAuth(st)
	mw := a.Middleware(nil, nil)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusUnauthorized)
	}
}

func TestAuth_BearerCaseInsensitive(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateUser(1, "alice", sha256Hex(t, "good-token-1")); err != nil {
		t.Fatalf("CreateUser failed: %v", err)
	}
	a := NewAuth(st)
	mw := a.Middleware(nil, nil)

	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	req.Header.Set("Authorization", "bearer good-token-1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !called {
		t.Fatalf("downstream handler was not called for lowercase bearer")
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
}

func TestAuth_BearerEmptyToken(t *testing.T) {
	st := newTestStore(t)
	a := NewAuth(st)
	mw := a.Middleware(nil, nil)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	req.Header.Set("Authorization", "Bearer ")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("empty bearer status = %d, want %d", rec.Code, http.StatusUnauthorized)
	}

	req2 := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	req2.Header.Set("Authorization", "Basic abcdef")
	rec2 := httptest.NewRecorder()
	handler.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusUnauthorized {
		t.Fatalf("basic scheme status = %d, want %d", rec2.Code, http.StatusUnauthorized)
	}
}

func TestAuth_MultipleUsers(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateUser(1, "alice", sha256Hex(t, "good-token-1")); err != nil {
		t.Fatalf("CreateUser alice failed: %v", err)
	}
	if _, err := st.CreateUser(1, "bob", sha256Hex(t, "good-token-2")); err != nil {
		t.Fatalf("CreateUser bob failed: %v", err)
	}
	a := NewAuth(st)
	mw := a.Middleware(nil, nil)

	var gotName string
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if u := UserFrom(r.Context()); u != nil {
			gotName = u.Name
		}
		w.WriteHeader(http.StatusOK)
	})
	handler := mw(next)

	req := httptest.NewRequest(http.MethodGet, "/api/secure", nil)
	req.Header.Set("Authorization", "Bearer good-token-2")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if gotName != "bob" {
		t.Fatalf("downstream user name = %q, want %q", gotName, "bob")
	}
}

func TestLogging_Captures500(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("oops"))
	})
	handler := Logging(next)

	req := httptest.NewRequest(http.MethodGet, "/boom", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusInternalServerError)
	}
	if rec.Body.String() != "oops" {
		t.Fatalf("body = %q, want %q", rec.Body.String(), "oops")
	}
}

func TestStatusRecorder_DoubleWriteHeader(t *testing.T) {
	rr := httptest.NewRecorder()
	rec := &statusRecorder{ResponseWriter: rr, status: http.StatusOK}

	rec.WriteHeader(http.StatusNotFound)
	rec.WriteHeader(http.StatusInternalServerError)

	if rec.status != http.StatusNotFound {
		t.Fatalf("statusRecorder status = %d, want %d", rec.status, http.StatusNotFound)
	}
	if rr.Code != http.StatusNotFound {
		t.Fatalf("underlying ResponseRecorder code = %d, want %d", rr.Code, http.StatusNotFound)
	}

	rr2 := httptest.NewRecorder()
	rec2 := &statusRecorder{ResponseWriter: rr2, status: http.StatusOK}
	if _, err := rec2.Write([]byte("body")); err != nil {
		t.Fatalf("Write failed: %v", err)
	}
	if rec2.status != http.StatusOK {
		t.Fatalf("statusRecorder status after Write = %d, want %d", rec2.status, http.StatusOK)
	}
	if !rec2.wroteHeader {
		t.Fatalf("statusRecorder wroteHeader = false after Write, want true")
	}
}
