package db

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func openDeep3(t *testing.T, path string) *sql.DB {
	t.Helper()
	conn, err := Open(path)
	if err != nil {
		t.Fatalf("Open(%q) 返回错误: %v", path, err)
	}
	if conn == nil {
		t.Fatalf("Open(%q) 返回 nil 连接", path)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return conn
}

func TestOpenPathIsDirectoryDeep3(t *testing.T) {
	dir := t.TempDir()
	conn, err := Open(dir)
	if err == nil {
		if conn != nil {
			_ = conn.Close()
		}
		t.Fatal("Open(目录路径) 期望返回错误，实际成功")
	}
	if conn != nil {
		_ = conn.Close()
		t.Fatalf("Open(目录路径) 期望 nil 连接，实际非 nil")
	}
}

func TestOpenRelativePathNoDirDeep3(t *testing.T) {
	base := t.TempDir()
	oldwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("Getwd 失败: %v", err)
	}
	if err := os.Chdir(base); err != nil {
		t.Fatalf("Chdir 失败: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(oldwd) })

	conn := openDeep3(t, "rel.db")
	if err := conn.Ping(); err != nil {
		t.Fatalf("Ping 失败: %v", err)
	}
	if _, err := os.Stat(filepath.Join(base, "rel.db")); err != nil {
		t.Fatalf("相对路径数据库文件应存在: %v", err)
	}
}

func TestAppliedVersionsAscendingStrictDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "asc.db")
	conn := openDeep3(t, path)

	versions, err := AppliedVersions(conn)
	if err != nil {
		t.Fatalf("AppliedVersions 错误: %v", err)
	}
	if len(versions) != len(migrations) {
		t.Fatalf("AppliedVersions 长度 %d, 期望 %d", len(versions), len(migrations))
	}
	for i, v := range versions {
		if v != migrations[i].version {
			t.Fatalf("AppliedVersions[%d] = %d, 期望 %d", i, v, migrations[i].version)
		}
	}
}

func TestAppliedVersionsEmptyTableDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "empty.db")
	conn := openDeep3(t, path)

	if _, err := conn.Exec(`DELETE FROM schema_migrations`); err != nil {
		t.Fatalf("清空 schema_migrations 失败: %v", err)
	}

	versions, err := AppliedVersions(conn)
	if err != nil {
		t.Fatalf("AppliedVersions 错误: %v", err)
	}
	if len(versions) != 0 {
		t.Fatalf("空表 AppliedVersions = %v, 期望空(长度为 0)", versions)
	}
}

func TestAppliedVersionsClosedConnDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "closed.db")
	conn, err := Open(path)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	if err := conn.Close(); err != nil {
		t.Fatalf("Close 失败: %v", err)
	}

	versions, err := AppliedVersions(conn)
	if err == nil {
		t.Fatalf("已关闭连接 AppliedVersions 期望错误，实际 %v", versions)
	}
	if versions != nil {
		t.Fatalf("已关闭连接 AppliedVersions 期望 nil，实际 %v", versions)
	}
}

func TestColumnExistsMissingTableDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "notable.db")
	conn := openDeep3(t, path)

	exists, err := columnExists(conn, "no_such_table_deep3", "id")
	if err != nil {
		t.Fatalf("columnExists 不存在的表返回错误: %v", err)
	}
	if exists {
		t.Fatal("不存在的表应返回 false")
	}
}

func TestColumnExistsCaseSensitivityDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "case.db")
	conn := openDeep3(t, path)

	exists, err := columnExists(conn, "monitors", "ID")
	if err != nil {
		t.Fatalf("columnExists 大小写测试错误: %v", err)
	}
	if exists {
		t.Fatal("列名大小写不匹配应返回 false（小写 id 存在但 ID 不同）")
	}

	lower, err := columnExists(conn, "monitors", "id")
	if err != nil {
		t.Fatalf("columnExists(monitors, id) 错误: %v", err)
	}
	if !lower {
		t.Fatal("小写 id 列应存在")
	}
}

func TestColumnExistsEmptyColumnNameDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "emptycol.db")
	conn := openDeep3(t, path)

	exists, err := columnExists(conn, "monitors", "")
	if err != nil {
		t.Fatalf("columnExists 空列名错误: %v", err)
	}
	if exists {
		t.Fatal("空列名应返回 false")
	}
}

