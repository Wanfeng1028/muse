package handlers

import (
	"database/sql"
	"net/http"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestSoul_SLA_BadMonthFormats(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-sla-bad",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	bad := []string{"202610", "2026-13", "2026-00", "abcd-ef", "1969-12"}
	for _, m := range bad {
		rec, _ := doJSON(t, mux, "GET", "/api/monitors/"+itoaSoul(id)+"/sla?month="+m, "")
		if rec.Code != http.StatusBadRequest {
			t.Errorf("month=%q: got status %d, want 400", m, rec.Code)
		}
	}
}

func TestSoul_SLA_MonitorNotFound(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, _ := doJSON(t, mux, "GET", "/api/monitors/999999/sla?month=2026-10", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("got status %d, want 404", rec.Code)
	}
}

func TestSoul_SLA_BadIDPath(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, body := doJSON(t, mux, "GET", "/api/monitors/abc/sla?month=2026-10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200", rec.Code)
	}
	if len(body) != 0 {
		t.Fatalf("expected empty body, got %v", body)
	}
}

func TestSoul_SLA_OK(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-sla-ok",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	t0, err := time.Parse(time.RFC3339, "2026-10-05T10:00:00Z")
	if err != nil {
		t.Fatalf("parse time: %v", err)
	}
	checks := []store.Check{
		{MonitorID: id, CheckedAt: t0.UTC().Format(time.RFC3339), Ok: 1, LatencyMs: 10},
		{MonitorID: id, CheckedAt: t0.Add(1 * time.Minute).UTC().Format(time.RFC3339), Ok: 1, LatencyMs: 20},
		{MonitorID: id, CheckedAt: t0.Add(2 * time.Minute).UTC().Format(time.RFC3339), Ok: 0, LatencyMs: 30},
	}
	for _, c := range checks {
		if _, err := st.InsertCheck(c); err != nil {
			t.Fatalf("InsertCheck: %v", err)
		}
	}

	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)
	rec, body := doJSON(t, mux, "GET", "/api/monitors/"+itoaSoul(id)+"/sla?month=2026-10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200", rec.Code)
	}
	if got, _ := body["month"].(string); got != "2026-10" {
		t.Fatalf("month = %v, want 2026-10", body["month"])
	}
	if got, _ := body["total_checks"].(float64); got != 3 {
		t.Fatalf("total_checks = %v, want 3", body["total_checks"])
	}
	up, ok := body["uptime_pct"].(float64)
	if !ok {
		t.Fatalf("uptime_pct not a number: %v", body["uptime_pct"])
	}
	if up < 0 || up > 100 {
		t.Fatalf("uptime_pct = %v, want in [0,100]", up)
	}
}

func TestSoul_SLA_DefaultMonth(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-sla-default",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, body := doJSON(t, mux, "GET", "/api/monitors/"+itoaSoul(id)+"/sla", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200", rec.Code)
	}
	want := time.Now().UTC().Format("2006-01")
	if got, _ := body["month"].(string); got != want {
		t.Fatalf("month = %v, want %v", body["month"], want)
	}
}

func TestSoul_Profile_NotFound(t *testing.T) {
	srv, _ := newTestServer(t)
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, _ := doJSON(t, mux, "GET", "/api/monitors/999999/profile", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("got status %d, want 404", rec.Code)
	}
}

func TestSoul_Profile_EmptyState(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-profile-empty",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, body := doJSON(t, mux, "GET", "/api/monitors/"+itoaSoul(id)+"/profile", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200", rec.Code)
	}
	for _, k := range []string{"monitor", "uptime_7d", "uptime_30d", "latency", "incidents_30d", "current", "cert_days_left", "daily"} {
		if _, ok := body[k]; !ok {
			t.Fatalf("missing key %q in response", k)
		}
	}
	if body["current"] != nil {
		t.Fatalf("current = %v, want nil", body["current"])
	}
	if body["cert_days_left"] != nil {
		t.Fatalf("cert_days_left = %v, want nil", body["cert_days_left"])
	}
	daily, ok := body["daily"].([]any)
	if !ok {
		t.Fatalf("daily not an array: %#v", body["daily"])
	}
	if len(daily) != 30 {
		t.Fatalf("daily len = %d, want 30 (one entry per day including check-less days)", len(daily))
	}
	today := time.Now().UTC().Format("2006-01-02")
	for i, e := range daily {
		m, ok := e.(map[string]any)
		if !ok {
			t.Fatalf("daily[%d] not an object", i)
		}
		if m["checks"].(float64) != 0 {
			t.Fatalf("daily[%d].checks = %v, want 0", i, m["checks"])
		}
		if m["uptime_pct"].(float64) != 100 {
			t.Fatalf("daily[%d].uptime_pct = %v, want 100", i, m["uptime_pct"])
		}
	}
	last := daily[29].(map[string]any)
	if last["date"].(string) != today {
		t.Fatalf("daily last date = %v, want today %v", last["date"], today)
	}
}

