package handlers

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestMonitorYearlySLAHandlerJSON(t *testing.T) {
	srv, st := newTestServer(t)

	mid, err := st.CreateMonitor(store.Monitor{
		Name:           "site",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}

	rec, out := doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/year?year=2024", mid), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if out["monitor_id"] != float64(mid) {
		t.Errorf("monitor_id = %v, want %d", out["monitor_id"], mid)
	}
	if out["monitor_name"] != "site" {
		t.Errorf("monitor_name = %v, want site", out["monitor_name"])
	}
	if out["year"] != float64(2024) {
		t.Errorf("year = %v, want 2024", out["year"])
	}
	items, ok := out["items"].([]interface{})
	if !ok {
		t.Fatalf("items missing or not a list: %v", out["items"])
	}
	if len(items) != 12 {
		t.Errorf("len(items) = %d, want 12", len(items))
	}

	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, "/api/monitors/999999/sla/year?year=2024", "")
	if rec.Code != http.StatusNotFound {
		t.Errorf("missing monitor status = %d, want 404", rec.Code)
	}

	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/year?year=abc", mid), "")
	if rec.Code != http.StatusBadRequest {
		t.Errorf("bad year status = %d, want 400", rec.Code)
	}

	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/year?year=1969", mid), "")
	if rec.Code != http.StatusBadRequest {
		t.Errorf("year 1969 status = %d, want 400", rec.Code)
	}
}

func TestMonitorYearlySLAHandlerHTML(t *testing.T) {
	srv, st := newTestServer(t)

	mid, err := st.CreateMonitor(store.Monitor{
		Name:           "site",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/year.html?year=2024", mid), nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	body := rec.Body.String()
	for _, want := range []string{"单监控年度 SLA 报告", "site", "可用性条形"} {
		if !strings.Contains(body, want) {
			t.Errorf("body missing %q", want)
		}
	}

	req = httptest.NewRequest(http.MethodGet, "/api/monitors/999999/sla/year.html?year=2024", nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Errorf("missing monitor status = %d, want 404", rec.Code)
	}

	req = httptest.NewRequest(http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/year.html?year=abc", mid), nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("bad year status = %d, want 400", rec.Code)
	}
}