package handlers

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestSLAHTMLPage(t *testing.T) {
	srv, st := newTestServer(t)
	mID, err := st.CreateMonitor(store.Monitor{Name: "SLA Mon", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 10, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	checks := []store.Check{
		{MonitorID: mID, CheckedAt: "2026-10-05T10:00:00Z", Ok: 1, LatencyMs: 100},
		{MonitorID: mID, CheckedAt: "2026-10-05T10:01:00Z", Ok: 1, LatencyMs: 120},
		{MonitorID: mID, CheckedAt: "2026-10-05T10:02:00Z", Ok: 0, LatencyMs: 0},
	}
	for _, c := range checks {
		if _, err := st.InsertCheck(c); err != nil {
			t.Fatalf("InsertCheck: %v", err)
		}
	}
	rec := httptest.NewRecorder()
	req := newReq(http.MethodGet, "/api/monitors/"+itoa(mID)+"/sla.html?month=2026-10", nil)
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Fatalf("Content-Type = %q, want text/html", ct)
	}
	body := rec.Body.String()
	if !strings.Contains(body, "SLA Mon") {
		t.Errorf("body missing monitor name")
	}
	if !strings.Contains(body, "月度 SLA 报告") {
		t.Errorf("body missing report heading")
	}
}

func TestSLAHTMLNotFound(t *testing.T) {
	srv, _ := newTestServer(t)
	rec := httptest.NewRecorder()
	req := newReq(http.MethodGet, "/api/monitors/999999/sla.html", nil)
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rec.Code)
	}
}

func TestSLAHTMLBadMonth(t *testing.T) {
	srv, st := newTestServer(t)
	mID, err := st.CreateMonitor(store.Monitor{Name: "SLA Mon", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 10, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	rec := httptest.NewRecorder()
	req := newReq(http.MethodGet, "/api/monitors/"+itoa(mID)+"/sla.html?month=2024-13", nil)
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}

func TestRenderSLAHTML(t *testing.T) {
	rep := store.SLAReport{
		Month:            "2026-10",
		UptimePct:        99.95,
		TotalChecks:      1000,
		DownIncidents:    2,
		TotalDowntimeSec: 3723,
		Target:           99.9,
		Met:              true,
		MTTRSec:          1861.5,
		Severity:         store.SeverityCounts{P1: 1, P2: 1, P3: 0},
		OpenIncidents:    0,
		Attribution:      map[string]int{"timeout": 1, "http_5xx": 1},
		AttributionPct:   map[string]float64{"timeout": 50.0, "http_5xx": 50.0},
	}
	out := renderSLAHTML("<b>Test</b>", rep)
	for _, want := range []string{"2026-10", "99.95%", "达标", "超时", "服务端 5xx", "1 小时 2 分钟", "P1", "&lt;b&gt;"} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q", want)
		}
	}
}
