package search

import (
	"reflect"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// 1
func TestTokenize_MixedLatinCJK_Exact(t *testing.T) {
	got := Tokenize("iPhone手机")
	want := []string{"iphone", "手机"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Tokenize(%q)=%v want %v", "iPhone手机", got, want)
	}
}

// 2
func TestTokenize_CJKBetweenLatin(t *testing.T) {
	got := Tokenize("Go笔记")
	want := []string{"go", "笔记"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Tokenize(%q)=%v want %v", "Go笔记", got, want)
	}
}

// 3
func TestTokenize_UnknownCJKCharFallback(t *testing.T) {
	got := Tokenize("世界")
	want := []string{"世", "界"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Tokenize(%q)=%v want %v", "世界", got, want)
	}
}

// 4
func TestTokenize_PunctuationSplits(t *testing.T) {
	got := Tokenize("手机,学习！")
	want := []string{"手机", "学习"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Tokenize(%q)=%v want %v", "手机,学习！", got, want)
	}
}

// 5
func TestTokenize_KeepCJKStop_QueryTermsFilter(t *testing.T) {
	gotTok := Tokenize("的")
	wantTok := []string{"的"}
	if !reflect.DeepEqual(gotTok, wantTok) {
		t.Fatalf("Tokenize(%q)=%v want %v", "的", gotTok, wantTok)
	}

	gotQT := QueryTerms("的")
	wantQT := []string{}
	if !reflect.DeepEqual(gotQT, wantQT) {
		t.Fatalf("QueryTerms(%q)=%v want %v", "的", gotQT, wantQT)
	}
}

// 6
func TestQueryTerms_StopPlusContent(t *testing.T) {
	got := QueryTerms("的学习")
	want := []string{"学习"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("QueryTerms(%q)=%v want %v", "的学习", got, want)
	}
}

// 7
// Score("手机","无关","手机"): query terms=["手机"]; title "手机" 命中1次 → 1*3.0=3.0; body "无关" 0 → 0. 合计 3.0
// Score("无关","手机","手机"): title "无关" 0; body "手机" 命中1次 → 1*1.0=1.0. 合计 1.0
func TestScore_TitleWeight3_BodyWeight1(t *testing.T) {
	if got := Score("手机", "无关", "手机"); got != 3.0 {
		t.Fatalf("Score title hit=%v want 3.0", got)
	}
	if got := Score("无关", "手机", "手机"); got != 1.0 {
		t.Fatalf("Score body hit=%v want 1.0", got)
	}
}

// 8
// QueryTerms("量子")=["量子"]. title "量子笔记" → ["量子","笔记"], term "量子" 命中1 → 3.0; tag nil → 0;
// body "无关" → ["无","关"] 0; AND 门通过; bigram ["量子"] 在 title → +2.0; compactQuery "量子" 在 title → +5.0; bodyScore 0.
// 合计 3+2+5=10.0
func TestScoreDetailed_CompositeExact_10(t *testing.T) {
	score, matches := ScoreDetailed("量子笔记", "无关", nil, "量子")
	if score != 10.0 {
		t.Fatalf("score=%v want 10.0", score)
	}
	found := false
	for _, m := range matches {
		if m.Field == FieldTitle && m.Term == "量子" {
			found = true
		}
	}
	if !found {
		t.Fatalf("matches missing {FieldTitle,量子}: %+v", matches)
	}
}

// 9
// QueryTerms("学习笔记")=["学习","笔记"]. title "学习笔记" → ["学习","笔记"], titleScore=3+3=6;
// bigrams ["学习","习笔","笔记"] 三个都在 title 中 → 3*2=6; compactQuery "学习笔记" 在 title → +5; body 0.
// 合计 6+6+5=17.0
func TestScoreDetailed_CompositeExact_17(t *testing.T) {
	score, _ := ScoreDetailed("学习笔记", "正文", nil, "学习笔记")
	if score != 17.0 {
		t.Fatalf("score=%v want 17.0", score)
	}
}

// 10
// 三条完全相同 → 分数相同 → RankDetailed 稳定排序保持输入顺序
func TestRankDetailed_TieKeepsInputOrder(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "学习笔记", Body: "正文"},
		{ID: 2, Title: "学习笔记", Body: "正文"},
		{ID: 3, Title: "学习笔记", Body: "正文"},
	}
	got := RankDetailed(notes, "学习")
	if len(got) != 3 {
		t.Fatalf("len=%d want 3", len(got))
	}
	if got[0].Note.ID != 1 || got[1].Note.ID != 2 || got[2].Note.ID != 3 {
		t.Fatalf("order=%d,%d,%d want 1,2,3", got[0].Note.ID, got[1].Note.ID, got[2].Note.ID)
	}
}

// 11
// A title "量子" 命中 → 3.0; B body "量子" 命中 → 1.0
func TestRankDetailed_TitleHitBeatsBodyHit(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "无关", Body: "量子"},
		{ID: 2, Title: "量子", Body: "无关"},
	}
	got := RankDetailed(notes, "量子")
	if len(got) != 2 {
		t.Fatalf("len=%d want 2", len(got))
	}
	if got[0].Note.ID != 2 {
		t.Fatalf("first=%d want 2", got[0].Note.ID)
	}
}

// 12
// A: hay 含 "手机" 与 "学习" → 通过 AND 门. B: hay="手机 y" 缺 "学习" → 被门控过滤
func TestSearchWithFallback_ANDRequiresAllTokens(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "手机 学习", Body: "x"},
		{ID: 2, Title: "手机", Body: "y"},
	}
	got := SearchWithFallback(notes, "手机 学习", 0)
	if len(got) != 1 {
		t.Fatalf("len=%d want 1", len(got))
	}
	if got[0].Note.ID != 1 {
		t.Fatalf("id=%d want 1", got[0].Note.ID)
	}
}
