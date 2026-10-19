package store

import (
	"testing"
	"time"

	"sentinel/internal/db"
)

func TestCountIncidents(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	n, err := st.CountIncidents(0)
	if err != nil {
		t.Fatalf("count empty: %v", err)
	}
	if n != 0 {
		t.Fatalf("empty count = %d, want 0", n)
	}

	mid1, err := st.CreateMonitor(Monitor{Name: "m1", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor1: %v", err)
	}
	mid2, err := st.CreateMonitor(Monitor{Name: "m2", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor2: %v", err)
	}

	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 3; i++ {
		start := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, _, err := st.OpenIncident(mid1, start, "err"); err != nil {
			t.Fatalf("open incident1 %d: %v", i, err)
		}
		if err := st.CloseOpenIncident(mid1, end, 60); err != nil {
			t.Fatalf("close incident1 %d: %v", i, err)
		}
	}
	for i := 0; i < 2; i++ {
		start := base.Add(time.Duration(10+i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(10+i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, _, err := st.OpenIncident(mid2, start, "err"); err != nil {
			t.Fatalf("open incident2 %d: %v", i, err)
		}
		if err := st.CloseOpenIncident(mid2, end, 60); err != nil {
			t.Fatalf("close incident2 %d: %v", i, err)
		}
	}

	all, err := st.CountIncidents(0)
	if err != nil {
		t.Fatalf("count all: %v", err)
	}
	if all != 5 {
		t.Fatalf("count all = %d, want 5", all)
	}

	c1, err := st.CountIncidents(mid1)
	if err != nil {
		t.Fatalf("count monitor1: %v", err)
	}
	if c1 != 3 {
		t.Fatalf("count monitor1 = %d, want 3", c1)
	}

	c2, err := st.CountIncidents(mid2)
	if err != nil {
		t.Fatalf("count monitor2: %v", err)
	}
	if c2 != 2 {
		t.Fatalf("count monitor2 = %d, want 2", c2)
	}
}

func TestListIncidentsPaged_OrderAndWindow(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	mid, err := st.CreateMonitor(Monitor{Name: "m", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}

	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 25; i++ {
		start := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, err := st.db.Exec(
			`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?, ?, ?, ?, ?)`,
			mid, start, end, 60, "err"); err != nil {
			t.Fatalf("insert incident %d: %v", i, err)
		}
	}

	first, err := st.ListIncidentsPaged(0, 0, 10)
	if err != nil {
		t.Fatalf("list page1: %v", err)
	}
	if len(first) != 10 {
		t.Fatalf("page1 len = %d, want 10", len(first))
	}
	newest := base.Add(24 * time.Minute).Format(time.RFC3339Nano)
	if first[0].StartedAt != newest {
		t.Fatalf("page1 first started_at = %q, want %q", first[0].StartedAt, newest)
	}
	for i := 1; i < len(first); i++ {
		if first[i-1].StartedAt < first[i].StartedAt {
			t.Fatalf("page1 not DESC at %d: %q < %q", i, first[i-1].StartedAt, first[i].StartedAt)
		}
	}

	last, err := st.ListIncidentsPaged(0, 20, 10)
	if err != nil {
		t.Fatalf("list page3: %v", err)
	}
	if len(last) != 5 {
		t.Fatalf("page3 len = %d, want 5", len(last))
	}
	oldest := base.Add(0 * time.Minute).Format(time.RFC3339Nano)
	if last[len(last)-1].StartedAt != oldest {
		t.Fatalf("page3 last started_at = %q, want %q", last[len(last)-1].StartedAt, oldest)
	}
}

func TestListIncidentsPaged_MonitorFilter(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	mid1, err := st.CreateMonitor(Monitor{Name: "m1", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor1: %v", err)
	}
	mid2, err := st.CreateMonitor(Monitor{Name: "m2", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor2: %v", err)
	}

	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 6; i++ {
		start := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, err := st.db.Exec(
			`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?, ?, ?, ?, ?)`,
			mid1, start, end, 60, "err"); err != nil {
			t.Fatalf("insert m1 %d: %v", i, err)
		}
	}
	for i := 0; i < 4; i++ {
		start := base.Add(time.Duration(100+i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(100+i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, err := st.db.Exec(
			`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?, ?, ?, ?, ?)`,
			mid2, start, end, 60, "err"); err != nil {
			t.Fatalf("insert m2 %d: %v", i, err)
		}
	}

	got, err := st.ListIncidentsPaged(mid1, 0, 100)
	if err != nil {
		t.Fatalf("list monitor1: %v", err)
	}
	if len(got) != 6 {
		t.Fatalf("monitor1 len = %d, want 6", len(got))
	}
	for _, it := range got {
		if it.MonitorID != mid1 {
			t.Fatalf("monitor1 result contains monitor_id=%d, want %d", it.MonitorID, mid1)
		}
	}
}

func TestListIncidentsPaged_InvalidArgs(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	mid, err := st.CreateMonitor(Monitor{Name: "m", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}

	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 25; i++ {
		start := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339Nano)
		end := base.Add(time.Duration(i)*time.Minute + 30*time.Second).Format(time.RFC3339Nano)
		if _, err := st.db.Exec(
			`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?, ?, ?, ?, ?)`,
			mid, start, end, 60, "err"); err != nil {
			t.Fatalf("insert incident %d: %v", i, err)
		}
	}

	negOffset, err := st.ListIncidentsPaged(0, -5, 10)
	if err != nil {
		t.Fatalf("list neg offset: %v", err)
	}
	if len(negOffset) != 10 {
		t.Fatalf("neg offset len = %d, want 10", len(negOffset))
	}
	newest := base.Add(24 * time.Minute).Format(time.RFC3339Nano)
	if negOffset[0].StartedAt != newest {
		t.Fatalf("neg offset first = %q, want %q", negOffset[0].StartedAt, newest)
	}

	zeroLimit, err := st.ListIncidentsPaged(0, 0, 0)
	if err != nil {
		t.Fatalf("list zero limit: %v", err)
	}
	if len(zeroLimit) != 20 {
		t.Fatalf("zero limit len = %d, want 20", len(zeroLimit))
	}
}
