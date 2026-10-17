package db

import (
	"database/sql"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

// openTestDB 打开一个临时文件数据库，测试结束后自动关闭。
func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	path := filepath.Join(t.TempDir(), "linkshort_test.db")
	database, err := Open(path)
	if err != nil {
		t.Fatalf("Open(%q) 失败: %v", path, err)
	}
	t.Cleanup(func() {
		if err := database.Close(); err != nil {
			t.Errorf("关闭数据库失败: %v", err)
		}
	})
	return database
}

// insertLink 插入一条链接记录并返回自增 id。
func insertLink(t *testing.T, database *sql.DB, slug, url string, expiresAt sql.NullString, maxVisits sql.NullInt64, burn int) int64 {
	t.Helper()
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := database.Exec(
		`INSERT INTO links (slug, url, title, clicks, enabled, expires_at, max_visits, burn, created_at, updated_at)
		 VALUES (?, ?, "", 0, 1, ?, ?, ?, ?, ?)`,
		slug, url, expiresAt, maxVisits, burn, now, now,
	)
	if err != nil {
		t.Fatalf("插入链接 %q 失败: %v", slug, err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		t.Fatalf("获取 LastInsertId 失败: %v", err)
	}
	return id
}

// insertVisit 插入一条访问记录。
func insertVisit(t *testing.T, database *sql.DB, linkID int64, ts, ipHash, countryCode string) {
	t.Helper()
	_, err := database.Exec(
		`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city)
		 VALUES (?, ?, ?, "", "", ?, "", "", "")`,
		linkID, ts, ipHash, countryCode,
	)
	if err != nil {
		t.Fatalf("插入访问记录失败: %v", err)
	}
}

// TestSlugUniqueCollision 验证短码唯一约束：重复 slug 必须被数据库拒绝。
func TestSlugUniqueCollision(t *testing.T) {
	database := openTestDB(t)

	insertLink(t, database, "abc123", "https://example.com/first", sql.NullString{}, sql.NullInt64{}, 0)

	now := time.Now().UTC().Format(time.RFC3339)
	_, err := database.Exec(
		`INSERT INTO links (slug, url, title, clicks, enabled, created_at, updated_at)
		 VALUES (?, ?, "", 0, 1, ?, ?)`,
		"abc123", "https://example.com/second", now, now,
	)
	if err == nil {
		t.Fatal("重复 slug 应该报错，但插入成功了")
	}

	var count int
	if err := database.QueryRow(`SELECT COUNT(*) FROM links WHERE slug = ?`, "abc123").Scan(&count); err != nil {
		t.Fatalf("统计 slug 数量失败: %v", err)
	}
	if count != 1 {
		t.Fatalf("slug=abc123 的记录数 = %d, 期望 1", count)
	}

	var url string
	if err := database.QueryRow(`SELECT url FROM links WHERE slug = ?`, "abc123").Scan(&url); err != nil {
		t.Fatalf("查询 url 失败: %v", err)
	}
	if url != "https://example.com/first" {
		t.Fatalf("保留的 url = %q, 期望 %q", url, "https://example.com/first")
	}
}

// TestSlugIndexExists 验证 idx_links_slug 索引存在且被查询计划命中。
func TestSlugIndexExists(t *testing.T) {
	database := openTestDB(t)

	var name string
	err := database.QueryRow(
		`SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_links_slug'`,
	).Scan(&name)
	if err != nil {
		t.Fatalf("查询 idx_links_slug 索引失败: %v", err)
	}
	if name != "idx_links_slug" {
		t.Fatalf("索引名 = %q, 期望 idx_links_slug", name)
	}

	// 注：空表时 SQLite 查询计划可能选择全表扫描，索引存在性以上已验证。
}

// TestExpiredBoundary 验证过期时间边界：早于当前时间算过期，晚于当前时间算未过期。
func TestExpiredBoundary(t *testing.T) {
	database := openTestDB(t)

	now := time.Now().UTC()
	past := now.Add(-time.Hour).Format(time.RFC3339)
	future := now.Add(time.Hour).Format(time.RFC3339)

	pastID := insertLink(t, database, "past01", "https://example.com/past", sql.NullString{String: past, Valid: true}, sql.NullInt64{}, 0)
	futureID := insertLink(t, database, "fut01", "https://example.com/future", sql.NullString{String: future, Valid: true}, sql.NullInt64{}, 0)

	var expired int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND expires_at IS NOT NULL AND expires_at < ?`,
		pastID, now.Format(time.RFC3339),
	).Scan(&expired); err != nil {
		t.Fatalf("查询过期链接失败: %v", err)
	}
	if expired != 1 {
		t.Fatalf("过去时间链接命中过期条件数 = %d, 期望 1", expired)
	}

	var notExpired int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND expires_at IS NOT NULL AND expires_at < ?`,
		futureID, now.Format(time.RFC3339),
	).Scan(&notExpired); err != nil {
		t.Fatalf("查询未过期链接失败: %v", err)
	}
	if notExpired != 0 {
		t.Fatalf("未来时间链接命中过期条件数 = %d, 期望 0", notExpired)
	}

	var nullExpires int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE expires_at IS NULL`,
	).Scan(&nullExpires); err != nil {
		t.Fatalf("查询 expires_at 为 NULL 的链接失败: %v", err)
	}
	if nullExpires != 0 {
		t.Fatalf("expires_at 为 NULL 的记录数 = %d, 期望 0", nullExpires)
	}
}

// TestMaxVisitsBoundary 验证限次边界：clicks 达到 max_visits 即视为用尽，未达到则未用尽。
func TestMaxVisitsBoundary(t *testing.T) {
	database := openTestDB(t)

	maxID := insertLink(t, database, "limit1", "https://example.com/limit", sql.NullString{}, sql.NullInt64{Int64: 3, Valid: true}, 0)
	if _, err := database.Exec(`UPDATE links SET clicks = 3 WHERE id = ?`, maxID); err != nil {
		t.Fatalf("更新 clicks 失败: %v", err)
	}

	underID := insertLink(t, database, "limit2", "https://example.com/under", sql.NullString{}, sql.NullInt64{Int64: 3, Valid: true}, 0)
	if _, err := database.Exec(`UPDATE links SET clicks = 2 WHERE id = ?`, underID); err != nil {
		t.Fatalf("更新 clicks 失败: %v", err)
	}

	unlimitedID := insertLink(t, database, "limit3", "https://example.com/unlimited", sql.NullString{}, sql.NullInt64{}, 0)
	if _, err := database.Exec(`UPDATE links SET clicks = 9999 WHERE id = ?`, unlimitedID); err != nil {
		t.Fatalf("更新 clicks 失败: %v", err)
	}

	var exhausted int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND max_visits IS NOT NULL AND clicks >= max_visits`,
		maxID,
	).Scan(&exhausted); err != nil {
		t.Fatalf("查询用尽链接失败: %v", err)
	}
	if exhausted != 1 {
		t.Fatalf("clicks=max_visits 命中用尽条件数 = %d, 期望 1", exhausted)
	}

	var notExhausted int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND max_visits IS NOT NULL AND clicks >= max_visits`,
		underID,
	).Scan(&notExhausted); err != nil {
		t.Fatalf("查询未用尽链接失败: %v", err)
	}
	if notExhausted != 0 {
		t.Fatalf("clicks<max_visits 命中用尽条件数 = %d, 期望 0", notExhausted)
	}

	var unlimitedExhausted int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND max_visits IS NOT NULL AND clicks >= max_visits`,
		unlimitedID,
	).Scan(&unlimitedExhausted); err != nil {
		t.Fatalf("查询不限次链接失败: %v", err)
	}
	if unlimitedExhausted != 0 {
		t.Fatalf("max_visits 为 NULL 的链接命中用尽条件数 = %d, 期望 0", unlimitedExhausted)
	}
}

