package store

import (
	"testing"
	"time"
)

func createNamedMonitor(t *testing.T, s *Store, name, target string) int64 {
	t.Helper()
	id, err := s.CreateMonitor(Monitor{Name: name, Kind: "http", Target: target, Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1, IsPublic: 1})
	if err != nil {
		t.Fatalf("创建监控 %s: %v", name, err)
	}
	return id
}

func TestGroupLatencyTrendEmptyAndInvalid(t *testing.T) {
	s := newTestStore(t)
	gid, err := s.CreateGroup("空组")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}

	report, err := s.GroupLatencyTrend(gid, 2024, 3, 3)
	if err != nil {
		t.Fatalf("GroupLatencyTrend: %v", err)
	}
	if report.GroupID != gid {
		t.Errorf("GroupID = %d, want %d", report.GroupID, gid)
	}
	if report.GroupName != "空组" {
		t.Errorf("GroupName = %q, want %q", report.GroupName, "空组")
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
	if first.MonitorCount != 0 {
		t.Errorf("MonitorCount = %d, want 0", first.MonitorCount)
	}
	if first.SlowestMonitorName != "" {
		t.Errorf("SlowestMonitorName = %q, want 空串", first.SlowestMonitorName)
	}

	if _, err := s.GroupLatencyTrend(gid, 2024, 3, 0); err == nil {
		t.Errorf("GroupLatencyTrend months=0 应报错")
	}
	if _, err := s.GroupLatencyTrend(gid, 2024, 13, 3); err == nil {
		t.Errorf("GroupLatencyTrend month=13 应报错")
	}
	if _, err := s.GroupLatencyTrend(999999, 2024, 3, 3); err == nil {
		t.Errorf("GroupLatencyTrend 不存在的分组应报错")
	}
	if _, err := s.GroupMonthlyLatency(gid, 2024, 13); err == nil {
		t.Errorf("GroupMonthlyLatency month=13 应报错")
	}
}

func TestGroupLatencyTrendTwoMonths(t *testing.T) {
	s := newTestStore(t)
	gid, err := s.CreateGroup("核心")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	fastID := createNamedMonitor(t, s, "组内快", "https://example.com/fast")
	slowID := createNamedMonitor(t, s, "组内慢", "https://example.com/slow")
	outID := createNamedMonitor(t, s, "组外", "https://example.com/outside")
	if err := s.AddMonitorToGroup(gid, fastID); err != nil {
		t.Fatalf("AddMonitorToGroup 组内快: %v", err)
	}
	if err := s.AddMonitorToGroup(gid, slowID); err != nil {
		t.Fatalf("AddMonitorToGroup 组内慢: %v", err)
	}

	feb := time.Date(2024, 2, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 2; i++ {
		at := feb.Add(time.Duration(i) * time.Minute)
		insertCheckAt(t, s, fastID, at, 1, int64(100+100*i))
		insertCheckAt(t, s, slowID, at, 1, 1000)
		insertCheckAt(t, s, outID, at, 1, 5000)
	}

	mar := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 3; i++ {
		insertCheckAt(t, s, fastID, mar.Add(time.Duration(i)*time.Minute), 1, int64(300+100*i))
	}
	insertCheckAt(t, s, fastID, mar.Add(3*time.Minute), 0, 9999)

	report, err := s.GroupLatencyTrend(gid, 2024, 3, 2)
	if err != nil {
		t.Fatalf("GroupLatencyTrend: %v", err)
	}
	if report.GroupID != gid {
		t.Errorf("GroupID = %d, want %d", report.GroupID, gid)
	}
	if report.GroupName != "核心" {
		t.Errorf("GroupName = %q, want %q", report.GroupName, "核心")
	}
	if len(report.Items) != 2 {
		t.Fatalf("len(Items) = %d, want 2", len(report.Items))
	}

	febItem := report.Items[0]
	if febItem.Month != "2024-02" {
		t.Errorf("2月 Month = %q, want %q", febItem.Month, "2024-02")
	}
	if febItem.TotalChecks != 4 {
		t.Errorf("2月 TotalChecks = %d, want 4", febItem.TotalChecks)
	}
	if febItem.P50Ms != 600 {
		t.Errorf("2月 P50Ms = %v, want 600", febItem.P50Ms)
	}
	if febItem.P95Ms != 1000 {
		t.Errorf("2月 P95Ms = %v, want 1000", febItem.P95Ms)
	}
	if febItem.P99Ms != 1000 {
		t.Errorf("2月 P99Ms = %v, want 1000", febItem.P99Ms)
	}
	if febItem.AvgMs != 575 {
		t.Errorf("2月 AvgMs = %v, want 575", febItem.AvgMs)
	}
	if febItem.MonitorCount != 2 {
		t.Errorf("2月 MonitorCount = %d, want 2", febItem.MonitorCount)
	}
	if febItem.SlowestMonitorName != "组内慢" {
		t.Errorf("2月 SlowestMonitorName = %q, want %q", febItem.SlowestMonitorName, "组内慢")
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
	if marItem.MonitorCount != 2 {
		t.Errorf("3月 MonitorCount = %d, want 2", marItem.MonitorCount)
	}
	if marItem.SlowestMonitorName != "组内快" {
		t.Errorf("3月 SlowestMonitorName = %q, want %q", marItem.SlowestMonitorName, "组内快")
	}
}

func TestGroupMonthlyLatencyEmpty(t *testing.T) {
	s := newTestStore(t)
	gid, err := s.CreateGroup("空组2")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}

	m, err := s.GroupMonthlyLatency(gid, 2024, 5)
	if err != nil {
		t.Fatalf("GroupMonthlyLatency: %v", err)
	}
	if m.Month != "2024-05" {
		t.Errorf("Month = %q, want %q", m.Month, "2024-05")
	}
	if m.GroupID != gid {
		t.Errorf("GroupID = %d, want %d", m.GroupID, gid)
	}
	if m.GroupName != "空组2" {
		t.Errorf("GroupName = %q, want %q", m.GroupName, "空组2")
	}
	if m.P50Ms != 0 || m.P95Ms != 0 || m.P99Ms != 0 || m.AvgMs != 0 {
		t.Errorf("分位值 = P50 %v / P95 %v / P99 %v / Avg %v, want 全 0", m.P50Ms, m.P95Ms, m.P99Ms, m.AvgMs)
	}
	if m.TotalChecks != 0 {
		t.Errorf("TotalChecks = %d, want 0", m.TotalChecks)
	}
	if m.MonitorCount != 0 {
		t.Errorf("MonitorCount = %d, want 0", m.MonitorCount)
	}
	if m.SlowestMonitorName != "" {
		t.Errorf("SlowestMonitorName = %q, want 空串", m.SlowestMonitorName)
	}

	if _, err := s.GroupMonthlyLatency(999999, 2024, 5); err == nil {
		t.Errorf("GroupMonthlyLatency 不存在的分组应报错")
	}
}
