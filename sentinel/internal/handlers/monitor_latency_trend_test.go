package handlers

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestMonitorLatencyTrendHandlerJSON(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	rec, out := doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/latency/trend?end=2026-10&months=2", mid), "")
	if rec.Code != 200 {
		t.Fatalf("latency trend: code=%d body=%s", rec.Code, rec.Body.String())
	}
	if out["monitor_id"].(float64) != float64(mid) {
		t.Fatalf("monitor_id 不符: %v", out["monitor_id"])
	}
	if out["monitor_name"] != "site" {
		t.Fatalf("monitor_name 不符: %v", out["monitor_name"])
	}
	if out["end_month"] != "2026-10" {
		t.Fatalf("end_month 不符: %v", out["end_month"])
	}
	if out["months"].(float64) != 2 {
		t.Fatalf("months 不符: %v", out["months"])
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, "/api/monitors/999999/latency/trend?end=2026-10&months=2", "")
	if rec.Code != 404 {
		t.Fatalf("不存在监控应为 404: code=%d", rec.Code)
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/latency/trend?end=2026-10&months=0", mid), "")
	if rec.Code != 400 {
		t.Fatalf("months=0 应为 400: code=%d", rec.Code)
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/monitors/%d/latency/trend?end=2026-13&months=2", mid), "")
	if rec.Code != 400 {
		t.Fatalf("end=2026-13 应为 400: code=%d", rec.Code)
	}
}

func TestMonitorLatencyTrendHandlerHTML(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site-b", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	req := httptest.NewRequest("GET", fmt.Sprintf("/api/monitors/%d/latency/trend.html?end=2026-10&months=2", mid), nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	htmlRec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(htmlRec, req)
	if htmlRec.Code != 200 {
		t.Fatalf("trend.html code=%d body=%s", htmlRec.Code, htmlRec.Body.String())
	}
	body := htmlRec.Body.String()
	if !strings.Contains(body, "单监控延迟趋势") {
		t.Errorf("body missing 单监控延迟趋势")
	}
	if !strings.Contains(body, "site-b") {
		t.Errorf("body missing site-b")
	}
	if !strings.Contains(body, "p95 延迟条形") {
		t.Errorf("body missing p95 延迟条形")
	}
	req404 := httptest.NewRequest("GET", "/api/monitors/999999/latency/trend.html?end=2026-10&months=2", nil)
	req404.Header.Set("Authorization", "Bearer "+testToken)
	rec404 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec404, req404)
	if rec404.Code != 404 {
		t.Fatalf("missing monitor code=%d want=404", rec404.Code)
	}
	req400 := httptest.NewRequest("GET", fmt.Sprintf("/api/monitors/%d/latency/trend.html?end=2026-13&months=2", mid), nil)
	req400.Header.Set("Authorization", "Bearer "+testToken)
	rec400 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec400, req400)
	if rec400.Code != 400 {
		t.Fatalf("invalid end code=%d want=400", rec400.Code)
	}
}
