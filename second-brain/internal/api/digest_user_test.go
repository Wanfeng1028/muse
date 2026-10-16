package api

import (
	"encoding/json"
	"net/http"
	"testing"
	"time"
)

func digestGet(t *testing.T, url, user string) map[string]interface{} {
	t.Helper()
	var resp *http.Response
	if user == "" {
		resp = doReviewJSON(t, http.MethodGet, url, nil)
	} else {
		resp = doReviewJSONUser(t, http.MethodGet, url, nil, user)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("GET %s 期望 200，实际 %d", url, resp.StatusCode)
	}
	var out map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	return out
}

func digestNotesOf(t *testing.T, out map[string]interface{}) []interface{} {
	t.Helper()
	raw, ok := out["notes"]
	if !ok {
		t.Fatalf("响应缺少 notes 字段: %+v", out)
	}
	notes, ok := raw.([]interface{})
	if !ok {
		t.Fatalf("notes 不是数组: %T", raw)
	}
	return notes
}

func TestDigestPerUserIsolation(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	aliceID := createNoteAs(t, srv.URL, "alice", "alice-due")
	yesterday := time.Now().AddDate(0, 0, -1)
	if _, err := st.RecordReview(aliceID, 0, yesterday, "alice"); err != nil {
		t.Fatalf("alice RecordReview 失败: %v", err)
	}
	bobID := createNoteAs(t, srv.URL, "bob", "bob-due")
	if _, err := st.RecordReview(bobID, 0, yesterday, "bob"); err != nil {
		t.Fatalf("bob RecordReview 失败: %v", err)
	}

	out := digestGet(t, srv.URL+"/api/digest?n=1", "alice")
	if u, _ := out["user"].(string); u != "alice" {
		t.Fatalf("user 字段期望 alice，实际 %v", out["user"])
	}
	notes := digestNotesOf(t, out)
	if len(notes) != 1 {
		t.Fatalf("notes 长度期望 1，实际 %d", len(notes))
	}
	first, _ := notes[0].(map[string]interface{})
	if title, _ := first["title"].(string); title != "alice-due" {
		t.Fatalf("notes[0].title 期望 alice-due，实际 %v", first["title"])
	}
}

func TestDigestQueryParamUser(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	aliceID := createNoteAs(t, srv.URL, "alice", "alice-due")
	yesterday := time.Now().AddDate(0, 0, -1)
	if _, err := st.RecordReview(aliceID, 0, yesterday, "alice"); err != nil {
		t.Fatalf("alice RecordReview 失败: %v", err)
	}
	bobID := createNoteAs(t, srv.URL, "bob", "bob-due")
	if _, err := st.RecordReview(bobID, 0, yesterday, "bob"); err != nil {
		t.Fatalf("bob RecordReview 失败: %v", err)
	}

	out := digestGet(t, srv.URL+"/api/digest?n=1&user=bob", "")
	if u, _ := out["user"].(string); u != "bob" {
		t.Fatalf("user 字段期望 bob，实际 %v", out["user"])
	}
	notes := digestNotesOf(t, out)
	if len(notes) != 1 {
		t.Fatalf("notes 长度期望 1，实际 %d", len(notes))
	}
	first, _ := notes[0].(map[string]interface{})
	if title, _ := first["title"].(string); title != "bob-due" {
		t.Fatalf("notes[0].title 期望 bob-due，实际 %v", first["title"])
	}
}

func TestDigestDefaultLocalFallback(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	id := createNoteAs(t, srv.URL, "local", "local-due")
	yesterday := time.Now().AddDate(0, 0, -1)
	if _, err := st.RecordReview(id, 0, yesterday, "local"); err != nil {
		t.Fatalf("local RecordReview 失败: %v", err)
	}

	out := digestGet(t, srv.URL+"/api/digest?n=1", "")
	if u, _ := out["user"].(string); u != "local" {
		t.Fatalf("user 字段期望 local，实际 %v", out["user"])
	}
	notes := digestNotesOf(t, out)
	if len(notes) != 1 {
		t.Fatalf("notes 长度期望 1，实际 %d", len(notes))
	}
	first, _ := notes[0].(map[string]interface{})
	if title, _ := first["title"].(string); title != "local-due" {
		t.Fatalf("notes[0].title 期望 local-due，实际 %v", first["title"])
	}
}

func TestDigestHeaderBeatsQueryParam(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	aliceID := createNoteAs(t, srv.URL, "alice", "alice-due")
	yesterday := time.Now().AddDate(0, 0, -1)
	if _, err := st.RecordReview(aliceID, 0, yesterday, "alice"); err != nil {
		t.Fatalf("alice RecordReview 失败: %v", err)
	}
	bobID := createNoteAs(t, srv.URL, "bob", "bob-due")
	if _, err := st.RecordReview(bobID, 0, yesterday, "bob"); err != nil {
		t.Fatalf("bob RecordReview 失败: %v", err)
	}

	out := digestGet(t, srv.URL+"/api/digest?n=1&user=bob", "alice")
	if u, _ := out["user"].(string); u != "alice" {
		t.Fatalf("user 字段期望 alice，实际 %v", out["user"])
	}
	notes := digestNotesOf(t, out)
	if len(notes) != 1 {
		t.Fatalf("notes 长度期望 1，实际 %d", len(notes))
	}
	first, _ := notes[0].(map[string]interface{})
	if title, _ := first["title"].(string); title != "alice-due" {
		t.Fatalf("notes[0].title 期望 alice-due，实际 %v", first["title"])
	}
}

func TestPushHistoryUserFilter(t *testing.T) {
	srv, st := newReviewTestServer(t)
	defer srv.Close()

	date := time.Now().Format("2006-01-02")
	if err := st.RecordPushFor(date, "webhook", "alice", "sent", ""); err != nil {
		t.Fatalf("alice RecordPushFor 失败: %v", err)
	}
	if err := st.RecordPushFor(date, "webhook", "bob", "sent", ""); err != nil {
		t.Fatalf("bob RecordPushFor 失败: %v", err)
	}

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/push/history?user=alice", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("history?user=alice 期望 200，实际 %d", resp.StatusCode)
	}
	var records []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&records); err != nil {
		t.Fatalf("解析 alice 响应失败: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("user=alice 期望 1 条，实际 %d", len(records))
	}
	if u, _ := records[0]["user"].(string); u != "alice" {
		t.Fatalf("records[0].user 期望 alice，实际 %v", records[0]["user"])
	}

	resp2 := doReviewJSON(t, http.MethodGet, srv.URL+"/api/push/history", nil)
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("history 期望 200，实际 %d", resp2.StatusCode)
	}
	var all []map[string]interface{}
	if err := json.NewDecoder(resp2.Body).Decode(&all); err != nil {
		t.Fatalf("解析全部响应失败: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("无 user 参数期望 2 条，实际 %d", len(all))
	}
}
