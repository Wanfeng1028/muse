package store

import (
	"errors"
	"testing"
)

// openTestStore 打开内存库并执行 Migrate，返回 Store 与清理函数。
// 任意一步失败直接 t.Fatalf，避免后续断言基于脏状态。
func openTestStore(t *testing.T) *Store {
	t.Helper()
	st, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open(\":memory:\") 期望成功，实际错误: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("首次 Migrate() 期望成功，实际错误: %v", err)
	}
	return st
}

// TestMigrateAddsOriginColumnToLegacyTable 验证老库迁移兼容：
// 旧 _m_views 表无 origin 列，Migrate 需补列并回填 manual，且幂等；
// 迁移后 SaveYAMLView 写入的记录 origin 应为 yaml。
func TestMigrateAddsOriginColumnToLegacyTable(t *testing.T) {
	st, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open(\":memory:\") 期望成功，实际错误: %v", err)
	}

	// 手动构造旧 schema：无 origin 列。
	legacyDDL := `CREATE TABLE "_m_views" ("name" TEXT PRIMARY KEY, "sql" TEXT, "description" TEXT, "created_at" TEXT)`
	if _, err := st.DB.Exec(legacyDDL); err != nil {
		t.Fatalf("建旧 schema _m_views 期望成功，实际错误: %v", err)
	}
	if _, err := st.DB.Exec(
		`INSERT INTO "_m_views" ("name","sql","description","created_at") VALUES (?,?,?,?)`,
		"v_old", "SELECT 1", "旧视图", "2024-01-01T00:00:00Z",
	); err != nil {
		t.Fatalf("插入旧行期望成功，实际错误: %v", err)
	}

	// 首次迁移必须成功。
	if err := st.Migrate(); err != nil {
		t.Fatalf("对旧库 Migrate() 期望成功，实际错误: %v", err)
	}
	// 幂等：再次迁移也必须成功。
	if err := st.Migrate(); err != nil {
		t.Fatalf("重复 Migrate() 期望幂等成功，实际错误: %v", err)
	}

	// 旧记录 origin 应被回填为 manual。
	old, err := st.GetView("v_old")
	if err != nil {
		t.Fatalf("GetView(\"v_old\") 期望成功，实际错误: %v", err)
	}
	if old.Origin != "manual" {
		t.Fatalf("旧视图 origin 期望 \"manual\"，实际 %q", old.Origin)
	}

	// 迁移后写入的 YAML 视图 origin 应为 yaml。
	if err := st.SaveYAMLView("v_new", "SELECT 2", "新"); err != nil {
		t.Fatalf("SaveYAMLView(\"v_new\") 期望成功，实际错误: %v", err)
	}
	nw, err := st.GetView("v_new")
	if err != nil {
		t.Fatalf("GetView(\"v_new\") 期望成功，实际错误: %v", err)
	}
	if nw.Origin != "yaml" {
		t.Fatalf("新视图 origin 期望 \"yaml\"，实际 %q", nw.Origin)
	}
}

// TestSaveViewKeepsManualOrigin 验证 SaveView 的 upsert 分支不会篡改 origin：
// 重复保存仅更新 desc，origin 始终为 manual。
func TestSaveViewKeepsManualOrigin(t *testing.T) {
	st := openTestStore(t)

	if err := st.SaveView("v_m", "SELECT 1", "手工"); err != nil {
		t.Fatalf("首次 SaveView 期望成功，实际错误: %v", err)
	}
	v1, err := st.GetView("v_m")
	if err != nil {
		t.Fatalf("首次 GetView 期望成功，实际错误: %v", err)
	}
	if v1.Origin != "manual" {
		t.Fatalf("首次保存 origin 期望 \"manual\"，实际 %q", v1.Origin)
	}

	// 第二次保存：改 desc，触发 upsert 更新分支。
	if err := st.SaveView("v_m", "SELECT 1", "手工-改"); err != nil {
		t.Fatalf("二次 SaveView 期望成功，实际错误: %v", err)
	}
	v2, err := st.GetView("v_m")
	if err != nil {
		t.Fatalf("二次 GetView 期望成功，实际错误: %v", err)
	}
	if v2.Origin != "manual" {
		t.Fatalf("upsert 后 origin 期望保持 \"manual\"，实际 %q", v2.Origin)
	}
}

// TestSaveYAMLViewSetsYamlOrigin 验证 SaveYAMLView 始终写入/保持 origin=yaml，
// 且重复保存会更新 SQL。
func TestSaveYAMLViewSetsYamlOrigin(t *testing.T) {
	st := openTestStore(t)

	if err := st.SaveYAMLView("v_y", "SELECT 1", ""); err != nil {
		t.Fatalf("首次 SaveYAMLView 期望成功，实际错误: %v", err)
	}
	v1, err := st.GetView("v_y")
	if err != nil {
		t.Fatalf("首次 GetView 期望成功，实际错误: %v", err)
	}
	if v1.Origin != "yaml" {
		t.Fatalf("首次保存 origin 期望 \"yaml\"，实际 %q", v1.Origin)
	}

	// 二次保存：SQL 应更新，origin 仍为 yaml。
	if err := st.SaveYAMLView("v_y", "SELECT 2", "改"); err != nil {
		t.Fatalf("二次 SaveYAMLView 期望成功，实际错误: %v", err)
	}
	v2, err := st.GetView("v_y")
	if err != nil {
		t.Fatalf("二次 GetView 期望成功，实际错误: %v", err)
	}
	if v2.SQL != "SELECT 2" {
		t.Fatalf("二次保存 SQL 期望 \"SELECT 2\"，实际 %q", v2.SQL)
	}
	if v2.Origin != "yaml" {
		t.Fatalf("二次保存 origin 期望保持 \"yaml\"，实际 %q", v2.Origin)
	}
}

// 编译期兜底：确保 ErrNotFound 语义可用（errors.Is 判定），避免遗漏导入。
var _ = errors.Is
