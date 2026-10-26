package store

import (
	"testing"
	"time"
)

func TestGroupMonthlySLAEmptyAndNotFound(t *testing.T) {
	s := newTestStore(t)
	gid, err := s.CreateGroup("空组")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	rep, err := s.GroupMonthlySLA(gid, 2024, 3)
	if err != nil {
		t.Fatalf("GroupMonthlySLA: %v", err)
	}
	if rep.GroupID != gid {
		t.Errorf("GroupID = %d, want %d", rep.GroupID, gid)
	}
	if rep.GroupName != "空组" {
		t.Errorf("GroupName = %q, want 空组", rep.GroupName)
	}
	if rep.MonitorCount != 0 {
		t.Errorf("MonitorCount = %d, want 0", rep.MonitorCount)
	}
	if rep.TotalChecks != 0 {
		t.Errorf("TotalChecks = %d, want 0", rep.TotalChecks)
	}
	if rep.UptimePct != 100 {
		t.Errorf("UptimePct = %v, want 100", rep.UptimePct)
	}
	if !rep.Met {
		t.Errorf("Met = false, want true")
	}
	if len(rep.Monitors) != 0 {
		t.Errorf("len(Monitors) = %d, want 0", len(rep.Monitors))
	}
	if _, err := s.GroupMonthlySLA(999999, 2024, 3); err == nil {
		t.Errorf("不存在的分组期望错误")
	}
	if _, err := s.GroupMonthlySLA(gid, 2024, 13); err == nil {
		t.Errorf("非法月份期望错误")
	}
}

func TestGroupMonthlySLAWeightedAndIsolated(t *testing.T) {
	s := newTestStore(t)
	aID := seedMonitor(t, s)
	bID := seedMonitor(t, s)
	cID := seedMonitor(t, s)
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
	baseC := time.Date(2024, 3, 7, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 100; i++ {
		insertCheckAt(t, s, cID, baseC.Add(time.Duration(i)*time.Minute), 0, 100)
	}
	gid, err := s.CreateGroup("组A")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	if err := s.AddMonitorToGroup(gid, aID); err != nil {
		t.Fatalf("AddMonitorToGroup a: %v", err)
	}
	if err := s.AddMonitorToGroup(gid, bID); err != nil {
		t.Fatalf("AddMonitorToGroup b: %v", err)
	}
	rep, err := s.GroupMonthlySLA(gid, 2024, 3)
	if err != nil {
		t.Fatalf("GroupMonthlySLA: %v", err)
	}
	if rep.MonitorCount != 2 || rep.TotalChecks != 200 || len(rep.Monitors) != 2 {
		t.Errorf("counts: MonitorCount=%d TotalChecks=%d Monitors=%d", rep.MonitorCount, rep.TotalChecks, len(rep.Monitors))
	}
	if rep.UptimePct < 94.99 || rep.UptimePct > 95.01 {
		t.Errorf("UptimePct = %v, want ~95", rep.UptimePct)
	}
	if rep.WorstMonitorID != aID {
		t.Errorf("WorstMonitorID = %d, want %d", rep.WorstMonitorID, aID)
	}
	if rep.Met {
		t.Errorf("Met = true, want false")
	}
}
