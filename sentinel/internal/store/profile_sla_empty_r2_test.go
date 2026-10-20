package store

import "testing"

func TestR2_SLAEmptyMonth(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slae",
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

	rep, err := st.MonthlySLA(mid, 2026, 6)
	if err != nil {
		t.Fatalf("MonthlySLA returned error: %v", err)
	}

	if rep.TotalChecks != 0 {
		t.Fatalf("TotalChecks = %d, want 0", rep.TotalChecks)
	}
	if rep.UptimePct != 100 {
		t.Fatalf("UptimePct = %v, want 100", rep.UptimePct)
	}
	if rep.DownIncidents != 0 {
		t.Fatalf("DownIncidents = %d, want 0", rep.DownIncidents)
	}
	if rep.TotalDowntimeSec != 0 {
		t.Fatalf("TotalDowntimeSec = %d, want 0", rep.TotalDowntimeSec)
	}
	if !rep.Met {
		t.Fatalf("Met = false, want true")
	}
	if rep.MTTRSec != 0 {
		t.Fatalf("MTTRSec = %v, want 0", rep.MTTRSec)
	}
	if rep.OpenIncidents != 0 {
		t.Fatalf("OpenIncidents = %d, want 0", rep.OpenIncidents)
	}
	if len(rep.Attribution) != 0 {
		t.Fatalf("len(Attribution) = %d, want 0", len(rep.Attribution))
	}
	if rep.Severity.P1 != 0 || rep.Severity.P2 != 0 || rep.Severity.P3 != 0 {
		t.Fatalf("Severity = %+v, want zero counts", rep.Severity)
	}
}
