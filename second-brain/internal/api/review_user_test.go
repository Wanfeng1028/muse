package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// createNoteAs 通过真实 HTTP 以指定用户身份创建一条笔记，返回其 id。
func createNoteAs(t *testing.T, srvURL, user, title string) int64 {
	t.Helper()
	body := map[string]any{"title": title, "content": "body of " + title}
	resp := doReviewJSONUser(t, http.MethodPost, srvURL+"/api/notes", body, user)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("create note as %q: status = %d, body = %s", user, resp.StatusCode, string(b))
	}
	var created store.Note
	if err := json.NewDecoder(resp.Body).Decode(&created); err != nil {
		t.Fatalf("decode created note: %v", err)
	}
	if created.ID == 0 {
		t.Fatalf("created note id is zero")
	}
	return created.ID
}

// getQueueAs 以指定身份（user=="" 表示不带 X-User 头）请求复习队列，返回原始响应体与状态码。
func getQueueAs(t *testing.T, srvURL, user string) (int, []byte) {
	t.Helper()
	var resp *http.Response
	if user == "" {
		resp = doReviewJSON(t, http.MethodGet, srvURL+"/api/review/queue", nil)
	} else {
		resp = doReviewJSONUser(t, http.MethodGet, srvURL+"/api/review/queue", nil, user)
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read queue body: %v", err)
	}
	return resp.StatusCode, b
}

func decodeQueue(t *testing.T, body []byte) []map[string]any {
	t.Helper()
	var items []map[string]any
	if err := json.Unmarshal(body, &items); err != nil {
		t.Fatalf("unmarshal queue %s: %v", string(body), err)
	}
	return items
}

// TestReviewUserIsolationQueue 验证 A 的到期复习 B 看不到。
func TestReviewUserIsolationQueue(t *testing.T) {
	srv, st := newReviewTestServer(t)
	yesterday := time.Now().AddDate(0, 0, -1)

	id := createNoteAs(t, srv.URL, "alice", "alice-secret")
	if _, err := st.RecordReview(id, 0, yesterday, "alice"); err != nil {
		t.Fatalf("RecordReview alice: %v", err)
	}

	// alice 看到自己的到期复习
	status, body := getQueueAs(t, srv.URL, "alice")
	if status != http.StatusOK {
		t.Fatalf("alice queue status = %d, body = %s", status, string(body))
	}
	items := decodeQueue(t, body)
	if len(items) != 1 {
		t.Fatalf("alice queue len = %d, want 1, body = %s", len(items), string(body))
	}
	if got, _ := items[0]["title"].(string); got != "alice-secret" {
		t.Fatalf("alice queue title = %q, want %q", got, "alice-secret")
	}

	// bob 看不到 alice 的数据
	status, body = getQueueAs(t, srv.URL, "bob")
	if status != http.StatusOK {
		t.Fatalf("bob queue status = %d, body = %s", status, string(body))
	}
	if string(bytes.TrimSpace(body)) != "[]" {
		t.Fatalf("bob queue body = %s, want []", string(body))
	}

	// 不带身份（默认 local）也看不到 alice 的数据
	status, body = getQueueAs(t, srv.URL, "")
	if status != http.StatusOK {
		t.Fatalf("default queue status = %d, body = %s", status, string(body))
	}
	if string(bytes.TrimSpace(body)) != "[]" {
		t.Fatalf("default queue body = %s, want []", string(body))
	}
}

