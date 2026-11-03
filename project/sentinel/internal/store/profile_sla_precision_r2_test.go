package store

import (
	"math"
	"testing"
	"time"
)

func TestR2_SLAUptimePrecision(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slap",
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

	checks := []Check{
		{MonitorID: mid, Ok: 1, CheckedAt: time.Date(2026, 4, 3, 10, 0, 0, 0, time.UTC).Format(time.RFC3339)},
		{MonitorID: mid, Ok: 1, CheckedAt: time.Date(2026, 4, 3, 10, 1, 0, 0, time.UTC).Format(time.RFC3339)},
		{MonitorID: mid, Ok: 0, CheckedAt: time.Date(2026, 4, 3, 10, 2, 0, 0, time.UTC).Format(time.RFC3339)},
	}
	for _, c := range checks {
		st.InsertCheck(c)
	}

	rep, err := st.MonthlySLA(mid, 2026, 4)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}

	const wantUptimePct = 66.66666666666667
	if diff := math.Abs(rep.UptimePct - wantUptimePct); diff >= 1e-9 {
		t.Fatalf("UptimePct = %v, want %v, diff = %v", rep.UptimePct, wantUptimePct, diff)
	}
	if rep.Met {
		t.Fatalf("Met = true, want false")
	}
}
