// Package store 提供 Sentinel 数据访问层。
package store

import (
	"database/sql"
	"errors"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"sentinel/internal/db"
)

// newTestStore 在临时目录创建测试用 Store。
func newTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	d, err := db.Open(dir + "/test.db")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = d.Close() })
	return New(d)
}

// sampleMonitor 构造一个合法 Monitor。
func sampleMonitor(name string) Monitor {
	now := time.Now().UTC().Format(time.RFC3339)
	return Monitor{
		Name:           name,
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
		WebhookURL:     "",
		CreatedAt:      now,
		UpdatedAt:      now,
	}
}

// TestMonitorCRUD 测试监控目标的增删改查。
func TestMonitorCRUD(t *testing.T) {
	s := newTestStore(t)

	id, err := s.CreateMonitor(sampleMonitor("m1"))
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if id <= 0 {
		t.Fatalf("expected id>0, got %d", id)
	}

	got, err := s.GetMonitor(id)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if got.Name != "m1" || got.Kind != "http" || got.Target != "http://example.com" {
		t.Fatalf("unexpected monitor: %+v", got)
	}
	if got.ExpectedStatus != 200 || got.TimeoutSec != 10 || got.IntervalSec != 60 || got.Enabled != 1 {
		t.Fatalf("unexpected fields: %+v", got)
	}

	got.Name = "m1-renamed"
	got.IntervalSec = 120
	if err := s.UpdateMonitor(id, got); err != nil {
		t.Fatalf("update: %v", err)
	}
	after, err := s.GetMonitor(id)
	if err != nil {
		t.Fatalf("get after update: %v", err)
	}
	if after.Name != "m1-renamed" || after.IntervalSec != 120 {
		t.Fatalf("update not applied: %+v", after)
	}

	if _, err := s.CreateMonitor(sampleMonitor("m2")); err != nil {
		t.Fatalf("create m2: %v", err)
	}
	list, err := s.ListMonitors()
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("expected 2 monitors, got %d", len(list))
	}

	if err := s.DeleteMonitor(id); err != nil {
		t.Fatalf("delete: %v", err)
	}
	if _, err := s.GetMonitor(id); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("expected sql.ErrNoRows, got %v", err)
	}
}

// TestChecksAndLast 测试检查记录插入与最新查询。
func TestChecksAndLast(t *testing.T) {
	s := newTestStore(t)
	id, err := s.CreateMonitor(sampleMonitor("m1"))
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	base := time.Now().UTC()
	t1 := base.Add(-2 * time.Minute).Format(time.RFC3339)
	t2 := base.Add(-1 * time.Minute).Format(time.RFC3339)

	if _, err := s.InsertCheck(Check{MonitorID: id, CheckedAt: t1, Ok: 1, LatencyMs: 100, Error: ""}); err != nil {
		t.Fatalf("insert c1: %v", err)
	}
	if _, err := s.InsertCheck(Check{MonitorID: id, CheckedAt: t2, Ok: 0, LatencyMs: 200, Error: "boom"}); err != nil {
		t.Fatalf("insert c2: %v", err)
	}

	last, err := s.LastCheck(id)
	if err != nil {
		t.Fatalf("last: %v", err)
	}
	if last == nil {
		t.Fatalf("expected last check, got nil")
	}
	if last.Ok != 0 {
		t.Fatalf("expected latest ok=0, got %d", last.Ok)
	}

	limited, err := s.ListChecks(id, 1)
	if err != nil {
		t.Fatalf("list checks: %v", err)
	}
	if len(limited) != 1 {
		t.Fatalf("expected 1 check, got %d", len(limited))
	}
}

