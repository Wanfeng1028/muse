package store

import (
	"bytes"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

// newTestStore 创建内存库并返回 Store，测试结束自动关闭
func newTestStore(t *testing.T) *Store {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open(:memory:) 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return New(database)
}

// TestCreateLink_自动与自定义slug 验证自动 slug 与自定义 slug 的创建
func TestCreateLink_自动与自定义slug(t *testing.T) {
	st := newTestStore(t)

	id1, err := st.CreateLink("", "https://example.com/a", "标题A", nil)
	if err != nil {
		t.Fatalf("CreateLink 自动 slug 失败: %v", err)
	}
	if id1 <= 0 {
		t.Fatalf("CreateLink 自动 slug 返回 id 非法: %d", id1)
	}
	l1, err := st.GetLink(id1)
	if err != nil {
		t.Fatalf("GetLink(%d) 失败: %v", id1, err)
	}
	if l1.Slug == "" {
		t.Errorf("自动生成的 slug 为空")
	}

	id2, err := st.CreateLink("my-custom-slug", "https://example.com/b", "标题B", nil)
	if err != nil {
		t.Fatalf("CreateLink 自定义 slug 失败: %v", err)
	}
	l2, err := st.GetLink(id2)
	if err != nil {
		t.Fatalf("GetLink(%d) 失败: %v", id2, err)
	}
	if l2.Slug != "my-custom-slug" {
		t.Errorf("自定义 slug 未生效: 期望 my-custom-slug，实际 %q", l2.Slug)
	}
	if l2.URL != "https://example.com/b" {
		t.Errorf("URL 未正确保存: 期望 https://example.com/b，实际 %q", l2.URL)
	}
	if l2.Title != "标题B" {
		t.Errorf("Title 未正确保存: 期望 标题B，实际 %q", l2.Title)
	}
}

// TestCreateLink_重复slug报错 验证重复 slug 返回错误
func TestCreateLink_重复slug报错(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.CreateLink("dup-slug", "https://example.com/1", "", nil); err != nil {
		t.Fatalf("第一次 CreateLink 失败: %v", err)
	}
	_, err := st.CreateLink("dup-slug", "https://example.com/2", "", nil)
	if err == nil {
		t.Errorf("重复 slug 期望返回错误，实际 nil")
	}
}

// TestListLinks_搜索分页排序 验证 ListLinks 的搜索、分页、排序
func TestListLinks_搜索分页排序(t *testing.T) {
	st := newTestStore(t)
	seeds := []struct {
		slug, url, title string
	}{
		{"alpha-1", "https://example.com/alpha", "Alpha One"},
		{"alpha-2", "https://example.com/alpha2", "Alpha Two"},
		{"beta-1", "https://example.com/beta", "Beta One"},
		{"gamma-1", "https://example.com/gamma", "Gamma One"},
	}
	for _, s := range seeds {
		if _, err := st.CreateLink(s.slug, s.url, s.title, nil); err != nil {
			t.Fatalf("CreateLink(%s) 失败: %v", s.slug, err)
		}
	}

	// 搜索
	items, total, err := st.ListLinks("alpha", 1, 10, "")
	if err != nil {
		t.Fatalf("ListLinks 搜索失败: %v", err)
	}
	if total != 2 {
		t.Errorf("搜索 alpha 期望 total=2，实际 %d", total)
	}
	if len(items) != 2 {
		t.Errorf("搜索 alpha 期望返回 2 条，实际 %d", len(items))
	}

	// 分页
	items, total, err = st.ListLinks("", 1, 2, "")
	if err != nil {
		t.Fatalf("ListLinks 分页失败: %v", err)
	}
	if total != 4 {
		t.Errorf("分页 total 期望 4，实际 %d", total)
	}
	if len(items) != 2 {
		t.Errorf("分页 perPage=2 期望返回 2 条，实际 %d", len(items))
	}

	// 排序白名单外 orderBy 应回落默认（不报错）
	_, _, err = st.ListLinks("", 1, 10, "id; DROP TABLE links")
	if err != nil {
		t.Errorf("orderBy 白名单外期望回落默认不报错，实际错误: %v", err)
	}
}

// TestRecordVisit_计数 验证 RecordVisit 后计数正确
func TestRecordVisit_计数(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLink("count-1", "https://example.com/c", "", nil)
	if err != nil {
		t.Fatalf("CreateLink 失败: %v", err)
	}
	for i := 0; i < 3; i++ {
		if err := st.RecordVisit(id, "iphash", "ua", "ref"); err != nil {
			t.Fatalf("RecordVisit 第 %d 次失败: %v", i+1, err)
		}
	}
	links, enabled, totalClicks, todayClicks, err := st.StatsOverview()
	if err != nil {
		t.Fatalf("StatsOverview 返回错误: %v", err)
	}
	if links != 1 {
		t.Errorf("StatsOverview links 期望 1，实际 %d", links)
	}
	if enabled != 1 {
		t.Errorf("StatsOverview enabledLinks 期望 1，实际 %d", enabled)
	}
	if totalClicks != 3 {
		t.Errorf("StatsOverview totalClicks 期望 3，实际 %d", totalClicks)
	}
	if todayClicks != 3 {
		t.Errorf("StatsOverview todayClicks 期望 3，实际 %d", todayClicks)
	}
}

// TestDailyClicks_补零 验证 DailyClicks 含今天且缺失日期补 0
func TestDailyClicks_补零(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLink("daily-1", "https://example.com/d", "", nil)
	if err != nil {
		t.Fatalf("CreateLink 失败: %v", err)
	}
	if err := st.RecordVisit(id, "iphash", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit 失败: %v", err)
	}
	points, err := st.DailyClicks(7)
	if err != nil {
		t.Fatalf("DailyClicks 失败: %v", err)
	}
	if len(points) != 7 {
		t.Fatalf("DailyClicks(7) 期望 7 个数据点，实际 %d", len(points))
	}
	today := time.Now().UTC().Format("2006-01-02")
	foundToday := false
	for _, p := range points {
		if p.Date == today {
			foundToday = true
			if p.Clicks != 1 {
				t.Errorf("今天点击期望 1，实际 %d", p.Clicks)
			}
		}
	}
	if !foundToday {
		t.Errorf("DailyClicks 结果中缺少今天 %s 的数据点: %+v", today, points)
	}
}

// TestExpiresAt_Roundtrip 验证过期时间存取一致
func TestExpiresAt_Roundtrip(t *testing.T) {
	st := newTestStore(t)
	exp := time.Now().UTC().Add(24 * time.Hour).Truncate(time.Second)
	id, err := st.CreateLink("exp-1", "https://example.com/e", "", &exp)
	if err != nil {
		t.Fatalf("CreateLink 失败: %v", err)
	}
	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink 失败: %v", err)
	}
	if l.ExpiresAt == nil {
		t.Fatalf("ExpiresAt 期望非空，实际 nil")
	}
	if !l.ExpiresAt.UTC().Truncate(time.Second).Equal(exp) {
		t.Errorf("ExpiresAt roundtrip 不一致: 期望 %v，实际 %v", exp, l.ExpiresAt.UTC())
	}
}