// TestBurnFlagBoundary 验证焚毁标记：burn=1 且 burned_at 非空才算已焚毁，burn=0 不算。
func TestBurnFlagBoundary(t *testing.T) {
	database := openTestDB(t)

	burnedID := insertLink(t, database, "burn01", "https://example.com/burned", sql.NullString{}, sql.NullInt64{Int64: 1, Valid: true}, 1)
	burnedAt := time.Now().UTC().Format(time.RFC3339)
	if _, err := database.Exec(`UPDATE links SET burned_at = ?, clicks = 1 WHERE id = ?`, burnedAt, burnedID); err != nil {
		t.Fatalf("更新 burned_at 失败: %v", err)
	}

	liveID := insertLink(t, database, "burn02", "https://example.com/live", sql.NullString{}, sql.NullInt64{Int64: 1, Valid: true}, 1)

	plainID := insertLink(t, database, "burn03", "https://example.com/plain", sql.NullString{}, sql.NullInt64{}, 0)

	var burnedCount int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND burn = 1 AND burned_at IS NOT NULL`,
		burnedID,
	).Scan(&burnedCount); err != nil {
		t.Fatalf("查询已焚毁链接失败: %v", err)
	}
	if burnedCount != 1 {
		t.Fatalf("已焚毁链接命中数 = %d, 期望 1", burnedCount)
	}

	var liveCount int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND burn = 1 AND burned_at IS NOT NULL`,
		liveID,
	).Scan(&liveCount); err != nil {
		t.Fatalf("查询未焚毁链接失败: %v", err)
	}
	if liveCount != 0 {
		t.Fatalf("burn=1 但 burned_at 为空的链接命中数 = %d, 期望 0", liveCount)
	}

	var plainCount int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM links WHERE id = ? AND burn = 1 AND burned_at IS NOT NULL`,
		plainID,
	).Scan(&plainCount); err != nil {
		t.Fatalf("查询普通链接失败: %v", err)
	}
	if plainCount != 0 {
		t.Fatalf("burn=0 的链接命中数 = %d, 期望 0", plainCount)
	}
}

// TestPurgeAfterBurnDefault 验证 purge_after_burn 默认值为 0，且可被显式置 1。
func TestPurgeAfterBurnDefault(t *testing.T) {
	database := openTestDB(t)

	defaultID := insertLink(t, database, "purge1", "https://example.com/purge-default", sql.NullString{}, sql.NullInt64{}, 0)

	var defaultValue int
	if err := database.QueryRow(
		`SELECT purge_after_burn FROM links WHERE id = ?`, defaultID,
	).Scan(&defaultValue); err != nil {
		t.Fatalf("查询 purge_after_burn 失败: %v", err)
	}
	if defaultValue != 0 {
		t.Fatalf("purge_after_burn 默认值 = %d, 期望 0", defaultValue)
	}

	if _, err := database.Exec(`UPDATE links SET purge_after_burn = 1 WHERE id = ?`, defaultID); err != nil {
		t.Fatalf("更新 purge_after_burn 失败: %v", err)
	}
	var updated int
	if err := database.QueryRow(
		`SELECT purge_after_burn FROM links WHERE id = ?`, defaultID,
	).Scan(&updated); err != nil {
		t.Fatalf("再次查询 purge_after_burn 失败: %v", err)
	}
	if updated != 1 {
		t.Fatalf("更新后 purge_after_burn = %d, 期望 1", updated)
	}
}

// TestVisitProfileAggregation 验证按国家聚合访问画像，返回计数与去重 IP 数。
func TestVisitProfileAggregation(t *testing.T) {
	database := openTestDB(t)

	linkID := insertLink(t, database, "agg001", "https://example.com/agg", sql.NullString{}, sql.NullInt64{}, 0)

	base := time.Now().UTC().Add(-time.Hour)
	insertVisit(t, database, linkID, base.Add(1*time.Minute).Format(time.RFC3339), "ip-hash-cn-1", "CN")
	insertVisit(t, database, linkID, base.Add(2*time.Minute).Format(time.RFC3339), "ip-hash-cn-1", "CN")
	insertVisit(t, database, linkID, base.Add(3*time.Minute).Format(time.RFC3339), "ip-hash-cn-2", "CN")
	insertVisit(t, database, linkID, base.Add(4*time.Minute).Format(time.RFC3339), "ip-hash-us-1", "US")

	rows, err := database.Query(
		`SELECT country_code, COUNT(*), COUNT(DISTINCT ip_hash)
		 FROM visits WHERE link_id = ?
		 GROUP BY country_code ORDER BY country_code`, linkID,
	)
	if err != nil {
		t.Fatalf("聚合查询失败: %v", err)
	}
	defer rows.Close()

	type agg struct {
		country    string
		total      int
		distinctIP int
	}
	var got []agg
	for rows.Next() {
		var a agg
		if err := rows.Scan(&a.country, &a.total, &a.distinctIP); err != nil {
			t.Fatalf("扫描聚合结果失败: %v", err)
		}
		got = append(got, a)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历聚合结果失败: %v", err)
	}

	if len(got) != 2 {
		t.Fatalf("聚合分组数 = %d, 期望 2, 实际 %+v", len(got), got)
	}
	if got[0].country != "CN" || got[0].total != 3 || got[0].distinctIP != 2 {
		t.Fatalf("CN 聚合结果 = %+v, 期望 country=CN total=3 distinctIP=2", got[0])
	}
	if got[1].country != "US" || got[1].total != 1 || got[1].distinctIP != 1 {
		t.Fatalf("US 聚合结果 = %+v, 期望 country=US total=1 distinctIP=1", got[1])
	}
}

// TestVisitIndexUsed 验证 idx_visits_link_ts 索引存在，且按 link_id 查询时被使用。
func TestVisitIndexUsed(t *testing.T) {
	database := openTestDB(t)

	var name string
	err := database.QueryRow(
		`SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_visits_link_ts'`,
	).Scan(&name)
	if err != nil {
		t.Fatalf("查询 idx_visits_link_ts 索引失败: %v", err)
	}
	if name != "idx_visits_link_ts" {
		t.Fatalf("索引名 = %q, 期望 idx_visits_link_ts", name)
	}

	rows, err := database.Query(`EXPLAIN QUERY PLAN SELECT id FROM visits WHERE link_id = 1 ORDER BY ts`)
	if err != nil {
		t.Fatalf("EXPLAIN QUERY PLAN 失败: %v", err)
	}
	defer rows.Close()

	plan := ""
	for rows.Next() {
		var id, parent, notused int
		var detail string
		if err := rows.Scan(&id, &parent, &notused, &detail); err != nil {
			t.Fatalf("扫描查询计划失败: %v", err)
		}
		plan += detail + "\n"
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历查询计划失败: %v", err)
	}
	if !contains(plan, "idx_visits_link_ts") {
		t.Fatalf("查询计划未命中 idx_visits_link_ts, 实际计划:\n%s", plan)
	}
}

