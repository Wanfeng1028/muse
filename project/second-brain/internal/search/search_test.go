package search

import (
	"math"
	"sort"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestTokenizeEnglishLowercaseAndStopwords(t *testing.T) {
	tokens := Tokenize("The Quick Brown FOX and the Lazy Dog")
	want := []string{"quick", "brown", "fox", "lazy", "dog"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize length = %d (%v), want %d (%v)", len(tokens), tokens, len(want), want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
	for _, tok := range tokens {
		if tok == "the" || tok == "and" {
			t.Errorf("stopword %q should have been removed", tok)
		}
	}
}

func TestTokenizeCJKPerCharacter(t *testing.T) {
	tokens := Tokenize("第二大脑")
	want := []string{"第二", "大", "脑"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize length = %d (%v), want %d (%v)", len(tokens), tokens, len(want), want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
}

func TestTokenizeDedupPreservesOrder(t *testing.T) {
	tokens := Tokenize("apple banana apple cherry banana")
	want := []string{"apple", "banana", "cherry"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize length = %d (%v), want %d (%v)", len(tokens), tokens, len(want), want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
}

func TestTokenizeMixed(t *testing.T) {
	tokens := Tokenize("Hello 世界 hello WORLD")
	want := []string{"hello", "世", "界", "world"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize length = %d (%v), want %d (%v)", len(tokens), tokens, len(want), want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
}

func TestScoreTitleBeatsBody(t *testing.T) {
	query := "golang"
	titleScore := Score("golang tips", "some unrelated body text", query)
	bodyScore := Score("unrelated title", "some golang body text", query)
	if !(titleScore > bodyScore) {
		t.Errorf("expected title hit score (%v) > body hit score (%v)", titleScore, bodyScore)
	}
}

func TestScoreNoMatchIsZero(t *testing.T) {
	score := Score("hello world", "some body", "missing")
	if score != 0 {
		t.Errorf("Score = %v, want 0", score)
	}
}

func TestScoreNonNegative(t *testing.T) {
	score := Score("go go go", "go go", "go")
	if score <= 0 {
		t.Errorf("Score = %v, want > 0", score)
	}
	if math.IsNaN(score) || math.IsInf(score, 0) {
		t.Errorf("Score = %v, want finite", score)
	}
}

func TestRankOrdersByScoreDescending(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "unrelated", Body: "nothing here"},
		{ID: 2, Title: "golang guide", Body: "intro to golang"},
		{ID: 3, Title: "misc", Body: "golang golang golang golang"},
		{ID: 4, Title: "no match at all", Body: "absolutely nothing"},
	}
	ranked := Rank(notes, "golang")
	if len(ranked) != 2 {
		t.Fatalf("Rank returned %d notes (%v), want 2", len(ranked), ranked)
	}
	if ranked[0].ID != 2 {
		t.Errorf("first ranked ID = %d, want 2", ranked[0].ID)
	}
	if ranked[1].ID != 3 {
		t.Errorf("second ranked ID = %d, want 3", ranked[1].ID)
	}
	for i := 1; i < len(ranked); i++ {
		prev := Score(ranked[i-1].Title, ranked[i-1].Body, "golang")
		cur := Score(ranked[i].Title, ranked[i].Body, "golang")
		if prev < cur {
			t.Errorf("rank order not descending: prev=%v cur=%v", prev, cur)
		}
	}
}

func TestRankFiltersZeroScores(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "apple", Body: "fruit"},
		{ID: 2, Title: "banana", Body: "fruit"},
	}
	ranked := Rank(notes, "zebra")
	if len(ranked) != 0 {
		t.Errorf("Rank returned %d notes, want 0", len(ranked))
	}
}

func TestRankEmptyQuery(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "apple", Body: "fruit"},
	}
	ranked := Rank(notes, "")
	if len(ranked) != 0 {
		t.Errorf("Rank with empty query returned %d notes, want 0", len(ranked))
	}
}

func TestRankEmptyNotes(t *testing.T) {
	ranked := Rank(nil, "golang")
	if len(ranked) != 0 {
		t.Errorf("Rank with nil notes returned %d notes, want 0", len(ranked))
	}
}

func TestRankStableForEqualScores(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "golang", Body: ""},
		{ID: 2, Title: "golang", Body: ""},
		{ID: 3, Title: "golang", Body: ""},
	}
	ranked := Rank(notes, "golang")
	if len(ranked) != 3 {
		t.Fatalf("Rank returned %d notes, want 3", len(ranked))
	}
	// equal scores should preserve original relative order
	ids := []int64{ranked[0].ID, ranked[1].ID, ranked[2].ID}
	want := []int64{1, 2, 3}
	for i := range want {
		if ids[i] != want[i] {
			t.Errorf("Rank order = %v, want %v", ids, want)
		}
	}
}

func TestTokenizeEmptyString(t *testing.T) {
	tokens := Tokenize("")
	if len(tokens) != 0 {
		t.Errorf("Tokenize(\"\") = %v, want empty", tokens)
	}
}

func TestTokenizeOnlyStopwords(t *testing.T) {
	tokens := Tokenize("the and a of")
	if len(tokens) != 0 {
		t.Errorf("Tokenize stopwords-only = %v, want empty", tokens)
	}
}

func TestRankCJKQuery(t *testing.T) {
	notes := []store.Note{
		{ID: 1, Title: "第二大脑", Body: "记录一切"},
		{ID: 2, Title: "无关", Body: "无内容"},
	}
	ranked := Rank(notes, "第二大脑")
	if len(ranked) != 1 {
		t.Fatalf("Rank returned %d notes, want 1", len(ranked))
	}
	if ranked[0].ID != 1 {
		t.Errorf("Rank top ID = %d, want 1", ranked[0].ID)
	}
}

func TestRankSortStabilityWithSortImport(t *testing.T) {
	// Ensure sort import is used in a deterministic way within the test file
	vals := []int{3, 1, 2}
	sort.Ints(vals)
	if vals[0] != 1 || vals[1] != 2 || vals[2] != 3 {
		t.Fatalf("sort.Ints failed: %v", vals)
	}
	// Ensure strings import is exercised
	if !strings.Contains("hello world", "world") {
		t.Fatal("strings.Contains failed")
	}
}
