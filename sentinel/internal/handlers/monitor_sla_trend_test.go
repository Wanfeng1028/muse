package handlers

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestMonitorSLATrendHandlerJSON(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	w, body := doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/trend?end=2026-10&months=2", mid), "")
	if w.Code != http.StatusOK || body["monitor_id"].(float64) != float64(mid) || body["monitor_name"] != "site" || body["end_month"] != "2026-10" || body["months"].(float64) != 2 {
		t.Fatalf("trend: status = %d, body = %v", w.Code, body)
	}
	if w, _ := doJSON(t, srv.Routes(), http.MethodGet, "/api/monitors/999999/sla/trend?end=2026-10&months=2", ""); w.Code != http.StatusNotFound {
		t.Fatalf("missing monitor: status = %d, want 404", w.Code)
	}
	if w, _ := doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/trend?end=2026-10&months=0", mid), ""); w.Code != http.StatusBadRequest {
		t.Fatalf("months=0: status = %d, want 400", w.Code)
	}
	if w, _ := doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/sla/trend?end=2026-13&months=2", mid), ""); w.Code != http.StatusBadRequest {
		t.Fatalf("end=2026-13: status = %d, want 400", w.Code)
	}
}
func TestMonitorSLATrendHandlerHTML(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	req := httptest.NewRequest("GET", fmt.Sprintf("/api/monitors/%d/sla/trend.html?end=2026-10&months=2", mid), nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("code = %d, want 200", rec.Code)
	}
	body := rec.Body.String()
	for _, want := range []string{"单监控 SLA 趋势", "site", "可用性条形"} {
		if !strings.Contains(body, want) {
			t.Errorf("body missing %q", want)
		}
	}
	req404 := httptest.NewRequest("GET", "/api/monitors/999999/sla/trend.html?end=2026-10&months=2", nil)
	req404.Header.Set("Authorization", "Bearer "+testToken)
	rec404 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec404, req404)
	if rec404.Code != 404 {
		t.Fatalf("missing monitor code=%d want=404", rec404.Code)
	}
}
