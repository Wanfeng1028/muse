package search

import "testing"

func TestScoreDetailed_CJKContainMatchHighlight(t *testing.T) {
	score, matches := ScoreDetailed("物理笔记", "量子力学是物理学的分支", nil, "量子")

	if !(score > 0) {
		t.Fatalf("ScoreDetailed 期望 score > 0（CJK 包含匹配应命中），实际 score=%v", score)
	}

	found := false
	for _, m := range matches {
		if m.Field == FieldBody && m.Term == "量子" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("ScoreDetailed 期望 matches 中存在 Field=%q Term=%q 的条目，实际 matches=%+v",
			FieldBody, "量子", matches)
	}
}