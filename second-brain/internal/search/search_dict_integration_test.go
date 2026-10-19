package search

import "testing"

func TestTokenizeDictSegmentation(t *testing.T) {
	tokens := Tokenize("量子计算")
	want := []string{"量子", "计算"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize(\"量子计算\") = %v, want %v", tokens, want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize(\"量子计算\")[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}

	tokens = Tokenize("机器学习笔记")
	want = []string{"机器学习", "笔记"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize(\"机器学习笔记\") = %v, want %v", tokens, want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize(\"机器学习笔记\")[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
}

func TestTokenizeDictFallback(t *testing.T) {
	tokens := Tokenize("大脑世界")
	want := []string{"大", "脑", "世", "界"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize(\"大脑世界\") = %v, want %v", tokens, want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize(\"大脑世界\")[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
}

func TestTokenizeDictMixedOrder(t *testing.T) {
	tokens := Tokenize("量子CPU计算")
	want := []string{"量子", "cpu", "计算"}
	if len(tokens) != len(want) {
		t.Fatalf("Tokenize(\"量子CPU计算\") = %v, want %v", tokens, want)
	}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("Tokenize(\"量子CPU计算\")[%d] = %q, want %q", i, tokens[i], want[i])
		}
	}
}

func TestQueryTermsDict(t *testing.T) {
	terms := QueryTerms("机器学习")
	want := []string{"机器学习"}
	if len(terms) != len(want) {
		t.Fatalf("QueryTerms(\"机器学习\") = %v, want %v", terms, want)
	}
	for i := range want {
		if terms[i] != want[i] {
			t.Errorf("QueryTerms(\"机器学习\")[%d] = %q, want %q", i, terms[i], want[i])
		}
	}
}

func TestScoreDetailedDictTitle(t *testing.T) {
	wholeScore, _ := ScoreDetailed("量子计算入门", "无关正文", nil, "量子计算")
	partialScore, _ := ScoreDetailed("量子计算入门", "无关正文", nil, "量子")
	if !(wholeScore > partialScore) {
		t.Errorf("expected whole-word query score (%v) > partial query score (%v)", wholeScore, partialScore)
	}
}

func TestQueryTermsDictStopwords(t *testing.T) {
	// 中文停用字过滤发生在 QueryTerms（filterCJKStop），
	// 而非 Tokenize；此处验证 QueryTerms 的过滤 + 词典分词。
	terms := QueryTerms("的学习笔记")
	want := []string{"学习", "笔记"}
	if len(terms) != len(want) {
		t.Fatalf("QueryTerms(\"的学习笔记\") = %v, want %v", terms, want)
	}
	for i := range want {
		if terms[i] != want[i] {
			t.Errorf("QueryTerms(\"的学习笔记\")[%d] = %q, want %q", i, terms[i], want[i])
		}
	}
}
