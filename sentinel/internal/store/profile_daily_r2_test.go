package store

import (
	"testing"
	"time"
)

func TestR2_DailyBreakdownIncludesEmptyDays(t *testing.T) {
	st := newTestStore(t)

	mid, err := st.CreateMonitor(Monitor{
		Name:        "db1",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor returned error: %v", err)
	}

	now := time.Now().UTC()
	todayCheckedAt := now.Format(time.RFC3339)

	if _, err := st.InsertCheck(Check{MonitorID: mid, Ok: 1, CheckedAt: todayCheckedAt}); err != nil {
		t.Fatalf("InsertCheck returned error: %v", err)
	}
	if _, err := st.InsertCheck(Check{MonitorID: mid, Ok: 1, CheckedAt: todayCheckedAt}); err != nil {
		t.Fatalf("InsertCheck returned error: %v", err)
	}

	twoDaysAgoCheckedAt := now.AddDate(0, 0, -2).Format(time.RFC3339)
	if _, err := st.InsertCheck(Check{MonitorID: mid, Ok: 0, CheckedAt: twoDaysAgoCheckedAt}); err != nil {
		t.Fatalf("InsertCheck returned error: %v", err)
	}

	stats, err := st.DailyBreakdown(mid, 3)
	if err != nil {
		t.Fatalf("DailyBreakdown returned error: %v", err)
	}
	if len(stats) != 3 {
		t.Fatalf("DailyBreakdown returned %d days, want 3", len(stats))
	}

	byDate := make(map[string]DayStat, len(stats))
	for _, ds := range stats {
		byDate[ds.Date] = ds
	}

	todayKey := now.Format("2006-01-02")
	today, ok := byDate[todayKey]
	if !ok {
		t.Fatalf("DailyBreakdown missing date %s", todayKey)
	}
	if today.Checks != 2 {
		t.Fatalf("today Checks = %d, want 2", today.Checks)
	}
	if today.Failures != 0 {
		t.Fatalf("today Failures = %d, want 0", today.Failures)
	}
	if today.UptimePct != 100 {
		t.Fatalf("today UptimePct = %v, want 100", today.UptimePct)
	}

	emptyKey := now.AddDate(0, 0, -1).Format("2006-01-02")
	empty, ok := byDate[emptyKey]
	if !ok {
		t.Fatalf("DailyBreakdown missing empty date %s", emptyKey)
	}
	if empty.Checks != 0 {
		t.Fatalf("empty day Checks = %d, want 0", empty.Checks)
	}
	if empty.Failures != 0 {
		t.Fatalf("empty day Failures = %d, want 0", empty.Failures)
	}
	if empty.UptimePct != 100 {
		t.Fatalf("empty day UptimePct = %v, want 100", empty.UptimePct)
	}

	olderKey := now.AddDate(0, 0, -2).Format("2006-01-02")
	older, ok := byDate[olderKey]
	if !ok {
		t.Fatalf("DailyBreakdown missing date %s", olderKey)
	}
	if older.Checks != 1 {
		t.Fatalf("older day Checks = %d, want 1", older.Checks)
	}
	if older.Failures != 1 {
		t.Fatalf("older day Failures = %d, want 1", older.Failures)
	}
	if older.UptimePct != 0 {
		t.Fatalf("older day UptimePct = %v, want 0", older.UptimePct)
	}
}