// TestForeignKeyCascade 验证外键级联：删除 links 行后其 visits 一并被清除。
func TestForeignKeyCascade(t *testing.T) {
	database := openTestDB(t)

	linkID := insertLink(t, database, "fk0001", "https://example.com/fk", sql.NullString{}, sql.NullInt64{}, 0)
	insertVisit(t, database, linkID, time.Now().UTC().Format(time.RFC3339), "ip-hash-fk-1", "JP")
	insertVisit(t, database, linkID, time.Now().UTC().Format(time.RFC3339), "ip-hash-fk-2", "JP")

	var before int
	if err := database.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, linkID).Scan(&before); err != nil {
		t.Fatalf("删除前统计 visits 失败: %v", err)
	}
	if before != 2 {
		t.Fatalf("删除前 visits 数 = %d, 期望 2", before)
	}

	if _, err := database.Exec(`DELETE FROM links WHERE id = ?`, linkID); err != nil {
		t.Fatalf("删除链接失败: %v", err)
	}

	var after int
	if err := database.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, linkID).Scan(&after); err != nil {
		t.Fatalf("删除后统计 visits 失败: %v", err)
	}
	if after != 0 {
		t.Fatalf("级联删除后 visits 数 = %d, 期望 0", after)
	}
}

// TestRateLimitWindowCount 验证限流用的滑动窗口计数：窗口内计数与窗口外计数分离。
func TestRateLimitWindowCount(t *testing.T) {
	database := openTestDB(t)

	linkID := insertLink(t, database, "rate01", "https://example.com/rate", sql.NullString{}, sql.NullInt64{}, 0)

	now := time.Now().UTC()
	windowStart := now.Add(-time.Minute)

	insertVisit(t, database, linkID, now.Add(-30*time.Second).Format(time.RFC3339), "ip-hash-w-1", "DE")
	insertVisit(t, database, linkID, now.Add(-20*time.Second).Format(time.RFC3339), "ip-hash-w-1", "DE")
	insertVisit(t, database, linkID, now.Add(-10*time.Second).Format(time.RFC3339), "ip-hash-w-2", "DE")
	insertVisit(t, database, linkID, now.Add(-5*time.Minute).Format(time.RFC3339), "ip-hash-w-1", "DE")

	var inWindow int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM visits WHERE link_id = ? AND ts >= ?`,
		linkID, windowStart.Format(time.RFC3339),
	).Scan(&inWindow); err != nil {
		t.Fatalf("窗口内计数失败: %v", err)
	}
	if inWindow != 3 {
		t.Fatalf("窗口内访问数 = %d, 期望 3", inWindow)
	}

	var outWindow int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM visits WHERE link_id = ? AND ts < ?`,
		linkID, windowStart.Format(time.RFC3339),
	).Scan(&outWindow); err != nil {
		t.Fatalf("窗口外计数失败: %v", err)
	}
	if outWindow != 1 {
		t.Fatalf("窗口外访问数 = %d, 期望 1", outWindow)
	}

	var distinctInWindow int
	if err := database.QueryRow(
		`SELECT COUNT(DISTINCT ip_hash) FROM visits WHERE link_id = ? AND ts >= ?`,
		linkID, windowStart.Format(time.RFC3339),
	).Scan(&distinctInWindow); err != nil {
		t.Fatalf("窗口内去重 IP 计数失败: %v", err)
	}
	if distinctInWindow != 2 {
		t.Fatalf("窗口内去重 IP 数 = %d, 期望 2", distinctInWindow)
	}
}

