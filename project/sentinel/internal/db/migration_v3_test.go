package db

import (
	"database/sql"
	"path/filepath"
	"testing"

	"sentinel/internal/store"
)

// TestMigrationV3_FreshDB 验证全新库迁移到 v3 后主题列存在且默认值正确。
func TestMigrationV3_FreshDB(t *testing.T) {
	dir := t.TempDir()
	conn, err := Open(filepath.Join(dir, "fresh.db"))
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	defer conn.Close()

	cols := tableColumns(t, conn, "status_pages")
	if !cols["theme"] {
		t.Fatalf("缺少 theme 列")
	}
	if !cols["accent_color"] {
		t.Fatalf("缺少 accent_color 列")
	}

	st := store.New(conn)
	id, err := st.CreateStatusPage(1, "fresh", "全新页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	sp, err := st.GetStatusPage(id)
	if err != nil {
		t.Fatalf("读取状态页失败: %v", err)
	}
	if sp.Theme != "light" {
		t.Fatalf("默认主题应为 light，实际为 %q", sp.Theme)
	}
	if sp.AccentColor != "" {
		t.Fatalf("默认主色应为空，实际为 %q", sp.AccentColor)
	}
}

// TestMigrationV3_LegacyUpgrade 验证真正的老库（只执行过 v1/v2，
// status_pages 无主题列）升级到 v3：老数据保留，新列按 DEFAULT 回填。
func TestMigrationV3_LegacyUpgrade(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "legacy.db")

	// 用包内 applyMigration 只执行 v1、v2，造出真正的老库。
	raw, err := sql.Open("sqlite", "file:"+path+"?_pragma=busy_timeout(5000)")
	if err != nil {
		t.Fatalf("打开数据库失败: %v", err)
	}
	if err := ensureMigrationsTable(raw); err != nil {
		t.Fatalf("建迁移表失败: %v", err)
	}
	if err := applyMigration(raw, migrations[0]); err != nil {
		t.Fatalf("应用 v1 失败: %v", err)
	}
	if err := applyMigration(raw, migrations[1]); err != nil {
		t.Fatalf("应用 v2 失败: %v", err)
	}
	// 老 schema 插入一行（没有 theme/accent_color 列）。
	if _, err := raw.Exec(`INSERT INTO status_pages(tenant_id, slug, title, created_at) VALUES(1, 'legacy', '老库页', '2026-10-16T00:00:00Z')`); err != nil {
		t.Fatalf("插入老数据失败: %v", err)
	}
	var legacyID int64
	if err := raw.QueryRow(`SELECT id FROM status_pages WHERE slug = 'legacy'`).Scan(&legacyID); err != nil {
		t.Fatalf("读老数据失败: %v", err)
	}
	if err := raw.Close(); err != nil {
		t.Fatalf("关闭数据库失败: %v", err)
	}

	// 正式 Open：应自动补上 v3。
	conn, err := Open(path)
	if err != nil {
		t.Fatalf("重新打开数据库失败: %v", err)
	}
	defer conn.Close()

	st := store.New(conn)
	sp, err := st.GetStatusPage(legacyID)
	if err != nil {
		t.Fatalf("读取状态页失败: %v", err)
	}
	if sp.Slug != "legacy" || sp.Title != "老库页" {
		t.Fatalf("老数据应保留，实际 slug=%q title=%q", sp.Slug, sp.Title)
	}
	if sp.Theme != "light" {
		t.Fatalf("老数据主题应回填默认值 light，实际为 %q", sp.Theme)
	}
	if sp.AccentColor != "" {
		t.Fatalf("老数据主色应回填空，实际为 %q", sp.AccentColor)
	}

	applied, err := AppliedVersions(conn)
	if err != nil {
		t.Fatalf("读取已应用版本失败: %v", err)
	}
	found := false
	for _, v := range applied {
		if v == 3 {
			found = true
		}
	}
	if !found {
		t.Fatalf("AppliedVersions 应包含 3，实际为 %v", applied)
	}
}

// tableColumns 返回指定表的列名集合。
func tableColumns(t *testing.T, conn *sql.DB, table string) map[string]bool {
	t.Helper()
	rows, err := conn.Query(`PRAGMA table_info(` + table + `)`)
	if err != nil {
		t.Fatalf("查询表结构失败: %v", err)
	}
	defer rows.Close()
	out := make(map[string]bool)
	for rows.Next() {
		var (
			cid       int
			name      string
			ctype     string
			notnull   int
			dfltValue any
			pk        int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dfltValue, &pk); err != nil {
			t.Fatalf("扫描表结构失败: %v", err)
		}
		out[name] = true
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历表结构失败: %v", err)
	}
	return out
}
