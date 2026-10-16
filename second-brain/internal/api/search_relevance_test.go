package api

import (
	"encoding/json"
	"net/http"
	"testing"
)

type searchResp struct {
	Query string        `json:"query"`
	Terms []string      `json:"terms"`
	Notes []noteSummary `json:"notes"`
	Meta  []metaEntry   `json:"meta"`
}

type noteSummary struct {
	ID    int64    `json:"id"`
	Title string   `json:"title"`
	Body  string   `json:"body"`
	Tags  []string `json:"tags"`
}

type metaEntry struct {
	ID     int64    `json:"id"`
	Score  float64  `json:"score"`
	Fields []string `json:"fields"`
}

func TestSearchRelevance_HTTP(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	notes := []map[string]any{
		{"title": "量子力学导论", "body": "正文无关", "tags": []string{}},
		{"title": "无关标题", "body": "无关正文", "tags": []string{"量子"}},
		{"title": "无关标题二", "body": "这里讨论量子纠缠的正文", "tags": []string{}},
		{"title": "完全无关", "body": "完全无关内容", "tags": []string{}},
		{"title": "普通笔记", "body": "普通内容", "tags": []string{}},
	}
	for _, n := range notes {
		resp := doJSON(t, srv, http.MethodPost, "/api/notes", n)
		if resp.StatusCode != http.StatusCreated {
			t.Fatalf("创建笔记失败，状态码 %d", resp.StatusCode)
		}
		resp.Body.Close()
	}

	resp := doJSON(t, srv, http.MethodGet, "/api/search?q=%E9%87%8F%E5%AD%90", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("搜索状态码 %d", resp.StatusCode)
	}
	var got searchResp
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		t.Fatalf("解码搜索响应失败: %v", err)
	}
	resp.Body.Close()

	if len(got.Notes) != 3 {
		t.Fatalf("期望 3 条命中，实际 %d 条", len(got.Notes))
	}
	if len(got.Meta) != len(got.Notes) {
		t.Fatalf("meta 长度 %d 应与 notes 长度 %d 一致", len(got.Meta), len(got.Notes))
	}
	if got.Notes[0].Title != "量子力学导论" {
		t.Fatalf("标题命中应排第一，实际 %q", got.Notes[0].Title)
	}
	if got.Notes[1].Title != "无关标题" {
		t.Fatalf("标签命中应排第二，实际 %q", got.Notes[1].Title)
	}
	if got.Notes[2].Title != "无关标题二" {
		t.Fatalf("正文命中应排第三，实际 %q", got.Notes[2].Title)
	}

	if len(got.Meta[0].Fields) == 0 || got.Meta[0].Fields[0] != "标题" {
		t.Fatalf("第一条 meta.fields 应包含\"标题\"，实际 %v", got.Meta[0].Fields)
	}
	if len(got.Meta[1].Fields) == 0 || got.Meta[1].Fields[0] != "标签" {
		t.Fatalf("第二条 meta.fields 应包含\"标签\"，实际 %v", got.Meta[1].Fields)
	}
	if len(got.Meta[2].Fields) == 0 || got.Meta[2].Fields[0] != "正文" {
		t.Fatalf("第三条 meta.fields 应包含\"正文\"，实际 %v", got.Meta[2].Fields)
	}
	if got.Meta[0].ID != got.Notes[0].ID {
		t.Fatalf("meta[0].id=%d 应等于 notes[0].id=%d", got.Meta[0].ID, got.Notes[0].ID)
	}
	if got.Meta[0].Score <= 0 {
		t.Fatalf("meta[0].score 应大于 0，实际 %.4f", got.Meta[0].Score)
	}
}

func TestSearchRelevance_EmptyQuery(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/search?q=", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("空查询状态码 %d", resp.StatusCode)
	}
	var got searchResp
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		t.Fatalf("解码空查询响应失败: %v", err)
	}
	resp.Body.Close()

	if got.Query != "" {
		t.Fatalf("空查询 query 应为空字符串，实际 %q", got.Query)
	}
	if len(got.Terms) != 0 {
		t.Fatalf("空查询 terms 应为空，实际 %v", got.Terms)
	}
	if len(got.Notes) != 0 {
		t.Fatalf("空查询 notes 应为空，实际 %d 条", len(got.Notes))
	}
	if len(got.Meta) != 0 {
		t.Fatalf("空查询 meta 应为空，实际 %d 条", len(got.Meta))
	}
}
