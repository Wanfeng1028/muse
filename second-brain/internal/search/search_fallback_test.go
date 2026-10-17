package search

import (
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func mkNote(title, body string, tags []string) store.Note {
	return store.Note{Title: title, Body: body, Tags: tags}
}

func TestSearchWithFallback_ANDHasResultsNoFallback(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 并发编程", "goroutine 调度器 channel", []string{"golang"}),
		mkNote("Python 入门", "python 基础语法", []string{"python"}),
	}
	res := SearchWithFallback(notes, "Go 并发", 10)
	if len(res) != 1 {
		t.Fatalf("期望 1 条结果，实际 %d", len(res))
	}
	if res[0].Note.Title != "Go 并发编程" {
		t.Errorf("期望标题 Go 并发编程，实际 %q", res[0].Note.Title)
	}
}

func TestSearchWithFallback_MultiWordANDFailsORWorks(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 并发编程", "goroutine 调度器", []string{"golang"}),
		mkNote("Python 入门", "python 基础语法", []string{"python"}),
	}
	res := SearchWithFallback(notes, "Go Python", 10)
	if len(res) == 0 {
		t.Fatalf("OR 回退后应有结果，实际 0 条")
	}
	if len(res) < 2 {
		t.Fatalf("OR 回退应命中两条，实际 %d 条", len(res))
	}
}

func TestSearchWithFallback_SingleTokenNoFallback(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 并发编程", "goroutine 调度器", []string{"golang"}),
		mkNote("Python 入门", "python 基础语法", []string{"python"}),
	}
	res := SearchWithFallback(notes, "zzzznothing", 10)
	if len(res) != 0 {
		t.Fatalf("单 token 不应回退，实际 %d 条", len(res))
	}
}

func TestSearchWithFallback_EmptyQuery(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 并发编程", "goroutine 调度器", []string{"golang"}),
	}
	res := SearchWithFallback(notes, "", 10)
	if len(res) != 0 {
		t.Fatalf("空 query 应返回空，实际 %d 条", len(res))
	}
	res2 := SearchWithFallback(notes, "   ", 10)
	if len(res2) != 0 {
		t.Fatalf("空白 query 应返回空，实际 %d 条", len(res2))
	}
}

func TestSearchWithFallback_SortByHitCountDesc(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 入门", "go 基础", []string{"golang"}),
		mkNote("Go Python", "go 和 python 混用", []string{"golang", "python"}),
		mkNote("Go Python Rust", "三门语言", []string{"golang", "python", "rust"}),
	}
	res := SearchWithFallback(notes, "Go Python Rust Java", 10)
	if len(res) < 3 {
		t.Fatalf("期望至少 3 条，实际 %d", len(res))
	}
	if res[0].Note.Title != "Go Python Rust" {
		t.Errorf("命中数最多的应排第一，实际 %q", res[0].Note.Title)
	}
	if res[len(res)-1].Note.Title != "Go 入门" {
		t.Errorf("命中数最少的应排最后，实际 %q", res[len(res)-1].Note.Title)
	}
}

func TestSearchWithFallback_TitleWeighting(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 入门", "无关正文", []string{"golang"}),
		mkNote("无关标题", "go 出现在正文里", []string{"misc"}),
	}
	res := SearchWithFallback(notes, "Go Python", 10)
	if len(res) < 2 {
		t.Fatalf("期望至少 2 条，实际 %d", len(res))
	}
	if res[0].Note.Title != "Go 入门" {
		t.Errorf("标题命中应加权排前，实际 %q", res[0].Note.Title)
	}
}

func TestSearchWithFallback_LimitTruncation(t *testing.T) {
	notes := []store.Note{
		mkNote("Go A", "go a", []string{"golang"}),
		mkNote("Go B", "go b", []string{"golang"}),
		mkNote("Go C", "go c", []string{"golang"}),
		mkNote("Go D", "go d", []string{"golang"}),
	}
	res := SearchWithFallback(notes, "Go Python", 2)
	if len(res) != 2 {
		t.Fatalf("limit=2 应截断为 2 条，实际 %d 条", len(res))
	}
	if res[0].Note.Title == "" || res[1].Note.Title == "" {
		t.Errorf("截断结果不应为空标题")
	}
}

func TestSearchWithFallback_NoMatchAnyToken(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 并发编程", "goroutine 调度器", []string{"golang"}),
	}
	res := SearchWithFallback(notes, "zzzz yyyy", 10)
	if len(res) != 0 {
		t.Fatalf("无 token 命中应返回空，实际 %d 条", len(res))
	}
}

func TestSearchWithFallback_ThreeTokensOR(t *testing.T) {
	notes := []store.Note{
		mkNote("Alpha", "alpha 内容", []string{"a"}),
		mkNote("Beta", "beta 内容", []string{"b"}),
		mkNote("Gamma", "gamma 内容", []string{"g"}),
	}
	res := SearchWithFallback(notes, "alpha beta gamma", 10)
	if len(res) != 3 {
		t.Fatalf("三 token 应各命中一条，实际 %d 条", len(res))
	}
	seen := map[string]bool{}
	for _, r := range res {
		seen[r.Note.Title] = true
	}
	if !seen["Alpha"] || !seen["Beta"] || !seen["Gamma"] {
		t.Errorf("应包含 Alpha/Beta/Gamma，实际 %v", seen)
	}
}

func TestSearchWithFallback_AndResultsTakePrecedence(t *testing.T) {
	notes := []store.Note{
		mkNote("Go 并发", "go 并发内容", []string{"golang"}),
		mkNote("Go 网络", "go 网络内容", []string{"golang"}),
	}
	res := SearchWithFallback(notes, "Go 并发", 10)
	if len(res) == 0 {
		t.Fatalf("AND 有结果时不应为空")
	}
	for _, r := range res {
		if r.Note.Title == "Go 网络" {
			t.Errorf("AND 命中时不应触发 OR 回退引入 Go 网络")
		}
	}
}