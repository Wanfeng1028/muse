package store

import (
	"fmt"
	"testing"
)

func TestR2_SLAMetBoundary(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{Name: "slam2", Kind: "http", Target: "http://x/", TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	for i := 0; i < 1000; i++ {
		ok := 1
		if i == 999 {
			ok = 0
		}
		ts := fmt.Sprintf("2026-04-10T08:%02d:%02dZ", (i/60)%24, i%60)
		if _, err := st.InsertCheck(Check{MonitorID: mid, Ok: ok, CheckedAt: ts}); err != nil {
			t.Fatalf("InsertCheck: %v", err)
		}
	}

	rep, err := st.MonthlySLA(mid, 2026, 4)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}
	if rep.UptimePct != 99.9 {
		t.Fatalf("UptimePct = %v, want 99.9", rep.UptimePct)
	}
	if !rep.Met {
		t.Fatalf("Met = false, want true")
	}

	mid2, err := st.CreateMonitor(Monitor{Name: "slam3", Kind: "http", Target: "http://x/", TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	for i := 0; i < 1000; i++ {
		ok := 1
		if i >= 998 {
			ok = 0
		}
		ts := fmt.Sprintf("2026-04-10T08:%02d:%02dZ", (i/60)%24, i%60)
		if _, err := st.InsertCheck(Check{MonitorID: mid2, Ok: ok, CheckedAt: ts}); err != nil {
			t.Fatalf("InsertCheck: %v", err)
		}
	}

	rep2, err := st.MonthlySLA(mid2, 2026, 4)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}
	if rep2.Met {
		t.Fatalf("Met = true, want false")
	}
}