// TestDeleteLink_级联删visits 验证删除 link 后 visits 一并删除
func TestDeleteLink_级联删visits(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLink("del-1", "https://example.com/del", "", nil)
	if err != nil {
		t.Fatalf("CreateLink 失败: %v", err)
	}
	if err := st.RecordVisit(id, "iphash", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit 失败: %v", err)
	}
	if _, _, totalClicks, _, err := st.StatsOverview(); err != nil || totalClicks != 1 {
		t.Fatalf("删除前 totalClicks 期望 1，实际 %d", totalClicks)
	}
	if err := st.DeleteLink(id); err != nil {
		t.Fatalf("DeleteLink 失败: %v", err)
	}
	links, _, totalClicks, _, err := st.StatsOverview()
	if err != nil {
		t.Fatalf("StatsOverview 返回错误: %v", err)
	}
	if links != 0 {
		t.Errorf("删除后 links 期望 0，实际 %d", links)
	}
	if totalClicks != 0 {
		t.Errorf("删除后 totalClicks 期望 0（visits 应级联删除），实际 %d", totalClicks)
	}
}

// TestImportExportCSV 验证 CSV 导入导出
func TestImportExportCSV(t *testing.T) {
	st := newTestStore(t)

	// 正常导入 + 重复 slug + 非法 URL
	csvIn := "slug,url,title\n" +
		"imp-1,https://example.com/1,标题1\n" +
		"imp-2,https://example.com/2,标题2\n" +
		"imp-1,https://example.com/dup,重复\n" +
		"bad,not-a-url,非法\n"
	imported, skipped, errs := st.ImportCSV(strings.NewReader(csvIn))
	if imported != 2 {
		t.Errorf("ImportCSV imported 期望 2，实际 %d", imported)
	}
	if skipped != 2 {
		t.Errorf("ImportCSV skipped 期望 2，实际 %d", skipped)
	}
	if len(errs) != 2 {
		t.Errorf("ImportCSV errs 期望 2 条，实际 %d 条: %v", len(errs), errs)
	}

	// 导出
	var buf bytes.Buffer
	if err := st.ExportCSV(&buf); err != nil {
		t.Fatalf("ExportCSV 失败: %v", err)
	}
	out := buf.String()
	if !strings.Contains(out, "imp-1") || !strings.Contains(out, "imp-2") {
		t.Errorf("ExportCSV 输出缺少已导入记录: %q", out)
	}

	// 再导入到新 store，验证行数一致
	st2 := newTestStore(t)
	imported2, _, errs2 := st2.ImportCSV(strings.NewReader(out))
	if len(errs2) != 0 {
		t.Errorf("二次导入出现错误: %v", errs2)
	}
	if imported2 != imported {
		t.Errorf("二次导入行数不一致: 期望 %d，实际 %d", imported, imported2)
	}
}