func TestAppliedVersionsOrderAfterManualInsertDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "manual.db")
	conn := openDeep3(t, path)

	if _, err := conn.Exec(`INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)`, 100, utcNow()); err != nil {
		t.Fatalf("插入迁移记录失败: %v", err)
	}
	if _, err := conn.Exec(`INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)`, 50, utcNow()); err != nil {
		t.Fatalf("插入迁移记录失败: %v", err)
	}

	versions, err := AppliedVersions(conn)
	if err != nil {
		t.Fatalf("AppliedVersions 错误: %v", err)
	}
	if len(versions) < 2 {
		t.Fatalf("AppliedVersions 长度 %d, 期望至少 2", len(versions))
	}
	for i := 1; i < len(versions); i++ {
		if versions[i-1] > versions[i] {
			t.Fatalf("AppliedVersions 未升序: %v", versions)
		}
	}
	last := versions[len(versions)-1]
	if last != 100 {
		t.Fatalf("最大版本应为 100, 实际 %d", last)
	}
}

func TestUtcNowStrictlyIncreasingDeep3(t *testing.T) {
	prev := utcNow()
	seen := map[string]bool{prev: true}
	for i := 0; i < 20; i++ {
		time.Sleep(time.Millisecond)
		cur := utcNow()
		if cur == "" {
			t.Fatal("utcNow 返回空")
		}
		if seen[cur] && cur == prev {
			// 同一毫秒内可能重复；仅当时间格式精度允许时才要求单调
			continue
		}
		if cur < prev {
			t.Fatalf("utcNow 倒退: prev=%q cur=%q", prev, cur)
		}
		prev = cur
		seen[cur] = true
	}
}

func TestUtcNowIsUTCDeep3(t *testing.T) {
	u := utcNow()
	parsed, err := time.Parse(time.RFC3339, u)
	if err != nil {
		t.Fatalf("utcNow 无法解析: %v", err)
	}
	if parsed.Location() != time.UTC {
		// RFC3339 解析出的 Z 后缀应表示 UTC 偏移为 0
		_, offset := parsed.Zone()
		if offset != 0 {
			t.Fatalf("utcNow 时区偏移非 0: %d (%q)", offset, u)
		}
	}
	if !strings.HasSuffix(u, "Z") && !strings.Contains(u, "+00:00") {
		t.Fatalf("utcNow 输出 %q 不以 UTC 后缀结束", u)
	}
}

func TestQuoteNowMatchesUtcNowPrefixDeep3(t *testing.T) {
	q := quoteNow()
	u := utcNow()
	if !strings.HasPrefix(q, "'") || !strings.HasSuffix(q, "'") {
		t.Fatalf("quoteNow = %q 未用单引号包裹", q)
	}
	inner := q[1 : len(q)-1]
	if inner == "" {
		t.Fatal("quoteNow 内部时间为空")
	}
	qi, err := time.Parse(time.RFC3339, inner)
	if err != nil {
		t.Fatalf("quoteNow 内部 %q 无法解析: %v", inner, err)
	}
	ui, err := time.Parse(time.RFC3339, u)
	if err != nil {
		t.Fatalf("utcNow %q 无法解析: %v", u, err)
	}
	diff := qi.Sub(ui)
	if diff < 0 {
		diff = -diff
	}
	if diff > 2*time.Second {
		t.Fatalf("quoteNow 与 utcNow 时间差 %v 过大", diff)
	}
}

func TestEnsureMigrationsTableIdempotentDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "migtab.db")
	conn := openDeep3(t, path)

	for i := 0; i < 3; i++ {
		if err := ensureMigrationsTable(conn); err != nil {
			t.Fatalf("第 %d 次 ensureMigrationsTable 错误: %v", i, err)
		}
	}

	var count int
	if err := conn.QueryRow(`SELECT COUNT(*) FROM schema_migrations`).Scan(&count); err != nil {
		t.Fatalf("统计 schema_migrations 失败: %v", err)
	}
	if count != len(migrations) {
		t.Fatalf("schema_migrations 行数 %d, 期望 %d", count, len(migrations))
	}
}

func TestApplyMigrationDuplicateVersionFailsDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "dupver.db")
	conn := openDeep3(t, path)

	dup := migration{
		version: 1,
		stmts:   []string{`CREATE TABLE IF NOT EXISTS dup_marker_deep3 (id INTEGER)`},
	}
	if err := applyMigration(conn, dup); err == nil {
		t.Fatal("重复应用已存在的迁移版本期望错误，实际成功")
	}

	exists, err := columnExists(conn, "dup_marker_deep3", "id")
	if err != nil {
		t.Fatalf("columnExists 错误: %v", err)
	}
	if exists {
		t.Fatal("重复迁移失败后不应创建表（事务应回滚）")
	}
}

func TestApplyMigrationRollbackOnBadStmtDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "badstmt.db")
	conn := openDeep3(t, path)

	bad := migration{
		version: 900,
		stmts: []string{
			`CREATE TABLE good_deep3 (id INTEGER)`,
			`THIS IS NOT VALID SQL DEEP3`,
		},
	}
	if err := applyMigration(conn, bad); err == nil {
		t.Fatal("包含非法语句的迁移期望错误，实际成功")
	}

	exists, err := columnExists(conn, "good_deep3", "id")
	if err != nil {
		t.Fatalf("columnExists 错误: %v", err)
	}
	if exists {
		t.Fatal("迁移失败后 good_deep3 表不应存在（整体回滚）")
	}

	var count int
	if err := conn.QueryRow(`SELECT COUNT(*) FROM schema_migrations WHERE version = 900`).Scan(&count); err != nil {
		t.Fatalf("统计迁移记录失败: %v", err)
	}
	if count != 0 {
		t.Fatalf("失败迁移不应写入 schema_migrations, 实际 count=%d", count)
	}
}

func TestApplyMigrationSuccessNewVersionDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "okver.db")
	conn := openDeep3(t, path)

	ok := migration{
		version: 800,
		stmts:   []string{`CREATE TABLE ok_deep3 (id INTEGER PRIMARY KEY, name TEXT)`},
	}
	if err := applyMigration(conn, ok); err != nil {
		t.Fatalf("applyMigration 成功路径错误: %v", err)
	}

	exists, err := columnExists(conn, "ok_deep3", "name")
	if err != nil {
		t.Fatalf("columnExists 错误: %v", err)
	}
	if !exists {
		t.Fatal("成功迁移后 ok_deep3.name 列应存在")
	}

	versions, err := AppliedVersions(conn)
	if err != nil {
		t.Fatalf("AppliedVersions 错误: %v", err)
	}
	found := false
	for _, v := range versions {
		if v == 800 {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("AppliedVersions 未包含 800: %v", versions)
	}
}

func TestOpenAppliesExtraMigrationViaConnStateDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "reopen.db")
	conn := openDeep3(t, path)

	if _, err := conn.Exec(`CREATE TABLE custom_deep3 (id INTEGER PRIMARY KEY, val TEXT NOT NULL)`); err != nil {
		t.Fatalf("创建自定义表失败: %v", err)
	}
	if _, err := conn.Exec(`INSERT INTO custom_deep3(val) VALUES('keep')`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	if err := conn.Close(); err != nil {
		t.Fatalf("关闭连接失败: %v", err)
	}

	conn2 := openDeep3(t, path)
	var val string
	if err := conn2.QueryRow(`SELECT val FROM custom_deep3 WHERE id = 1`).Scan(&val); err != nil {
		t.Fatalf("重开后读取自定义表失败: %v", err)
	}
	if val != "keep" {
		t.Fatalf("重开后数据丢失: %q", val)
	}
}

func TestOpenRejectsNonSQLiteExistingFileDeep3(t *testing.T) {
	base := t.TempDir()
	path := filepath.Join(base, "garbage.db")
	if err := os.WriteFile(path, []byte("this is not a sqlite database file at all, deep3"), 0o644); err != nil {
		t.Fatalf("写入垃圾文件失败: %v", err)
	}

	conn, err := Open(path)
	if err == nil {
		if conn != nil {
			_ = conn.Close()
		}
		t.Fatal("Open(非 SQLite 文件) 期望错误，实际成功")
	}
	if conn != nil {
		_ = conn.Close()
		t.Fatalf("Open(非 SQLite 文件) 期望 nil 连接，实际非 nil")
	}
}

func TestForeignKeyCascadeOnDeleteDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cascade.db")
	conn := openDeep3(t, path)

	now := utcNow()
	res, err := conn.Exec(`INSERT INTO monitors(name, target, created_at, updated_at) VALUES(?, ?, ?, ?)`,
		"cascade-mon", "http://example.com", now, now)
	if err != nil {
		t.Fatalf("插入 monitor 失败: %v", err)
	}
	mid, err := res.LastInsertId()
	if err != nil {
		t.Fatalf("LastInsertId 失败: %v", err)
	}

	if _, err := conn.Exec(`INSERT INTO checks(monitor_id, checked_at, ok) VALUES(?, ?, 1)`, mid, now); err != nil {
		t.Fatalf("插入 check 失败: %v", err)
	}
	if _, err := conn.Exec(`INSERT INTO incidents(monitor_id, started_at) VALUES(?, ?)`, mid, now); err != nil {
		t.Fatalf("插入 incident 失败: %v", err)
	}

	if _, err := conn.Exec(`DELETE FROM monitors WHERE id = ?`, mid); err != nil {
		t.Fatalf("删除 monitor 失败: %v", err)
	}

	var checks, incidents int
	if err := conn.QueryRow(`SELECT COUNT(*) FROM checks WHERE monitor_id = ?`, mid).Scan(&checks); err != nil {
		t.Fatalf("统计 checks 失败: %v", err)
	}
	if err := conn.QueryRow(`SELECT COUNT(*) FROM incidents WHERE monitor_id = ?`, mid).Scan(&incidents); err != nil {
		t.Fatalf("统计 incidents 失败: %v", err)
	}
	if checks != 0 {
		t.Fatalf("级联删除后 checks 残留 %d 行", checks)
	}
	if incidents != 0 {
		t.Fatalf("级联删除后 incidents 残留 %d 行", incidents)
	}
}

func TestUniqueTokenHashConstraintDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "uniq.db")
	conn := openDeep3(t, path)

	now := utcNow()
	if _, err := conn.Exec(`INSERT INTO users(tenant_id, name, token_hash, created_at) VALUES(1, 'a', 'hash-x', ?)`, now); err != nil {
		t.Fatalf("插入首个用户失败: %v", err)
	}
	if _, err := conn.Exec(`INSERT INTO users(tenant_id, name, token_hash, created_at) VALUES(1, 'b', 'hash-x', ?)`, now); err == nil {
		t.Fatal("重复 token_hash 期望唯一约束错误，实际成功")
	}

	var count int
	if err := conn.QueryRow(`SELECT COUNT(*) FROM users WHERE token_hash = 'hash-x'`).Scan(&count); err != nil {
		t.Fatalf("统计 users 失败: %v", err)
	}
	if count != 1 {
		t.Fatalf("users 中 token_hash 应唯一，实际 count=%d", count)
	}
}

func TestLongTextInputDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "long.db")
	conn := openDeep3(t, path)

	longName := strings.Repeat("名", 5000)
	longTarget := "http://example.com/" + strings.Repeat("x", 20000)
	now := utcNow()

	res, err := conn.Exec(`INSERT INTO monitors(name, target, created_at, updated_at) VALUES(?, ?, ?, ?)`,
		longName, longTarget, now, now)
	if err != nil {
		t.Fatalf("插入超长文本失败: %v", err)
	}
	mid, err := res.LastInsertId()
	if err != nil {
		t.Fatalf("LastInsertId 失败: %v", err)
	}

	var gotName, gotTarget string
	if err := conn.QueryRow(`SELECT name, target FROM monitors WHERE id = ?`, mid).Scan(&gotName, &gotTarget); err != nil {
		t.Fatalf("读回超长文本失败: %v", err)
	}
	if gotName != longName {
		t.Fatalf("name 长度不一致: got %d want %d", len(gotName), len(longName))
	}
	if gotTarget != longTarget {
		t.Fatalf("target 长度不一致: got %d want %d", len(gotTarget), len(longTarget))
	}
}

