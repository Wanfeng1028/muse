package store

import (
	"testing"
	"time"
)

func TestMonitorSLATrendEmptyAndInvalid(t *testing.T) {
	s := newTestStore(t)
	mid := seedMonitor(t, s)

	rep, err := s.MonitorSLATrend(mid, 2024, 3, 3)
	if err != nil {
		t.Fatalf("MonitorSLATrend() error = %v", err)
	}
	if rep.MonitorID != mid || rep.MonitorName != "test-mon" {
		t.Errorf("got MonitorID=%d MonitorName=%q, want %d test-mon", rep.MonitorID, rep.MonitorName, mid)
	}
	if rep.EndMonth != "2024-03" || rep.Months != 3 || rep.SLATarget != 99.9 {
		t.Errorf("got EndMonth=%q Months=%d SLATarget=%v, want 2024-03 3 99.9", rep.EndMonth, rep.Months, rep.SLATarget)
	}
	if len(rep.Items) != 3 {
		t.Fatalf("len(Items) = %d, want 3", len(rep.Items))
	}
	if rep.Items[0].Month != "2024-01" || rep.Items[0].UptimePct != 100 {
		t.Errorf("Items[0] = %+v, want Month 2024-01 UptimePct 100", rep.Items[0])
	}
	if rep.Items[2].Month != "2024-03" {
		t.Errorf("Items[2].Month = %q, want %q", rep.Items[2].Month, "2024-03")
	}

	if _, err := s.MonitorSLATrend(mid, 2024, 3, 0); err == nil {
		t.Error("months=0: expected error, got nil")
	}
	if _, err := s.MonitorSLATrend(mid, 2024, 13, 3); err == nil {
		t.Error("endMonth=13: expected error, got nil")
	}
	if _, err := s.MonitorSLATrend(999999, 2024, 3, 3); err == nil {
		t.Error("nonexistent monitor 999999: expected error, got nil")
	}
}
func TestMonitorSLATrendTwoMonths(t *testing.T) {
	s := newTestStore(t)
	mid := seedMonitor(t, s)

	feb := time.Date(2024, 2, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 10; i++ {
		insertCheckAt(t, s, mid, feb.Add(time.Duration(i)*time.Minute), 1, 100)
	}

	mar := time.Date(2024, 3, 5, 10, 0, 0, 0, time.UTC)
	for i := 0; i < 10; i++ {
		ok := 1
		if i == 9 {
			ok = 0
		}
		insertCheckAt(t, s, mid, mar.Add(time.Duration(i)*time.Minute), ok, 100)
	}

	rep, err := s.MonitorSLATrend(mid, 2024, 3, 2)
	if err != nil {
		t.Fatalf("MonitorSLATrend returned error: %v", err)
	}
	if len(rep.Items) != 2 {
		t.Fatalf("len(Items) = %d, want 2", len(rep.Items))
	}
	if rep.Items[0].Month != "2024-02" || rep.Items[0].TotalChecks != 10 {
		t.Fatalf("Items[0] = %+v, want Month 2024-02 with TotalChecks 10", rep.Items[0])
	}
	if rep.Items[1].Month != "2024-03" || rep.Items[1].TotalChecks != 10 {
		t.Fatalf("Items[1] = %+v, want Month 2024-03 with TotalChecks 10", rep.Items[1])
	}
	if rep.Items[1].UptimePct < 89.99 || rep.Items[1].UptimePct > 90.01 {
		t.Fatalf("Items[1].UptimePct = %v, want around 90", rep.Items[1].UptimePct)
	}
}