// TestReviewUserQueryParam 验证 ?user= 查询参数与 X-User 头的优先级。
func TestReviewUserQueryParam(t *testing.T) {
	srv, st := newReviewTestServer(t)
	yesterday := time.Now().AddDate(0, 0, -1)

	id := createNoteAs(t, srv.URL, "alice", "alice-note")
	if _, err := st.RecordReview(id, 0, yesterday, "alice"); err != nil {
		t.Fatalf("RecordReview alice: %v", err)
	}

	// ?user=alice（不带头）→ 长度 1
	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/queue?user=alice", nil)
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("?user=alice status = %d, body = %s", resp.StatusCode, string(body))
	}
	if items := decodeQueue(t, body); len(items) != 1 {
		t.Fatalf("?user=alice queue len = %d, want 1, body = %s", len(items), string(body))
	}

	// ?user=BOB（大写，归一化为 bob，与 alice 不同）→ 长度 0
	resp = doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/queue?user=BOB", nil)
	body, _ = io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("?user=BOB status = %d, body = %s", resp.StatusCode, string(body))
	}
	if items := decodeQueue(t, body); len(items) != 0 {
		t.Fatalf("?user=BOB queue len = %d, want 0, body = %s", len(items), string(body))
	}

	// 同时带 X-User: bob 头和 ?user=alice → 按头解析（bob），长度 0
	resp = doReviewJSONUser(t, http.MethodGet, srv.URL+"/api/review/queue?user=alice", nil, "bob")
	body, _ = io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("header-over-param status = %d, body = %s", resp.StatusCode, string(body))
	}
	if items := decodeQueue(t, body); len(items) != 0 {
		t.Fatalf("header-over-param queue len = %d, want 0, body = %s", len(items), string(body))
	}
}

// TestReviewScoreIsolation 验证评分互不干扰。
func TestReviewScoreIsolation(t *testing.T) {
	srv, st := newReviewTestServer(t)
	yesterday := time.Now().AddDate(0, 0, -1)

	id := createNoteAs(t, srv.URL, "alice", "alice-card")
	if _, err := st.RecordReview(id, 0, yesterday, "alice"); err != nil {
		t.Fatalf("RecordReview alice: %v", err)
	}

	// bob 给同一 note id 打 5 分 → 200（为 bob 自动建行，不 404）
	reviewURL := srv.URL + "/api/review/" + itoa(id)
	resp := doReviewJSONUser(t, http.MethodPost, reviewURL, map[string]any{"grade": 5}, "bob")
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("bob grade status = %d, body = %s", resp.StatusCode, string(body))
	}

	// bob 刚打 5 分，due=明天 → 队列空
	status, qbody := getQueueAs(t, srv.URL, "bob")
	if status != http.StatusOK {
		t.Fatalf("bob queue status = %d, body = %s", status, string(qbody))
	}
	if string(bytes.TrimSpace(qbody)) != "[]" {
		t.Fatalf("bob queue body = %s, want []", string(qbody))
	}

	// alice 的到期行未被 bob 影响 → 仍为 1
	status, qbody = getQueueAs(t, srv.URL, "alice")
	if status != http.StatusOK {
		t.Fatalf("alice queue status = %d, body = %s", status, string(qbody))
	}
	if items := decodeQueue(t, qbody); len(items) != 1 {
		t.Fatalf("alice queue len = %d, want 1, body = %s", len(items), string(qbody))
	}

	// stats 隔离
	status, sbody := getStatsAs(t, srv.URL, "alice")
	if status != http.StatusOK {
		t.Fatalf("alice stats status = %d, body = %s", status, string(sbody))
	}
	aliceStats := decodeStats(t, sbody)
	if aliceStats["dueToday"] != float64(1) {
		t.Fatalf("alice dueToday = %v, want 1, body = %s", aliceStats["dueToday"], string(sbody))
	}

	status, sbody = getStatsAs(t, srv.URL, "bob")
	if status != http.StatusOK {
		t.Fatalf("bob stats status = %d, body = %s", status, string(sbody))
	}
	bobStats := decodeStats(t, sbody)
	if bobStats["dueToday"] != float64(0) {
		t.Fatalf("bob dueToday = %v, want 0, body = %s", bobStats["dueToday"], string(sbody))
	}
}

// getStatsAs 以指定身份请求复习统计。
func getStatsAs(t *testing.T, srvURL, user string) (int, []byte) {
	t.Helper()
	resp := doReviewJSONUser(t, http.MethodGet, srvURL+"/api/review/stats", nil, user)
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read stats body: %v", err)
	}
	return resp.StatusCode, b
}

func decodeStats(t *testing.T, body []byte) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		t.Fatalf("unmarshal stats %s: %v", string(body), err)
	}
	return m
}

