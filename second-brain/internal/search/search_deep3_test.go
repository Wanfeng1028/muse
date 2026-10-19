package search

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// TestRankOrHitCountOrdering 回归 hitCounts 索引错位 bug：
// noteHigh 命中 2 个 token（都在正文，单词分数低），
// noteSingle 只命中 1 个 token（标题命中，单词分数高）。
// 期望：命中数优先于分数，noteHigh 排在 noteSingle 之前。
func TestRankOrHitCountOrdering(t *testing.T) {
	noteHigh := store.Note{
		ID:    1,
		Title: "普通笔记",
		Body:  "量子 纠缠 基础介绍",
		Tags:  []string{},
	}
	noteSingle := store.Note{
		ID:    2,
		Title: "量子专论",
		Body:  "这是一篇专门讨论相关内容的笔记",
		Tags:  []string{},
	}
	notes := []store.Note{noteSingle, noteHigh}

	got := RankOr(notes, "量子 纠缠", 0)
	if len(got) != 2 {
		t.Fatalf("RankOr 返回条数 = %d, want 2", len(got))
	}
	if got[0].Note.ID != 1 {
		t.Fatalf("RankOr[0].ID = %d, want 1（2-hit 优先）", got[0].Note.ID)
	}
	if got[1].Note.ID != 2 {
		t.Fatalf("RankOr[1].ID = %d, want 2", got[1].Note.ID)
	}
	if got[0].HitCount != 2 {
		t.Fatalf("RankOr[0].HitCount = %d, want 2", got[0].HitCount)
	}
	if got[1].HitCount != 1 {
		t.Fatalf("RankOr[1].HitCount = %d, want 1", got[1].HitCount)
	}
	if got[0].Score > got[1].Score {
		t.Fatalf("预期 noteSingle 单词分数更高以体现“命中数优先于分数”，got Score0=%v Score1=%v",
			got[0].Score, got[1].Score)
	}
}

// TestSearchWithFallbackOrPath：无笔记同时命中两词 → 走 OR 路径，每项 HitCount>=1。
func TestSearchWithFallbackOrPath(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "量子力学入门", Body: "介绍量子相关概念", Tags: []string{}},
		{ID: 2, Title: "机器学习应用", Body: "讨论应用与落地", Tags: []string{}},
	}
	got := SearchWithFallback(notes, "量子 应用", 0)
	if len(got) != 2 {
		t.Fatalf("OR 路径返回条数 = %d, want 2", len(got))
	}
	for i, r := range got {
		if r.HitCount < 1 {
			t.Fatalf("OR 结果[%d].HitCount = %d, want >=1", i, r.HitCount)
		}
	}
}

// TestSearchWithFallbackAndPreferred：有笔记同时命中两词 → 只返回 AND 结果，不掺 OR。
func TestSearchWithFallbackAndPreferred(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "量子应用综述", Body: "量子 与 应用 的结合", Tags: []string{}},
		{ID: 2, Title: "量子力学入门", Body: "只讲量子", Tags: []string{}},
		{ID: 3, Title: "机器学习应用", Body: "只讲应用", Tags: []string{}},
	}
	got := SearchWithFallback(notes, "量子 应用", 0)
	if len(got) != 1 {
		t.Fatalf("AND 优先返回条数 = %d, want 1", len(got))
	}
	if got[0].Note.ID != 1 {
		t.Fatalf("AND 结果 ID = %d, want 1", got[0].Note.ID)
	}
	if got[0].HitCount != 2 {
		t.Fatalf("AND 结果 HitCount = %d, want 2", got[0].HitCount)
	}
}

// TestSearchWithFallbackLimit：limit=1 时 OR 路径只返回 1 篇。
func TestSearchWithFallbackLimit(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "量子力学入门", Body: "只讲量子", Tags: []string{}},
		{ID: 2, Title: "机器学习应用", Body: "只讲应用", Tags: []string{}},
	}
	got := SearchWithFallback(notes, "量子 应用", 1)
	if len(got) != 1 {
		t.Fatalf("limit=1 OR 路径返回条数 = %d, want 1", len(got))
	}
}

// TestRankOrHitCountRegression3 命中数错位 bug 的真回归测试（3 元素）。
// 旧实现（hitCounts 用追加前索引做 key + 原地 sort.SliceStable）在 3 元素插入排序
// 中途会错位：本用例旧代码给出 [B, A, C]，正确结果是 [B, C, A]。
func TestRankOrHitCountRegression3(t *testing.T) {
	filler := ""
	for i := 0; i < 200; i++ {
		filler += "填充"
	}
	notes := []store.Note{
		{ID: 1, Title: "量子专论", Body: "这是一篇专门讨论相关内容的笔记", Tags: []string{}},
		{ID: 2, Title: "普通笔记B", Body: "量子 纠缠 基础", Tags: []string{}},
		{ID: 3, Title: "普通笔记C", Body: "量子" + filler + "纠缠", Tags: []string{}},
	}
	got := RankOr(notes, "量子 纠缠", 0)
	if len(got) != 3 {
		t.Fatalf("RankOr 返回条数 = %d, want 3", len(got))
	}
	wantIDs := []int64{2, 3, 1}
	for i, want := range wantIDs {
		if got[i].Note.ID != want {
			t.Fatalf("RankOr[%d].ID = %d, want %d（2-hit 优先，B 分数高于 C）", i, got[i].Note.ID, want)
		}
	}
	for i, want := range []int{2, 2, 1} {
		if got[i].HitCount != want {
			t.Fatalf("RankOr[%d].HitCount = %d, want %d", i, got[i].HitCount, want)
		}
	}
}
