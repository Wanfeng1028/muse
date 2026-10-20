package store

import "testing"

func TestR2_AddMonitorToPageIdempotent(t *testing.T) {
	st := newTestStore(t)

	pageID, err := st.CreateStatusPage(1, "pg-r2", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage failed: %v", err)
	}

	mid1, err := st.CreateMonitor(Monitor{
		Name:        "pa1",
		Kind:        "http",
		Target:      "http://x/1",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor pa1 failed: %v", err)
	}

	mid2, err := st.CreateMonitor(Monitor{
		Name:        "pa2",
		Kind:        "http",
		Target:      "http://x/2",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor pa2 failed: %v", err)
	}

	if err := st.AddMonitorToPage(pageID, mid1); err != nil {
		t.Fatalf("AddMonitorToPage mid1 first failed: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, mid1); err != nil {
		t.Fatalf("AddMonitorToPage mid1 repeat failed: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, mid2); err != nil {
		t.Fatalf("AddMonitorToPage mid2 failed: %v", err)
	}

	mons, err := st.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors failed: %v", err)
	}
	if len(mons) != 2 {
		t.Fatalf("expected 2 monitors, got %d", len(mons))
	}
	if mons[0].ID != mid1 {
		t.Errorf("expected first monitor ID %d, got %d", mid1, mons[0].ID)
	}
	if mons[1].ID != mid2 {
		t.Errorf("expected second monitor ID %d, got %d", mid2, mons[1].ID)
	}
}
