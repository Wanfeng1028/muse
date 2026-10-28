package handlers

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"sentinel/internal/db"
	"sentinel/internal/scheduler"
	"sentinel/internal/store"
)

func TestMonitorProfileSuccess(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	req := newReq(http.MethodGet, fmt.Sprintf("/api/monitors/%d/profile", mid), nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d, body: %s", rec.Code, rec.Body.String())
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal body: %v", err)
	}

	expectedKeys := []string{"monitor", "uptime_7d", "uptime_30d", "latency", "incidents_30d", "current", "cert_days_left", "daily", "jitter_score", "jitter_level", "timeline"}
	for _, key := range expectedKeys {
		if _, ok := resp[key]; !ok {
			t.Fatalf("missing key: %s", key)
		}
	}

	if resp["uptime_7d"] != 100.0 {
		t.Fatalf("uptime_7d = %v, want 100", resp["uptime_7d"])
	}
	if resp["current"] != nil {
		t.Fatalf("current = %v, want nil", resp["current"])
	}

	daily, ok := resp["daily"].([]interface{})
	if !ok {
		t.Fatalf("daily is not an array: %T", resp["daily"])
	}
	if len(daily) != 30 {
		t.Fatalf("daily len = %d, want 30", len(daily))
	}

	if resp["jitter_level"] != "数据不足" {
		t.Fatalf("jitter_level = %v, want 数据不足", resp["jitter_level"])
	}

	timeline, ok := resp["timeline"].([]interface{})
	if !ok {
		t.Fatalf("timeline is not an array: %T", resp["timeline"])
	}
	if len(timeline) != 0 {
		t.Fatalf("timeline len = %d, want 0", len(timeline))
	}
}

func TestMonitorProfileNonexistent(t *testing.T) {
	srv, _ := newTestServer(t)
	req := newReq(http.MethodGet, "/api/monitors/999999/profile", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d, body: %s", rec.Code, rec.Body.String())
	}
}

func TestMonitorProfileStoreErrorReturns500(t *testing.T) {
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

	id, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if _, err := sqlDB.Exec("DROP TABLE checks"); err != nil {
		t.Fatalf("DROP TABLE checks: %v", err)
	}

	req := newReq(http.MethodGet, fmt.Sprintf("/api/monitors/%d/profile", id), nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected status 500, got %d, body: %s", rec.Code, rec.Body.String())
	}
}
