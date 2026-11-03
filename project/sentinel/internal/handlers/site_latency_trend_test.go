package handlers

import (
	"database/sql"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

func insertLatencyCheck(t *testing.T, database *sql.DB, monitorID int64, checkedAt string, ok int, latencyMs int) {
	t.Helper()
	_, err := database.Exec("INSERT INTO checks (monitor_id, checked_at, ok, latency_ms) VALUES (?, ?, ?, ?)", monitorID, checkedAt, ok, latencyMs)
	if err != nil {
		t.Fatalf("insert check: %v", err)
	}
}

func TestSiteLatencyTrendJSON(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()
	monitorID := insertMonitor(t, database)

	for _, latency := range []int{100, 200, 300} {
		insertLatencyCheck(t, database, monitorID, "2024-03-05T10:00:00Z", 1, latency)
	}
	insertLatencyCheck(t, database, monitorID, "2024-03-05T10:00:00Z", 0, 9999)

	req := httptest.NewRequest("GET", "/api/latency/trend?end=2024-03&months=2", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteLatencyTrendJSON(rec, req)
	if rec.Code != 200 {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var resp struct {
		EndMonth string `json:"end_month"`
		Months   int    `json:"months"`
		Items    []struct {
			Month       string  `json:"month"`
			P50Ms       float64 `json:"p50_ms"`
			P95Ms       float64 `json:"p95_ms"`
			TotalChecks int     `json:"total_checks"`
		} `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if resp.EndMonth != "2024-03" {
		t.Fatalf("end_month = %q, want 2024-03", resp.EndMonth)
	}
	if resp.Months != 2 {
		t.Fatalf("months = %d, want 2", resp.Months)
	}
	if len(resp.Items) != 2 {
		t.Fatalf("len(items) = %d, want 2", len(resp.Items))
		return
	}
	if resp.Items[1].Month != "2024-03" {
		t.Fatalf("items[1].month = %q, want 2024-03", resp.Items[1].Month)
	}
	if resp.Items[1].TotalChecks != 3 {
		t.Fatalf("items[1].total_checks = %d, want 3 (failed check not counted)", resp.Items[1].TotalChecks)
	}
	if resp.Items[1].P50Ms != 200 {
		t.Fatalf("items[1].p50_ms = %v, want 200", resp.Items[1].P50Ms)
	}
	if resp.Items[1].P95Ms != 290 {
		t.Fatalf("items[1].p95_ms = %v, want 290", resp.Items[1].P95Ms)
	}
	if resp.Items[0].Month != "2024-02" {
		t.Fatalf("items[0].month = %q, want 2024-02", resp.Items[0].Month)
	}
	if resp.Items[0].TotalChecks != 0 {
		t.Fatalf("items[0].total_checks = %d, want 0", resp.Items[0].TotalChecks)
	}
	if resp.Items[0].P50Ms != 0 {
		t.Fatalf("items[0].p50_ms = %v, want 0", resp.Items[0].P50Ms)
	}
}

func TestSiteLatencyTrendJSONBadParams(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	for _, url := range []string{
		"/api/latency/trend?end=2024-03&months=0",
		"/api/latency/trend?end=2024-13&months=2",
		"/api/latency/trend?end=2024-03&months=abc",
	} {
		req := httptest.NewRequest("GET", url, nil)
		rec := httptest.NewRecorder()
		srv.handleSiteLatencyTrendJSON(rec, req)
		if rec.Code != 400 {
			t.Fatalf("%s: expected 400, got %d: %s", url, rec.Code, rec.Body.String())
		}
	}
}

func TestSiteLatencyTrendHTML(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	monitorID := insertMonitor(t, database)
	insertLatencyCheck(t, database, monitorID, "2024-03-05T10:00:00Z", 1, 100)
	insertLatencyCheck(t, database, monitorID, "2024-03-05T10:00:00Z", 1, 200)

	req := httptest.NewRequest("GET", "/api/latency/trend.html?end=2024-03&months=2", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteLatencyTrendHTML(rec, req)

	if rec.Code != 200 {
		t.Fatalf("expected status 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := rec.Body.String()
	for _, want := range []string{"全站延迟趋势", "2024-03", "p95 延迟条形", "150.00"} {
		if !strings.Contains(body, want) {
			t.Errorf("body does not contain %q", want)
		}
	}

	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Errorf("Content-Type = %q, want it to contain %q", ct, "text/html")
	}

	req2 := httptest.NewRequest("GET", "/api/latency/trend.html?end=2024-13&months=2", nil)
	rec2 := httptest.NewRecorder()
	srv.handleSiteLatencyTrendHTML(rec2, req2)

	if rec2.Code != 400 {
		t.Fatalf("expected status 400 for invalid month, got %d", rec2.Code)
	}
}
