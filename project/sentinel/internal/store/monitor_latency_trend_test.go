package store

import (
	"testing"
	"time"
)

func TestMonitorLatencyTrendEmptyAndInvalid(t *testing.T) {
	s := newTestStore(t)
	mid := createNamedMonitor(t, s, "空监控", "https://example.com/empty")

	report, err := s.MonitorLatencyTrend(mid, 2024, 3, 3)
	if err != nil {
		t.Fatalf("MonitorLatencyTrend: %v", err)
	}
	if report.MonitorID != mid {
		t.Errorf("MonitorID = %d, want %d", report.MonitorID, mid)
	}
	if report.MonitorName != "空监控" {
		t.Errorf("MonitorName = %q, want %q", report.MonitorName, "空监控")
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
		t.Errorf("首月分位值 = P50 %v / P95 %v / P99 %v / Avg %v, want 全 0", first.P50Ms, first.P95Ms, first.P99Ms, first.AvgMs)
	}
	if first.TotalChecks != 0 {
		t.Errorf("TotalChecks = %d, want 0", first.TotalChecks)
	}

	if _, err := s.MonitorLatencyTrend(mid, 2024, 3, 0); err == nil {
		t.Errorf("MonitorLatencyTrend months=0 应报错")
	}
	if _, err := s.MonitorLatencyTrend(mid, 2024, 13, 3); err == nil {
		t.Errorf("MonitorLatencyTrend month=13 应报错")
	}
	if _, err := s.MonitorLatencyTrend(999999, 2024, 3, 3); err == nil {
		t.Errorf("MonitorLatencyTrend 不存在的监控应报错")
	}
	if _, err := s.MonitorMonthlyLatency(mid, 2024, 13); err == nil {
		t.Errorf("MonitorMonthlyLatency month=13 应报错")
	}
}

func TestMonitorMonthlyLatencyEmpty(t *testing.T) {
	s := newTestStore(t)
	mid := createNamedMonitor(t, s, "空监控2", "https://example.com/empty2")

	m, err := s.MonitorMonthlyLatency(mid, 2024, 5)
	if err != nil {
		t.Fatalf("MonitorMonthlyLatency: %v", err)
	}
	if m.Month != "2024-05" {
		t.Errorf("Month = %q, want %q", m.Month, "2024-05")
	}
	if m.MonitorID != mid {
		t.Errorf("MonitorID = %d, want %d", m.MonitorID, mid)
	}
	if m.MonitorName != "空监控2" {
		t.Errorf("MonitorName = %q, want %q", m.MonitorName, "空监控2")
	}
	if m.P50Ms != 0 || m.P95Ms != 0 || m.P99Ms != 0 || m.AvgMs != 0 {
		t.Errorf("分位值 = P50 %v / P95 %v / P99 %v / Avg %v, want 全 0", m.P50Ms, m.P95Ms, m.P99Ms, m.AvgMs)
	}
	if m.TotalChecks != 0 {
		t.Errorf("TotalChecks = %d, want 0", m.TotalChecks)
	}

	if _, err := s.MonitorMonthlyLatency(999999, 2024, 5); err == nil {
		t.Errorf("MonitorMonthlyLatency 不存在的监控应报错")
	}
}

func TestMonitorLatencyTrendTwoMonths(t *testing.T) {
	s := newTestStore(t)
	mid := createNamedMonitor(t, s, "趋势监控", "https://example.com/trend")

	feb := time.Date(2024, 2, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 2; i++ {
		insertCheckAt(t, s, mid, feb.Add(time.Duration(i)*time.Minute), 1, int64(100+100*i))
	}

	mar := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 3; i++ {
		insertCheckAt(t, s, mid, mar.Add(time.Duration(i)*time.Minute), 1, int64(300+100*i))
	}
	insertCheckAt(t, s, mid, mar.Add(3*time.Minute), 0, 9999)

	report, err := s.MonitorLatencyTrend(mid, 2024, 3, 2)
	if err != nil {
		t.Fatalf("MonitorLatencyTrend: %v", err)
	}
	if len(report.Items) != 2 {
		t.Fatalf("len(Items) = %d, want 2", len(report.Items))
	}

	febItem := report.Items[0]
	if febItem.Month != "2024-02" {
		t.Errorf("2月 Month = %q, want %q", febItem.Month, "2024-02")
	}
	if febItem.TotalChecks != 2 {
		t.Errorf("2月 TotalChecks = %d, want 2", febItem.TotalChecks)
	}
	if febItem.P50Ms != 150 {
		t.Errorf("2月 P50Ms = %v, want 150", febItem.P50Ms)
	}
	if febItem.P95Ms != 195 {
		t.Errorf("2月 P95Ms = %v, want 195", febItem.P95Ms)
	}
	if febItem.P99Ms != 199 {
		t.Errorf("2月 P99Ms = %v, want 199", febItem.P99Ms)
	}
	if febItem.AvgMs != 150 {
		t.Errorf("2月 AvgMs = %v, want 150", febItem.AvgMs)
	}

	marItem := report.Items[1]
	if marItem.Month != "2024-03" {
		t.Errorf("3月 Month = %q, want %q", marItem.Month, "2024-03")
	}
	if marItem.TotalChecks != 3 {
		t.Errorf("3月 TotalChecks = %d, want 3", marItem.TotalChecks)
	}
	if marItem.P50Ms != 400 {
		t.Errorf("3月 P50Ms = %v, want 400", marItem.P50Ms)
	}
	if marItem.P95Ms != 490 {
		t.Errorf("3月 P95Ms = %v, want 490", marItem.P95Ms)
	}
	if marItem.P99Ms != 498 {
		t.Errorf("3月 P99Ms = %v, want 498", marItem.P99Ms)
	}
	if marItem.AvgMs != 400 {
		t.Errorf("3月 AvgMs = %v, want 400", marItem.AvgMs)
	}
}
