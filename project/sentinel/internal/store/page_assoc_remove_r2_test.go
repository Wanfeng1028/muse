package store

import "testing"

func TestR2_RemoveMonitorFromPage(t *testing.T) {
	st := newTestStore(t)

	pageID, err := st.CreateStatusPage(1, "pg-r2b", "t")
	if err != nil {
		t.Fatalf("CreateStatusPage returned error: %v", err)
	}

	mid1, err := st.CreateMonitor(Monitor{
		Name:        "pb1",
		Kind:        "http",
		Target:      "http://x/1",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor pb1 returned error: %v", err)
	}

	mid2, err := st.CreateMonitor(Monitor{
		Name:        "pb2",
		Kind:        "http",
		Target:      "http://x/2",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor pb2 returned error: %v", err)
	}

	if err := st.AddMonitorToPage(pageID, mid1); err != nil {
		t.Fatalf("AddMonitorToPage mid1 returned error: %v", err)
	}
	if err := st.AddMonitorToPage(pageID, mid2); err != nil {
		t.Fatalf("AddMonitorToPage mid2 returned error: %v", err)
	}

	if err := st.RemoveMonitorFromPage(pageID, mid1); err != nil {
		t.Fatalf("RemoveMonitorFromPage mid1 returned error: %v", err)
	}

	mons, err := st.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors returned error: %v", err)
	}
	if len(mons) != 1 {
		t.Fatalf("expected 1 page monitor after removal, got %d", len(mons))
	}
	if mons[0].ID != mid2 {
		t.Fatalf("expected remaining monitor ID %d, got %d", mid2, mons[0].ID)
	}

	if err := st.RemoveMonitorFromPage(pageID, mid1); err != nil {
		t.Fatalf("repeated RemoveMonitorFromPage returned error: %v", err)
	}

	mons, err = st.ListPageMonitors(pageID)
	if err != nil {
		t.Fatalf("ListPageMonitors after repeated removal returned error: %v", err)
	}
	if len(mons) != 1 {
		t.Fatalf("expected 1 page monitor after repeated removal, got %d", len(mons))
	}
	if mons[0].ID != mid2 {
		t.Fatalf("expected remaining monitor ID %d after repeated removal, got %d", mid2, mons[0].ID)
	}

	if err := st.SetMonitorPublic(mid2, 5); err != nil {
		t.Fatalf("SetMonitorPublic mid2 with non-zero value returned error: %v", err)
	}

	m, err := st.GetMonitor(mid2)
	if err != nil {
		t.Fatalf("GetMonitor mid2 returned error: %v", err)
	}
	if m.IsPublic != 1 {
		t.Fatalf("expected IsPublic normalized to 1, got %d", m.IsPublic)
	}

	if err := st.SetMonitorPublic(mid2, 0); err != nil {
		t.Fatalf("SetMonitorPublic mid2 with zero returned error: %v", err)
	}

	m, err = st.GetMonitor(mid2)
	if err != nil {
		t.Fatalf("GetMonitor mid2 after clearing public returned error: %v", err)
	}
	if m.IsPublic != 0 {
		t.Fatalf("expected IsPublic 0, got %d", m.IsPublic)
	}
}
