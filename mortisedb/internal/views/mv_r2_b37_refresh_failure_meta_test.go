package views

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestMvR2B37FailedRefreshKeepsMetadata(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)`)
	if _, err := st.DB.Exec(`INSERT INTO items (id, name) VALUES (1, 'a'), (2, 'b')`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "items_view", `SELECT id, name FROM items`)

	rows, err := Refresh(st, "items_view")
	if err != nil {
		t.Fatalf("首次刷新失败: %v", err)
	}
	if rows != 2 {
		t.Fatalf("首次刷新行数期望 2，实际 %d", rows)
	}

	v1, err := st.GetView("items_view")
	if err != nil {
		t.Fatalf("获取视图 v1 失败: %v", err)
	}
	if v1.LastRefreshAt == "" {
		t.Fatalf("首次刷新后 LastRefreshAt 不应为空")
	}
	if v1.LastRefreshRows != 2 {
		t.Fatalf("首次刷新后 LastRefreshRows 期望 2，实际 %d", v1.LastRefreshRows)
	}

	if err := st.SaveView("items_view", `SELECT FROM WHERE`, "yaml"); err != nil {
		t.Fatalf("改坏 SQL 失败: %v", err)
	}

	if _, err := Refresh(st, "items_view"); err == nil {
		t.Fatalf("改坏 SQL 后刷新应当失败")
	}

	v2, err := st.GetView("items_view")
	if err != nil {
		t.Fatalf("获取视图 v2 失败: %v", err)
	}
	if v2.LastRefreshAt != v1.LastRefreshAt {
		t.Fatalf("失败刷新后 LastRefreshAt 不应改变，期望 %q，实际 %q", v1.LastRefreshAt, v2.LastRefreshAt)
	}
	if v2.LastRefreshRows != v1.LastRefreshRows {
		t.Fatalf("失败刷新后 LastRefreshRows 不应改变，期望 %d，实际 %d", v1.LastRefreshRows, v2.LastRefreshRows)
	}
}

func TestMvR2B37RecoveryAfterFailure(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)`)
	if _, err := st.DB.Exec(`INSERT INTO items (id, name) VALUES (1, 'a'), (2, 'b')`); err != nil {
		t.Fatalf("插入数据失败: %v", err)
	}
	createView(t, st, "items_view", `SELECT id, name FROM items`)

	if _, err := Refresh(st, "items_view"); err != nil {
		t.Fatalf("首次刷新失败: %v", err)
	}

	if err := st.SaveView("items_view", `SELECT FROM WHERE`, "yaml"); err != nil {
		t.Fatalf("改坏 SQL 失败: %v", err)
	}
	if _, err := Refresh(st, "items_view"); err == nil {
		t.Fatalf("改坏 SQL 后刷新应当失败")
	}

	if _, err := st.DB.Exec(`INSERT INTO items (id, name) VALUES (3, 'c')`); err != nil {
		t.Fatalf("追加数据失败: %v", err)
	}
	if err := st.SaveView("items_view", `SELECT id, name FROM items`, "yaml"); err != nil {
		t.Fatalf("修好 SQL 失败: %v", err)
	}

	rows, err := Refresh(st, "items_view")
	if err != nil {
		t.Fatalf("恢复后刷新失败: %v", err)
	}
	if rows != 3 {
		t.Fatalf("恢复后刷新行数期望 3，实际 %d", rows)
	}

	tbl, err := store.MaterializeTableName("items_view")
	if err != nil {
		t.Fatalf("计算物化表名失败: %v", err)
	}
	var cnt int
	if err := st.DB.QueryRow(`SELECT COUNT(*) FROM "` + tbl + `"`).Scan(&cnt); err != nil {
		t.Fatalf("查询物化表行数失败: %v", err)
	}
	if cnt != 3 {
		t.Fatalf("物化表行数期望 3，实际 %d", cnt)
	}

	v3, err := st.GetView("items_view")
	if err != nil {
		t.Fatalf("获取视图 v3 失败: %v", err)
	}
	if v3.LastRefreshRows != 3 {
		t.Fatalf("恢复后 LastRefreshRows 期望 3，实际 %d", v3.LastRefreshRows)
	}
}