// TestReviewDigestIsolation 验证 digest 只反映该用户自己的笔记。
//
// 语义：digest = 该用户到期优先 + 该用户从未复习过的笔记补足。
func TestReviewDigestIsolation(t *testing.T) {
	srv, st := newReviewTestServer(t)
	yesterday := time.Now().AddDate(0, 0, -1)

	a1 := createNoteAs(t, srv.URL, "alice", "alice-digest")
	b1 := createNoteAs(t, srv.URL, "bob", "bob-digest")
	// 各造一条到期数据（grade 0 按 SM-2 得 due=昨天+1天=今天），使 n=1 时取到期首条确定。
	if _, err := st.RecordReview(a1, 0, yesterday, "alice"); err != nil {
		t.Fatalf("RecordReview a1: %v", err)
	}
	if _, err := st.RecordReview(b1, 0, yesterday, "bob"); err != nil {
		t.Fatalf("RecordReview b1: %v", err)
	}

	// alice 视角：digest 首条应是 A1
	resp := doReviewJSONUser(t, http.MethodGet, srv.URL+"/api/review/digest?n=1", nil, "alice")
	abody, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("alice digest status = %d, body = %s", resp.StatusCode, string(abody))
	}
	anotes := decodeDigestNotes(t, abody)
	if len(anotes) != 1 {
		t.Fatalf("alice digest len = %d, want 1, body = %s", len(anotes), string(abody))
	}
	if anotes[0] != a1 {
		t.Fatalf("alice digest notes[0].id = %d, want %d (A1)", anotes[0], a1)
	}

	// bob 视角：digest 首条应是 B1
	resp = doReviewJSONUser(t, http.MethodGet, srv.URL+"/api/review/digest?n=1", nil, "bob")
	bbody, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("bob digest status = %d, body = %s", resp.StatusCode, string(bbody))
	}
	bnotes := decodeDigestNotes(t, bbody)
	if len(bnotes) != 1 {
		t.Fatalf("bob digest len = %d, want 1, body = %s", len(bnotes), string(bbody))
	}
	if bnotes[0] != b1 {
		t.Fatalf("bob digest notes[0].id = %d, want %d (B1)", bnotes[0], b1)
	}
}

// decodeDigestNotes 从 digest 响应中提取 notes 的 id 列表。
func decodeDigestNotes(t *testing.T, body []byte) []int64 {
	t.Helper()
	var payload struct {
		Notes []struct {
			ID int64 `json:"id"`
		} `json:"notes"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatalf("unmarshal digest %s: %v", string(body), err)
	}
	ids := make([]int64, 0, len(payload.Notes))
	for _, n := range payload.Notes {
		ids = append(ids, n.ID)
	}
	return ids
}

// TestReviewDefaultUser 验证不带头时等价于显式 "local"，且与 alice 隔离。
func TestReviewDefaultUser(t *testing.T) {
	srv, st := newReviewTestServer(t)
	yesterday := time.Now().AddDate(0, 0, -1)

	// 不带头创建 → 归属 local
	id := createNoteAs(t, srv.URL, "", "local-note")

	if _, err := st.GetReviewState(id, "local"); err != nil {
		t.Fatalf("GetReviewState local: %v", err)
	}
	if _, err := st.GetReviewState(id, "alice"); err != store.ErrNotFound {
		t.Fatalf("GetReviewState alice err = %v, want ErrNotFound", err)
	}

	// 让 local 的复习到期
	if _, err := st.RecordReview(id, 0, yesterday, "local"); err != nil {
		t.Fatalf("RecordReview local: %v", err)
	}

	// 不带头能看到
	status, body := getQueueAs(t, srv.URL, "")
	if status != http.StatusOK {
		t.Fatalf("default queue status = %d, body = %s", status, string(body))
	}
	if items := decodeQueue(t, body); len(items) != 1 {
		t.Fatalf("default queue len = %d, want 1, body = %s", len(items), string(body))
	}

	// 显式 X-User: local 与不带头一致
	status, body = getQueueAs(t, srv.URL, "local")
	if status != http.StatusOK {
		t.Fatalf("X-User local queue status = %d, body = %s", status, string(body))
	}
	if items := decodeQueue(t, body); len(items) != 1 {
		t.Fatalf("X-User local queue len = %d, want 1, body = %s", len(items), string(body))
	}
}
