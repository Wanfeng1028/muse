package handlers

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestGroupSLAHandlerJSON(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"组A"}`)
	if rec.Code != 201 {
		t.Fatalf("create group: code=%d body=%s", rec.Code, rec.Body.String())
	}
	gid := int64(out["id"].(float64))
	rec, _ = doJSON(t, srv.Routes(), http.MethodPost, fmt.Sprintf("/api/groups/%d/monitors", gid), fmt.Sprintf(`{"monitor_id":%d}`, mid))
	if rec.Code != 200 {
		t.Fatalf("add monitor to group: code=%d body=%s", rec.Code, rec.Body.String())
	}
	rec, out = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/groups/%d/sla?month=2026-10", gid), "")
	if rec.Code != 200 {
		t.Fatalf("group sla: code=%d body=%s", rec.Code, rec.Body.String())
	}
	if out["group_id"].(float64) != float64(gid) {
		t.Fatalf("group_id 字段不符: %v", out["group_id"])
	}
	if out["group_name"] != "组A" {
		t.Fatalf("group_name 字段不符: %v", out["group_name"])
	}
	if out["month"] != "2026-10" {
		t.Fatalf("month 字段不符: %v", out["month"])
	}
	if out["monitor_count"].(float64) != 1 {
		t.Fatalf("monitor_count 字段不符: %v", out["monitor_count"])
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, "/api/groups/999999/sla?month=2026-10", "")
	if rec.Code != 404 {
		t.Fatalf("不存在分组应为 404: code=%d", rec.Code)
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/groups/%d/sla?month=2026-13", gid), "")
	if rec.Code != 400 {
		t.Fatalf("非法月份应为 400: code=%d", rec.Code)
	}
}

func TestGroupSLAHandlerHTML(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"组B"}`)
	if rec.Code != 201 {
		t.Fatalf("create group code=%d body=%s", rec.Code, rec.Body.String())
	}
	gid := int64(out["id"].(float64))
	req := httptest.NewRequest("GET", fmt.Sprintf("/api/groups/%d/sla.html?month=2026-10", gid), nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	htmlRec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(htmlRec, req)
	if htmlRec.Code != 200 {
		t.Fatalf("sla.html code=%d body=%s", htmlRec.Code, htmlRec.Body.String())
	}
	body := htmlRec.Body.String()
	if !strings.Contains(body, "分组 SLA 月报") {
		t.Errorf("body missing 分组 SLA 月报")
	}
	if !strings.Contains(body, "组B") {
		t.Errorf("body missing 组B")
	}
	if !strings.Contains(body, "本组暂无监控") {
		t.Errorf("body missing 本组暂无监控")
	}
	req404 := httptest.NewRequest("GET", "/api/groups/999999/sla.html?month=2026-10", nil)
	req404.Header.Set("Authorization", "Bearer "+testToken)
	rec404 := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec404, req404)
	if rec404.Code != 404 {
		t.Fatalf("missing group code=%d want=404", rec404.Code)
	}
}
