package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestGroupYearlySLAHandlerJSON(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "site", Kind: "http", Target: "https://example.com", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1})
	if err != nil {
		t.Fatal(err)
	}
	rec, out := doJSON(t, srv.Routes(), http.MethodPost, "/api/groups", `{"name":"组A"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create group: %d", rec.Code)
	}
	gid := int(out["id"].(float64))
	if rec, _ = doJSON(t, srv.Routes(), http.MethodPost, fmt.Sprintf("/api/groups/%d/monitors", gid), fmt.Sprintf(`{"monitor_id":%d}`, mid)); rec.Code != 200 {
		t.Fatalf("add member: %d", rec.Code)
	}
	if rec, out = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/groups/%d/sla/year?year=2024", gid), ""); rec.Code != 200 {
		t.Fatalf("sla: %d", rec.Code)
	}
	items, _ := out["items"].([]any)
	if int(out["group_id"].(float64)) != gid || out["group_name"] != "组A" || int(out["year"].(float64)) != 2024 || len(items) != 12 {
		t.Fatalf("summary: %+v", out)
	}
	if rec, _ = doJSON(t, srv.Routes(), http.MethodGet, "/api/groups/999999/sla/year?year=2024", ""); rec.Code != 404 {
		t.Fatalf("missing group: %d", rec.Code)
	}
	if rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/groups/%d/sla/year?year=abc", gid), ""); rec.Code != 400 {
		t.Fatalf("year=abc: %d", rec.Code)
	}
	if rec, _ = doJSON(t, srv.Routes(), http.MethodGet, fmt.Sprintf("/api/groups/%d/sla/year?year=1969", gid), ""); rec.Code != 400 {
		t.Fatalf("year=1969: %d", rec.Code)
	}
}

func TestGroupYearlySLAHandlerHTML(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, _ := doJSON(t, srv.Routes(), "POST", "/api/groups", `{"name":"组B"}`)
	if rec.Code != 201 {
		t.Fatalf("create group: got %d want 201", rec.Code)
	}
	var g struct {
		ID int64 `json:"id"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &g); err != nil {
		t.Fatalf("parse gid: %v", err)
	}
	do := func(path string) *httptest.ResponseRecorder {
		req := httptest.NewRequest("GET", path, nil)
		req.Header.Set("Authorization", "Bearer "+testToken)
		w := httptest.NewRecorder()
		srv.Routes().ServeHTTP(w, req)
		return w
	}
	w := do(fmt.Sprintf("/api/groups/%d/sla/year.html?year=2024", g.ID))
	if w.Code != 200 {
		t.Fatalf("year report: got %d want 200", w.Code)
	}
	body := w.Body.String()
	for _, s := range []string{"分组年度 SLA 报告", "组B", "可用性条形"} {
		if !strings.Contains(body, s) {
			t.Errorf("body missing %q", s)
		}
	}
	if w = do("/api/groups/999999/sla/year.html?year=2024"); w.Code != 404 {
		t.Errorf("missing group: got %d want 404", w.Code)
	}
	if w = do(fmt.Sprintf("/api/groups/%d/sla/year.html?year=abc", g.ID)); w.Code != 400 {
		t.Errorf("invalid year: got %d want 400", w.Code)
	}
}
