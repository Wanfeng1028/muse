package store

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// newProfileTestStore 打开一个内存 SQLite，建好 profile 相关表，返回 *Store。
// 依赖 *sql.DB 是真实数据库，不 mock 被测逻辑。
func newProfileTestStore(t *testing.T) (*Store, *sql.DB) {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("打开内存数据库失败: %v", err)
	}
	db.SetMaxOpenConns(1)
	stmts := []string{
		`CREATE TABLE checks (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			monitor_id INTEGER NOT NULL,
			ok INTEGER NOT NULL,
			latency_ms INTEGER NOT NULL,
			checked_at TEXT NOT NULL
		)`,
		`CREATE TABLE incidents (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			monitor_id INTEGER NOT NULL,
			started_at TEXT NOT NULL,
			ended_at TEXT,
			downtime_sec INTEGER
		)`,
		`CREATE TABLE status_pages (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			tenant_id INTEGER NOT NULL,
			slug TEXT NOT NULL,
			title TEXT NOT NULL,
			theme TEXT NOT NULL,
			accent_color TEXT NOT NULL,
			created_at TEXT NOT NULL
		)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("建表失败: %v", err)
		}
	}
	return &Store{db: db}, db
}

func mustInsertCheck(t *testing.T, db *sql.DB, monitorID int64, ok int, latency int64, checkedAt string) {
	t.Helper()
	if _, err := db.Exec(
		`INSERT INTO checks(monitor_id, ok, latency_ms, checked_at) VALUES(?,?,?,?)`,
		monitorID, ok, latency, checkedAt,
	); err != nil {
		t.Fatalf("插入 checks 失败: %v", err)
	}
}

func TestLatencyPercentiles_Boundary(t *testing.T) {
	cases := []struct {
		name      string
		days      int
		latencies []int64
		wantP50   float64
		wantP95   float64
		wantP99   float64
	}{
		{
			name:      "空数据返回全零",
			days:      1,
			latencies: nil,
			wantP50:   0,
			wantP95:   0,
			wantP99:   0,
		},
		{
			name:      "单条数据三个分位相同",
			days:      1,
			latencies: []int64{42},
			wantP50:   42,
			wantP95:   42,
			wantP99:   42,
		},
		{
			name:      "两条数据线性插值",
			days:      1,
			latencies: []int64{10, 20},
			wantP50:   15,
			wantP95:   19.5,
			wantP99:   19.9,
		},
		{
			name:      "非法 days 归一到 1 天",
			days:      0,
			latencies: []int64{5, 15},
			wantP50:   10,
			wantP95:   14.5,
			wantP99:   14.9,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s, db := newProfileTestStore(t)
			now := time.Now().UTC().Format(time.RFC3339)
			for _, v := range tc.latencies {
				mustInsertCheck(t, db, 1, 1, v, now)
			}
			p50, p95, p99, err := s.LatencyPercentiles(1, tc.days)
			if err != nil {
				t.Fatalf("LatencyPercentiles 返回错误: %v", err)
			}
			if p50 != tc.wantP50 {
				t.Fatalf("p50 = %v, 期望 %v", p50, tc.wantP50)
			}
			if p95 != tc.wantP95 {
				t.Fatalf("p95 = %v, 期望 %v", p95, tc.wantP95)
			}
			if p99 != tc.wantP99 {
				t.Fatalf("p99 = %v, 期望 %v", p99, tc.wantP99)
			}
		})
	}
}

func TestLatencyPercentiles_OutsideWindowIgnored(t *testing.T) {
	s, db := newProfileTestStore(t)
	now := time.Now().UTC()
	mustInsertCheck(t, db, 1, 1, 10, now.Format(time.RFC3339))
	mustInsertCheck(t, db, 1, 1, 999, now.AddDate(0, 0, -30).Format(time.RFC3339))
	p50, p95, p99, err := s.LatencyPercentiles(1, 1)
	if err != nil {
		t.Fatalf("LatencyPercentiles 返回错误: %v", err)
	}
	if p50 != 10 {
		t.Fatalf("p50 = %v, 期望 10（窗口外数据被排除）", p50)
	}
	if p95 != 10 || p99 != 10 {
		t.Fatalf("p95=%v p99=%v, 期望都为 10", p95, p99)
	}
}

func TestLatencyPercentiles_QueryErrorOnMissingTable(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("打开内存数据库失败: %v", err)
	}
	s := &Store{db: db}
	p50, p95, p99, err := s.LatencyPercentiles(1, 3)
	if err == nil {
		t.Fatalf("表不存在时期望报错, 实际 nil")
	}
	if p50 != 0 || p95 != 0 || p99 != 0 {
		t.Fatalf("出错时应返回全零, 实际 p50=%v p95=%v p99=%v", p50, p95, p99)
	}
}

func TestDailyBreakdown_IncludesEmptyDaysAndBoundaries(t *testing.T) {
	s, db := newProfileTestStore(t)
	now := time.Now().UTC()
	today := now.Format("2006-01-02")
	yesterday := now.AddDate(0, 0, -1).Format("2006-01-02")

	mustInsertCheck(t, db, 1, 1, 10, today+"T01:00:00Z")
	mustInsertCheck(t, db, 1, 1, 20, today+"T02:00:00Z")
	mustInsertCheck(t, db, 1, 0, 30, today+"T03:00:00Z")
	mustInsertCheck(t, db, 1, 1, 40, yesterday+"T01:00:00Z")
	// 其他 monitor 不应混入。
	mustInsertCheck(t, db, 2, 0, 50, today+"T04:00:00Z")

	stats, err := s.DailyBreakdown(1, 3)
	if err != nil {
		t.Fatalf("DailyBreakdown 返回错误: %v", err)
	}
	if len(stats) != 3 {
		t.Fatalf("len(stats) = %d, 期望 3", len(stats))
	}
	if stats[0].Date >= stats[1].Date || stats[1].Date >= stats[2].Date {
		t.Fatalf("日期未按升序: %v", []string{stats[0].Date, stats[1].Date, stats[2].Date})
	}
	last := stats[2]
	if last.Date != today {
		t.Fatalf("最后一天 = %s, 期望 %s", last.Date, today)
	}
	if last.Checks != 3 {
		t.Fatalf("今天 Checks = %d, 期望 3", last.Checks)
	}
	if last.Failures != 1 {
		t.Fatalf("今天 Failures = %d, 期望 1", last.Failures)
	}
	wantUptime := 2.0 / 3.0 * 100.0
	if last.UptimePct != wantUptime {
		t.Fatalf("今天 UptimePct = %v, 期望 %v", last.UptimePct, wantUptime)
	}
	mid := stats[1]
	if mid.Date != yesterday {
		t.Fatalf("中间一天 = %s, 期望 %s", mid.Date, yesterday)
	}
	if mid.Checks != 1 || mid.Failures != 0 || mid.UptimePct != 100 {
		t.Fatalf("昨天统计错误: %+v", mid)
	}
	first := stats[0]
	if first.Checks != 0 || first.Failures != 0 || first.UptimePct != 100 {
		t.Fatalf("无数据那天应 Checks=0 Failures=0 UptimePct=100, 实际 %+v", first)
	}
}

func TestDailyBreakdown_NonPositiveDaysNormalized(t *testing.T) {
	s, _ := newProfileTestStore(t)
	stats, err := s.DailyBreakdown(1, 0)
	if err != nil {
		t.Fatalf("DailyBreakdown 返回错误: %v", err)
	}
	if len(stats) != 1 {
		t.Fatalf("days<=0 应归一到 1, 实际长度 %d", len(stats))
	}
	if stats[0].Checks != 0 || stats[0].UptimePct != 100 {
		t.Fatalf("空数据应 Checks=0 UptimePct=100, 实际 %+v", stats[0])
	}
}

func TestMonthlySLA_InvalidMonth(t *testing.T) {
	cases := []struct {
		name  string
		year  int
		month int
	}{
		{name: "月份为 0", year: 2024, month: 0},
		{name: "月份为 13", year: 2024, month: 13},
		{name: "月份为负", year: 2024, month: -3},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s, _ := newProfileTestStore(t)
			report, err := s.MonthlySLA(1, tc.year, tc.month)
			if err == nil {
				t.Fatalf("非法月份 %d 期望报错, 实际 nil", tc.month)
			}
			if !strings.Contains(err.Error(), "非法月份") {
				t.Fatalf("错误信息应包含 非法月份, 实际 %v", err)
			}
			if report.Target != 99.9 {
				t.Fatalf("Target = %v, 期望 99.9", report.Target)
			}
			if report.TotalChecks != 0 || report.UptimePct != 0 {
				t.Fatalf("非法月份不应查询, 实际 %+v", report)
			}
		})
	}
}

func TestMonthlySLA_NoData(t *testing.T) {
	s, _ := newProfileTestStore(t)
	report, err := s.MonthlySLA(1, 2024, 6)
	if err != nil {
		t.Fatalf("MonthlySLA 返回错误: %v", err)
	}
	if report.Month != "2024-06" {
		t.Fatalf("Month = %s, 期望 2024-06", report.Month)
	}
	if report.UptimePct != 100 {
		t.Fatalf("无数据 UptimePct = %v, 期望 100", report.UptimePct)
	}
	if report.TotalChecks != 0 || report.DownIncidents != 0 || report.TotalDowntimeSec != 0 {
		t.Fatalf("无数据应全零, 实际 %+v", report)
	}
	if !report.Met {
		t.Fatalf("无数据 UptimePct=100 应 Met=true, 实际 %+v", report)
	}
}

func TestMonthlySLA_WithClosedAndOpenIncident(t *testing.T) {
	s, db := newProfileTestStore(t)
	// 6 月共 4 次检查, 3 次成功 => 75%。
	mustInsertCheck(t, db, 1, 1, 10, "2024-06-01T00:00:00Z")
	mustInsertCheck(t, db, 1, 1, 20, "2024-06-02T00:00:00Z")
	mustInsertCheck(t, db, 1, 1, 30, "2024-06-03T00:00:00Z")
	mustInsertCheck(t, db, 1, 0, 40, "2024-06-04T00:00:00Z")
	// 5 月数据不应混入。
	mustInsertCheck(t, db, 1, 0, 50, "2024-05-31T23:59:59Z")

	// 已关闭 incident: 60 秒。
	if _, err := db.Exec(
		`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec) VALUES(?,?,?,?)`,
		1, "2024-06-04T00:00:00Z", "2024-06-04T00:01:00Z", 60,
	); err != nil {
		t.Fatalf("插入 incidents 失败: %v", err)
	}
	// 未关闭 incident: 开始时间 10 秒前, 期望按 now-started 估算, 结果 > 0。
	openStart := time.Now().UTC().Add(-10 * time.Second).Format(time.RFC3339)
	if _, err := db.Exec(
		`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec) VALUES(?,?,?,?)`,
		1, openStart, nil, nil,
	); err != nil {
		t.Fatalf("插入 incidents 失败: %v", err)
	}

	report, err := s.MonthlySLA(1, 2024, 6)
	if err != nil {
		t.Fatalf("MonthlySLA 返回错误: %v", err)
	}
	if report.TotalChecks != 4 {
		t.Fatalf("TotalChecks = %d, 期望 4", report.TotalChecks)
	}
	if report.UptimePct != 75 {
		t.Fatalf("UptimePct = %v, 期望 75", report.UptimePct)
	}
	if report.DownIncidents != 2 {
		t.Fatalf("DownIncidents = %d, 期望 2", report.DownIncidents)
	}
	if report.TotalDowntimeSec < 70 {
		t.Fatalf("TotalDowntimeSec = %d, 期望 >= 70 (60 + 未关闭估算)", report.TotalDowntimeSec)
	}
	if report.Met {
		t.Fatalf("75%% < 99.9%% 应 Met=false, 实际 %+v", report)
	}
}

func TestMonthlySLA_AllChecksOK(t *testing.T) {
	s, db := newProfileTestStore(t)
	mustInsertCheck(t, db, 1, 1, 10, "2024-07-15T00:00:00Z")
	mustInsertCheck(t, db, 1, 1, 20, "2024-07-16T00:00:00Z")
	report, err := s.MonthlySLA(1, 2024, 7)
	if err != nil {
		t.Fatalf("MonthlySLA 返回错误: %v", err)
	}
	if report.UptimePct != 100 {
		t.Fatalf("UptimePct = %v, 期望 100", report.UptimePct)
	}
	if !report.Met {
		t.Fatalf("100%% >= 99.9%% 应 Met=true, 实际 %+v", report)
	}
}

func TestCreateStatusPage_IdempotentSlugAndList(t *testing.T) {
	s, _ := newProfileTestStore(t)
	id1, err := s.CreateStatusPage(7, "main", "主状态页")
	if err != nil {
		t.Fatalf("CreateStatusPage 返回错误: %v", err)
	}
	id2, err := s.CreateStatusPage(7, "main", "主状态页")
	if err != nil {
		t.Fatalf("CreateStatusPage 第二次返回错误: %v", err)
	}
	if id1 == id2 {
		t.Fatalf("两次创建应返回不同 ID, 实际都为 %d", id1)
	}
	if _, err := s.CreateStatusPage(8, "other", "别的租户"); err != nil {
		t.Fatalf("CreateStatusPage 其他租户返回错误: %v", err)
	}

	pages, err := s.ListStatusPages(7)
	if err != nil {
		t.Fatalf("ListStatusPages 返回错误: %v", err)
	}
	if len(pages) != 2 {
		t.Fatalf("租户 7 状态页数量 = %d, 期望 2", len(pages))
	}
	if pages[0].ID >= pages[1].ID {
		t.Fatalf("应按 id 升序, 实际 %d, %d", pages[0].ID, pages[1].ID)
	}
	if pages[0].TenantID != 7 || pages[1].TenantID != 7 {
		t.Fatalf("TenantID 错误: %d, %d", pages[0].TenantID, pages[1].TenantID)
	}
	if pages[0].Slug != "main" || pages[0].Title != "主状态页" {
		t.Fatalf("第一条记录内容错误: %+v", pages[0])
	}
	if pages[0].Theme != "light" || pages[0].AccentColor != "" {
		t.Fatalf("默认 theme/accent 错误: %+v", pages[0])
	}
	if pages[0].CreatedAt == "" {
		t.Fatalf("CreatedAt 不应为空")
	}

	other, err := s.ListStatusPages(8)
	if err != nil {
		t.Fatalf("ListStatusPages 租户 8 返回错误: %v", err)
	}
	if len(other) != 1 || other[0].TenantID != 8 {
		t.Fatalf("租户 8 结果错误: %+v", other)
	}

	none, err := s.ListStatusPages(999)
	if err != nil {
		t.Fatalf("ListStatusPages 空租户返回错误: %v", err)
	}
	if len(none) != 0 {
		t.Fatalf("不存在的租户应返回空, 实际 %+v", none)
	}
}

func TestCreateStatusPage_DBFailure(t *testing.T) {
	s, db := newProfileTestStore(t)
	if _, err := db.Exec(`DROP TABLE status_pages`); err != nil {
		t.Fatalf("删除表失败: %v", err)
	}
	id, err := s.CreateStatusPage(1, "x", "标题")
	if err == nil {
		t.Fatalf("表不存在时期望报错, 实际 nil")
	}
	if id != 0 {
		t.Fatalf("出错时 ID 应为 0, 实际 %d", id)
	}
	pages, err := s.ListStatusPages(1)
	if err == nil {
		t.Fatalf("ListStatusPages 表不存在时期望报错, 实际 nil")
	}
	if pages != nil {
		t.Fatalf("出错时应返回 nil, 实际 %+v", pages)
	}
}

func TestCreateStatusPage_LongSlugAndTitle(t *testing.T) {
	s, _ := newProfileTestStore(t)
	longSlug := strings.Repeat("a", 4096)
	longTitle := strings.Repeat("标题", 2000)
	id, err := s.CreateStatusPage(3, longSlug, longTitle)
	if err != nil {
		t.Fatalf("超长字段应能写入, 实际错误: %v", err)
	}
	if id <= 0 {
		t.Fatalf("ID 应大于 0, 实际 %d", id)
	}
	pages, err := s.ListStatusPages(3)
	if err != nil {
		t.Fatalf("ListStatusPages 返回错误: %v", err)
	}
	if len(pages) != 1 {
		t.Fatalf("状态页数量 = %d, 期望 1", len(pages))
	}
	if pages[0].Slug != longSlug {
		t.Fatalf("Slug 长度 = %d, 期望 %d", len(pages[0].Slug), len(longSlug))
	}
	if pages[0].Title != longTitle {
		t.Fatalf("Title 长度 = %d, 期望 %d", len(pages[0].Title), len(longTitle))
	}
}

func TestProfileConcurrentReadsAndWrites(t *testing.T) {
	s, db := newProfileTestStore(t)
	now := time.Now().UTC().Format(time.RFC3339)
	for i := 0; i < 20; i++ {
		mustInsertCheck(t, db, 1, 1, int64(i+1), now)
	}
	if _, err := db.Exec(
		`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec) VALUES(?,?,?,?)`,
		1, "2024-08-01T00:00:00Z", "2024-08-01T00:05:00Z", 300,
	); err != nil {
		t.Fatalf("插入 incidents 失败: %v", err)
	}

	const workers = 8
	var wg sync.WaitGroup
	errCh := make(chan error, workers*4)
	start := make(chan struct{})

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			<-start
			p50, p95, p99, err := s.LatencyPercentiles(1, 1)
			if err != nil {
				errCh <- fmt.Errorf("worker %d LatencyPercentiles: %w", idx, err)
				return
			}
			if p50 <= 0 || p95 < p50 || p99 < p95 {
				errCh <- fmt.Errorf("worker %d 分位数次序错误: p50=%v p95=%v p99=%v", idx, p50, p95, p99)
				return
			}
			stats, err := s.DailyBreakdown(1, 2)
			if err != nil {
				errCh <- fmt.Errorf("worker %d DailyBreakdown: %w", idx, err)
				return
			}
			if len(stats) != 2 {
				errCh <- fmt.Errorf("worker %d DailyBreakdown 长度 = %d", idx, len(stats))
				return
			}
			if stats[1].Checks != 20 {
				errCh <- fmt.Errorf("worker %d 今日 Checks = %d, 期望 20", idx, stats[1].Checks)
				return
			}
			report, err := s.MonthlySLA(1, 2024, 8)
			if err != nil {
				errCh <- fmt.Errorf("worker %d MonthlySLA: %w", idx, err)
				return
			}
			if report.DownIncidents != 1 || report.TotalDowntimeSec != 300 {
				errCh <- fmt.Errorf("worker %d MonthlySLA 数据错误: %+v", idx, report)
				return
			}
			id, err := s.CreateStatusPage(int64(idx), fmt.Sprintf("slug-%d", idx), "标题")
			if err != nil {
				errCh <- fmt.Errorf("worker %d CreateStatusPage: %w", idx, err)
				return
			}
			if id <= 0 {
				errCh <- fmt.Errorf("worker %d 返回 ID = %d", idx, id)
				return
			}
		}(i)
	}
	close(start)
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != nil {
			t.Fatalf("并发执行失败: %v", err)
		}
	}

	// 全部写入完成后逐个租户校验。
	for i := 0; i < workers; i++ {
		pages, err := s.ListStatusPages(int64(i))
		if err != nil {
			t.Fatalf("ListStatusPages(%d) 错误: %v", i, err)
		}
		if len(pages) != 1 {
			t.Fatalf("租户 %d 状态页数量 = %d, 期望 1", i, len(pages))
		}
		if pages[0].Slug != fmt.Sprintf("slug-%d", i) {
			t.Fatalf("租户 %d Slug = %s", i, pages[0].Slug)
		}
	}
}

func TestProfileIdempotentReads(t *testing.T) {
	s, db := newProfileTestStore(t)
	now := time.Now().UTC().Format(time.RFC3339)
	mustInsertCheck(t, db, 1, 1, 100, now)
	mustInsertCheck(t, db, 1, 1, 200, now)
	mustInsertCheck(t, db, 1, 0, 300, now)

	p50a, p95a, p99a, err := s.LatencyPercentiles(1, 1)
	if err != nil {
		t.Fatalf("首次 LatencyPercentiles 错误: %v", err)
	}
	p50b, p95b, p99b, err := s.LatencyPercentiles(1, 1)
	if err != nil {
		t.Fatalf("二次 LatencyPercentiles 错误: %v", err)
	}
	if p50a != p50b || p95a != p95b || p99a != p99b {
		t.Fatalf("重复读取结果应一致: (%v,%v,%v) vs (%v,%v,%v)", p50a, p95a, p99a, p50b, p95b, p99b)
	}

	sa, err := s.DailyBreakdown(1, 2)
	if err != nil {
		t.Fatalf("首次 DailyBreakdown 错误: %v", err)
	}
	sb, err := s.DailyBreakdown(1, 2)
	if err != nil {
		t.Fatalf("二次 DailyBreakdown 错误: %v", err)
	}
	if len(sa) != len(sb) {
		t.Fatalf("长度不一致: %d vs %d", len(sa), len(sb))
	}
	for i := range sa {
		if sa[i] != sb[i] {
			t.Fatalf("第 %d 天不一致: %+v vs %+v", i, sa[i], sb[i])
		}
	}

	ra, err := s.MonthlySLA(1, 2024, 9)
	if err != nil {
		t.Fatalf("首次 MonthlySLA 错误: %v", err)
	}
	rb, err := s.MonthlySLA(1, 2024, 9)
	if err != nil {
		t.Fatalf("二次 MonthlySLA 错误: %v", err)
	}
	if ra != rb {
		t.Fatalf("重复 SLA 结果应一致: %+v vs %+v", ra, rb)
	}
}

func TestProfileErrorPropagationOnClosedDB(t *testing.T) {
	s, db := newProfileTestStore(t)
	if err := db.Close(); err != nil {
		t.Fatalf("关闭数据库失败: %v", err)
	}
	if _, _, _, err := s.LatencyPercentiles(1, 1); err == nil {
		t.Fatalf("关闭 DB 后 LatencyPercentiles 应报错")
	}
	if _, err := s.DailyBreakdown(1, 1); err == nil {
		t.Fatalf("关闭 DB 后 DailyBreakdown 应报错")
	}
	if _, err := s.MonthlySLA(1, 2024, 1); err == nil {
		t.Fatalf("关闭 DB 后 MonthlySLA 应报错")
	}
	if _, err := s.CreateStatusPage(1, "x", "y"); err == nil {
		t.Fatalf("关闭 DB 后 CreateStatusPage 应报错")
	}
	if _, err := s.ListStatusPages(1); err == nil {
		t.Fatalf("关闭 DB 后 ListStatusPages 应报错")
	}
	_ = errors.New
}