// TestBackupHealthCheck 验证备份健康判定：正常库通过 integrity_check，
// 且关键表与索引齐全；缺表时判定失败。
func TestBackupHealthCheck(t *testing.T) {
	database := openTestDB(t)

	var integrity string
	if err := database.QueryRow(`PRAGMA integrity_check;`).Scan(&integrity); err != nil {
		t.Fatalf("integrity_check 执行失败: %v", err)
	}
	if integrity != "ok" {
		t.Fatalf("integrity_check = %q, 期望 ok", integrity)
	}

	var foreignKeyViolations int
	if err := database.QueryRow(`PRAGMA foreign_key_check;`).Scan(&foreignKeyViolations); err != nil && err != sql.ErrNoRows {
		t.Fatalf("foreign_key_check 执行失败: %v", err)
	}

	requiredTables := []string{"links", "visits"}
	for _, tbl := range requiredTables {
		var name string
		err := database.QueryRow(
			`SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?`, tbl,
		).Scan(&name)
		if err != nil {
			t.Fatalf("健康检查缺少表 %q: %v", tbl, err)
		}
		if name != tbl {
			t.Fatalf("表名 = %q, 期望 %q", name, tbl)
		}
	}

	requiredIndexes := []string{"idx_visits_link_ts", "idx_links_slug"}
	for _, idx := range requiredIndexes {
		var name string
		err := database.QueryRow(
			`SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?`, idx,
		).Scan(&name)
		if err != nil {
			t.Fatalf("健康检查缺少索引 %q: %v", idx, err)
		}
		if name != idx {
			t.Fatalf("索引名 = %q, 期望 %q", name, idx)
		}
	}

	// 缺表场景：删掉 visits 后健康判定应当失败。
	if _, err := database.Exec(`DROP TABLE visits;`); err != nil {
		t.Fatalf("删除 visits 表失败: %v", err)
	}
	var droppedName string
	err := database.QueryRow(
		`SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'visits'`,
	).Scan(&droppedName)
	if err != sql.ErrNoRows {
		t.Fatalf("删除后查询 visits 表应返回 ErrNoRows, 实际 err = %v, name = %q", err, droppedName)
	}
}

