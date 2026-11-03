package db

import (
	"database/sql"
	"path/filepath"
	"testing"

	"sentinel/internal/store"
)

// TestMigrationV4_FreshDB 全新库应建出 status_subscriptions 表与索引。
func TestMigrationV4_FreshDB(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sentinel.db")
	d, err := Open(path)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	defer d.Close()

	rows, err := d.Query(`PRAGMA table_info(status_subscriptions)`)
	if err != nil {
		t.Fatalf("查询表结构失败: %v", err)
	}
	cols := map[string]bool{}
	for rows.Next() {
		var cid int
		var name, ctype string
		var notnull, pk int
		var dflt sql.NullString
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			rows.Close()
			t.Fatalf("扫描列失败: %v", err)
		}
		cols[name] = true
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历列失败: %v", err)
	}

	for _, want := range []string{"id", "page_id", "email", "token", "confirmed", "created_at", "confirmed_at"} {
		if !cols[want] {
			t.Errorf("缺少列 %s", want)
		}
	}

	var idxName string
	err = d.QueryRow(
		`SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_status_subscriptions_page_email'`,
	).Scan(&idxName)
	if err != nil {
		t.Fatalf("缺少索引 idx_status_subscriptions_page_email: %v", err)
	}
}

// TestMigrationV4_LegacyUpgrade 老库（v1~v3）升级到 v4 后订阅表可用。
func TestMigrationV4_LegacyUpgrade(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sentinel.db")

	legacy, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("打开老库失败: %v", err)
	}
	if err := ensureMigrationsTable(legacy); err != nil {
		legacy.Close()
		t.Fatalf("建迁移表失败: %v", err)
	}
	for i := 0; i < 3; i++ {
		if err := applyMigration(legacy, migrations[i]); err != nil {
			legacy.Close()
			t.Fatalf("执行老迁移 v%d 失败: %v", i+1, err)
		}
	}
	if _, err := legacy.Exec(
		`INSERT INTO status_pages(tenant_id, slug, title, created_at) VALUES(?,?,?,?)`,
		1, "legacy", "老页面", utcNow(),
	); err != nil {
		legacy.Close()
		t.Fatalf("插入老页面失败: %v", err)
	}
	if err := legacy.Close(); err != nil {
		t.Fatalf("关闭老库失败: %v", err)
	}

	d, err := Open(path)
	if err != nil {
		t.Fatalf("Open 升级失败: %v", err)
	}
	defer d.Close()

	versions, err := AppliedVersions(d)
	if err != nil {
		t.Fatalf("读取已应用版本失败: %v", err)
	}
	found := false
	for _, v := range versions {
		if v == 4 {
			found = true
		}
	}
	if !found {
		t.Fatalf("升级后未包含版本 4: %v", versions)
	}

	st := store.New(d)
	if _, err := st.CreateSubscription(1, "user@example.com", "tok-legacy"); err != nil {
		t.Fatalf("升级后创建订阅失败: %v", err)
	}
}
