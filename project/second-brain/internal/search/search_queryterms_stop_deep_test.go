package search

import (
	"testing"
)

// TestQueryTerms_CJKStopFiltered 验证 QueryTerms 对单字符中文停用字（"的"）的过滤，
// 英文停用词（"the"）在 Tokenize 阶段即被剔除，以及空查询返回空切片。
func TestQueryTerms_CJKStopFiltered(t *testing.T) {
	terms := QueryTerms("量子力学的未来")
	contains := func(list []string, target string) bool {
		for _, v := range list {
			if v == target {
				return true
			}
		}
		return false
	}

	if contains(terms, "的") {
		t.Errorf("QueryTerms(\"量子力学的未来\") 期望过滤单字停用字\"的\"，实际返回 %v", terms)
	}
	if !contains(terms, "量子力学") {
		t.Errorf("QueryTerms(\"量子力学的未来\") 期望包含词典词\"量子力学\"，实际返回 %v", terms)
	}

	terms2 := QueryTerms("the 量子")
	if contains(terms2, "the") {
		t.Errorf("QueryTerms(\"the 量子\") 期望英文停用词\"the\"已被剔除，实际返回 %v", terms2)
	}
	if !contains(terms2, "量子") {
		t.Errorf("QueryTerms(\"the 量子\") 期望包含\"量子\"，实际返回 %v", terms2)
	}

	empty := QueryTerms("")
	if len(empty) != 0 {
		t.Errorf("QueryTerms(\"\") 期望返回空切片，实际长度 %d，内容 %v", len(empty), empty)
	}
}