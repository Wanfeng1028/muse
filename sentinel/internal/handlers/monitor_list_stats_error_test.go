package handlers

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"sentinel/internal/db"
	"sentinel/internal/scheduler"
	"sentinel/internal/store"
)

func TestMonitorListStatsErrorReturns500(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.db")
	sqlDB, err := db.Open(path)
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { _ = sqlDB.Close() })
	st := store.New(sqlDB)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}
	sum := sha256.Sum256([]byte("test-token"))
	tokenHash := hex.EncodeToString(sum[:])
	if _, err := st.CreateUser(1, "tester", tokenHash); err != nil {
		t.Fatalf("CreateUser: %v", err)
	}
	sc := scheduler.New(st, func(m store.Monitor, event, name, target, at, errMsg string) {}, 10, 5, 2)
	srv := New(st, sc, 2)
	if _, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1}); err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	if _, err := sqlDB.Exec("DROP TABLE checks"); err != nil {
		t.Fatalf("DROP TABLE checks: %v", err)
	}
	req := newReq(http.MethodGet, "/api/monitors", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != 500 {
		t.Fatalf("expected 500, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestMonitorListSuccessUptime(t *testing.T) {
	srv, st := newTestServer(t)
	if _, err := st.CreateMonitor(store.Monitor{
		Name:           "site",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	}); err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	req := newReq(http.MethodGet, "/api/monitors", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	var items []map[string]interface{}
	if err := json.NewDecoder(rec.Body).Decode(&items); err != nil {
		t.Fatalf("failed to unmarshal response body: %v", err)
	}

	if len(items) != 1 {
		t.Fatalf("len(items) = %d, want 1", len(items))
	}
	if uptime, ok := items[0]["uptime_24h"].(float64); !ok || uptime != 100.0 {
		t.Fatalf("uptime_24h = %v, want 100.0", items[0]["uptime_24h"])
	}
}

func TestMonitorListEmptyReturnsArray(t *testing.T) {
	srv, _ := newTestServer(t)

	req := newReq(http.MethodGet, "/api/monitors", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	var items []interface{}
	if err := json.NewDecoder(rec.Body).Decode(&items); err != nil {
		t.Fatalf("failed to unmarshal response body: %v", err)
	}

	if len(items) != 0 {
		t.Fatalf("len(items) = %d, want 0", len(items))
	}
}
