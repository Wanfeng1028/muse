package handlers

import (
	"net/http"
	"strconv"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestHandleGetIncident(t *testing.T) {
	srv, st := newTestServer(t)
	mid, err := st.CreateMonitor(store.Monitor{Name: "m", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	start := base.Format(time.RFC3339Nano)
	end := base.Add(10 * time.Minute).Format(time.RFC3339Nano)
	incID, _, err := st.OpenIncident(mid, start, "boom")
	if err != nil {
		t.Fatalf("open incident: %v", err)
	}
	if _, err := st.InsertCheck(store.Check{MonitorID: mid, CheckedAt: end, Ok: 1, LatencyMs: 42, Error: ""}); err != nil {
		t.Fatalf("insert recovery check: %v", err)
	}
	if _, err := st.CloseOpenIncident(mid, end, 600); err != nil {
		t.Fatalf("close incident: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents/"+strconv.FormatInt(incID, 10), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body = %s, want 200", rec.Code, rec.Body.String())
	}
	inc, ok := body["incident"].(map[string]any)
	if !ok || inc["monitor_name"] != "m" || inc["start_error"] != "boom" {
		t.Fatalf("incident = %v, want monitor m / boom", body["incident"])
	}
	rc, ok := body["recovery_check"].(map[string]any)
	if !ok || rc["latency_ms"] != float64(42) {
		t.Fatalf("recovery_check = %v, want latency 42", body["recovery_check"])
	}
	deliveries, ok := body["deliveries"].([]any)
	if !ok {
		t.Fatalf("deliveries not array: %T", body["deliveries"])
	}
	if len(deliveries) != 0 {
		t.Fatalf("deliveries len = %d, want 0 (no deliveries seeded in this handler test)", len(deliveries))
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents/999999", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("missing status = %d, want 404", rec.Code)
	}
	rec, _ = doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents/abc", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("bad id status = %d, want 400", rec.Code)
	}
}
