package handlers

import (
	"net/http"
	"testing"
	"time"

	"sentinel/internal/store"
)

func seedIncidents(t *testing.T, st *store.Store, n int) int64 {
	t.Helper()
	mid, err := st.CreateMonitor(store.Monitor{Name: "m", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < n; i++ {
		start := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, _, err := st.OpenIncident(mid, start, "err"); err != nil {
			t.Fatalf("open incident %d: %v", i, err)
		}
		if err := st.CloseOpenIncident(mid, end, 60); err != nil {
			t.Fatalf("close incident %d: %v", i, err)
		}
	}
	return mid
}

func TestHandleListIncidents_DefaultPage(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if got := body["total"]; got != float64(45) {
		t.Fatalf("total = %v, want 45", got)
	}
	if got := body["page"]; got != float64(1) {
		t.Fatalf("page = %v, want 1", got)
	}
	if got := body["page_size"]; got != float64(20) {
		t.Fatalf("page_size = %v, want 20", got)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items not array: %T", body["items"])
	}
	if len(items) != 20 {
		t.Fatalf("items len = %d, want 20", len(items))
	}
	first := items[0].(map[string]any)
	want := time.Date(2026, 10, 1, 0, 44, 0, 0, time.UTC).Format(time.RFC3339Nano)
	if first["started_at"] != want {
		t.Fatalf("first started_at = %v, want %v", first["started_at"], want)
	}
}

func TestHandleListIncidents_Page2(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	_, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=2&page_size=20", "")
	items := body["items"].([]any)
	if len(items) != 20 {
		t.Fatalf("page2 items len = %d, want 20", len(items))
	}

	_, body3 := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=3&page_size=20", "")
	items3 := body3["items"].([]any)
	if len(items3) != 5 {
		t.Fatalf("page3 items len = %d, want 5", len(items3))
	}
	if body3["page"] != float64(3) {
		t.Fatalf("page3 page = %v, want 3", body3["page"])
	}
}

func TestHandleListIncidents_PageSizeClamp(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	_, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page_size=500", "")
	if body["page_size"] != float64(100) {
		t.Fatalf("page_size = %v, want 100", body["page_size"])
	}
	items := body["items"].([]any)
	if len(items) > 100 {
		t.Fatalf("items len = %d, want <= 100", len(items))
	}
	if len(items) != 45 {
		t.Fatalf("items len = %d, want 45", len(items))
	}
}

func TestHandleListIncidents_LegacyLimit(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	_, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?limit=10", "")
	if body["page"] != float64(1) {
		t.Fatalf("page = %v, want 1", body["page"])
	}
	if body["page_size"] != float64(10) {
		t.Fatalf("page_size = %v, want 10", body["page_size"])
	}
	if body["total"] != float64(45) {
		t.Fatalf("total = %v, want 45", body["total"])
	}
	items := body["items"].([]any)
	if len(items) != 10 {
		t.Fatalf("items len = %d, want 10", len(items))
	}
}

func TestHandleListIncidents_InvalidPage(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=abc&page_size=xyz", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if body["page"] != float64(1) {
		t.Fatalf("page = %v, want 1", body["page"])
	}
	if body["page_size"] != float64(20) {
		t.Fatalf("page_size = %v, want 20", body["page_size"])
	}
}

func TestHandleListIncidents_MonitorFilter(t *testing.T) {
	srv, st := newTestServer(t)

	midA, err := st.CreateMonitor(store.Monitor{Name: "a", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor a: %v", err)
	}
	midB, err := st.CreateMonitor(store.Monitor{Name: "b", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor b: %v", err)
	}

	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 30; i++ {
		start := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, _, err := st.OpenIncident(midA, start, "err"); err != nil {
			t.Fatalf("open a %d: %v", i, err)
		}
		if err := st.CloseOpenIncident(midA, end, 60); err != nil {
			t.Fatalf("close a %d: %v", i, err)
		}
	}
	for i := 0; i < 7; i++ {
		start := base.Add(time.Duration(100+i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(100+i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, _, err := st.OpenIncident(midB, start, "err"); err != nil {
			t.Fatalf("open b %d: %v", i, err)
		}
		if err := st.CloseOpenIncident(midB, end, 60); err != nil {
			t.Fatalf("close b %d: %v", i, err)
		}
	}

	path := "/api/incidents?monitor_id=" + itoa(midA)
	_, body := doJSON(t, srv.Routes(), http.MethodGet, path, "")
	if body["total"] != float64(30) {
		t.Fatalf("total = %v, want 30", body["total"])
	}
	items := body["items"].([]any)
	for _, raw := range items {
		it := raw.(map[string]any)
		if it["monitor_id"] != float64(midA) {
			t.Fatalf("monitor_id = %v, want %d", it["monitor_id"], midA)
		}
	}

	path2 := "/api/incidents?monitor_id=" + itoa(midA) + "&page=2&page_size=20"
	_, body2 := doJSON(t, srv.Routes(), http.MethodGet, path2, "")
	if body2["total"] != float64(30) {
		t.Fatalf("page2 total = %v, want 30", body2["total"])
	}
	if body2["page"] != float64(2) {
		t.Fatalf("page2 page = %v, want 2", body2["page"])
	}
	items2 := body2["items"].([]any)
	if len(items2) != 10 {
		t.Fatalf("page2 items len = %d, want 10", len(items2))
	}
}

func TestHandleListIncidents_PageBeyondTotal(t *testing.T) {
	srv, st := newTestServer(t)
	seedIncidents(t, st, 45)

	_, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?page=99", "")
	if body["total"] != float64(45) {
		t.Fatalf("total = %v, want 45", body["total"])
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items not array: %T", body["items"])
	}
	if items == nil {
		t.Fatalf("items is nil, want empty array")
	}
	if len(items) != 0 {
		t.Fatalf("items len = %d, want 0", len(items))
	}
}
