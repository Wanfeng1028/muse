package search

// 深测补强：CJK 搜索 recall 边界（分词/停用/OR 降级/排序）。
// 模型生成 + 编排手工修正落盘（修正：RankedNote 无 Title 字段，只用 HitCount/len 断言）。

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestTokenize_混合中英(t *testing.T) {
	tokens := Tokenize("AI绘画教程")

	hasAI := false
	for _, tok := range tokens {
		if tok == "ai" {
			hasAI = true
			break
		}
	}
	if !hasAI {
		t.Errorf("期望包含 'ai'，实际 tokens: %v", tokens)
	}

	// CJK 部分经 SegmentCJK 分词后非空
	hasCJK := false
	for _, tok := range tokens {
		if tok != "ai" {
			hasCJK = true
			break
		}
	}
	if !hasCJK {
		t.Errorf("期望 CJK 分词结果非空，实际 tokens: %v", tokens)
	}

	// 断言结果无空串、无重复
	seen := make(map[string]bool)
	for _, tok := range tokens {
		if tok == "" {
			t.Errorf("Tokenize 结果包含空字符串")
		}
		if seen[tok] {
			t.Errorf("Tokenize 结果包含重复 token: %s", tok)
		}
		seen[tok] = true
	}
}

func TestTokenize_标点被过滤(t *testing.T) {
	// 全角逗号是标点，应被过滤
	tokens := Tokenize("，")
	if len(tokens) != 0 {
		t.Errorf("全角逗号应被过滤，期望 0 个 token，实际 %d: %v", len(tokens), tokens)
	}
}

func TestRankOr_空tokens返回nil(t *testing.T) {
	notes := []store.Note{
		{Title: "测试笔记"},
	}
	result := RankOr(notes, "，", 10)
	if result != nil {
		t.Errorf("空 tokens 应返回 nil，实际 %v", result)
	}
}

func TestSearchWithFallback_单token不降级(t *testing.T) {
	notes := []store.Note{
		{Title: "苹果发布会"},
		{Title: "香蕉价格"},
	}

	// 单 token "苹果"：AND 命中 "苹果发布会"
	result := SearchWithFallback(notes, "苹果", 10)
	if len(result) != 1 {
		t.Fatalf("单 token '苹果' 期望命中 1 条，实际 %d", len(result))
	}

	// 单 token "电脑"（词典收词）：AND 为空，且 token 数<2 不降级 OR
	result = SearchWithFallback(notes, "电脑", 10)
	if len(result) != 0 {
		t.Errorf("单 token 不降级，期望 0 条，实际 %d", len(result))
	}
}

func TestSearchWithFallback_双词降级OR(t *testing.T) {
	notes := []store.Note{
		{Title: "苹果发布会"},
		{Title: "香蕉价格"},
	}

	// 先验证前提：Tokenize("苹果 香蕉") 至少 2 个 token
	tokens := Tokenize("苹果 香蕉")
	if len(tokens) < 2 {
		t.Fatalf("前提不成立：Tokenize('苹果 香蕉') 期望 >=2 个 token，实际 %d: %v", len(tokens), tokens)
	}

	// AND 为空（无笔记同时含两词）→ 降级 OR
	result := SearchWithFallback(notes, "苹果 香蕉", 10)
	if len(result) != 2 {
		t.Fatalf("双词降级 OR 期望 2 条，实际 %d", len(result))
	}
}

func TestRankOr_排序HitCount优先(t *testing.T) {
	notes := []store.Note{
		{Title: "苹果 香蕉"},    // 两词各一次，HitCount=2
		{Title: "苹果 苹果 苹果"}, // 一词多次，HitCount=1
		{Body: "苹果 香蕉"},     // 正文含两词，HitCount=2
	}

	result := RankOr(notes, "苹果 香蕉", 10)
	if len(result) == 0 {
		t.Fatalf("RankOr 不应返回空结果")
	}
	// 排序先按 HitCount 降序，再按 Score 降序。
	// 词典分词实测：Tokenize("苹果 香蕉")=["苹果","香","蕉"]（"香蕉"未被收词，按单字切），全命中者 HitCount=3
	if result[0].HitCount != 3 {
		t.Errorf("HitCount 优先于 Score，期望第一条 HitCount=3，实际 %d", result[0].HitCount)
	}
}