// TestStats 测试统计与事件开闭。
func TestStats(t *testing.T) {
	s := newTestStore(t)
	id, err := s.CreateMonitor(sampleMonitor("m1"))
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	base := time.Now().UTC()
	oks := []int{1, 1, 1, 0}
	lats := []int64{100, 200, 300, 400}
	for i := 0; i < 4; i++ {
		ts := base.Add(time.Duration(i) * time.Minute).Format(time.RFC3339)
		if _, err := s.InsertCheck(Check{MonitorID: id, CheckedAt: ts, Ok: oks[i], LatencyMs: lats[i]}); err != nil {
			t.Fatalf("insert check %d: %v", i, err)
		}
	}

	uptime, avg, total, down, err := s.MonitorStats(id, 30)
	if err != nil {
		t.Fatalf("stats: %v", err)
	}
	if total != 4 {
		t.Fatalf("expected total 4, got %d", total)
	}
	if uptime != 75.0 {
		t.Fatalf("expected uptime 75.0, got %v", uptime)
	}
	if avg != 250.0 {
		t.Fatalf("expected avg 250.0, got %v", avg)
	}

	startedAt := base.Format(time.RFC3339)
	if _, err := s.OpenIncident(id, startedAt, "boom"); err != nil {
		t.Fatalf("open incident: %v", err)
	}
	_, _, _, down, err = s.MonitorStats(id, 30)
	if err != nil {
		t.Fatalf("stats2: %v", err)
	}
	if down != 1 {
		t.Fatalf("expected down incidents 1, got %d", down)
	}

	if err := s.CloseOpenIncident(id, base.Add(time.Minute).Format(time.RFC3339), 60); err != nil {
		t.Fatalf("close incident: %v", err)
	}
	if _, err := s.OpenIncidentStartedAt(id); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("expected sql.ErrNoRows after close, got %v", err)
	}
}

// TestOverview 测试概览统计。
func TestOverview(t *testing.T) {
	s := newTestStore(t)

	m1 := sampleMonitor("m1")
	id1, err := s.CreateMonitor(m1)
	if err != nil {
		t.Fatalf("create m1: %v", err)
	}

	m2 := sampleMonitor("m2")
	m2.Enabled = 0
	id2, err := s.CreateMonitor(m2)
	if err != nil {
		t.Fatalf("create m2: %v", err)
	}

	ts := time.Now().UTC().Format(time.RFC3339)
	if _, err := s.InsertCheck(Check{MonitorID: id1, CheckedAt: ts, Ok: 1, LatencyMs: 10}); err != nil {
		t.Fatalf("insert c1: %v", err)
	}
	if _, err := s.InsertCheck(Check{MonitorID: id2, CheckedAt: ts, Ok: 0, LatencyMs: 20, Error: "x"}); err != nil {
		t.Fatalf("insert c2: %v", err)
	}

	total, enabled, up, down, unknown, checks24h, incidents7d, err := s.Overview()
	if err != nil {
		t.Fatalf("overview: %v", err)
	}
	if total != 2 {
		t.Fatalf("total expected 2, got %d", total)
	}
	if enabled != 1 {
		t.Fatalf("enabled expected 1, got %d", enabled)
	}
	if up != 1 {
		t.Fatalf("up expected 1, got %d", up)
	}
	if down != 1 {
		t.Fatalf("down expected 1, got %d", down)
	}
	if unknown != 0 {
		t.Fatalf("unknown expected 0, got %d", unknown)
	}
	if checks24h != 2 {
		t.Fatalf("checks24h expected 2, got %d", checks24h)
	}
	if incidents7d != 0 {
		t.Fatalf("incidents7d expected 0, got %d", incidents7d)
	}
}

// TestCascade 测试删除监控级联删除检查与事件。
func TestCascade(t *testing.T) {
	s := newTestStore(t)
	id, err := s.CreateMonitor(sampleMonitor("m1"))
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	ts := time.Now().UTC().Format(time.RFC3339)
	if _, err := s.InsertCheck(Check{MonitorID: id, CheckedAt: ts, Ok: 1, LatencyMs: 10}); err != nil {
		t.Fatalf("insert check: %v", err)
	}
	if _, err := s.OpenIncident(id, ts, "boom"); err != nil {
		t.Fatalf("open incident: %v", err)
	}

	if err := s.DeleteMonitor(id); err != nil {
		t.Fatalf("delete: %v", err)
	}

	checks, err := s.ListChecks(id, 100)
	if err != nil {
		t.Fatalf("list checks: %v", err)
	}
	if len(checks) != 0 {
		t.Fatalf("expected 0 checks after cascade, got %d", len(checks))
	}

	incs, err := s.ListIncidents(id, 100)
	if err != nil {
		t.Fatalf("list incidents: %v", err)
	}
	if len(incs) != 0 {
		t.Fatalf("expected 0 incidents after cascade, got %d", len(incs))
	}
}
