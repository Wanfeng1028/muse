package search

import (
	"testing"
)

func TestScoreDetailed_HighlightMatchesAllFields(t *testing.T) {
	score, matches := ScoreDetailed("机器学习入门", "机器学习改变世界", []string{"机器学习"}, "机器学习")

	if score <= 0 {
		t.Fatalf("期望 score > 0，实际 score=%v", score)
	}

	type matchKey struct {
		field MatchField
		term  string
	}

	counts := make(map[matchKey]int, len(matches))
	for _, m := range matches {
		counts[matchKey{field: m.Field, term: m.Term}]++
	}

	wantKeys := []matchKey{
		{field: FieldTitle, term: "机器学习"},
		{field: FieldTag, term: "机器学习"},
		{field: FieldBody, term: "机器学习"},
	}
	for _, k := range wantKeys {
		if counts[k] != 1 {
			t.Fatalf("期望高亮集合包含且仅包含一次 %s/%q，实际计数=%d，matches=%+v", k.field, k.term, counts[k], matches)
		}
	}

	for k, c := range counts {
		if c != 1 {
			t.Errorf("期望 matches 无重复条目，但 field=%s term=%q 出现 %d 次", k.field, k.term, c)
		}
	}
}