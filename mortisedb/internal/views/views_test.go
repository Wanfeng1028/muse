package views

import (
	"fmt"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}
	if _, err := st.DB.Exec(`CREATE TABLE "users" ("id" INTEGER PRIMARY KEY, "name" TEXT, "_m_hash" TEXT, "_m_source" TEXT, "_m_synced_at" TEXT, "_m_deleted" INTEGER NOT NULL DEFAULT 0)`); err != nil {
		t.Fatalf("建表失败: %v", err)
	}
	if _, err := st.DB.Exec(`INSERT INTO "users" ("id","name","_m_deleted") VALUES (1,'张三',0),(2,'李四',0),(3,'王五',1)`); err != nil {
		t.Fatalf("插入失败: %v", err)
	}
	return st
}

func TestAddValidView(t *testing.T) {
	st := newTestStore(t)
	if err := Add(st, "v_users", `SELECT "id","name" FROM "users"`, "用户视图"); err != nil {
		t.Fatalf("Add 合法视图应成功，实际: %v", err)
	}
	v, err := st.GetView("v_users")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.Name != "v_users" || v.Description != "用户视图" {
		t.Fatalf("视图元数据不匹配: %+v", v)
	}
	if v.SQL == "" {
		t.Fatalf("视图 SQL 不应为空")
	}
}

func TestAddNonSelectFails(t *testing.T) {
	st := newTestStore(t)
	if err := Add(st, "v_bad", `DELETE FROM "users"`, ""); err == nil {
		t.Fatalf("Add 非 SELECT 语句应失败")
	}
	if _, err := st.GetView("v_bad"); err == nil {
		t.Fatalf("非法视图不应被保存")
	}
}

func TestAddInvalidSQLFails(t *testing.T) {
	st := newTestStore(t)
	if err := Add(st, "v_err", `SELECT FROM WHERE`, ""); err == nil {
		t.Fatalf("Add 非法 SQL 应失败")
	}
}

func TestRunReturnsColumnsAndRows(t *testing.T) {
	st := newTestStore(t)
	if err := Add(st, "v_users", `SELECT "id","name" FROM "users" WHERE "_m_deleted"=0 ORDER BY "id"`, ""); err != nil {
		t.Fatalf("Add 失败: %v", err)
	}
	cols, rows, err := Run(st, "v_users", 10)
	if err != nil {
		t.Fatalf("Run 失败: %v", err)
	}
	if len(cols) != 2 || cols[0] != "id" || cols[1] != "name" {
		t.Fatalf("列不匹配: %v", cols)
	}
	if len(rows) != 2 {
		t.Fatalf("行数应为 2，实际 %d", len(rows))
	}
	if got := fmt.Sprintf("%v", rows[0][1]); got != "张三" {
		t.Fatalf("首行 name 应为 张三，实际 %v", got)
	}
}

func TestRunLimit(t *testing.T) {
	st := newTestStore(t)
	if err := Add(st, "v_users", `SELECT "id","name" FROM "users" ORDER BY "id"`, ""); err != nil {
		t.Fatalf("Add 失败: %v", err)
	}
	_, rows, err := Run(st, "v_users", 1)
	if err != nil {
		t.Fatalf("Run 失败: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("LIMIT 1 应返回 1 行，实际 %d", len(rows))
	}
}

func TestRunMissingView(t *testing.T) {
	st := newTestStore(t)
	if _, _, err := Run(st, "v_missing", 10); err == nil {
		t.Fatalf("Run 不存在的视图应失败")
	}
}

func TestSaveViewOverwrite(t *testing.T) {
	st := newTestStore(t)
	if err := Add(st, "v_users", `SELECT "id" FROM "users"`, "第一版"); err != nil {
		t.Fatalf("首次 Add 失败: %v", err)
	}
	if err := Add(st, "v_users", `SELECT "id","name" FROM "users"`, "第二版"); err != nil {
		t.Fatalf("覆盖 Add 失败: %v", err)
	}
	v, err := st.GetView("v_users")
	if err != nil {
		t.Fatalf("GetView 失败: %v", err)
	}
	if v.Description != "第二版" {
		t.Fatalf("描述应被覆盖为 第二版，实际 %q", v.Description)
	}
	list, err := st.ListViews()
	if err != nil {
		t.Fatalf("ListViews 失败: %v", err)
	}
	count := 0
	for _, item := range list {
		if item.Name == "v_users" {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("重名视图应只有一条，实际 %d", count)
	}
}
