package db

import (
	"database/sql"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

func openDeep2(t *testing.T, path string) *sql.DB {
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

func TestOpenEmptyPathDeep2(t *testing.T) {
	conn, err := Open("")
	if err == nil {
		if conn != nil {
			_ = conn.Close()
		}
		t.Fatal("Open(\"\") 期望返回错误，实际返回 nil")
	}
	if conn != nil {
		_ = conn.Close()
		t.Fatalf("Open(\"\") 期望返回 nil 连接，实际非 nil")
	}
}

func TestOpenCreatesNestedParentDirsDeep2(t *testing.T) {
	base := t.TempDir()
	path := filepath.Join(base, "a", "b", "c", "sentinel.db")

	if _, err := os.Stat(filepath.Dir(path)); !os.IsNotExist(err) {
		t.Fatalf("前置条件失败：父目录不应存在，stat err=%v", err)
	}

	conn := openDeep2(t, path)
	if err := conn.Ping(); err != nil {
		t.Fatalf("Ping 失败: %v", err)
	}

	info, err := os.Stat(filepath.Dir(path))
	if err != nil {
		t.Fatalf("Open 后父目录应存在，stat err=%v", err)
	}
	if !info.IsDir() {
		t.Fatalf("父路径 %q 应为目录", filepath.Dir(path))
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("Open 后数据库文件应存在: %v", err)
	}
}

func TestFreshDBAppliedVersionsDeep2(t *testing.T) {
	path := filepath.Join(t.TempDir(), "fresh.db")
	conn := openDeep2(t, path)

	versions, err := AppliedVersions(conn)
	if err != nil {
		t.Fatalf("AppliedVersions 返回错误: %v", err)
	}

	want := []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
	if !reflect.DeepEqual(versions, want) {
		t.Fatalf("全新库 AppliedVersions = %v, 期望 %v", versions, want)
	}

	for i := 1; i < len(versions); i++ {
		if versions[i-1] >= versions[i] {
			t.Fatalf("AppliedVersions 应严格升序，实际 %v", versions)
		}
	}
}

func TestSecondOpenIdempotentDeep2(t *testing.T) {
	path := filepath.Join(t.TempDir(), "idem.db")

	conn1 := openDeep2(t, path)
	first, err := AppliedVersions(conn1)
	if err != nil {
		t.Fatalf("首次 AppliedVersions 错误: %v", err)
	}
	if err := conn1.Close(); err != nil {
		t.Fatalf("关闭首个连接失败: %v", err)
	}

	conn2 := openDeep2(t, path)
	second, err := AppliedVersions(conn2)
	if err != nil {
		t.Fatalf("二次 AppliedVersions 错误: %v", err)
	}

	if !reflect.DeepEqual(first, second) {
		t.Fatalf("二次 Open 后 AppliedVersions 变化: 首次 %v, 二次 %v", first, second)
	}

	var total int
	if err := conn2.QueryRow(`SELECT COUNT(*) FROM schema_migrations`).Scan(&total); err != nil {
		t.Fatalf("统计 schema_migrations 失败: %v", err)
	}
	if total != len(second) {
		t.Fatalf("schema_migrations 行数 %d 与 AppliedVersions 长度 %d 不一致，存在重复应用", total, len(second))
	}
}

func TestColumnExistsMonitorsDeep2(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cols.db")
	conn := openDeep2(t, path)

	rows, err := conn.Query(`PRAGMA table_info(monitors)`)
	if err != nil {
		t.Fatalf("PRAGMA table_info(monitors) 失败: %v", err)
	}
	defer rows.Close()

	var realCols []string
	for rows.Next() {
		var cid int
		var name, ctype string
		var notnull, pk int
		var dflt sql.NullString
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			t.Fatalf("扫描 table_info 行失败: %v", err)
		}
		realCols = append(realCols, name)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历 table_info 出错: %v", err)
	}
	if len(realCols) == 0 {
		t.Fatal("monitors 表无任何列，前置条件失败")
	}

	for _, col := range realCols {
		exists, err := columnExists(conn, "monitors", col)
		if err != nil {
			t.Fatalf("columnExists(monitors, %q) 返回错误: %v", col, err)
		}
		if !exists {
			t.Fatalf("真实列 %q 应存在，columnExists 返回 false", col)
		}
	}

	exists, err := columnExists(conn, "monitors", "no_such_column_deep2")
	if err != nil {
		t.Fatalf("columnExists(monitors, 不存在列) 返回错误: %v", err)
	}
	if exists {
		t.Fatal("不存在的列应返回 false，实际 true")
	}
}

func TestEnsureMonitorColumnsIdempotentDeep2(t *testing.T) {
	path := filepath.Join(t.TempDir(), "ensure.db")
	conn := openDeep2(t, path)

	snapshot := func() map[string]string {
		rows, err := conn.Query(`PRAGMA table_info(monitors)`)
		if err != nil {
			t.Fatalf("PRAGMA table_info(monitors) 失败: %v", err)
		}
		defer rows.Close()
		cols := make(map[string]string)
		for rows.Next() {
			var cid int
			var name, ctype string
			var notnull, pk int
			var dflt sql.NullString
			if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
				t.Fatalf("扫描 table_info 行失败: %v", err)
			}
			cols[name] = ctype
		}
		if err := rows.Err(); err != nil {
			t.Fatalf("遍历 table_info 出错: %v", err)
		}
		return cols
	}

	before := snapshot()
	if len(before) == 0 {
		t.Fatal("monitors 表无列，前置条件失败")
	}

	if err := ensureMonitorColumns(conn); err != nil {
		t.Fatalf("首次 ensureMonitorColumns 错误: %v", err)
	}
	afterFirst := snapshot()

	if err := ensureMonitorColumns(conn); err != nil {
		t.Fatalf("二次 ensureMonitorColumns 错误: %v", err)
	}
	afterSecond := snapshot()

	if !reflect.DeepEqual(afterFirst, afterSecond) {
		t.Fatalf("二次 ensureMonitorColumns 非幂等: 第一次 %v, 第二次 %v", afterFirst, afterSecond)
	}
	if !reflect.DeepEqual(before, afterSecond) {
		t.Fatalf("ensureMonitorColumns 改变了列结构: 之前 %v, 之后 %v", before, afterSecond)
	}
}

