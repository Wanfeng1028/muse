package handlers

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type siteSLAReportResp struct {
	Month        string `json:"month"`
	MonitorCount int    `json:"monitor_count"`
}

func TestSiteSLAJSON(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()
	monitorID := insertMonitor(t, database)
	insertChecks(t, database, monitorID, 10, true)
	req := httptest.NewRequest("GET", "/api/sla?month=2024-03", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteSLAJSON(rec, req)
	resp := rec.Result()
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200，得到 %d", resp.StatusCode)
	}
	var body siteSLAReportResp
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if body.Month != "2024-03" {
		t.Errorf("Month 期望 2024-03，实际 %s", body.Month)
	}
	if body.MonitorCount != 1 {
		t.Errorf("MonitorCount 期望 1，实际 %d", body.MonitorCount)
	}
	reqBad := httptest.NewRequest("GET", "/api/sla?month=2024-13", nil)
	recBad := httptest.NewRecorder()
	srv.handleSiteSLAJSON(recBad, reqBad)
	if recBad.Result().StatusCode != http.StatusBadRequest {
		t.Errorf("非法月份期望 400，实际 %d", recBad.Result().StatusCode)
	}
}
func TestSiteSLAHTML(t *testing.T) {
	srv, _, database := newSLATestServer(t)
	defer database.Close()
	monitorID := insertMonitor(t, database)
	insertChecks(t, database, monitorID, 10, true)
	req := httptest.NewRequest("GET", "/api/sla.html?month=2024-03", nil)
	rec := httptest.NewRecorder()
	srv.handleSiteSLAHTML(rec, req)
	resp := rec.Result()
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("期望状态码 200，得到 %d", resp.StatusCode)
	}
	if ct := resp.Header.Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Errorf("Content-Type 期望含 text/html，实际 %s", ct)
	}
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("读取响应失败: %v", err)
	}
	if !strings.Contains(string(bodyBytes), "全站") {
		t.Errorf("HTML 响应期望含 全站")
	}
}
