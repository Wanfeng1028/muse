package store

import "testing"

func TestR2_OpenIncidentIdempotent(t *testing.T) {
	st := newTestStore(t)

	mid, err := st.CreateMonitor(Monitor{
		Name:        "ii1",
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

	id1, created1, err := st.OpenIncident(mid, "2026-01-01T00:00:00Z", "boom")
	if err != nil {
		t.Fatalf("OpenIncident first: %v", err)
	}
	if !created1 {
		t.Fatalf("OpenIncident first created = false, want true")
	}
	if id1 <= 0 {
		t.Fatalf("OpenIncident first id = %d, want > 0", id1)
	}

	id2, created2, err := st.OpenIncident(mid, "2026-01-01T00:05:00Z", "boom2")
	if err != nil {
		t.Fatalf("OpenIncident second: %v", err)
	}
	if created2 {
		t.Fatalf("OpenIncident second created = true, want false")
	}
	if id2 != id1 {
		t.Fatalf("OpenIncident second id = %d, want %d", id2, id1)
	}
}