func TestJournalModeWalDeep2(t *testing.T) {
	path := filepath.Join(t.TempDir(), "wal.db")
	conn := openDeep2(t, path)

	var mode string
	if err := conn.QueryRow(`PRAGMA journal_mode`).Scan(&mode); err != nil {
		t.Fatalf("查询 journal_mode 失败: %v", err)
	}
	if mode != "wal" {
		t.Fatalf("journal_mode = %q, 期望 \"wal\"", mode)
	}
}

func TestForeignKeysOnDeep2(t *testing.T) {
	path := filepath.Join(t.TempDir(), "fk.db")
	conn := openDeep2(t, path)

	var fk int
	if err := conn.QueryRow(`PRAGMA foreign_keys`).Scan(&fk); err != nil {
		t.Fatalf("查询 foreign_keys 失败: %v", err)
	}
	if fk != 1 {
		t.Fatalf("foreign_keys = %d, 期望 1", fk)
	}
}

func TestQuoteNowAndUtcNowParseableDeep2(t *testing.T) {
	q := quoteNow()
	if q == "" {
		t.Fatal("quoteNow() 返回空字符串")
	}
	// quoteNow 返回 SQL 引用格式（首尾单引号），去引号后应为 RFC3339 时间
	trimmed := q
	if len(trimmed) >= 2 && trimmed[0] == '\'' && trimmed[len(trimmed)-1] == '\'' {
		trimmed = trimmed[1 : len(trimmed)-1]
	} else {
		t.Fatalf("quoteNow() = %q 首尾不是单引号", q)
	}
	if _, err := time.Parse(time.RFC3339Nano, trimmed); err != nil {
		if _, err2 := time.Parse(time.RFC3339, trimmed); err2 != nil {
			t.Fatalf("quoteNow() = %q 去引号后无法解析为时间: %v / %v", q, err, err2)
		}
	}

	u := utcNow()
	if u == "" {
		t.Fatal("utcNow() 返回空字符串")
	}
	if _, err := time.Parse(time.RFC3339Nano, u); err != nil {
		if _, err2 := time.Parse(time.RFC3339, u); err2 != nil {
			t.Fatalf("utcNow() = %q 无法解析为时间: %v / %v", u, err, err2)
		}
	}
}