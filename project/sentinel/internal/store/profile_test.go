package store

import (
	"testing"
	"time"
)

// seedMonitor 创建一个 monitor 并返回其 ID。
func seedMonitor(t *testing.T, s *Store) int64 {
	t.Helper()
	id, err := s.CreateMonitor(Monitor{
		Name:           "test-mon",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
		IsPublic:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	return id
}

// insertCheckAt 插入一条指定时间的检查记录。
func insertCheckAt(t *testing.T, s *Store, monitorID int64, at time.Time, ok int, latencyMs int64) {
	t.Helper()
	c := Check{
		MonitorID: monitorID,
		CheckedAt: at.UTC().Format(time.RFC3339),
		Ok:        ok,
		LatencyMs: latencyMs,
	}
	if _, err := s.InsertCheck(c); err != nil {
		t.Fatalf("InsertCheck: %v", err)
	}
}

func TestLatencyPercentiles(t *testing.T) {
	s := newTestStore(t)
	mid := seedMonitor(t, s)

	now := time.Now().UTC()
	// 插入 1..100 作为延迟（全部 ok）。
	for i := 1; i <= 100; i++ {
		insertCheckAt(t, s, mid, now.Add(-time.Duration(i)*time.Minute), 1, int64(i))
	}

	p50, p95, p99, err := s.LatencyPercentiles(mid, 30)
	if err != nil {
		t.Fatalf("LatencyPercentiles: %v", err)
	}
	// 升序数组 1..100，使用 (n-1) 线性插值：
	// p50 -> rank=49.5 -> 50 + (51-50)*0.5 = 50.5
	if p50 < 50.4 || p50 > 50.6 {
		t.Errorf("p50 期望约 50.5，实际 %v", p50)
	}
	// p95 -> rank=94.05 -> 95 + (96-95)*0.05 = 95.05
	if p95 < 95.0 || p95 > 95.1 {
		t.Errorf("p95 期望约 95.05，实际 %v", p95)
	}
	// p99 -> rank=98.01 -> 99 + (100-99)*0.01 = 99.01
	if p99 < 99.0 || p99 > 99.1 {
		t.Errorf("p99 期望约 99.01，实际 %v", p99)
	}

	// 无数据场景。
	empty := newTestStore(t)
	emid := seedMonitor(t, empty)
	e50, e95, e99, err := empty.LatencyPercentiles(emid, 30)
	if err != nil {
		t.Fatalf("empty LatencyPercentiles: %v", err)
	}
	if e50 != 0 || e95 != 0 || e99 != 0 {
		t.Errorf("无数据应返回 0，实际 %v %v %v", e50, e95, e99)
	}
}

func TestDailyBreakdown(t *testing.T) {
	s := newTestStore(t)
	mid := seedMonitor(t, s)

	now := time.Now().UTC()
	today := time.Date(now.Year(), now.Month(), now.Day(), 12, 0, 0, 0, time.UTC)
	yesterday := today.AddDate(0, 0, -1)
	// 昨天：3 条，全部失败。
	for i := 0; i < 3; i++ {
		insertCheckAt(t, s, mid, yesterday.Add(time.Duration(i)*time.Minute), 0, 100)
	}
	// 今天：4 条，3 ok 1 fail。
	insertCheckAt(t, s, mid, today.Add(1*time.Minute), 1, 50)
	insertCheckAt(t, s, mid, today.Add(2*time.Minute), 1, 60)
	insertCheckAt(t, s, mid, today.Add(3*time.Minute), 1, 70)
	insertCheckAt(t, s, mid, today.Add(4*time.Minute), 0, 80)

	stats, err := s.DailyBreakdown(mid, 7)
	if err != nil {
		t.Fatalf("DailyBreakdown: %v", err)
	}
	if len(stats) != 7 {
		t.Fatalf("期望 7 天，实际 %d", len(stats))
	}
	// 校验升序。
	for i := 1; i < len(stats); i++ {
		if stats[i-1].Date >= stats[i].Date {
			t.Fatalf("日期未升序: %v", stats)
		}
	}
	// 找到昨天与今天。
	yKey := yesterday.Format("2006-01-02")
	tKey := today.Format("2006-01-02")
	var yStat, tStat *DayStat
	for i := range stats {
		if stats[i].Date == yKey {
			yStat = &stats[i]
		}
		if stats[i].Date == tKey {
			tStat = &stats[i]
		}
	}
	if yStat == nil || tStat == nil {
		t.Fatalf("未找到昨天或今天的统计")
	}
	if yStat.UptimePct != 0 {
		t.Errorf("昨天应 uptime=0，实际 %v", yStat.UptimePct)
	}
	if yStat.Checks != 3 || yStat.Failures != 3 {
		t.Errorf("昨天 checks/fails 期望 3/3，实际 %d/%d", yStat.Checks, yStat.Failures)
	}
	// 今天 4 条，1 失败 => uptime = 75。
	if tStat.Checks != 4 || tStat.Failures != 1 {
		t.Errorf("今天 checks/fails 期望 4/1，实际 %d/%d", tStat.Checks, tStat.Failures)
	}
	if tStat.UptimePct < 74.9 || tStat.UptimePct > 75.1 {
		t.Errorf("今天 uptime 期望 75，实际 %v", tStat.UptimePct)
	}
}

func TestMonthlySLA(t *testing.T) {
	s := newTestStore(t)
	mid := seedMonitor(t, s)

	// 使用固定的过去月份：2024-03。
	start := time.Date(2024, 3, 1, 0, 0, 0, 0, time.UTC)
	// 该月内插入 10 条 checks，9 ok 1 fail => uptime 90。
	for i := 0; i < 9; i++ {
		insertCheckAt(t, s, mid, start.Add(time.Duration(i)*time.Hour), 1, 100)
	}
	insertCheckAt(t, s, mid, start.Add(9*time.Hour), 0, 100)

	// 两条已关闭 incidents：300 + 200 = 500s。
	// 一条未关闭 incident（started 在本月内，downtime 为 NULL），估算 now-started。
	// 为让结果可预测，构造 downtime_sec 显式的情况，并在另一个测试覆盖未关闭分支。

	// 直接插入 incidents 使用原生 SQL。
	// 已关闭：3 月 5 日。
	_, err := s.db.Exec(
		`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error)
		 VALUES(?,?,?,?,?)`,
		mid,
		time.Date(2024, 3, 5, 1, 0, 0, 0, time.UTC).Format(time.RFC3339),
		time.Date(2024, 3, 5, 1, 5, 0, 0, time.UTC).Format(time.RFC3339),
		int64(300),
		"",
	)
	if err != nil {
		t.Fatalf("insert incident1: %v", err)
	}
	_, err = s.db.Exec(
		`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error)
		 VALUES(?,?,?,?,?)`,
		mid,
		time.Date(2024, 3, 10, 2, 0, 0, 0, time.UTC).Format(time.RFC3339),
		time.Date(2024, 3, 10, 2, 3, 20, 0, time.UTC).Format(time.RFC3339),
		int64(200),
		"",
	)
	if err != nil {
		t.Fatalf("insert incident2: %v", err)
	}
	// 跨月 incident：4 月的（不应计入 3 月）。
	_, err = s.db.Exec(
		`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error)
		 VALUES(?,?,?,?,?)`,
		mid,
		time.Date(2024, 4, 2, 1, 0, 0, 0, time.UTC).Format(time.RFC3339),
		time.Date(2024, 4, 2, 1, 5, 0, 0, time.UTC).Format(time.RFC3339),
		int64(999),
		"",
	)
	if err != nil {
		t.Fatalf("insert incident3: %v", err)
	}

	rep, err := s.MonthlySLA(mid, 2024, 3)
	if err != nil {
		t.Fatalf("MonthlySLA: %v", err)
	}
	if rep.Month != "2024-03" {
		t.Errorf("month 期望 2024-03，实际 %s", rep.Month)
	}
	if rep.TotalChecks != 10 {
		t.Errorf("total checks 期望 10，实际 %d", rep.TotalChecks)
	}
	if rep.UptimePct < 89.9 || rep.UptimePct > 90.1 {
		t.Errorf("uptime 期望 90，实际 %v", rep.UptimePct)
	}
	if rep.DownIncidents != 2 {
		t.Errorf("down incidents 期望 2，实际 %d", rep.DownIncidents)
	}
	if rep.TotalDowntimeSec != 500 {
		t.Errorf("downtime 期望 500，实际 %d", rep.TotalDowntimeSec)
	}
	if rep.Target != 99.9 {
		t.Errorf("target 期望 99.9，实际 %v", rep.Target)
	}
	if rep.Met {
		t.Errorf("uptime 90 < 99.9，Met 应为 false")
	}
}

func TestStatusPageCRUDAndAddIdempotent(t *testing.T) {
	s := newTestStore(t)
	mid := seedMonitor(t, s)

	// Create。
	id, err := s.CreateStatusPage(1, "main", "主状态页")
	if err != nil {
		t.Fatalf("CreateStatusPage: %v", err)
	}
	if id <= 0 {
		t.Fatalf("CreateStatusPage 返回非法 ID: %d", id)
	}

	// Get。
	got, err := s.GetStatusPage(id)
	if err != nil {
		t.Fatalf("GetStatusPage: %v", err)
	}
	if got.Slug != "main" || got.Title != "主状态页" || got.TenantID != 1 {
		t.Errorf("GetStatusPage 内容不符: %+v", got)
	}

	// GetBySlug。
	got2, err := s.GetStatusPageBySlug("main")
	if err != nil {
		t.Fatalf("GetStatusPageBySlug: %v", err)
	}
	if got2.ID != id {
		t.Errorf("BySlug ID 期望 %d，实际 %d", id, got2.ID)
	}

	// List。
	list, err := s.ListStatusPages(1)
	if err != nil {
		t.Fatalf("ListStatusPages: %v", err)
	}
	if len(list) != 1 || list[0].ID != id {
		t.Errorf("ListStatusPages 结果不符: %+v", list)
	}

	// AddMonitorToPage 幂等：加两次不应报错。
	if err := s.AddMonitorToPage(id, mid); err != nil {
		t.Fatalf("AddMonitorToPage 第一次: %v", err)
	}
	if err := s.AddMonitorToPage(id, mid); err != nil {
		t.Fatalf("AddMonitorToPage 第二次(幂等): %v", err)
	}
	mons, err := s.ListPageMonitors(id)
	if err != nil {
		t.Fatalf("ListPageMonitors: %v", err)
	}
	if len(mons) != 1 || mons[0].ID != mid {
		t.Errorf("ListPageMonitors 期望 1 个 monitor，实际 %+v", mons)
	}

	// Remove。
	if err := s.RemoveMonitorFromPage(id, mid); err != nil {
		t.Fatalf("RemoveMonitorFromPage: %v", err)
	}
	mons, err = s.ListPageMonitors(id)
	if err != nil {
		t.Fatalf("ListPageMonitors after remove: %v", err)
	}
	if len(mons) != 0 {
		t.Errorf("移除后应为空，实际 %+v", mons)
	}

	// Delete。
	if err := s.DeleteStatusPage(id); err != nil {
		t.Fatalf("DeleteStatusPage: %v", err)
	}
	if _, err := s.GetStatusPage(id); err == nil {
		t.Errorf("删除后 GetStatusPage 应报错")
	}
}
