package store

import (
	"testing"
	"time"
)

func TestR2_SLAOpenIncidentEstimate(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slao",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	startedAt := time.Now().Add(-120 * time.Second).UTC().Format(time.RFC3339)
	if _, _, err := st.OpenIncident(mid, startedAt, "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}

	now := time.Now()
	rep, err := st.MonthlySLA(mid, now.Year(), int(now.Month()))
	if err != nil {
		t.Fatalf("MonthlySLA failed: %v", err)
	}

	if rep.OpenIncidents != 1 {
		t.Fatalf("OpenIncidents = %d, want 1", rep.OpenIncidents)
	}
	if rep.DownIncidents != 1 {
		t.Fatalf("DownIncidents = %d, want 1", rep.DownIncidents)
	}
	if rep.TotalDowntimeSec < 100 || rep.TotalDowntimeSec >= 600 {
		t.Fatalf("TotalDowntimeSec = %d, want >= 100 and < 600", rep.TotalDowntimeSec)
	}
	if rep.Severity.P3 != 1 {
		t.Fatalf("Severity.P3 = %d, want 1", rep.Severity.P3)
	}
}