func TestSoul_Profile_WithChecks(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-profile-checks",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	now := time.Now().UTC()
	if _, err := st.InsertCheck(store.Check{
		MonitorID: id,
		CheckedAt: now.Format(time.RFC3339),
		Ok:        1,
		LatencyMs: 15,
	}); err != nil {
		t.Fatalf("InsertCheck ok: %v", err)
	}

	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)
	rec, body := doJSON(t, mux, "GET", "/api/monitors/"+itoaSoul(id)+"/profile", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200", rec.Code)
	}
	if body["current"] == nil {
		t.Fatalf("current = nil, want non-nil after inserting check")
	}

	if _, err := st.InsertCheck(store.Check{
		MonitorID:    id,
		CheckedAt:    now.Add(1 * time.Minute).Format(time.RFC3339),
		Ok:           1,
		LatencyMs:    12,
		CertDaysLeft: sql.NullInt64{Int64: 30, Valid: true},
	}); err != nil {
		t.Fatalf("InsertCheck cert: %v", err)
	}

	rec2, body2 := doJSON(t, mux, "GET", "/api/monitors/"+itoaSoul(id)+"/profile", "")
	if rec2.Code != http.StatusOK {
		t.Fatalf("got status %d, want 200", rec2.Code)
	}
	cd, ok := body2["cert_days_left"].(float64)
	if !ok {
		t.Fatalf("cert_days_left not a number: %#v", body2["cert_days_left"])
	}
	if cd != 30 {
		t.Fatalf("cert_days_left = %v, want 30", cd)
	}
}

func TestSoul_SetPublic_Validation(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-setpublic-val",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, _ := doJSON(t, mux, "PUT", "/api/monitors/999999/public", `{"is_public":1}`)
	if rec.Code != http.StatusNotFound {
		t.Errorf("not found: got %d, want 404", rec.Code)
	}

	rec2, _ := doJSON(t, mux, "PUT", "/api/monitors/"+itoaSoul(id)+"/public", `{`)
	if rec2.Code != http.StatusBadRequest {
		t.Errorf("bad body: got %d, want 400", rec2.Code)
	}

	rec3, _ := doJSON(t, mux, "PUT", "/api/monitors/"+itoaSoul(id)+"/public", `{"is_public":2}`)
	if rec3.Code != http.StatusBadRequest {
		t.Errorf("bad value: got %d, want 400", rec3.Code)
	}
}

func TestSoul_SetPublic_OK(t *testing.T) {
	srv, st := newTestServer(t)
	id, err := st.CreateMonitor(store.Monitor{
		Name:           "soul-setpublic-ok",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	mux := http.NewServeMux()
	srv.RegisterSoulRoutes(mux)

	rec, _ := doJSON(t, mux, "PUT", "/api/monitors/"+itoaSoul(id)+"/public", `{"is_public":1}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("set 1: got %d, want 200", rec.Code)
	}
	m1, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("GetMonitor: %v", err)
	}
	if m1.IsPublic != 1 {
		t.Fatalf("IsPublic = %d, want 1", m1.IsPublic)
	}

	rec2, _ := doJSON(t, mux, "PUT", "/api/monitors/"+itoaSoul(id)+"/public", `{"is_public":0}`)
	if rec2.Code != http.StatusOK {
		t.Fatalf("set 0: got %d, want 200", rec2.Code)
	}
	m2, err := st.GetMonitor(id)
	if err != nil {
		t.Fatalf("GetMonitor: %v", err)
	}
	if m2.IsPublic != 0 {
		t.Fatalf("IsPublic = %d, want 0", m2.IsPublic)
	}
}

func itoaSoul(id int64) string {
	if id == 0 {
		return "0"
	}
	neg := id < 0
	if neg {
		id = -id
	}
	var buf [20]byte
	i := len(buf)
	for id > 0 {
		i--
		buf[i] = byte('0' + id%10)
		id /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
