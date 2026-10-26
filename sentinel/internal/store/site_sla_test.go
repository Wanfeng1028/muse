package store

import (
	"testing"
	"time"
)

func TestSiteMonthlySLAEmpty(t *testing.T) {
	s := newTestStore(t)
	rep, err := s.SiteMonthlySLA(2024, 3)
	if err != nil {
		t.Fatalf("SiteMonthlySLA: %v", err)
	}
	if rep.MonitorCount != 0 {
		t.Errorf("MonitorCount 期望 0，实际 %d", rep.MonitorCount)
	}
	if rep.TotalChecks != 0 {
		t.Errorf("TotalChecks 期望 0，实际 %d", rep.TotalChecks)
	}
	if rep.UptimePct != 100 {
		t.Errorf("UptimePct 期望 100，实际 %v", rep.UptimePct)
	}
	if !rep.Met {
		t.Errorf("Met 期望 true")
	}
	if len(rep.Monitors) != 0 {
		t.Errorf("Monitors 长度期望 0，实际 %d", len(rep.Monitors))
	}
	if _, err := s.SiteMonthlySLA(2024, 13); err == nil {
		t.Errorf("非法月份期望错误")
	}
}
func TestSiteMonthlySLAWeighted(t *testing.T) {
	s := newTestStore(t)
	aID := seedMonitor(t, s)
	bID := seedMonitor(t, s)
	baseA := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 100; i++ {
		ok := 1
		if i >= 90 {
			ok = 0
		}
		insertCheckAt(t, s, aID, baseA.Add(time.Duration(i)*time.Minute), ok, 100)
	}
	baseB := time.Date(2024, 3, 6, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 100; i++ {
		insertCheckAt(t, s, bID, baseB.Add(time.Duration(i)*time.Minute), 1, 100)
	}
	rep, err := s.SiteMonthlySLA(2024, 3)
	if err != nil {
		t.Fatalf("SiteMonthlySLA: %v", err)
	}
	if rep.MonitorCount != 2 {
		t.Errorf("MonitorCount 期望 2，实际 %d", rep.MonitorCount)
	}
	if rep.TotalChecks != 200 {
		t.Errorf("TotalChecks 期望 200，实际 %d", rep.TotalChecks)
	}
	if rep.UptimePct < 94.99 || rep.UptimePct > 95.01 {
		t.Errorf("UptimePct 期望 95，实际 %v", rep.UptimePct)
	}
	if rep.WorstMonitorID != aID {
		t.Errorf("WorstMonitorID 期望 %d，实际 %d", aID, rep.WorstMonitorID)
	}
	if rep.DownIncidents != 0 {
		t.Errorf("DownIncidents 期望 0，实际 %d", rep.DownIncidents)
	}
}
