package api

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// TestSearchFallbackOrRecall：两篇各命中一个 token 的笔记，AND 无结果 → OR 降级召回两篇。
func TestSearchFallbackOrRecall(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	// 建笔记 1：量子力学入门（含 量子、纠缠）
	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title":   "量子力学入门",
		"content": "量子 纠缠 基础介绍",
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("建笔记1状态 = %d, want 201", resp.StatusCode)
	}
	var n1 store.Note
	decodeBody(t, resp, &n1)

	// 建笔记 2：机器学习应用（含 应用、落地）
	resp = doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title":   "机器学习应用",
		"content": "应用 落地 案例",
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("建笔记2状态 = %d, want 201", resp.StatusCode)
	}
	var n2 store.Note
	decodeBody(t, resp, &n2)

	// object 响应
	resp = doJSON(t, srv, http.MethodGet, "/api/search?q=%E9%87%8F%E5%AD%90%20%E5%BA%94%E7%94%A8", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("search 状态 = %d, want 200", resp.StatusCode)
	}
	var body struct {
		Query    string       `json:"query"`
		Terms    []string     `json:"terms"`
		Notes    []store.Note `json:"notes"`
		Fallback bool         `json:"fallback"`
	}
	decodeBody(t, resp, &body)
	if len(body.Notes) != 2 {
		t.Fatalf("object notes 条数 = %d, want 2", len(body.Notes))
	}
	if !body.Fallback {
		t.Fatalf("object fallback = false, want true")
	}
	if len(body.Terms) != 2 {
		t.Fatalf("terms 条数 = %d, want 2", len(body.Terms))
	}
	seen := map[string]bool{}
	for _, term := range body.Terms {
		seen[term] = true
	}
	if !seen["量子"] || !seen["应用"] {
		t.Fatalf("terms = %v, want 含 量子 与 应用", body.Terms)
	}

	// legacy 响应
	resp = doJSON(t, srv, http.MethodGet, "/api/search?q=%E9%87%8F%E5%AD%90%20%E5%BA%94%E7%94%A8&format=legacy", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("legacy search 状态 = %d, want 200", resp.StatusCode)
	}
	var arr []store.Note
	decodeBody(t, resp, &arr)
	if len(arr) != 2 {
		t.Fatalf("legacy 数组条数 = %d, want 2", len(arr))
	}
	// 确认返回的是 store.Note 结构，字段有效
	for i, n := range arr {
		if n.ID == 0 {
			t.Fatalf("legacy[%d].ID = 0, want 非零", i)
		}
	}
}

// TestSearchFallbackNotTriggered：一篇同时含两词的笔记 → AND 命中，fallback=false 且 notes=1。
func TestSearchFallbackNotTriggered(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title":   "量子应用综述",
		"content": "量子 与 应用 的结合",
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("建笔记状态 = %d, want 201", resp.StatusCode)
	}
	var n store.Note
	decodeBody(t, resp, &n)

	resp = doJSON(t, srv, http.MethodGet, "/api/search?q=%E9%87%8F%E5%AD%90%20%E5%BA%94%E7%94%A8", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("search 状态 = %d, want 200", resp.StatusCode)
	}
	var body struct {
		Notes    []store.Note `json:"notes"`
		Fallback bool         `json:"fallback"`
	}
	decodeBody(t, resp, &body)
	if len(body.Notes) != 1 {
		t.Fatalf("notes 条数 = %d, want 1", len(body.Notes))
	}
	if body.Fallback {
		t.Fatalf("fallback = true, want false（AND 命中）")
	}
}
