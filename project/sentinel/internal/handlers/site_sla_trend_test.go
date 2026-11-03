package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSiteSLATrendJSON(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	monitorID := insertMonitor(t, database)
	insertChecks(t, database, monitorID, 10, true)

	req := httptest.NewRequest("GET", "/api/sla/trend?end=2024-03&months=2", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteSLATrendJSON(rec, req)

	if rec.Code != 200 {
		t.Fatalf("status code = %d, want 200", rec.Code)
	}

	type siteSLATrendMonthResp struct {
		Month string `json:"month"`
	}
	type siteSLATrendResp struct {
		EndMonth string                  `json:"end_month"`
		Months   int                     `json:"months"`
		Items    []siteSLATrendMonthResp `json:"items"`
	}

	var resp siteSLATrendResp
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal response body: %v", err)
	}

	if resp.EndMonth != "2024-03" {
		t.Errorf("end_month = %q, want %q", resp.EndMonth, "2024-03")
	}
	if resp.Months != 2 {
		t.Errorf("months = %d, want 2", resp.Months)
	}
	if len(resp.Items) != 2 {
		t.Errorf("len(items) = %d, want 2", len(resp.Items))
	}
	if len(resp.Items) != 2 {
		return
	}
	if resp.Items[1].Month != "2024-03" {
		t.Errorf("items[1].month = %q, want %q", resp.Items[1].Month, "2024-03")
	}
}

func TestSiteSLATrendJSONBadParams(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/api/sla/trend?end=2024-03&months=0", nil)
	srv.handleSiteSLATrendJSON(rec, req)
	if rec.Code != 400 {
		t.Errorf("expected status 400 for months=0, got %d", rec.Code)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest("GET", "/api/sla/trend?end=2024-13&months=2", nil)
	srv.handleSiteSLATrendJSON(rec, req)
	if rec.Code != 400 {
		t.Errorf("expected status 400 for end=2024-13, got %d", rec.Code)
	}

	rec = httptest.NewRecorder()
	req = httptest.NewRequest("GET", "/api/sla/trend?end=2024-03&months=abc", nil)
	srv.handleSiteSLATrendJSON(rec, req)
	if rec.Code != 400 {
		t.Errorf("expected status 400 for months=abc, got %d", rec.Code)
	}
}

func TestSiteSLATrendHTML(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	monitorID := insertMonitor(t, database)
	insertChecks(t, database, monitorID, 10, true)

	req := httptest.NewRequest(http.MethodGet, "/api/sla/trend.html?end=2024-03&months=2", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteSLATrendHTML(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 %d", rec.Code, http.StatusOK)
	}

	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Errorf("Content-Type = %q, 应包含 text/html", ct)
	}

	body := rec.Body.String()
	if !strings.Contains(body, "全站 SLA 趋势") {
		t.Errorf("响应体缺少 %q", "全站 SLA 趋势")
	}
	if !strings.Contains(body, "2024-03") {
		t.Errorf("响应体缺少 %q", "2024-03")
	}
	if !strings.Contains(body, "可用性条形") {
		t.Errorf("响应体缺少 %q", "可用性条形")
	}

	req2 := httptest.NewRequest(http.MethodGet, "/api/sla/trend.html?end=2024-03&months=abc", nil)
	rec2 := httptest.NewRecorder()
	srv.handleSiteSLATrendHTML(rec2, req2)

	if rec2.Code != http.StatusBadRequest {
		t.Errorf("months=abc 状态码 = %d, 期望 %d", rec2.Code, http.StatusBadRequest)
	}
}
