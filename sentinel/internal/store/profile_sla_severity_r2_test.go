package store

import "testing"

func TestR2_SLASeverityBoundary(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slas",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	cases := []struct {
		startedAt string
		endedAt   string
		downtime  int64
	}{
		{"2026-05-01T10:00:00Z", "2026-05-01T11:00:00Z", 1800},
		{"2026-05-02T10:00:00Z", "2026-05-02T11:00:00Z", 1799},
		{"2026-05-03T10:00:00Z", "2026-05-03T11:00:00Z", 300},
		{"2026-05-04T10:00:00Z", "2026-05-04T11:00:00Z", 299},
	}

	for i, c := range cases {
		if _, opened, err := st.OpenIncident(mid, c.startedAt, "x"); err != nil || !opened {
			t.Fatalf("OpenIncident %d: err=%v opened=%v", i, err, opened)
		}
		if err := st.CloseOpenIncident(mid, c.endedAt, c.downtime); err != nil {
			t.Fatalf("CloseOpenIncident %d: %v", i, err)
		}
	}

	rep, err := st.MonthlySLA(mid, 2026, 5)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}

	if got := rep.Severity.P1; got != 1 {
		t.Fatalf("Severity.P1 = %d, want 1", got)
	}
	if got := rep.Severity.P2; got != 2 {
		t.Fatalf("Severity.P2 = %d, want 2", got)
	}
	if got := rep.Severity.P3; got != 1 {
		t.Fatalf("Severity.P3 = %d, want 1", got)
	}
}
