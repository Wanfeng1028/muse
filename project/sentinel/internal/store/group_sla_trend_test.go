package store

import (
	"testing"
	"time"
)

func TestGroupSLATrendEmptyAndInvalid(t *testing.T) {
	s := newTestStore(t)
	gid, err := s.CreateGroup("空组")
	if err != nil {
		t.Fatalf("CreateGroup failed: %v", err)
	}
	rep, err := s.GroupSLATrend(gid, 2024, 3, 3)
	if err != nil {
		t.Fatalf("GroupSLATrend failed: %v", err)
	}
	if rep.GroupID != gid || rep.GroupName != "空组" || rep.EndMonth != "2024-03" || rep.Months != 3 || rep.Target != 99.9 {
		t.Errorf("unexpected report: %+v", rep)
	}
	if len(rep.Items) != 3 {
		t.Errorf("Items len = %d, want 3", len(rep.Items))
	}
	if len(rep.Items) > 0 && (rep.Items[0].Month != "2024-01" || rep.Items[0].UptimePct != 100 || rep.Items[0].MonitorCount != 0) {
		t.Errorf("unexpected Items[0]: %+v", rep.Items[0])
	}
	if len(rep.Items) > 2 && rep.Items[2].Month != "2024-03" {
		t.Errorf("Items[2].Month = %q, want 2024-03", rep.Items[2].Month)
	}
	if _, err := s.GroupSLATrend(gid, 2024, 3, 0); err == nil {
		t.Errorf("months=0 want error")
	}
	if _, err := s.GroupSLATrend(gid, 2024, 13, 3); err == nil {
		t.Errorf("endMonth=13 want error")
	}
	if _, err := s.GroupSLATrend(999999, 2024, 3, 3); err == nil {
		t.Errorf("nonexistent group want error")
	}
}
func TestGroupSLATrendTwoMonths(t *testing.T) {
	s := newTestStore(t)
	aID := seedMonitor(t, s)
	baseFeb := time.Date(2024, 2, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 10; i++ {
		insertCheckAt(t, s, aID, baseFeb.Add(time.Duration(i)*time.Minute), 1, 100)
	}
	baseMar := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 10; i++ {
		ok := 1
		if i == 9 {
			ok = 0
		}
		insertCheckAt(t, s, aID, baseMar.Add(time.Duration(i)*time.Minute), ok, 100)
	}
	gid, err := s.CreateGroup("组A")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	if err := s.AddMonitorToGroup(gid, aID); err != nil {
		t.Fatalf("AddMonitorToGroup: %v", err)
	}
	rep, err := s.GroupSLATrend(gid, 2024, 3, 2)
	if err != nil {
		t.Fatalf("GroupSLATrend: %v", err)
	}
	if len(rep.Items) != 2 {
		t.Errorf("len=%d want 2", len(rep.Items))
		return
	}
	if rep.Items[0].Month != "2024-02" || rep.Items[0].TotalChecks != 10 {
		t.Errorf("Feb %+v", rep.Items[0])
	}
	if rep.Items[1].Month != "2024-03" || rep.Items[1].TotalChecks != 10 {
		t.Errorf("Mar %+v", rep.Items[1])
	}
	if rep.Items[1].UptimePct < 89.99 || rep.Items[1].UptimePct > 90.01 {
		t.Errorf("Mar uptime=%v want 90", rep.Items[1].UptimePct)
	}
}
