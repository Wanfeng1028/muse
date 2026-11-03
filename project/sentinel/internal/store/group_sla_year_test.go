package store

import (
	"testing"
	"time"
)

func TestGroupYearlySLAEmpty(t *testing.T) {
	store := newTestStore(t)
	gid, err := store.CreateGroup("组A")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	rep, err := store.GroupYearlySLA(gid, 2024)
	if err != nil {
		t.Fatalf("GroupYearlySLA: %v", err)
	}
	if rep.Year != 2024 || rep.Target != 99.9 {
		t.Errorf("Year/Target = %v/%v, want 2024/99.9", rep.Year, rep.Target)
	}
	if len(rep.Items) != 12 {
		t.Fatalf("len(Items) = %d, want 12", len(rep.Items))
	}
	if rep.Items[0].Month != "2024-01" || rep.Items[11].Month != "2024-12" {
		t.Errorf("Months = %s..%s, want 2024-01..2024-12", rep.Items[0].Month, rep.Items[11].Month)
	}
	if rep.Items[0].UptimePct != 100 || rep.TotalChecks != 0 || rep.UptimePct != 100 || !rep.Met {
		t.Errorf("empty report = %+v, want uptime 100, TotalChecks 0, Met true", rep)
	}
	if rep.BestMonth != "2024-01" || rep.WorstMonth != "2024-01" {
		t.Errorf("Best/Worst = %s/%s, want 2024-01/2024-01", rep.BestMonth, rep.WorstMonth)
	}
	if rep.GroupName != "组A" || rep.MonitorCount != 0 {
		t.Errorf("Name/Count = %s/%d, want 组A/0", rep.GroupName, rep.MonitorCount)
	}
	for _, y := range []int{1969, 10000} {
		if _, err := store.GroupYearlySLA(gid, y); err == nil {
			t.Errorf("year %d: want error, got nil", y)
		}
	}
	if _, err := store.GroupYearlySLA(999999, 2024); err == nil {
		t.Error("missing group: want error, got nil")
	}
}

func TestGroupYearlySLATwoMonths(t *testing.T) {
	store := newTestStore(t)
	monitorID := seedMonitor(t, store)
	gid, err := store.CreateGroup("组A")
	if err != nil {
		t.Fatalf("CreateGroup: %v", err)
	}
	if err := store.AddMonitorToGroup(gid, monitorID); err != nil {
		t.Fatalf("AddMonitorToGroup: %v", err)
	}
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
	sla, err := store.GroupYearlySLA(gid, 2024)
	if err != nil {
		t.Fatalf("GroupYearlySLA(2024): %v", err)
	}
	if sla.MonitorCount != 1 {
		t.Errorf("MonitorCount = %d, want 1", sla.MonitorCount)
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
