package store

import (
	"database/sql"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

func newSLATestStore(t *testing.T) *Store {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	if _, err := db.Exec(`CREATE TABLE checks (id INTEGER PRIMARY KEY AUTOINCREMENT, monitor_id INTEGER NOT NULL, ok INTEGER NOT NULL, latency_ms INTEGER NOT NULL, checked_at TEXT NOT NULL)`); err != nil {
		t.Fatalf("create checks: %v", err)
	}
	if _, err := db.Exec(`CREATE TABLE incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, monitor_id INTEGER NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, downtime_sec INTEGER)`); err != nil {
		t.Fatalf("create incidents: %v", err)
	}
	return &Store{db: db}
}

func insertClosedIncident(t *testing.T, s *Store, monitorID int64, startedAt string, downtimeSec int64) {
	t.Helper()
	endedAt := time.Now().UTC().Format(time.RFC3339)
	if _, err := s.db.Exec(
		`INSERT INTO incidents (monitor_id, started_at, ended_at, downtime_sec) VALUES (?, ?, ?, ?)`,
		monitorID, startedAt, endedAt, downtimeSec,
	); err != nil {
		t.Fatalf("insert closed incident: %v", err)
	}
}

func insertOpenIncident(t *testing.T, s *Store, monitorID int64, startedAt string) {
	t.Helper()
	if _, err := s.db.Exec(
		`INSERT INTO incidents (monitor_id, started_at, ended_at, downtime_sec) VALUES (?, ?, NULL, NULL)`,
		monitorID, startedAt,
	); err != nil {
		t.Fatalf("insert open incident: %v", err)
	}
}

func TestMonthlySLA_MTTRAndSeverity(t *testing.T) {
	s := newSLATestStore(t)
	const monitorID = 1

	// 未关闭事件必须落在查询月份内：以其 started_at 所在月份为查询月份。
	openStartTime := time.Now().UTC().Add(-10 * time.Minute)
	year, month := openStartTime.Year(), int(openStartTime.Month())
	monStr := openStartTime.Format("2006-01")

	insertClosedIncident(t, s, monitorID, monStr+"-02T01:00:00Z", 100)
	insertClosedIncident(t, s, monitorID, monStr+"-05T02:00:00Z", 500)
	insertClosedIncident(t, s, monitorID, monStr+"-10T03:00:00Z", 2000)
	insertOpenIncident(t, s, monitorID, openStartTime.Format(time.RFC3339))

	report, err := s.MonthlySLA(monitorID, year, month)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}

	wantMTTR := 2600.0 / 3.0
	if diff := report.MTTRSec - wantMTTR; diff < -1e-6 || diff > 1e-6 {
		t.Fatalf("MTTRSec = %v, want %v", report.MTTRSec, wantMTTR)
	}

	wantSeverity := SeverityCounts{P1: 1, P2: 2, P3: 1}
	if report.Severity != wantSeverity {
		t.Fatalf("Severity = %+v, want %+v", report.Severity, wantSeverity)
	}

	if report.OpenIncidents != 1 {
		t.Fatalf("OpenIncidents = %d, want 1", report.OpenIncidents)
	}
	if report.DownIncidents != 4 {
		t.Fatalf("DownIncidents = %d, want 4", report.DownIncidents)
	}
}

func TestMonthlySLA_NoIncidents(t *testing.T) {
	s := newSLATestStore(t)
	report, err := s.MonthlySLA(1, 2024, 6)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}
	if report.MTTRSec != 0 {
		t.Fatalf("MTTRSec = %v, want 0", report.MTTRSec)
	}
	if report.Severity != (SeverityCounts{}) {
		t.Fatalf("Severity = %+v, want zero", report.Severity)
	}
	if report.OpenIncidents != 0 {
		t.Fatalf("OpenIncidents = %d, want 0", report.OpenIncidents)
	}
}

func TestMonthlySLA_InvalidMonthStillErrors(t *testing.T) {
	s := newSLATestStore(t)
	if _, err := s.MonthlySLA(1, 2024, 13); err == nil {
		t.Fatalf("MonthlySLA(2024, 13) expected error, got nil")
	}
}
