package scheduler

import (
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestR2_NotifySkippedWhenSilenced(t *testing.T) {
	st := newTestStore(t)
	m := newMonitor(t, st, "api-prod", 1)

	_, err := st.CreateSilence(store.Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  time.Now().Add(-time.Hour).UTC().Format(time.RFC3339),
		EndsAt:    time.Now().Add(time.Hour).UTC().Format(time.RFC3339),
		Reason:    "维护",
	})
	if err != nil {
		t.Fatalf("CreateSilence: %v", err)
	}

	called := false
	s := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {
		called = true
	}, 10, 5, 0)

	s.notifyUnlessSilenced(m, "down", m.Name, m.Target, "now", "boom")

	if called {
		t.Fatal("expected notify skipped when active silence matches, but notify was called")
	}
}

func TestR2_NotifySentWhenSilenceExpired(t *testing.T) {
	st := newTestStore(t)
	m2 := newMonitor(t, st, "api-prod-2", 1)

	oldID, err := st.CreateSilence(store.Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  time.Now().Add(-2 * time.Hour).UTC().Format(time.RFC3339),
		EndsAt:    time.Now().Add(-time.Hour).UTC().Format(time.RFC3339),
		Reason:    "old",
	})
	if err != nil {
		t.Fatalf("CreateSilence old: %v", err)
	}
	if err := st.DeleteSilence(oldID); err != nil {
		t.Fatalf("DeleteSilence: %v", err)
	}

	_, err = st.CreateSilence(store.Silence{
		MonitorID: 0,
		NameMatch: "",
		StartsAt:  time.Now().Add(-3 * time.Hour).UTC().Format(time.RFC3339),
		EndsAt:    time.Now().Add(-time.Hour).UTC().Format(time.RFC3339),
		Reason:    "expired",
	})
	if err != nil {
		t.Fatalf("CreateSilence expired: %v", err)
	}

	called := false
	s := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {
		called = true
	}, 10, 5, 0)

	s.notifyUnlessSilenced(m2, "down", m2.Name, m2.Target, "now", "boom")

	if !called {
		t.Fatal("expected notify called when silence expired")
	}
}

func TestR2_NotifySkippedByNameMatch(t *testing.T) {
	st := newTestStore(t)

	_, err := st.CreateSilence(store.Silence{
		MonitorID: 0,
		NameMatch: "prod",
		StartsAt:  time.Now().Add(-time.Hour).UTC().Format(time.RFC3339),
		EndsAt:    time.Now().Add(time.Hour).UTC().Format(time.RFC3339),
		Reason:    "maintenance",
	})
	if err != nil {
		t.Fatalf("CreateSilence: %v", err)
	}

	calledProd := false
	sProd := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {
		calledProd = true
	}, 10, 5, 0)
	mProd := newMonitor(t, st, "web-prod-1", 1)
	sProd.notifyUnlessSilenced(mProd, "down", mProd.Name, mProd.Target, "now", "boom")
	if calledProd {
		t.Fatal("expected notify skipped for web-prod-1 with name match prod")
	}

	calledStaging := false
	sStaging := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {
		calledStaging = true
	}, 10, 5, 0)
	mStaging := newMonitor(t, st, "web-staging-1", 1)
	sStaging.notifyUnlessSilenced(mStaging, "down", mStaging.Name, mStaging.Target, "now", "boom")
	if !calledStaging {
		t.Fatal("expected notify called for web-staging-1 without name match")
	}
}
