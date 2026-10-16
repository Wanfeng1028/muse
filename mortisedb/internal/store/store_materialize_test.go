package store

import (
	"database/sql"
	"errors"
	"testing"
)

// TestMigrateAddsMaterializeColumns 校验老库迁移后新增列存在且旧行 materialized=0。
func TestMigrateAddsMaterializeColumns(t *testing.T) {
	s := openTestStore(t)
	defer s.Close()

	// 手动构造仅含旧四列的 schema，模拟 v1.0/v1.1 老库。
	if _, err := s.DB.Exec(`DROP TABLE IF EXISTS "_m_views"`); err != nil {
		t.Fatalf("删除旧表失败: %v", err)
	}
	if _, err := s.DB.Exec(`CREATE TABLE "_m_views" (
		"name" TEXT PRIMARY KEY,
		"sql" TEXT,
		"description" TEXT,
		"created_at" TEXT
	)`); err != nil {
		t.Fatalf("创建旧表失败: %v", err)
	}
	if _, err := s.DB.Exec(
		`INSERT INTO "_m_views" ("name","sql","description","created_at") VALUES (?,?,?,?)`,
		"legacy", "SELECT 1", "旧视图", "2024-01-01T00:00:00Z",
	); err != nil {
		t.Fatalf("插入旧行失败: %v", err)
	}

	if err := s.Migrate(); err != nil {
		t.Fatalf("Migrate 失败: %v", err)
	}

	rows, err := s.DB.Query(`PRAGMA table_info("_m_views")`)
	if err != nil {
		t.Fatalf("读取列信息失败: %v", err)
	}
	defer rows.Close()
	cols := map[string]bool{}
	for rows.Next() {
		var (
			cid       int
			name      string
			ctype     string
			notnull   int
			dfltValue sql.NullString
			pk        int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dfltValue, &pk); err != nil {
			t.Fatalf("扫描列信息失败: %v", err)
		}
		cols[name] = true
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("遍历列信息失败: %v", err)
	}
	for _, c := range []string{"origin", "materialized", "refresh_policy", "last_refresh_at", "last_refresh_rows"} {
		if !cols[c] {
			t.Fatalf("迁移后缺少列 %q", c)
		}
	}

	v, err := s.GetView("legacy")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.Materialized {
		t.Fatalf("旧行 materialized 期望 false，实际 true")
	}
	if v.LastRefreshRows != 0 {
		t.Fatalf("旧行 last_refresh_rows 期望 0，实际 %d", v.LastRefreshRows)
	}

	// 再次 Migrate 必须幂等。
	if err := s.Migrate(); err != nil {
		t.Fatalf("二次 Migrate 失败: %v", err)
	}
}

// TestMaterializeTableName 校验物化表名生成与非法名称拒绝。
func TestMaterializeTableName(t *testing.T) {
	got, err := MaterializeTableName("sales")
	if err != nil {
		t.Fatalf("合法名称报错: %v", err)
	}
	if got != "_mv_sales" {
		t.Fatalf("期望 _mv_sales，实际 %q", got)
	}

	if _, err := MaterializeTableName("bad-name"); err == nil {
		t.Fatalf("bad-name 期望报错，实际通过")
	}
	if _, err := MaterializeTableName(`"select"`); err == nil {
		t.Fatalf("含引号名称期望报错，实际通过")
	}
}

// TestUpdateViewMaterializeAndRecordRefresh 校验物化配置更新与刷新记录。
func TestUpdateViewMaterializeAndRecordRefresh(t *testing.T) {
	s := openTestStore(t)
	defer s.Close()

	if err := s.SaveView("sales", "SELECT 1", "销售视图"); err != nil {
		t.Fatalf("SaveView 失败: %v", err)
	}

	if err := s.UpdateViewMaterialize("sales", true, "on_sync"); err != nil {
		t.Fatalf("UpdateViewMaterialize 失败: %v", err)
	}
	v, err := s.GetView("sales")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if !v.Materialized {
		t.Fatalf("Materialized 期望 true，实际 false")
	}
	if v.RefreshPolicy != "on_sync" {
		t.Fatalf("RefreshPolicy 期望 on_sync，实际 %q", v.RefreshPolicy)
	}

	if err := s.RecordViewRefresh("sales", 42); err != nil {
		t.Fatalf("RecordViewRefresh 失败: %v", err)
	}
	v, err = s.GetView("sales")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.LastRefreshRows != 42 {
		t.Fatalf("LastRefreshRows 期望 42，实际 %d", v.LastRefreshRows)
	}
	if v.LastRefreshAt == "" {
		t.Fatalf("LastRefreshAt 期望非空")
	}

	if err := s.UpdateViewMaterialize("not_exist", true, "on_sync"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("不存在视图 UpdateViewMaterialize 期望 ErrNotFound，实际 %v", err)
	}
	if err := s.RecordViewRefresh("not_exist", 1); !errors.Is(err, ErrNotFound) {
		t.Fatalf("不存在视图 RecordViewRefresh 期望 ErrNotFound，实际 %v", err)
	}
}
