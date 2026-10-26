package scheduler

import (
	"context"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestRunOneSkippedInMaintenanceWindow(t *testing.T) {
	st := newTestStore(t)
	monID, err := st.CreateMonitor(store.Monitor{
		Name: "mw-target", Kind: "http", Target: "http://127.0.0.1:9/health",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 2, IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	m, err := st.GetMonitor(monID)
	if err != nil {
		t.Fatalf("GetMonitor: %v", err)
	}
	now := time.Now().UTC()
	winID, err := st.CreateMaintenanceWindow(store.MaintenanceWindow{
		MonitorID: 0, Title: "割接",
		StartsAt: now.Add(-time.Hour).Format(time.RFC3339),
		EndsAt:   now.Add(time.Hour).Format(time.RFC3339),
	})
	if err != nil {
		t.Fatalf("CreateMaintenanceWindow: %v", err)
	}
	notified := 0
	s := New(st, func(m store.Monitor, event, name, target, at, errMsg string) {
		notified++
	}, 10, 5, 0)
	s.runOne(context.Background(), m, false, false)
	checks, err := st.ListChecks(monID, 10)
	if err != nil {
		t.Fatalf("ListChecks: %v", err)
	}
	if len(checks) != 0 {
		t.Fatalf("维护窗口内期望 0 条检查记录，得到 %d", len(checks))
	}
	if notified != 0 {
		t.Fatalf("维护窗口内期望 0 次通知，得到 %d", notified)
	}
	if err := st.DeleteMaintenanceWindow(winID); err != nil {
		t.Fatalf("DeleteMaintenanceWindow: %v", err)
	}
}
