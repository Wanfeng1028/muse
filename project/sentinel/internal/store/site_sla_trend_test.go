package store

import (
	"testing"
	"time"
)

func TestSiteSLATrendEmpty(t *testing.T) {
	store := newTestStore(t)

	report, err := store.SiteSLATrend(2024, 3, 3)
	if err != nil {
		t.Fatalf("SiteSLATrend(2024, 3, 3) 返回错误: %v", err)
	}
	if report.EndMonth != "2024-03" {
		t.Errorf("EndMonth = %q, 期望 %q", report.EndMonth, "2024-03")
	}
	if report.Months != 3 {
		t.Errorf("Months = %d, 期望 3", report.Months)
	}
	if report.Target != 99.9 {
		t.Errorf("Target = %v, 期望 99.9", report.Target)
	}
	if len(report.Items) != 3 {
		t.Errorf("len(Items) = %d, 期望 3", len(report.Items))
	}
	if len(report.Items) > 0 {
		if report.Items[0].Month != "2024-01" {
			t.Errorf("Items[0].Month = %q, 期望 %q", report.Items[0].Month, "2024-01")
		}
		if len(report.Items) > 2 && report.Items[2].Month != "2024-03" {
			t.Errorf("Items[2].Month = %q, 期望 %q", report.Items[2].Month, "2024-03")
		}
		if report.Items[0].UptimePct != 100 {
			t.Errorf("Items[0].UptimePct = %v, 期望 100", report.Items[0].UptimePct)
		}
	}

	if _, err := store.SiteSLATrend(2024, 3, 0); err == nil {
		t.Errorf("SiteSLATrend(2024, 3, 0) 期望返回错误, 实际为 nil")
	}
	if _, err := store.SiteSLATrend(2024, 13, 3); err == nil {
		t.Errorf("SiteSLATrend(2024, 13, 3) 期望返回错误, 实际为 nil")
	}
}

func TestSiteSLATrendTwoMonths(t *testing.T) {
	s := newTestStore(t)
	monitorID := seedMonitor(t, s)

	baseFeb := time.Date(2024, 2, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 10; i++ {
		insertCheckAt(t, s, monitorID, baseFeb.Add(time.Duration(i)*time.Minute), 1, 100)
	}

	baseMar := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 10; i++ {
		ok := 1
		if i == 9 {
			ok = 0
		}
		insertCheckAt(t, s, monitorID, baseMar.Add(time.Duration(i)*time.Minute), ok, 100)
	}

	report, err := s.SiteSLATrend(2024, 3, 2)
	if err != nil {
		t.Fatalf("SiteSLATrend() error = %v", err)
	}

	if len(report.Items) != 2 {
		t.Errorf("len(Items) = %d, want 2", len(report.Items))
		return
	}

	if report.Items[0].Month != "2024-02" {
		t.Errorf("Items[0].Month = %q, want %q", report.Items[0].Month, "2024-02")
	}
	if report.Items[0].TotalChecks != 10 {
		t.Errorf("Items[0].TotalChecks = %d, want 10", report.Items[0].TotalChecks)
	}

	if report.Items[1].Month != "2024-03" {
		t.Errorf("Items[1].Month = %q, want %q", report.Items[1].Month, "2024-03")
	}
	if report.Items[1].UptimePct < 89.99 || report.Items[1].UptimePct > 90.01 {
		t.Errorf("Items[1].UptimePct = %v, want around 90", report.Items[1].UptimePct)
	}
}
