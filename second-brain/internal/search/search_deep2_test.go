package search

import (
	"math"
	"reflect"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestScore_ExactValue_Deep2(t *testing.T) {
	got := Score("Go 并发编程", "Go Go Go", "Go")
	// Tokenize 已去重保序：标题中 "go" 计 1 次 → 3.0；正文 "Go Go Go" 去重后仅 ["go"] 计 1 次 → 1.0；合计 4.0
	if got != 4.0 {
		t.Fatalf("Score = %v, want 4.0", got)
	}
}

func TestScore_RepeatedQueryTermsDeduped_Deep2(t *testing.T) {
	s1 := Score("Go 指南", "", "go go go")
	s2 := Score("Go 指南", "", "go")
	if s1 != s2 {
		t.Fatalf("Score(go go go)=%v != Score(go)=%v", s1, s2)
	}
	if s1 != 3.0 {
		t.Fatalf("Score = %v, want 3.0", s1)
	}
}

func TestTokenize_Alphanumeric_Deep2(t *testing.T) {
	got := Tokenize("abc123 XYZ-99")
	want := []string{"abc123", "xyz", "99"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Tokenize = %v, want %v", got, want)
	}
}

func TestScoreDetailed_TagInternalDedup_Deep2(t *testing.T) {
	score, matches := ScoreDetailed("t", "b", []string{"go go"}, "go")
	if score != 2.0 {
		t.Fatalf("score = %v, want 2.0", score)
	}
	if len(matches) == 0 {
		t.Fatalf("matches empty, want non-empty")
	}
}

func TestScoreDetailed_TagCountsPerTag_Deep2(t *testing.T) {
	score, _ := ScoreDetailed("t", "b", []string{"go", "go 语言"}, "go")
	if score != 8.0 {
		t.Fatalf("score = %v, want 8.0", score)
	}
}

func TestScoreDetailed_BigramDedup_Deep2(t *testing.T) {
	// 意图不变：验证查询二元组去重后不重复计分。
	// 新词典语义下 "学习" 是整词，标题/查询分词均为 ["学习"]，
	// 查询二元组 {学习, 习学} 去重后各计一次。
	score, _ := ScoreDetailed("学习学习", "", nil, "学习学习")
	if score != 12.0 {
		t.Fatalf("score = %v, want 12.0", score)
	}
}

func TestScoreDetailed_PhraseBonusFallsToTag_Deep2(t *testing.T) {
	score, _ := ScoreDetailed("无关", "无关", []string{"机器学习"}, "机器学习")
	if score != 10.5 {
		t.Fatalf("score = %v, want 10.5", score)
	}
}

func TestScoreDetailed_PhraseBonusFallsToBody_Deep2(t *testing.T) {
	score, _ := ScoreDetailed("无关标题", "机器学习很有趣", nil, "机器学习")
	normalizer := 1 + math.Log10(1.0+7.0/200.0)
	expected := 1.0/normalizer + 3.0
	if math.Abs(score-expected) >= 1e-9 {
		t.Fatalf("score = %v, want %v", score, expected)
	}
}

func TestScoreDetailed_TagOnlyHit_Deep2(t *testing.T) {
	score, matches := ScoreDetailed("aaa", "bbb", []string{"golang"}, "golang")
	if score != 6.0 {
		t.Fatalf("score = %v, want 6.0", score)
	}
	found := false
	for _, m := range matches {
		if m.Field == FieldTag && m.Term == "golang" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("matches = %v, want to contain {Field:FieldTag, Term:golang}", matches)
	}
}

func TestSearchWithFallback_OrTitleBonusOrder_Deep2(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "Go 指南", Body: ""},
		{ID: 2, Title: "Python", Body: "python python"},
	}
	res := SearchWithFallback(notes, "Go Python", 0)
	if len(res) != 2 {
		t.Fatalf("len(res) = %d, want 2", len(res))
	}
	if res[0].Note.ID != 2 {
		t.Fatalf("res[0].Note.ID = %d, want 2", res[0].Note.ID)
	}
	if res[1].Note.ID != 1 {
		t.Fatalf("res[1].Note.ID = %d, want 1", res[1].Note.ID)
	}
}
