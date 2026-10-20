package search

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func containsStrR3LaneE(list []string, want string) bool {
	for _, s := range list {
		if s == want {
			return true
		}
	}
	return false
}

func TestMixedCJKLatinQuery_RanksMoreHitsFirst(t *testing.T) {
	toks := Tokenize("Go 并发编程")
	if !containsStrR3LaneE(toks, "go") {
		t.Fatalf("Tokenize(\"Go 并发编程\") 期望包含小写化词元 %q，实际词元=%v", "go", toks)
	}
	if !containsStrR3LaneE(toks, "并发") {
		t.Fatalf("Tokenize(\"Go 并发编程\") 期望词典切出词元 %q，实际词元=%v", "并发", toks)
	}

	notes := []store.Note{
		{Title: "Go 并发编程指南", Body: "用 Go 写高并发程序"},
		{Title: "Go 并发", Body: "Go"},
	}
	res := RankDetailed(notes, "Go 并发")
	if len(res) != 2 {
		t.Fatalf("RankDetailed 期望返回 2 条结果，实际 len=%d，结果=%+v", len(res), res)
	}
	if res[0].Note.Title != "Go 并发编程指南" {
		t.Fatalf("RankDetailed 期望首位标题为 %q（命中词更多），实际为 %q", "Go 并发编程指南", res[0].Note.Title)
	}
	if !(res[0].Score > res[1].Score) {
		t.Fatalf("RankDetailed 期望首位分数严格大于次位，实际 res[0].Score=%v res[1].Score=%v", res[0].Score, res[1].Score)
	}
}