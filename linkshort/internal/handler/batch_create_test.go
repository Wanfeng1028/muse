package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func parseBatch(t *testing.T, data []byte) (map[string]any, []map[string]any) {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal batch response: %v", err)
	}
	raw, ok := m["items"].([]any)
	if !ok {
		t.Fatalf("items missing or not an array: %v", m)
	}
	items := make([]map[string]any, 0, len(raw))
	for _, r := range raw {
		im, ok := r.(map[string]any)
		if !ok {
			t.Fatalf("item is not an object: %v", r)
		}
		items = append(items, im)
	}
	return m, items
}

func batchOK(it map[string]any) bool {
	v, ok := it["ok"].(bool)
	return ok && v
}

func batchIndex(it map[string]any) int {
	return int(it["index"].(float64))
}

func batchID(it map[string]any) int64 {
	return int64(it["id"].(float64))
}

func batchErr(it map[string]any) string {
	if v, ok := it["error"]; ok && v != nil {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

func batchOKCount(m map[string]any) int {
	return int(m["ok_count"].(float64))
}

func TestBatch_EmptyArray(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{}
	resp, _ := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
}

func TestBatch_TooMany(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := make([]map[string]any, 0, 101)
	for i := 0; i < 101; i++ {
		slug := string(rune('a'+i/26)) + string(rune('a'+i%26))
		body = append(body, map[string]any{
			"url":  "https://a.com/x",
			"slug": slug,
		})
	}
	resp, _ := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
}

func TestBatch_AllOK(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/1", "slug": "s1"},
		{"url": "https://a.com/2", "slug": "s2"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("status = %d, want 201", resp.StatusCode)
	}
	m, items := parseBatch(t, data)
	if got := batchOKCount(m); got != 2 {
		t.Fatalf("ok_count = %d, want 2", got)
	}
	if len(items) != 2 {
		t.Fatalf("len(items) = %d, want 2", len(items))
	}
	if !batchOK(items[0]) {
		t.Fatalf("items[0].ok = false, want true")
	}
	if got := batchIndex(items[0]); got != 0 {
		t.Fatalf("items[0].index = %d, want 0", got)
	}
	if got := batchID(items[0]); got <= 0 {
		t.Fatalf("items[0].id = %d, want > 0", got)
	}
}

func TestBatch_Partial(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/3", "slug": "s3"},
		{"url": "ftp://bad", "slug": "s4"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusMultiStatus {
		t.Fatalf("status = %d, want 207", resp.StatusCode)
	}
	m, items := parseBatch(t, data)
	if got := batchOKCount(m); got != 1 {
		t.Fatalf("ok_count = %d, want 1", got)
	}
	if batchOK(items[1]) {
		t.Fatalf("items[1].ok = true, want false")
	}
	if batchErr(items[1]) == "" {
		t.Fatalf("items[1].error is empty, want non-empty")
	}
}

func TestBatch_DupSlug(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/5", "slug": "dup"},
		{"url": "https://a.com/6", "slug": "dup"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusMultiStatus {
		t.Fatalf("status = %d, want 207", resp.StatusCode)
	}
	_, items := parseBatch(t, data)
	if !strings.Contains(batchErr(items[1]), "重复") {
		t.Fatalf("items[1].error = %q, want contains 重复", batchErr(items[1]))
	}
}

func TestBatch_Password(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/7", "slug": "pw", "password": "x"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
	m, items := parseBatch(t, data)
	if got := batchOKCount(m); got != 0 {
		t.Fatalf("ok_count = %d, want 0", got)
	}
	if !strings.Contains(batchErr(items[0]), "密码") {
		t.Fatalf("items[0].error = %q, want contains 密码", batchErr(items[0]))
	}
}

func TestBatch_MaxVisits(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/8", "slug": "mv", "max_visits": 0},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
	_, items := parseBatch(t, data)
	if !strings.Contains(batchErr(items[0]), "max_visits") {
		t.Fatalf("items[0].error = %q, want contains max_visits", batchErr(items[0]))
	}
}

func TestBatch_BurnVisits(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/9", "slug": "bv", "burn": true, "max_visits": 5},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
	_, items := parseBatch(t, data)
	if !strings.Contains(batchErr(items[0]), "burn") {
		t.Fatalf("items[0].error = %q, want contains burn", batchErr(items[0]))
	}
}

func TestBatch_PurgeNoBurn(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/10", "slug": "pb", "purge": true, "burn": false},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
	_, items := parseBatch(t, data)
	if !strings.Contains(batchErr(items[0]), "purge") {
		t.Fatalf("items[0].error = %q, want contains purge", batchErr(items[0]))
	}
}

func TestBatch_BadExpiry(t *testing.T) {
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/11", "slug": "ex", "expires_at": "not-a-date"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
	_, items := parseBatch(t, data)
	if !strings.Contains(batchErr(items[0]), "expires_at") {
		t.Fatalf("items[0].error = %q, want contains expires_at", batchErr(items[0]))
	}
}