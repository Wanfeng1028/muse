package store

import "testing"

func TestListOpenIncidentsAndClose(t *testing.T) {
	st := newTestStore(t)

	mid, err := st.CreateMonitor(Monitor{Name: "m1", Target: "http://x", IntervalSec: 60, TimeoutSec: 5})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}

	incID, err := st.OpenIncident(mid, "2026-10-16T00:00:00Z", "boom")
	if err != nil {
		t.Fatalf("open incident: %v", err)
	}

	open, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("list open: %v", err)
	}
	found := false
	for _, inc := range open {
		if inc.ID == incID {
			found = true
		}
	}
	if !found {
		t.Fatalf("incident %d not found in open list", incID)
	}

	if err := st.CloseOpenIncident(mid, "2026-10-16T01:00:00Z", 3600); err != nil {
		t.Fatalf("close incident: %v", err)
	}

	open2, err := st.ListOpenIncidents()
	if err != nil {
		t.Fatalf("list open2: %v", err)
	}
	for _, inc := range open2 {
		if inc.ID == incID {
			t.Fatalf("incident %d should be closed", incID)
		}
	}
}

func TestMarkEscalationSentIdempotent(t *testing.T) {
	st := newTestStore(t)

	mid, err := st.CreateMonitor(Monitor{Name: "m1", Target: "http://x", IntervalSec: 60, TimeoutSec: 5})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	incID, err := st.OpenIncident(mid, "2026-10-16T00:00:00Z", "boom")
	if err != nil {
		t.Fatalf("open incident: %v", err)
	}

	if err := st.MarkEscalationSent(incID, 15); err != nil {
		t.Fatalf("mark 1: %v", err)
	}
	if err := st.MarkEscalationSent(incID, 15); err != nil {
		t.Fatalf("mark 2: %v", err)
	}

	sent, err := st.SentEscalationLevels(incID)
	if err != nil {
		t.Fatalf("sent levels: %v", err)
	}
	if len(sent) != 1 || sent[0] != 15 {
		t.Fatalf("expected [15], got %+v", sent)
	}
}
