package store

import (
	"testing"
	"time"
)

func TestSiteLatencyTrendEmpty(t *testing.T) {
	store := newTestStore(t)

	report, err := store.SiteLatencyTrend(2024, 3, 3)
	if err != nil {
		t.Fatalf("SiteLatencyTrend() error = %v, want nil", err)
	}

	if report.EndMonth != "2024-03" {
		t.Errorf("EndMonth = %q, want %q", report.EndMonth, "2024-03")
	}
	if report.Months != 3 {
		t.Errorf("Months = %d, want 3", report.Months)
	}
	if len(report.Items) != 3 {
		t.Fatalf("len(Items) = %d, want 3", len(report.Items))
	}
	if report.Items[0].Month != "2024-01" {
		t.Errorf("Items[0].Month = %q, want %q", report.Items[0].Month, "2024-01")
	}
	if report.Items[2].Month != "2024-03" {
		t.Errorf("Items[2].Month = %q, want %q", report.Items[2].Month, "2024-03")
	}

	first := report.Items[0]
	if first.P50Ms != 0 || first.P95Ms != 0 || first.P99Ms != 0 || first.AvgMs != 0 {
		t.Errorf("Items[0] latencies = (P50=%v, P95=%v, P99=%v, Avg=%v), want all 0",
			first.P50Ms, first.P95Ms, first.P99Ms, first.AvgMs)
	}
	if first.TotalChecks != 0 {
		t.Errorf("Items[0].TotalChecks = %d, want 0", first.TotalChecks)
	}
	if first.MonitorCount != 0 {
		t.Errorf("Items[0].MonitorCount = %d, want 0", first.MonitorCount)
	}
	if first.SlowestMonitorName != "" {
		t.Errorf("Items[0].SlowestMonitorName = %q, want empty", first.SlowestMonitorName)
	}
}

func TestSiteLatencyTrendInvalid(t *testing.T) {
	store := newTestStore(t)

	if _, err := store.SiteLatencyTrend(2024, 3, 0); err == nil {
		t.Error("SiteLatencyTrend(2024, 3, 0) error = nil, want error")
	}
	if _, err := store.SiteLatencyTrend(2024, 3, 13); err == nil {
		t.Error("SiteLatencyTrend(2024, 3, 13) error = nil, want error")
	}
	if _, err := store.SiteLatencyTrend(2024, 13, 3); err == nil {
		t.Error("SiteLatencyTrend(2024, 13, 3) error = nil, want error")
	}

	if _, err := store.SiteMonthlyLatency(2024, 13); err == nil {
		t.Error("SiteMonthlyLatency(2024, 13) error = nil, want error")
	}
	if _, err := store.SiteMonthlyLatency(2024, 0); err == nil {
		t.Error("SiteMonthlyLatency(2024, 0) error = nil, want error")
	}
}

func TestSiteLatencyTrendTwoMonths(t *testing.T) {
	s := newTestStore(t)
	aID := seedMonitor(t, s)
	bID := seedMonitor(t, s)

	febBase := time.Date(2024, 2, 5, 10, 0, 0, 0, time.UTC)
	for i, lat := range []int64{100, 200} {
		insertCheckAt(t, s, aID, febBase.Add(time.Duration(i)*time.Minute), 1, lat)
	}
	for i := 0; i < 2; i++ {
		insertCheckAt(t, s, bID, febBase.Add(time.Duration(i)*time.Minute), 1, 1000)
	}

	marBase := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i, lat := range []int64{300, 400, 500} {
		insertCheckAt(t, s, aID, marBase.Add(time.Duration(i)*time.Minute), 1, lat)
	}
	insertCheckAt(t, s, aID, marBase.Add(3*time.Minute), 0, 9999)

	report, err := s.SiteLatencyTrend(2024, 3, 2)
	if err != nil {
		t.Fatalf("SiteLatencyTrend returned error: %v", err)
	}
	if len(report.Items) != 2 {
		t.Fatalf("SiteLatencyTrend: got %d items, want 2", len(report.Items))
		return
	}

	feb := report.Items[0]
	if feb.Month != "2024-02" {
		t.Errorf("Items[0].Month = %q, want %q", feb.Month, "2024-02")
	}
	if feb.TotalChecks != 4 {
		t.Errorf("Items[0].TotalChecks = %d, want 4", feb.TotalChecks)
	}
	if feb.P50Ms != 600 {
		t.Errorf("Items[0].P50Ms = %v, want 600", feb.P50Ms)
	}
	if feb.P95Ms != 1000 {
		t.Errorf("Items[0].P95Ms = %v, want 1000", feb.P95Ms)
	}
	if feb.P99Ms != 1000 {
		t.Errorf("Items[0].P99Ms = %v, want 1000", feb.P99Ms)
	}
	if feb.AvgMs != 575 {
		t.Errorf("Items[0].AvgMs = %v, want 575", feb.AvgMs)
	}
	if feb.MonitorCount != 2 {
		t.Errorf("Items[0].MonitorCount = %d, want 2", feb.MonitorCount)
	}
	if feb.SlowestMonitorName == "" {
		t.Errorf("Items[0].SlowestMonitorName is empty, want non-empty")
	}

	mar := report.Items[1]
	if mar.Month != "2024-03" {
		t.Errorf("Items[1].Month = %q, want %q", mar.Month, "2024-03")
	}
	if mar.TotalChecks != 3 {
		t.Errorf("Items[1].TotalChecks = %d, want 3 (failed check must be excluded)", mar.TotalChecks)
	}
	if mar.P50Ms != 400 {
		t.Errorf("Items[1].P50Ms = %v, want 400", mar.P50Ms)
	}
	if mar.P95Ms != 490 {
		t.Errorf("Items[1].P95Ms = %v, want 490", mar.P95Ms)
	}
	if mar.P99Ms != 498 {
		t.Errorf("Items[1].P99Ms = %v, want 498", mar.P99Ms)
	}
	if mar.AvgMs != 400 {
		t.Errorf("Items[1].AvgMs = %v, want 400", mar.AvgMs)
	}
}
