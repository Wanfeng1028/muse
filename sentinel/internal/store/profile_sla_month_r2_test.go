package store

import (
	"strings"
	"testing"
)

func TestR2_SLAIllegalMonth(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()

	mid, err := st.CreateMonitor(Monitor{
		Name:        "slam",
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
	if mid <= 0 {
		t.Fatalf("CreateMonitor returned invalid monitor id: %d", mid)
	}

	_, err = st.MonthlySLA(mid, 2026, 0)
	if err == nil {
		t.Fatal("MonthlySLA with month 0 expected error, got nil")
	}
	if !strings.Contains(err.Error(), "非法月份") {
		t.Fatalf("MonthlySLA with month 0 error = %q, want contains %q", err.Error(), "非法月份")
	}

	_, err = st.MonthlySLA(mid, 2026, 13)
	if err == nil {
		t.Fatal("MonthlySLA with month 13 expected error, got nil")
	}
	if !strings.Contains(err.Error(), "非法月份") {
		t.Fatalf("MonthlySLA with month 13 error = %q, want contains %q", err.Error(), "非法月份")
	}

	rep, err := st.MonthlySLA(mid, 2026, 1)
	if err != nil {
		t.Fatalf("MonthlySLA with month 1 returned error: %v", err)
	}
	if rep.Month != "2026-01" {
		t.Fatalf("MonthlySLA month field = %q, want %q", rep.Month, "2026-01")
	}
	if rep.Target != 99.9 {
		t.Fatalf("MonthlySLA target = %v, want %v", rep.Target, 99.9)
	}

	rep2, err := st.MonthlySLA(mid, 2026, 12)
	if err != nil {
		t.Fatalf("MonthlySLA with month 12 returned error: %v", err)
	}
	if rep2.Month != "2026-12" {
		t.Fatalf("MonthlySLA month field = %q, want %q", rep2.Month, "2026-12")
	}
}
