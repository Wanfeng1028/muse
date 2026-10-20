package store

import "testing"

func TestR2_SLAAttributionPctRounding(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slap3",
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

	_, opened, err := st.OpenIncident(mid, "2026-04-03T10:00:00Z", "a")
	if err != nil {
		t.Fatalf("OpenIncident first: %v", err)
	}
	if !opened {
		t.Fatalf("OpenIncident first: expected opened true")
	}
	if err := st.CloseOpenIncident(mid, "2026-04-03T10:01:00Z", 60); err != nil {
		t.Fatalf("CloseOpenIncident first: %v", err)
	}

	_, opened, err = st.OpenIncident(mid, "2026-04-04T10:00:00Z", "b")
	if err != nil {
		t.Fatalf("OpenIncident second: %v", err)
	}
	if !opened {
		t.Fatalf("OpenIncident second: expected opened true")
	}
	if err := st.CloseOpenIncident(mid, "2026-04-04T10:01:00Z", 60); err != nil {
		t.Fatalf("CloseOpenIncident second: %v", err)
	}

	_, opened, err = st.OpenIncident(mid, "2026-04-05T10:00:00Z", "证书过期")
	if err != nil {
		t.Fatalf("OpenIncident third: %v", err)
	}
	if !opened {
		t.Fatalf("OpenIncident third: expected opened true")
	}
	if err := st.CloseOpenIncident(mid, "2026-04-05T10:01:00Z", 60); err != nil {
		t.Fatalf("CloseOpenIncident third: %v", err)
	}

	rep, err := st.MonthlySLA(mid, 2026, 4)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}
	if rep.DownIncidents != 3 {
		t.Fatalf("DownIncidents = %d, want 3", rep.DownIncidents)
	}
	if rep.AttributionPct["other"] != 66.7 {
		t.Fatalf(`AttributionPct["other"] = %v, want 66.7`, rep.AttributionPct["other"])
	}
	if rep.AttributionPct["cert"] != 33.3 {
		t.Fatalf(`AttributionPct["cert"] = %v, want 33.3`, rep.AttributionPct["cert"])
	}
}