func TestOpenConcurrentSameFileDeep3(t *testing.T) {
	const workers = 4
	var wg sync.WaitGroup
	errCh := make(chan error, workers)
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		i := i
		go func() {
			defer wg.Done()
			path := filepath.Join(t.TempDir(), fmt.Sprintf("concurrent-%d.db", i))
			conn, err := Open(path)
			if err != nil {
				errCh <- err
				return
			}
			defer conn.Close()
			if err := conn.Ping(); err != nil {
				errCh <- err
				return
			}
			versions, err := AppliedVersions(conn)
			if err != nil {
				errCh <- err
				return
			}
			if len(versions) != len(migrations) {
				errCh <- fmt.Errorf("并发后迁移版本数 %d, 期望 %d", len(versions), len(migrations))
				return
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("并发 Open 出错: %v", err)
	}
}

func TestMigrationsTableShapeDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "shape.db")
	conn := openDeep3(t, path)

	hasVersion, err := columnExists(conn, "schema_migrations", "version")
	if err != nil {
		t.Fatalf("columnExists 错误: %v", err)
	}
	if !hasVersion {
		t.Fatal("schema_migrations 缺少 version 列")
	}
	hasApplied, err := columnExists(conn, "schema_migrations", "applied_at")
	if err != nil {
		t.Fatalf("columnExists 错误: %v", err)
	}
	if !hasApplied {
		t.Fatal("schema_migrations 缺少 applied_at 列")
	}

	rows, err := conn.Query(`SELECT applied_at FROM schema_migrations`)
	if err != nil {
		t.Fatalf("查询 applied_at 失败: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var appliedAt string
		if err := rows.Scan(&appliedAt); err != nil {
			t.Fatalf("扫描 applied_at 失败: %v", err)
		}
		if _, err := time.Parse(time.RFC3339, appliedAt); err != nil {
			t.Fatalf("applied_at %q 非 RFC3339: %v", appliedAt, err)
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历 applied_at 出错: %v", err)
	}
}

func TestMonitorDefaultsDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "defaults.db")
	conn := openDeep3(t, path)

	now := utcNow()
	res, err := conn.Exec(`INSERT INTO monitors(name, target, created_at, updated_at) VALUES(?, ?, ?, ?)`,
		"defaults", "http://example.com", now, now)
	if err != nil {
		t.Fatalf("插入失败: %v", err)
	}
	mid, err := res.LastInsertId()
	if err != nil {
		t.Fatalf("LastInsertId 失败: %v", err)
	}

	var kind, method string
	var expectedStatus, timeoutSec, intervalSec, enabled, tenantID, isPublic int
	var webhook, notify, sms string
	if err := conn.QueryRow(`SELECT kind, method, expected_status, timeout_sec, interval_sec, enabled, webhook_url, tenant_id, is_public, notify_channels, sms_phones FROM monitors WHERE id = ?`, mid).
		Scan(&kind, &method, &expectedStatus, &timeoutSec, &intervalSec, &enabled, &webhook, &tenantID, &isPublic, &notify, &sms); err != nil {
		t.Fatalf("读取默认值失败: %v", err)
	}
	if kind != "http" {
		t.Fatalf("kind 默认值 = %q, 期望 http", kind)
	}
	if method != "GET" {
		t.Fatalf("method 默认值 = %q, 期望 GET", method)
	}
	if expectedStatus != 200 {
		t.Fatalf("expected_status 默认值 = %d, 期望 200", expectedStatus)
	}
	if timeoutSec != 10 {
		t.Fatalf("timeout_sec 默认值 = %d, 期望 10", timeoutSec)
	}
	if intervalSec != 60 {
		t.Fatalf("interval_sec 默认值 = %d, 期望 60", intervalSec)
	}
	if enabled != 1 {
		t.Fatalf("enabled 默认值 = %d, 期望 1", enabled)
	}
	if webhook != "" {
		t.Fatalf("webhook_url 默认值 = %q, 期望空", webhook)
	}
	if tenantID != 1 {
		t.Fatalf("tenant_id 默认值 = %d, 期望 1", tenantID)
	}
	if isPublic != 0 {
		t.Fatalf("is_public 默认值 = %d, 期望 0", isPublic)
	}
	if notify != "" {
		t.Fatalf("notify_channels 默认值 = %q, 期望空", notify)
	}
	if sms != "" {
		t.Fatalf("sms_phones 默认值 = %q, 期望空", sms)
	}
}

func TestOpenSecondCallAddsColumnsAfterDropDeep3(t *testing.T) {
	path := filepath.Join(t.TempDir(), "recover.db")
	conn := openDeep3(t, path)

	has, err := columnExists(conn, "monitors", "tenant_id")
	if err != nil {
		t.Fatalf("columnExists 错误: %v", err)
	}
	if !has {
		t.Fatal("前置条件失败：tenant_id 应存在")
	}
	if err := conn.Close(); err != nil {
		t.Fatalf("关闭失败: %v", err)
	}

	raw, err := sql.Open("sqlite", fmt.Sprintf("file:%s", path))
	if err != nil {
		t.Fatalf("直接打开失败: %v", err)
	}
	if _, err := raw.Exec(`CREATE TABLE monitors_old_deep3 AS SELECT * FROM monitors`); err != nil {
		raw.Close()
		t.Fatalf("复制表失败: %v", err)
	}
	raw.Close()

	conn2 := openDeep3(t, path)
	for _, col := range []string{"tenant_id", "is_public", "notify_channels"} {
		ok, err := columnExists(conn2, "monitors", col)
		if err != nil {
			t.Fatalf("columnExists(%s) 错误: %v", col, err)
		}
		if !ok {
			t.Fatalf("重开后 monitors 应含列 %s", col)
		}
	}
}
