package handlers

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func insertYearChecks(t *testing.T, database *sql.DB, monitorID int64, year, month, okCount, failCount int) {
	t.Helper()
	total := okCount + failCount
	for i := 0; i < total; i++ {
		ok := 0
		if i < okCount {
			ok = 1
		}
		checkedAt := time.Date(year, time.Month(month), 1+i, 10, 0, 0, 0, time.UTC).Format(time.RFC3339)
		_, err := database.Exec(
			"INSERT INTO checks (monitor_id, ok, latency_ms, checked_at) VALUES (?, ?, ?, ?)",
			monitorID, ok, 100, checkedAt,
		)
		if err != nil {
			t.Fatalf("insert check row: %v", err)
		}
	}
}

func TestSiteYearlySLAJSON(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	monitorID := insertMonitor(t, database)

	insertYearChecks(t, database, monitorID, 2024, 2, 10, 0)
	insertYearChecks(t, database, monitorID, 2024, 3, 9, 1)

	req := httptest.NewRequest(http.MethodGet, "/api/sla/year?year=2024", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteYearlySLAJSON(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("handleSiteYearlySLAJSON status = %d, want %d, body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var payload struct {
		Year        int     `json:"year"`
		UptimePct   float64 `json:"uptime_pct"`
		TotalChecks int     `json:"total_checks"`
		BestMonth   string  `json:"best_month"`
		WorstMonth  string  `json:"worst_month"`
		Items       []struct {
			Month     string  `json:"month"`
			UptimePct float64 `json:"uptime_pct"`
		} `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response json: %v", err)
	}

	if payload.Year != 2024 {
		t.Errorf("year = %d, want 2024", payload.Year)
	}
	if payload.TotalChecks != 20 {
		t.Errorf("total_checks = %d, want 20", payload.TotalChecks)
	}
	if payload.UptimePct != 95 {
		t.Errorf("uptime_pct = %v, want 95", payload.UptimePct)
	}
	if len(payload.Items) != 12 {
		t.Fatalf("len(items) = %d, want 12", len(payload.Items))
	}
	if got := fmt.Sprintf("%s %.2f", payload.Items[1].Month, payload.Items[1].UptimePct); got != "2024-02 100.00" {
		t.Errorf("items[1] = %s, want 2024-02 100.00", got)
	}
	if got := fmt.Sprintf("%s %.2f", payload.Items[2].Month, payload.Items[2].UptimePct); got != "2024-03 90.00" {
		t.Errorf("items[2] = %s, want 2024-03 90.00", got)
	}
	if payload.BestMonth != "2024-02" {
		t.Errorf("best_month = %s, want 2024-02", payload.BestMonth)
	}
	if payload.WorstMonth != "2024-03" {
		t.Errorf("worst_month = %s, want 2024-03", payload.WorstMonth)
	}
}

func TestSiteYearlySLAJSONBadYear(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	for _, year := range []string{"abc", "1969", "10000"} {
		req := httptest.NewRequest(http.MethodGet, "/api/sla/year?year="+year, nil)
		rec := httptest.NewRecorder()
		srv.handleSiteYearlySLAJSON(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Errorf("year=%s: handleSiteYearlySLAJSON status = %d, want %d", year, rec.Code, http.StatusBadRequest)
		}
	}
}

func TestSiteYearlySLAHTML(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/sla/year.html?year=2024", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteYearlySLAHTML(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("handleSiteYearlySLAHTML status = %d, want %d", rec.Code, http.StatusOK)
	}
	body := rec.Body.String()
	if !strings.Contains(body, "全站年度 SLA 报告 2024") {
		t.Errorf("handleSiteYearlySLAHTML body does not contain %q", "全站年度 SLA 报告 2024")
	}
	if !strings.Contains(body, "可用性条形") {
		t.Errorf("handleSiteYearlySLAHTML body does not contain %q", "可用性条形")
	}

	badReq := httptest.NewRequest(http.MethodGet, "/api/sla/year.html?year=abc", nil)
	badRec := httptest.NewRecorder()
	srv.handleSiteYearlySLAHTML(badRec, badReq)

	if badRec.Code != http.StatusBadRequest {
		t.Errorf("year=abc: handleSiteYearlySLAHTML status = %d, want %d", badRec.Code, http.StatusBadRequest)
	}
}
