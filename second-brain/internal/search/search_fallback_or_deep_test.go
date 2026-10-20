package search

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestSearchWithFallback_ORFallbackHitCountOrder(t *testing.T) {
	notes := []store.Note{
		{Title: "alpha server", Body: "x"},
		{Title: "beta client", Body: "y"},
	}
	res := SearchWithFallback(notes, "alpha beta", 10)
	if len(res) != 2 {
		t.Fatalf("OR 回退期望返回 2 条，实际 %d 条: %+v", len(res), res)
	}
	if res[0].HitCount != 1 {
		t.Fatalf("res[0] 期望 HitCount==1，实际 %d", res[0].HitCount)
	}
	if res[1].HitCount != 1 {
		t.Fatalf("res[1] 期望 HitCount==1，实际 %d", res[1].HitCount)
	}
	if res[0].Note.Title != "alpha server" {
		t.Fatalf("res[0].Note.Title 期望 %q，实际 %q", "alpha server", res[0].Note.Title)
	}
	if res[1].Note.Title != "beta client" {
		t.Fatalf("res[1].Note.Title 期望 %q，实际 %q", "beta client", res[1].Note.Title)
	}
	if res[0].Score <= 0 {
		t.Fatalf("res[0].Score 期望 > 0，实际 %v", res[0].Score)
	}
	if diff := res[0].Score - res[1].Score; diff < -1e-9 || diff > 1e-9 {
		t.Fatalf("期望 res[0].Score 与 res[1].Score 相等，实际 %v vs %v", res[0].Score, res[1].Score)
	}

	notes2 := []store.Note{{Title: "alpha beta", Body: "z"}}
	res2 := SearchWithFallback(notes2, "alpha beta", 10)
	if len(res2) != 1 {
		t.Fatalf("AND 命中期望返回 1 条，实际 %d 条: %+v", len(res2), res2)
	}
	if res2[0].HitCount != 2 {
		t.Fatalf("AND 路径期望 HitCount==2，实际 %d", res2[0].HitCount)
	}
}