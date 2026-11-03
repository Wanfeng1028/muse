package store

import (
	"database/sql"
	"errors"
	"strings"
	"testing"
)

// 已删除：复用 store_test.go 中的 newTestStore

// TestUpdateStatusPageTheme_OK 验证合法主题与主色更新后读取正确。
func TestUpdateStatusPageTheme_OK(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	if err := st.UpdateStatusPageTheme(id, "dark", "#A1b2C3"); err != nil {
		t.Fatalf("更新主题失败: %v", err)
	}
	sp, err := st.GetStatusPage(id)
	if err != nil {
		t.Fatalf("读取状态页失败: %v", err)
	}
	if sp.Theme != "dark" {
		t.Fatalf("主题应为 dark，实际为 %q", sp.Theme)
	}
	if sp.AccentColor != "#A1b2C3" {
		t.Fatalf("主色应为 #A1b2C3，实际为 %q", sp.AccentColor)
	}
}

// TestUpdateStatusPageTheme_InvalidTheme 验证非法主题被拒绝。
func TestUpdateStatusPageTheme_InvalidTheme(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	err = st.UpdateStatusPageTheme(id, "blue", "")
	if err == nil {
		t.Fatalf("期望返回错误")
	}
	if !strings.Contains(err.Error(), "主题非法") {
		t.Fatalf("错误信息应含 主题非法，实际为 %q", err.Error())
	}
}

// TestUpdateStatusPageTheme_InvalidAccent 验证非法主色被拒绝，空字符串合法。
func TestUpdateStatusPageTheme_InvalidAccent(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	bad := []string{"#123ab", "red", "#gggggg"}
	for _, c := range bad {
		err := st.UpdateStatusPageTheme(id, "dark", c)
		if err == nil {
			t.Fatalf("主色 %q 期望返回错误", c)
		}
		if !strings.Contains(err.Error(), "主色非法") {
			t.Fatalf("主色 %q 错误信息应含 主色非法，实际为 %q", c, err.Error())
		}
	}
	if err := st.UpdateStatusPageTheme(id, "dark", ""); err != nil {
		t.Fatalf("空主色应合法，实际错误: %v", err)
	}
}

// TestUpdateStatusPageTheme_NotFound 验证不存在的页面返回 sql.ErrNoRows。
func TestUpdateStatusPageTheme_NotFound(t *testing.T) {
	st := newTestStore(t)
	err := st.UpdateStatusPageTheme(999999, "dark", "")
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("期望 sql.ErrNoRows，实际为 %v", err)
	}
}

// TestStatusPageTheme_ReadPaths 验证按 slug 查询与列表查询都透出主题字段。
func TestStatusPageTheme_ReadPaths(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateStatusPage(1, "demo", "演示页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	if err := st.UpdateStatusPageTheme(id, "dark", "#123abc"); err != nil {
		t.Fatalf("更新主题失败: %v", err)
	}

	bySlug, err := st.GetStatusPageBySlug("demo")
	if err != nil {
		t.Fatalf("按 slug 读取失败: %v", err)
	}
	if bySlug.Theme != "dark" {
		t.Fatalf("按 slug 主题应为 dark，实际为 %q", bySlug.Theme)
	}
	if bySlug.AccentColor != "#123abc" {
		t.Fatalf("按 slug 主色应为 #123abc，实际为 %q", bySlug.AccentColor)
	}

	list, err := st.ListStatusPages(1)
	if err != nil {
		t.Fatalf("列出状态页失败: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("状态页数量应为 1，实际为 %d", len(list))
	}
	if list[0].Theme != "dark" {
		t.Fatalf("列表主题应为 dark，实际为 %q", list[0].Theme)
	}
	if list[0].AccentColor != "#123abc" {
		t.Fatalf("列表主色应为 #123abc，实际为 %q", list[0].AccentColor)
	}
}
