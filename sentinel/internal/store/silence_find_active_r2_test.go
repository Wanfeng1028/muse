package store

import (
	"testing"
	"time"
)

func TestR2_FindActiveSilenceBoundary(t *testing.T) {
	st := newTestStore(t)
	now := time.Date(2026, 6, 15, 12, 0, 0, 0, time.UTC)

	idA, err := st.CreateSilence(Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  now.Format(time.RFC3339),
		EndsAt:    now.Add(time.Hour).Format(time.RFC3339),
		Reason:    "r",
	})
	if err != nil {
		t.Fatalf("CreateSilence A: %v", err)
	}

	found, ok, err := st.FindActiveSilence(42, "web", now)
	if err != nil {
		t.Fatalf("FindActiveSilence A: %v", err)
	}
	if !ok {
		t.Fatalf("FindActiveSilence A: ok = false, want true")
	}
	if found == nil {
		t.Fatalf("FindActiveSilence A: found = nil, want non-nil")
	}
	if found.ID != idA {
		t.Fatalf("FindActiveSilence A: id = %d, want %d", found.ID, idA)
	}

	idB, err := st.CreateSilence(Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  now.Add(-2 * time.Hour).Format(time.RFC3339),
		EndsAt:    now.Format(time.RFC3339),
		Reason:    "r",
	})
	if err != nil {
		t.Fatalf("CreateSilence B: %v", err)
	}

	if err := st.DeleteSilence(idA); err != nil {
		t.Fatalf("DeleteSilence A: %v", err)
	}

	found, ok, err = st.FindActiveSilence(42, "web", now)
	if err != nil {
		t.Fatalf("FindActiveSilence B: %v", err)
	}
	if !ok {
		t.Fatalf("FindActiveSilence B at end boundary: ok = false, want true")
	}
	if found == nil {
		t.Fatalf("FindActiveSilence B at end boundary: found = nil, want non-nil")
	}
	if found.ID != idB {
		t.Fatalf("FindActiveSilence B at end boundary: id = %d, want %d", found.ID, idB)
	}

	if _, err := st.CreateSilence(Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  now.Format(time.RFC3339),
		EndsAt:    now.Add(time.Hour).Format(time.RFC3339),
		Reason:    "r",
	}); err != nil {
		t.Fatalf("CreateSilence A again: %v", err)
	}

	found, ok, err = st.FindActiveSilence(42, "web", now.Add(2*time.Hour))
	if err != nil {
		t.Fatalf("FindActiveSilence after windows: %v", err)
	}
	if ok {
		t.Fatalf("FindActiveSilence after windows: ok = true, want false")
	}
	if found != nil {
		t.Fatalf("FindActiveSilence after windows: found = %+v, want nil", found)
	}
}

func TestR2_FindActiveSilenceMatch(t *testing.T) {
	st := newTestStore(t)
	now := time.Date(2026, 6, 15, 12, 0, 0, 0, time.UTC)

	idC, err := st.CreateSilence(Silence{
		MonitorID: 42,
		NameMatch: "prod",
		StartsAt:  now.Add(-time.Hour).Format(time.RFC3339),
		EndsAt:    now.Add(time.Hour).Format(time.RFC3339),
		Reason:    "r",
	})
	if err != nil {
		t.Fatalf("CreateSilence C: %v", err)
	}

	found, ok, err := st.FindActiveSilence(42, "api-prod-1", now)
	if err != nil {
		t.Fatalf("FindActiveSilence matching monitor and name: %v", err)
	}
	if !ok {
		t.Fatalf("FindActiveSilence matching monitor and name: ok = false, want true")
	}
	if found == nil {
		t.Fatalf("FindActiveSilence matching monitor and name: found = nil, want non-nil")
	}
	if found.ID != idC {
		t.Fatalf("FindActiveSilence matching monitor and name: id = %d, want %d", found.ID, idC)
	}

	found, ok, err = st.FindActiveSilence(43, "api-prod-1", now)
	if err != nil {
		t.Fatalf("FindActiveSilence mismatched monitor: %v", err)
	}
	if ok {
		t.Fatalf("FindActiveSilence mismatched monitor: ok = true, want false")
	}
	if found != nil {
		t.Fatalf("FindActiveSilence mismatched monitor: found = %+v, want nil", found)
	}

	found, ok, err = st.FindActiveSilence(42, "api-staging-1", now)
	if err != nil {
		t.Fatalf("FindActiveSilence mismatched name: %v", err)
	}
	if ok {
		t.Fatalf("FindActiveSilence mismatched name: ok = true, want false")
	}
	if found != nil {
		t.Fatalf("FindActiveSilence mismatched name: found = %+v, want nil", found)
	}
}

func TestR2_FindActiveSilenceSmallestID(t *testing.T) {
	st := newTestStore(t)
	now := time.Date(2026, 6, 15, 12, 0, 0, 0, time.UTC)

	idFirst, err := st.CreateSilence(Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  now.Add(-time.Hour).Format(time.RFC3339),
		EndsAt:    now.Add(time.Hour).Format(time.RFC3339),
		Reason:    "r",
	})
	if err != nil {
		t.Fatalf("CreateSilence first: %v", err)
	}

	idSecond, err := st.CreateSilence(Silence{
		MonitorID: 42,
		NameMatch: "web",
		StartsAt:  now.Add(-time.Hour).Format(time.RFC3339),
		EndsAt:    now.Add(time.Hour).Format(time.RFC3339),
		Reason:    "r",
	})
	if err != nil {
		t.Fatalf("CreateSilence second: %v", err)
	}

	found, ok, err := st.FindActiveSilence(42, "web", now)
	if err != nil {
		t.Fatalf("FindActiveSilence smallest id: %v", err)
	}
	if !ok {
		t.Fatalf("FindActiveSilence smallest id: ok = false, want true")
	}
	if found == nil {
		t.Fatalf("FindActiveSilence smallest id: found = nil, want non-nil")
	}
	if found.ID != idFirst {
		t.Fatalf("FindActiveSilence smallest id: id = %d, want %d", found.ID, idFirst)
	}
	if idSecond <= idFirst {
		t.Fatalf("FindActiveSilence smallest id: second id = %d, want greater than %d", idSecond, idFirst)
	}
}
