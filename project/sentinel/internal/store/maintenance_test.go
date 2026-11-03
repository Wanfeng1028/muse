package store

import (
	"testing"
	"time"
)

func TestCreateMaintenanceWindowAndList(t *testing.T) {
	st := newTestStore(t)
	start := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	end := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	id, err := st.CreateMaintenanceWindow(MaintenanceWindow{
		MonitorID: 0,
		Title:     "割接",
		StartsAt:  start,
		EndsAt:    end,
	})
	if err != nil {
		t.Fatalf("CreateMaintenanceWindow: %v", err)
	}
	if id <= 0 {
		t.Fatalf("期望正 id，得到 %d", id)
	}
	list, err := st.ListMaintenanceWindows()
	if err != nil {
		t.Fatalf("ListMaintenanceWindows: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("期望 1 条，得到 %d", len(list))
	}
	got := list[0]
	if got.ID != id || got.MonitorID != 0 || got.Title != "割接" || got.StartsAt != start || got.EndsAt != end {
		t.Fatalf("列表内容不符: %+v", got)
	}
}

func TestCreateMaintenanceWindowRejects(t *testing.T) {
	st := newTestStore(t)
	now := time.Now().UTC()
	start := now.Format(time.RFC3339)
	end := now.Add(time.Hour).Format(time.RFC3339)
	if _, err := st.CreateMaintenanceWindow(MaintenanceWindow{MonitorID: 0, Title: "   ", StartsAt: start, EndsAt: end}); err == nil {
		t.Fatalf("期望空标题被拒")
	}
	if _, err := st.CreateMaintenanceWindow(MaintenanceWindow{MonitorID: 0, Title: "x", StartsAt: end, EndsAt: start}); err == nil {
		t.Fatalf("期望开始晚于结束被拒")
	}
	if _, err := st.CreateMaintenanceWindow(MaintenanceWindow{MonitorID: 0, Title: "x", StartsAt: "not-a-time", EndsAt: end}); err == nil {
		t.Fatalf("期望非法时间被拒")
	}
	if _, err := st.CreateMaintenanceWindow(MaintenanceWindow{MonitorID: 999999, Title: "x", StartsAt: start, EndsAt: end}); err == nil {
		t.Fatalf("期望不存在的监控被拒")
	}
	if _, err := st.CreateMaintenanceWindow(MaintenanceWindow{MonitorID: -1, Title: "x", StartsAt: start, EndsAt: end}); err == nil {
		t.Fatalf("期望负监控 ID 被拒")
	}
}

func TestActiveMaintenanceWindow(t *testing.T) {
	st := newTestStore(t)
	monID, err := st.CreateMonitor(Monitor{
		Name: "mw-mon", Kind: "http", Target: "http://example.invalid/health",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	now := time.Now().UTC()
	mk := func(mon int64, s, e time.Time) MaintenanceWindow {
		return MaintenanceWindow{MonitorID: mon, Title: "w", StartsAt: s.Format(time.RFC3339), EndsAt: e.Format(time.RFC3339)}
	}
	if _, err := st.CreateMaintenanceWindow(mk(monID, now.Add(-time.Hour), now.Add(time.Hour))); err != nil {
		t.Fatalf("创建专属窗口: %v", err)
	}
	if _, err := st.CreateMaintenanceWindow(mk(0, now.Add(time.Hour), now.Add(2*time.Hour))); err != nil {
		t.Fatalf("创建未来全局窗口: %v", err)
	}
	if _, err := st.CreateMaintenanceWindow(mk(0, now.Add(-2*time.Hour), now.Add(-time.Hour))); err != nil {
		t.Fatalf("创建过期全局窗口: %v", err)
	}
	active, w, err := st.ActiveMaintenanceWindow(monID, time.Now().UTC())
	if err != nil {
		t.Fatalf("ActiveMaintenanceWindow: %v", err)
	}
	if !active || w == nil || w.MonitorID != monID {
		t.Fatalf("期望命中专属窗口，得到 active=%v w=%+v", active, w)
	}
	active, _, err = st.ActiveMaintenanceWindow(999999, time.Now().UTC())
	if err != nil {
		t.Fatalf("ActiveMaintenanceWindow: %v", err)
	}
	if active {
		t.Fatalf("期望不存在的监控无生效窗口")
	}
	active, w, err = st.ActiveMaintenanceWindow(monID, time.Now().UTC().Add(90*time.Minute))
	if err != nil {
		t.Fatalf("ActiveMaintenanceWindow: %v", err)
	}
	if !active || w == nil || w.MonitorID != 0 {
		t.Fatalf("期望 90 分钟后命中全局窗口，得到 active=%v w=%+v", active, w)
	}
}
