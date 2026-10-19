package handlers

import (
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestStatusPageSnapshot(t *testing.T) {
	srv, st := newTestServer(t)

	pageID, err := st.CreateStatusPage(1, "acme", "Acme 状态")
	if err != nil {
		t.Fatalf("create status page: %v", err)
	}
	if err := st.UpdateStatusPageTheme(pageID, "dark", ""); err != nil {
		t.Fatalf("update theme: %v", err)
	}

	m1, err := st.CreateMonitor(store.Monitor{
		Name:           "API 网关",
		Kind:           "http",
		Target:         "example.local",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("create monitor 1: %v", err)
	}
	m2, err := st.CreateMonitor(store.Monitor{
		Name:           "数据库",
		Kind:           "http",
		Target:         "db.local",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("create monitor 2: %v", err)
	}

	if err := st.AddMonitorToPage(pageID, m1); err != nil {
		t.Fatalf("add monitor 1: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, m2); err != nil {
		t.Fatalf("add monitor 2: %v", err)
	}

	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := st.InsertCheck(store.Check{
		MonitorID: m1,
		CheckedAt: now,
		Ok:        1,
		LatencyMs: 42,
	}); err != nil {
		t.Fatalf("insert check 1: %v", err)
	}
	if _, err := st.InsertCheck(store.Check{
		MonitorID: m2,
		CheckedAt: now,
		Ok:        0,
		LatencyMs: 12,
	}); err != nil {
		t.Fatalf("insert check 2: %v", err)
	}

	path := "/api/status-pages/" + strconv.FormatInt(pageID, 10) + "/snapshot"
	rec := httptest.NewRecorder()
	req := newReq(http.MethodPost, path, nil)
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Fatalf("content-type = %q", ct)
	}
	cd := rec.Header().Get("Content-Disposition")
	if !strings.Contains(cd, "attachment") {
		t.Fatalf("content-disposition missing attachment: %q", cd)
	}
	if !strings.Contains(cd, "acme") {
		t.Fatalf("content-disposition missing slug: %q", cd)
	}

	body := rec.Body.String()
	if !strings.Contains(body, "API 网关") || !strings.Contains(body, "数据库") {
		t.Fatalf("body missing monitor names")
	}
	if got := strings.Count(body, "data-day="); got != 90*2 {
		t.Fatalf("data-day count = %d, want %d", got, 90*2)
	}
	if strings.Contains(body, "http://") || strings.Contains(body, "https://") {
		t.Fatalf("body contains external resource reference")
	}
	if !strings.Contains(body, "#0f172a") {
		t.Fatalf("dark theme background missing")
	}

	// 不存在的页面应返回 404。
	rec404 := httptest.NewRecorder()
	req404 := newReq(http.MethodPost, "/api/status-pages/999999/snapshot", nil)
	srv.Routes().ServeHTTP(rec404, req404)
	if rec404.Code != http.StatusNotFound {
		t.Fatalf("missing page status = %d, want 404", rec404.Code)
	}
}
