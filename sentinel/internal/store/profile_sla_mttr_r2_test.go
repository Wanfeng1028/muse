package store

import "testing"

func TestR2_SLAMTTR(t *testing.T) {
	st := newTestStore(t)
	if err := st.EnsureDefaultTenant(); err != nil {
		t.Fatalf("EnsureDefaultTenant: %v", err)
	}

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slamt",
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

	if _, _, err := st.OpenIncident(mid, "2026-05-01T10:00:00Z", "x"); err != nil {
		t.Fatalf("OpenIncident first: %v", err)
	}
	if _, err := st.CloseOpenIncident(mid, "2026-05-01T10:01:00Z", 60); err != nil {
		t.Fatalf("CloseOpenIncident first: %v", err)
	}

	if _, _, err := st.OpenIncident(mid, "2026-05-02T10:00:00Z", "x"); err != nil {
		t.Fatalf("OpenIncident second: %v", err)
	}
	if _, err := st.CloseOpenIncident(mid, "2026-05-02T10:03:00Z", 180); err != nil {
		t.Fatalf("CloseOpenIncident second: %v", err)
	}

	rep, err := st.MonthlySLA(mid, 2026, 5)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}
	if rep.MTTRSec != 120 {
		t.Fatalf("MTTRSec = %v, want 120", rep.MTTRSec)
	}

	mid2, err := st.CreateMonitor(Monitor{
		Name:        "slamt2",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor second: %v", err)
	}

	if _, _, err := st.OpenIncident(mid2, "2026-05-01T10:00:00Z", "x"); err != nil {
		t.Fatalf("OpenIncident second monitor: %v", err)
	}

	rep2, err := st.MonthlySLA(mid2, 2026, 5)
	if err != nil {
		t.Fatalf("MonthlySLA second monitor: %v", err)
	}
	if rep2.MTTRSec != 0 {
		t.Fatalf("MTTRSec with no closed incidents = %v, want 0", rep2.MTTRSec)
	}
}
