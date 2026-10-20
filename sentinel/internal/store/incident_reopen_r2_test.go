package store

import "testing"

func TestR2_OpenIncidentReopenAfterClose(t *testing.T) {
	st := newTestStore(t)

	mid, err := st.CreateMonitor(Monitor{
		Name:        "ii2",
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

	id1, created1, err := st.OpenIncident(mid, "2026-01-01T00:00:00Z", "boom")
	if err != nil {
		t.Fatalf("OpenIncident returned error: %v", err)
	}
	if !created1 {
		t.Fatalf("expected first OpenIncident to create a new incident")
	}

	if err := st.CloseOpenIncident(mid, "2026-01-01T01:00:00Z", 3600); err != nil {
		t.Fatalf("CloseOpenIncident returned error: %v", err)
	}

	id3, created3, err := st.OpenIncident(mid, "2026-01-02T00:00:00Z", "boom3")
	if err != nil {
		t.Fatalf("second OpenIncident returned error: %v", err)
	}
	if !created3 {
		t.Fatalf("expected OpenIncident after close to create a new incident")
	}
	if id3 == id1 {
		t.Fatalf("expected reopened incident id %d to differ from original id %d", id3, id1)
	}

	startedAt, err := st.OpenIncidentStartedAt(mid)
	if err != nil {
		t.Fatalf("OpenIncidentStartedAt returned error: %v", err)
	}
	if startedAt != "2026-01-02T00:00:00Z" {
		t.Fatalf("unexpected startedAt: got %q", startedAt)
	}

	mid2, err := st.CreateMonitor(Monitor{
		Name:        "ii3",
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor for monitor2 returned error: %v", err)
	}

	if _, err := st.OpenIncidentStartedAt(mid2); err == nil {
		t.Fatalf("expected OpenIncidentStartedAt to fail when no incident is open")
	}
}
