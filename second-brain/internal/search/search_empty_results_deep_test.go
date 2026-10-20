package search

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestSearchWithFallback_EmptyResults(t *testing.T) {
	notes := []store.Note{{Title: "hello world", Body: "foo bar"}}

	// 组 1：无意义拉丁查询，单 token，AND 为空且 token 数 <2 不触发 OR。
	res := SearchWithFallback(notes, "zzqxjkw", 10)
	if len(res) != 0 {
		t.Fatalf("SearchWithFallback(notes, \"zzqxjkw\", 10) 期望 len==0，实际 len==%d", len(res))
	}

	// 组 2：纯停用词查询，Tokenize 去停用词后为空。
	res2 := SearchWithFallback(notes, "the and", 10)
	if len(res2) != 0 {
		t.Fatalf("SearchWithFallback(notes, \"the and\", 10) 期望 len==0，实际 len==%d", len(res2))
	}

	// 组 3：空笔记列表。
	res3 := SearchWithFallback(nil, "hello", 10)
	if len(res3) != 0 {
		t.Fatalf("SearchWithFallback(nil, \"hello\", 10) 期望 len==0，实际 len==%d", len(res3))
	}

	res4 := RankOr(nil, "hello", 10)
	if len(res4) != 0 {
		t.Fatalf("RankOr(nil, \"hello\", 10) 期望 len==0，实际 len==%d", len(res4))
	}
}