package search

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestScoreDetailed_TitleBeatsTagBeatsBody(t *testing.T) {
	query := "量子"
	titleScore, _ := ScoreDetailed("量子物理", "无关内容", nil, query)
	tagScore, _ := ScoreDetailed("无关标题", "无关内容", []string{"量子"}, query)
	bodyScore, _ := ScoreDetailed("无关标题", "这是一段关于量子物理的正文", nil, query)

	if titleScore <= tagScore {
		t.Fatalf("标题命中分数 %.4f 应大于标签命中分数 %.4f", titleScore, tagScore)
	}
	if tagScore <= bodyScore {
		t.Fatalf("标签命中分数 %.4f 应大于正文命中分数 %.4f", tagScore, bodyScore)
	}
}

func TestScoreDetailed_AND(t *testing.T) {
	score, matches := ScoreDetailed("机器学习", "这是关于机器学习的内容", nil, "机器 学习 不存在的词")
	if score != 0 {
		t.Fatalf("多词查询缺一词应得 0 分，实际 %.4f", score)
	}
	if matches != nil {
		t.Fatalf("得 0 分时 Matches 应为 nil，实际 %v", matches)
	}
}

func TestScoreDetailed_BigramBonus(t *testing.T) {
	// 标题含"复习"整体，比"复""习"分散在不同位置分高。
	combined, _ := ScoreDetailed("复习计划", "无关", nil, "复习")
	scattered, _ := ScoreDetailed("复 习", "无关", nil, "复习")
	if combined <= scattered {
		t.Fatalf("标题含词组整体 %.4f 应高于分散 %.4f", combined, scattered)
	}
}

func TestScoreDetailed_ExactMatchBonus(t *testing.T) {
	withExact, _ := ScoreDetailed("完整匹配内容在这里", "无关", nil, "完整匹配内容")
	without, _ := ScoreDetailed("这里包含完整和匹配和内容", "无关", nil, "完整匹配内容")
	if withExact <= without {
		t.Fatalf("标题含完整查询串 %.4f 应高于不含 %.4f", withExact, without)
	}
}

func TestScoreDetailed_CJKStopWord(t *testing.T) {
	score, matches := ScoreDetailed("随便标题", "随便正文", nil, "的")
	if score != 0 {
		t.Fatalf("查询\"的\"应被过滤得 0 分，实际 %.4f", score)
	}
	if matches != nil {
		t.Fatalf("查询\"的\"Matches 应为 nil，实际 %v", matches)
	}
	score2, _ := ScoreDetailed("随便标题", "随便正文", nil, "了")
	if score2 != 0 {
		t.Fatalf("查询\"了\"应被过滤得 0 分，实际 %.4f", score2)
	}
}

func TestScoreDetailed_BodyLengthNormalization(t *testing.T) {
	short, _ := ScoreDetailed("无关标题", "量子物理", nil, "量子")
	longBody := "量子物理"
	for i := 0; i < 2000; i++ {
		longBody += "填充内容"
	}
	long, _ := ScoreDetailed("无关标题", longBody, nil, "量子")
	if short <= long {
		t.Fatalf("同样词频下短正文 %.4f 应高于长正文 %.4f", short, long)
	}
}

func TestScoreDetailed_MatchesFields(t *testing.T) {
	score, matches := ScoreDetailed("量子标题", "量子正文", []string{"量子"}, "量子")
	if score <= 0 {
		t.Fatalf("分数应大于 0，实际 %.4f", score)
	}
	fieldSet := map[MatchField]bool{}
	for _, m := range matches {
		if m.Term != "量子" {
			t.Fatalf("Matches.Term 应为 \"量子\"，实际 %q", m.Term)
		}
		fieldSet[m.Field] = true
	}
	if !fieldSet[FieldTitle] {
		t.Fatalf("Matches 应包含 title 字段命中")
	}
	if !fieldSet[FieldTag] {
		t.Fatalf("Matches 应包含 tag 字段命中")
	}
	if !fieldSet[FieldBody] {
		t.Fatalf("Matches 应包含 body 字段命中")
	}
}

func TestRankDetailed_DescendingAndFilterZero(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "无关", Body: "完全无关内容"},
		{ID: 2, Title: "无关", Body: "量子出现在正文"},
		{ID: 3, Title: "量子标题", Body: "无关"},
	}
	ranked := RankDetailed(notes, "量子")
	if len(ranked) != 2 {
		t.Fatalf("应过滤 0 分，期望 2 条实际 %d 条", len(ranked))
	}
	if ranked[0].Note.ID != 3 {
		t.Fatalf("标题命中应排第一，实际 ID=%d", ranked[0].Note.ID)
	}
	if ranked[1].Note.ID != 2 {
		t.Fatalf("正文命中应排第二，实际 ID=%d", ranked[1].Note.ID)
	}
	if ranked[0].Score < ranked[1].Score {
		t.Fatalf("应降序排列 %.4f < %.4f", ranked[0].Score, ranked[1].Score)
	}
}

func TestScoreDetailed_EmptyQuery(t *testing.T) {
	score, matches := ScoreDetailed("标题", "正文", nil, "")
	if score != 0 {
		t.Fatalf("空查询应得 0 分，实际 %.4f", score)
	}
	if matches != nil {
		t.Fatalf("空查询 Matches 应为 nil，实际 %v", matches)
	}
}

func TestQueryTerms_FiltersStop(t *testing.T) {
	// 词典语义：停用字"的/了"被过滤；"量子"在词典 → 整词；
	// "力学"不在词典 → 逐字切成 "力"、"学"。
	terms := QueryTerms("的 量子 了 力学")
	if len(terms) != 3 {
		t.Fatalf("期望 3 个有效词，实际 %d: %v", len(terms), terms)
	}

	got := map[string]bool{}
	for _, t := range terms {
		got[t] = true
	}
	if !got["量子"] || !got["力"] || !got["学"] {
		t.Fatalf("期望包含 量子/力/学，实际 %v", terms)
	}
}
