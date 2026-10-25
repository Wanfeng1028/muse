package store

import (
	"database/sql"
	"testing"
	"time"

	"sentinel/internal/db"
)

func seedIncidentDetail(t *testing.T) (*Store, int64, int64) {
	t.Helper()
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	t.Cleanup(func() { _ = d.Close() })
	st := New(d)
	mid, err := st.CreateMonitor(Monitor{Name: "m", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
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
	if _, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: base.Add(1 * time.Minute).Format(time.RFC3339Nano), Ok: 0, LatencyMs: 10, Error: "boom"}); err != nil {
		t.Fatalf("insert fail check: %v", err)
	}
	if _, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: end, Ok: 1, LatencyMs: 42, Error: ""}); err != nil {
		t.Fatalf("insert recovery check: %v", err)
	}
	if _, err := st.CloseOpenIncident(mid, end, 600); err != nil {
		t.Fatalf("close incident: %v", err)
	}
	insertDelivery := func(event, createdAt string) {
		t.Helper()
		if _, err := d.Exec(`INSERT INTO webhook_deliveries(monitor_id, url, event, payload, status, attempt, max_attempts, next_retry_at, last_error, created_at, updated_at) VALUES (?, ?, ?, ?, 'done', 1, 8, '', '', ?, ?)`, mid, "https://example.com/hook", event, "{}", createdAt, createdAt); err != nil {
			t.Fatalf("insert delivery %s: %v", event, err)
		}
	}
	insertDelivery("down", base.Add(1*time.Minute).Format(time.RFC3339Nano))
	insertDelivery("recovered", end)
	insertDelivery("down", base.Add(-1*time.Hour).Format(time.RFC3339Nano))
	insertDelivery("recovered", base.Add(1*time.Hour).Format(time.RFC3339Nano))
	insertDelivery("other", base.Add(2*time.Minute).Format(time.RFC3339Nano))
	return st, mid, incID
}

func TestIncidentDetail_Closed(t *testing.T) {
	st, _, incID := seedIncidentDetail(t)
	inc, err := st.GetIncidentByID(incID)
	if err != nil {
		t.Fatalf("GetIncidentByID: %v", err)
	}
	if inc.MonitorName != "m" || inc.StartError != "boom" || !inc.EndedAt.Valid {
		t.Fatalf("incident = %+v, want monitor m / boom / ended", inc)
	}
	rc, err := st.FirstRecoveryCheck(inc)
	if err != nil {
		t.Fatalf("FirstRecoveryCheck: %v", err)
	}
	if rc == nil || rc.Ok != 1 || rc.LatencyMs != 42 {
		t.Fatalf("recovery check = %+v, want ok=1 latency=42", rc)
	}
	deliveries, err := st.ListIncidentDeliveries(inc)
	if err != nil {
		t.Fatalf("ListIncidentDeliveries: %v", err)
	}
	if len(deliveries) != 2 {
		t.Fatalf("deliveries len = %d, want 2 (window down+recovered only)", len(deliveries))
	}
	if deliveries[0].Event != "down" || deliveries[1].Event != "recovered" {
		t.Fatalf("deliveries events = %q %q, want down recovered", deliveries[0].Event, deliveries[1].Event)
	}
}

func TestIncidentDetail_OpenAndNotFound(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	t.Cleanup(func() { _ = d.Close() })
	st := New(d)
	mid, err := st.CreateMonitor(Monitor{Name: "m2", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	start := time.Date(2026, 10, 2, 0, 0, 0, 0, time.UTC).Format(time.RFC3339Nano)
	incID, _, err := st.OpenIncident(mid, start, "boom")
	if err != nil {
		t.Fatalf("open incident: %v", err)
	}
	inc, err := st.GetIncidentByID(incID)
	if err != nil {
		t.Fatalf("GetIncidentByID open: %v", err)
	}
	rc, err := st.FirstRecoveryCheck(inc)
	if err != nil {
		t.Fatalf("FirstRecoveryCheck open: %v", err)
	}
	if rc != nil {
		t.Fatalf("open incident recovery check = %+v, want nil", rc)
	}
	deliveries, err := st.ListIncidentDeliveries(inc)
	if err != nil {
		t.Fatalf("ListIncidentDeliveries open: %v", err)
	}
	if deliveries == nil || len(deliveries) != 0 {
		t.Fatalf("open deliveries = %v, want empty non-nil", deliveries)
	}
	if _, err := st.GetIncidentByID(999999); err != sql.ErrNoRows {
		t.Fatalf("GetIncidentByID missing err = %v, want sql.ErrNoRows", err)
	}
}
