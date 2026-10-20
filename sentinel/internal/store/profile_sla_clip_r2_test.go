package store

import (
	"testing"
	"time"
)

func newClipMonitor(t *testing.T, st *Store, name string) int64 {
	t.Helper()
	mid, err := st.CreateMonitor(Monitor{
		Name:        name,
		Kind:        "http",
		Target:      "http://x/",
		TimeoutSec:  5,
		IntervalSec: 60,
		Enabled:     1,
		TenantID:    1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}
	return mid
}

func TestR2_SLAOpenIncidentClippedToMonthEnd(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()
	mid := newClipMonitor(t, st, "slac1")

	if _, _, err := st.OpenIncident(mid, "2026-06-10T00:00:00Z", "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}
	rep, err := st.MonthlySLA(mid, 2026, 6)
	if err != nil {
		t.Fatalf("MonthlySLA failed: %v", err)
	}
	// 6 月 10 日 00:00 到 7 月 1 日 00:00 = 21 天 = 1814400 秒；旧逻辑会算到查询时刻（远大于此）。
	const want = int64(21 * 24 * 3600)
	if rep.TotalDowntimeSec != want {
		t.Fatalf("TotalDowntimeSec = %d, want %d (clipped to month end)", rep.TotalDowntimeSec, want)
	}
	if rep.OpenIncidents != 1 {
		t.Fatalf("OpenIncidents = %d, want 1", rep.OpenIncidents)
	}
	if rep.DownIncidents != 1 {
		t.Fatalf("DownIncidents = %d, want 1", rep.DownIncidents)
	}
}

func TestR2_SLAOpenIncidentClippedSeverity(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()
	mid := newClipMonitor(t, st, "slac2")

	if _, _, err := st.OpenIncident(mid, "2026-06-30T23:59:00Z", "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}
	rep, err := st.MonthlySLA(mid, 2026, 6)
	if err != nil {
		t.Fatalf("MonthlySLA failed: %v", err)
	}
	// 裁剪后约 60 秒 -> P3；旧逻辑下 now-started 远超 1800 秒会被记 P1。
	if rep.Severity.P3 != 1 {
		t.Fatalf("Severity = %+v, want P3=1 (clipped duration ~60s)", rep.Severity)
	}
	if rep.Severity.P1 != 0 || rep.Severity.P2 != 0 {
		t.Fatalf("Severity = %+v, want P1=P2=0", rep.Severity)
	}
}

func TestR2_SLAOpenIncidentCurrentMonthUnchanged(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()
	mid := newClipMonitor(t, st, "slac3")

	startedAt := time.Now().Add(-120 * time.Second).UTC().Format(time.RFC3339)
	if _, _, err := st.OpenIncident(mid, startedAt, "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}
	now := time.Now()
	rep, err := st.MonthlySLA(mid, now.Year(), int(now.Month()))
	if err != nil {
		t.Fatalf("MonthlySLA failed: %v", err)
	}
	// 查当前月：end > now，不裁剪，行为与原来一致。
	if rep.TotalDowntimeSec < 100 || rep.TotalDowntimeSec >= 600 {
		t.Fatalf("TotalDowntimeSec = %d, want in [100, 600)", rep.TotalDowntimeSec)
	}
}

func TestR2_SLAClipDoesNotAffectMTTR(t *testing.T) {
	st := newTestStore(t)
	st.EnsureDefaultTenant()
	mid := newClipMonitor(t, st, "slac4")

	if _, _, err := st.OpenIncident(mid, "2026-06-05T00:00:00Z", "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}
	if err := st.CloseOpenIncident(mid, "2026-06-05T00:10:00Z", 600); err != nil {
		t.Fatalf("CloseOpenIncident failed: %v", err)
	}
	if _, _, err := st.OpenIncident(mid, "2026-06-10T00:00:00Z", "boom2"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	}
	rep, err := st.MonthlySLA(mid, 2026, 6)
	if err != nil {
		t.Fatalf("MonthlySLA failed: %v", err)
	}
	// MTTR 只统计已关闭事件，不受裁剪影响。
	if rep.MTTRSec != 600 {
		t.Fatalf("MTTRSec = %v, want 600", rep.MTTRSec)
	}
	const wantDown = int64(600 + 21*24*3600)
	if rep.TotalDowntimeSec != wantDown {
		t.Fatalf("TotalDowntimeSec = %d, want %d", rep.TotalDowntimeSec, wantDown)
	}
	if rep.OpenIncidents != 1 || rep.DownIncidents != 2 {
		t.Fatalf("OpenIncidents = %d, DownIncidents = %d, want 1 and 2", rep.OpenIncidents, rep.DownIncidents)
	}
}