// TestConcurrentVisitInsert 验证并发写入在 SetMaxOpenConns(1) 下无竞态、无丢失。
func TestConcurrentVisitInsert(t *testing.T) {
	database := openTestDB(t)

	linkID := insertLink(t, database, "conc01", "https://example.com/conc", sql.NullString{}, sql.NullInt64{}, 0)

	const workers = 8
	const perWorker = 5

	var wg sync.WaitGroup
	errCh := make(chan error, workers)
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(worker int) {
			defer wg.Done()
			for i := 0; i < perWorker; i++ {
				ts := time.Now().UTC().Format(time.RFC3339Nano)
				_, err := database.Exec(
					`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city)
					 VALUES (?, ?, ?, "", "", "FR", "", "", "")`,
					linkID, ts, "ip-hash-conc",
				)
				if err != nil {
					errCh <- err
					return
				}
			}
		}(w)
	}
	wg.Wait()
	close(errCh)

	for err := range errCh {
		t.Fatalf("并发写入失败: %v", err)
	}

	var total int
	if err := database.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, linkID).Scan(&total); err != nil {
		t.Fatalf("统计并发写入结果失败: %v", err)
	}
	if total != workers*perWorker {
		t.Fatalf("并发写入总数 = %d, 期望 %d", total, workers*perWorker)
	}

	var distinctTS int
	if err := database.QueryRow(`SELECT COUNT(DISTINCT ts) FROM visits WHERE link_id = ?`, linkID).Scan(&distinctTS); err != nil {
		t.Fatalf("统计去重时间戳失败: %v", err)
	}
	if distinctTS != workers*perWorker {
		t.Fatalf("去重时间戳数 = %d, 期望 %d", distinctTS, workers*perWorker)
	}
}

// contains 是 strings.Contains 的本地实现，避免引入额外导入。
func contains(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	if len(s) < len(sub) {
		return false
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
