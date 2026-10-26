package store

import (
	"testing"
	"time"
)

func TestMonitorYearlySLAEmpty(t *testing.T) {
	store := newTestStore(t)
	monitorID := seedMonitor(t, store)

	report, err := store.MonitorYearlySLA(monitorID, 2024)
	if err != nil {
		t.Fatalf("MonitorYearlySLA returned error: %v", err)
	}
	if report.Year != 2024 {
		t.Fatalf("Year = %d, want 2024", report.Year)
	}
	if report.Target != 99.9 {
		t.Fatalf("Target = %v, want 99.9", report.Target)
	}
	if len(report.Items) != 12 {
		t.Fatalf("len(Items) = %d, want 12", len(report.Items))
	}
	if report.Items[0].Month != "2024-01" {
		t.Fatalf("Items[0].Month = %q, want 2024-01", report.Items[0].Month)
	}
	if report.Items[11].Month != "2024-12" {
		t.Fatalf("Items[11].Month = %q, want 2024-12", report.Items[11].Month)
	}
	if report.Items[0].UptimePct != 100 {
		t.Fatalf("Items[0].UptimePct = %v, want 100", report.Items[0].UptimePct)
	}
	if report.TotalChecks != 0 {
		t.Fatalf("TotalChecks = %d, want 0", report.TotalChecks)
	}
	if report.UptimePct != 100 {
		t.Fatalf("UptimePct = %v, want 100", report.UptimePct)
	}
	if !report.Met {
		t.Fatalf("Met = false, want true")
	}
	if report.BestMonth != "2024-01" {
		t.Fatalf("BestMonth = %q, want 2024-01", report.BestMonth)
	}
	if report.WorstMonth != "2024-01" {
		t.Fatalf("WorstMonth = %q, want 2024-01", report.WorstMonth)
	}
	if report.MonitorName == "" {
		t.Fatalf("MonitorName is empty, want non-empty")
	}

	if _, err := store.MonitorYearlySLA(monitorID, 1969); err == nil {
		t.Fatalf("MonitorYearlySLA with year 1969: expected error, got nil")
	}
	if _, err := store.MonitorYearlySLA(monitorID, 10000); err == nil {
		t.Fatalf("MonitorYearlySLA with year 10000: expected error, got nil")
	}
	if _, err := store.MonitorYearlySLA(999999, 2024); err == nil {
		t.Fatalf("MonitorYearlySLA with missing monitor 999999: expected error, got nil")
	}
}

func TestMonitorYearlySLATwoMonths(t *testing.T) {
	store := newTestStore(t)
	mid := seedMonitor(t, store)

	for i := 0; i < 10; i++ {
		insertCheckAt(t, store, mid, time.Date(2024, 2, 5, 0, i, 0, 0, time.UTC), 1, 100)
	}
	for i := 0; i < 10; i++ {
		ok := 1
		if i == 9 {
			ok = 0
		}
		insertCheckAt(t, store, mid, time.Date(2024, 3, 5, 0, i, 0, 0, time.UTC), ok, 100)
	}

	report, err := store.MonitorYearlySLA(mid, 2024)
	if err != nil {
		t.Fatalf("MonitorYearlySLA returned error: %v", err)
	}
	if report.TotalChecks != 20 {
		t.Fatalf("TotalChecks = %d, want 20", report.TotalChecks)
	}
	if report.UptimePct != 95.0 {
		t.Fatalf("UptimePct = %v, want 95.0", report.UptimePct)
	}
	if len(report.Items) != 12 {
		t.Fatalf("len(Items) = %d, want 12", len(report.Items))
	}
	if report.Items[1].Month != "2024-02" {
		t.Fatalf("Items[1].Month = %q, want 2024-02", report.Items[1].Month)
	}
	if report.Items[1].UptimePct != 100.0 {
		t.Fatalf("Items[1].UptimePct = %v, want 100.0", report.Items[1].UptimePct)
	}
	if report.Items[2].Month != "2024-03" {
		t.Fatalf("Items[2].Month = %q, want 2024-03", report.Items[2].Month)
	}
	if report.Items[2].UptimePct != 90.0 {
		t.Fatalf("Items[2].UptimePct = %v, want 90.0", report.Items[2].UptimePct)
	}
	if report.BestMonth != "2024-02" {
		t.Fatalf("BestMonth = %q, want 2024-02", report.BestMonth)
	}
	if report.WorstMonth != "2024-03" {
		t.Fatalf("WorstMonth = %q, want 2024-03", report.WorstMonth)
	}
	if report.Met {
		t.Fatalf("Met = true, want false")
	}
}