package api

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// TestReviewHardMarkSetAndQueue 标记困难后队列里该项 hard=true，取消后 hard=false。
func TestReviewHardMarkSetAndQueue(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	if _, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"}); err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	// 先产生一条今日到期的复习记录，否则 queue 为空（SetHardMark 建的行 due 是明天）
	yesterday := time.Now().UTC().AddDate(0, 0, -1)
	if _, err := st.RecordReview(context.Background(), 1, 4, yesterday, store.DefaultUser); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}

	// 标记 hard=true
	resp := doReviewJSON(t, "POST", srv.URL+"/api/review/1/hard", map[string]any{"hard": true})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("mark hard status = %d, want 200", resp.StatusCode)
	}
	var marked struct {
		ID   int64 `json:"id"`
		Hard bool  `json:"hard"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&marked); err != nil {
		t.Fatalf("decode mark resp: %v", err)
	}
	resp.Body.Close()
	if marked.ID != 1 || marked.Hard != true {
		t.Fatalf("mark resp = %+v, want id=1 hard=true", marked)
	}

	// queue 里该篇 hard=true
	resp = doReviewJSON(t, "GET", srv.URL+"/api/review/queue", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("queue status = %d, want 200", resp.StatusCode)
	}
	var items []struct {
		ID   int64 `json:"id"`
		Hard bool  `json:"hard"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&items); err != nil {
		t.Fatalf("decode queue: %v", err)
	}
	resp.Body.Close()
	found := false
	for _, it := range items {
		if it.ID == 1 {
			found = true
			if !it.Hard {
				t.Fatalf("queue item 1 hard = false, want true")
			}
		}
	}
	if !found {
		t.Fatalf("queue missing note 1")
	}

	// 取消 hard
	resp = doReviewJSON(t, "POST", srv.URL+"/api/review/1/hard", map[string]any{"hard": false})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("unmark hard status = %d, want 200", resp.StatusCode)
	}
	var unmarked struct {
		Hard bool `json:"hard"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&unmarked); err != nil {
		t.Fatalf("decode unmark resp: %v", err)
	}
	resp.Body.Close()
	if unmarked.Hard != false {
		t.Fatalf("unmark resp hard = true, want false")
	}

	resp = doReviewJSON(t, "GET", srv.URL+"/api/review/queue", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("queue status = %d, want 200", resp.StatusCode)
	}
	items = nil
	if err := json.NewDecoder(resp.Body).Decode(&items); err != nil {
		t.Fatalf("decode queue2: %v", err)
	}
	resp.Body.Close()
	for _, it := range items {
		if it.ID == 1 && it.Hard {
			t.Fatalf("queue item 1 hard = true after unmark, want false")
		}
	}
}

// TestReviewHardMarkNotFound 不存在的笔记 id 返回 404。
func TestReviewHardMarkNotFound(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	defer srv.Close()

	resp := doReviewJSON(t, "POST", srv.URL+"/api/review/99999/hard", map[string]any{"hard": true})
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("missing note status = %d, want 404", resp.StatusCode)
	}
	resp.Body.Close()
}

// TestReviewHardMarkBadBody body 缺失 hard 字段或非法 JSON 返回 400。
func TestReviewHardMarkBadBody(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	if _, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"}); err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	resp := doReviewJSON(t, "POST", srv.URL+"/api/review/1/hard", map[string]any{})
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("empty body status = %d, want 400", resp.StatusCode)
	}
	resp.Body.Close()

	resp = doReviewJSON(t, "POST", srv.URL+"/api/review/1/hard", "not-json")
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("invalid json status = %d, want 400", resp.StatusCode)
	}
	resp.Body.Close()
}

// TestReviewHardMarkUserIsolation 用户 A 标记 hard 不影响用户 B 的队列。
func TestReviewHardMarkUserIsolation(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	if _, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"}); err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	resp := doReviewJSONUser(t, "POST", srv.URL+"/api/review/1/hard", map[string]any{"hard": true}, "A")
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("user A mark status = %d, want 200", resp.StatusCode)
	}
	resp.Body.Close()

	// 用户 B 也产生一条今日到期的复习记录，使其队列包含该笔记（hard 应为 false）
	yesterday := time.Now().UTC().AddDate(0, 0, -1)
	if _, err := st.RecordReview(context.Background(), 1, 4, yesterday, "B"); err != nil {
		t.Fatalf("RecordReview B: %v", err)
	}

	resp = doReviewJSONUser(t, "GET", srv.URL+"/api/review/queue", nil, "B")
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("user B queue status = %d, want 200", resp.StatusCode)
	}
	var items []struct {
		ID   int64 `json:"id"`
		Hard bool  `json:"hard"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&items); err != nil {
		t.Fatalf("decode queue: %v", err)
	}
	resp.Body.Close()
	found := false
	for _, it := range items {
		if it.ID == 1 {
			found = true
			if it.Hard {
				t.Fatalf("user B queue item 1 hard = true, want false")
			}
		}
	}
	if !found {
		t.Fatalf("user B queue missing note 1")
	}
}
