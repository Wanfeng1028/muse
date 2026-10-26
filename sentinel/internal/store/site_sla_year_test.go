package store

import (
	"testing"
	"time"
)

func TestSiteYearlySLAEmpty(t *testing.T) {
	store := newTestStore(t)
	report, err := store.SiteYearlySLA(2024)
	if err != nil {
		t.Fatalf("SiteYearlySLA(2024) returned error: %v", err)
	}
	if report.Year != 2024 {
		t.Errorf("Year = %d, want 2024", report.Year)
	}
	if report.Target != 99.9 {
		t.Errorf("Target = %v, want 99.9", report.Target)
	}
	if len(report.Items) != 12 {
		t.Errorf("len(Items) = %d, want 12", len(report.Items))
		return
	}
	if report.Items[0].Month != "2024-01" {
		t.Errorf("Items[0].Month = %v, want 2024-01", report.Items[0].Month)
	}
	if report.Items[11].Month != "2024-12" {
		t.Errorf("Items[11].Month = %v, want 2024-12", report.Items[11].Month)
	}
	if report.Items[0].UptimePct != 100 {
		t.Errorf("Items[0].UptimePct = %v, want 100", report.Items[0].UptimePct)
	}
	if report.TotalChecks != 0 {
		t.Errorf("TotalChecks = %d, want 0", report.TotalChecks)
	}
	if report.UptimePct != 100 {
		t.Errorf("UptimePct = %v, want 100", report.UptimePct)
	}
	if !report.Met {
		t.Errorf("Met = false, want true")
	}
	if report.BestMonth != "2024-01" {
		t.Errorf("BestMonth = %v, want 2024-01", report.BestMonth)
	}
	if report.WorstMonth != "2024-01" {
		t.Errorf("WorstMonth = %v, want 2024-01", report.WorstMonth)
	}
	for _, year := range []int{1969, 10000} {
		if _, err := store.SiteYearlySLA(year); err == nil {
			t.Errorf("SiteYearlySLA(%d) expected error, got nil", year)
		}
	}
}

func TestSiteYearlySLATwoMonths(t *testing.T) {
	store := newTestStore(t)
	monitorID := seedMonitor(t, store)

	for i := 0; i < 10; i++ {
		insertCheckAt(t, store, monitorID, time.Date(2024, 2, 5, 0, i, 0, 0, time.UTC), 1, 100)
	}
	for i := 0; i < 10; i++ {
		ok := 1
		if i == 9 {
			ok = 0
		}
		insertCheckAt(t, store, monitorID, time.Date(2024, 3, 5, 0, i, 0, 0, time.UTC), ok, 100)
	}

	sla, err := store.SiteYearlySLA(2024)
	if err != nil {
		t.Fatalf("SiteYearlySLA(2024): %v", err)
	}

	if sla.TotalChecks != 20 {
		t.Errorf("TotalChecks = %d, want 20", sla.TotalChecks)
	}
	if sla.UptimePct != 95.0 {
		t.Errorf("UptimePct = %v, want 95", sla.UptimePct)
	}
	if len(sla.Items) != 12 {
		t.Errorf("len(Items) = %d, want 12", len(sla.Items))
		return
	}
	if sla.Items[1].Month != "2024-02" || sla.Items[1].UptimePct != 100.0 {
		t.Errorf("Items[1] = {%s %v}, want {2024-02 100}", sla.Items[1].Month, sla.Items[1].UptimePct)
	}
	if sla.Items[2].Month != "2024-03" || sla.Items[2].UptimePct != 90.0 {
		t.Errorf("Items[2] = {%s %v}, want {2024-03 90}", sla.Items[2].Month, sla.Items[2].UptimePct)
	}
	if sla.BestMonth != "2024-02" {
		t.Errorf("BestMonth = %q, want %q", sla.BestMonth, "2024-02")
	}
	if sla.WorstMonth != "2024-03" {
		t.Errorf("WorstMonth = %q, want %q", sla.WorstMonth, "2024-03")
	}
	if sla.Met {
		t.Errorf("Met = true, want false")
	}
}
