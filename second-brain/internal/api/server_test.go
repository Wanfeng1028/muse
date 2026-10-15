package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	return httptest.NewServer(NewServer(st, config.Load()))
}

func doJSON(t *testing.T, srv *httptest.Server, method, path string, body any) *http.Response {
	t.Helper()
	var reader *bytes.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		reader = bytes.NewReader(b)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequest(method, srv.URL+path, reader)
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := srv.Client().Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	return resp
}

func decodeBody(t *testing.T, resp *http.Response, v any) {
	t.Helper()
	defer resp.Body.Close()
	if err := json.NewDecoder(resp.Body).Decode(v); err != nil {
		t.Fatalf("decode body: %v", err)
	}
}

func TestHealth(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/health", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var out map[string]string
	decodeBody(t, resp, &out)
	if out["status"] != "ok" {
		t.Fatalf("status field = %q, want ok", out["status"])
	}
}

func TestCreateNote(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "Hello World",
		"body":  "This is a **test** note with [[Other]] link.",
		"tags":  []string{"Go", "Test"},
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("status = %d, want 201", resp.StatusCode)
	}
	var n store.Note
	decodeBody(t, resp, &n)
	if n.ID == 0 {
		t.Fatalf("expected non-zero ID")
	}
	if n.Title != "Hello World" {
		t.Fatalf("title = %q", n.Title)
	}
	if len(n.Tags) != 2 {
		t.Fatalf("tags = %v", n.Tags)
	}
}

func TestListNotes(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	for i := 0; i < 3; i++ {
		resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
			"title": "Note " + string(rune('A'+i)),
			"body":  "body",
		})
		if resp.StatusCode != http.StatusCreated {
			t.Fatalf("create status = %d", resp.StatusCode)
		}
		resp.Body.Close()
	}

	resp := doJSON(t, srv, http.MethodGet, "/api/notes", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var notes []store.Note
	decodeBody(t, resp, &notes)
	if len(notes) != 3 {
		t.Fatalf("notes len = %d, want 3", len(notes))
	}
}

func TestGetNote(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	createResp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "GetMe",
		"body":  "content",
	})
	var created store.Note
	decodeBody(t, createResp, &created)

	resp := doJSON(t, srv, http.MethodGet, "/api/notes/"+itoa(created.ID), nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var got store.Note
	decodeBody(t, resp, &got)
	if got.ID != created.ID || got.Title != "GetMe" {
		t.Fatalf("got = %+v", got)
	}
}

func TestUpdateNote(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	createResp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "Original",
		"body":  "old",
	})
	var created store.Note
	decodeBody(t, createResp, &created)

	resp := doJSON(t, srv, http.MethodPut, "/api/notes/"+itoa(created.ID), map[string]any{
		"id":    created.ID,
		"title": "Updated",
		"body":  "new body",
		"tags":  []string{"x"},
	})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var updated store.Note
	decodeBody(t, resp, &updated)
	if updated.Title != "Updated" {
		t.Fatalf("title = %q", updated.Title)
	}
	if updated.Body != "new body" {
		t.Fatalf("body = %q", updated.Body)
	}
}

func TestSearch(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	for _, item := range []map[string]any{
		{"title": "Go Programming", "body": "learn golang"},
		{"title": "Cooking", "body": "make pasta"},
	} {
		r := doJSON(t, srv, http.MethodPost, "/api/notes", item)
		r.Body.Close()
	}

	resp := doJSON(t, srv, http.MethodGet, "/api/search?q=Go", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var notes []store.Note
	decodeBody(t, resp, &notes)
	if len(notes) == 0 {
		t.Fatalf("expected search results")
	}
	if notes[0].Title != "Go Programming" {
		t.Fatalf("top result = %q", notes[0].Title)
	}
}

func TestTagsAndStats(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	r1 := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "A",
		"body":  "alpha beta",
		"tags":  []string{"go", "web"},
	})
	r1.Body.Close()
	r2 := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "B",
		"body":  "gamma",
		"tags":  []string{"go"},
	})
	r2.Body.Close()

	tagsResp := doJSON(t, srv, http.MethodGet, "/api/tags", nil)
	if tagsResp.StatusCode != http.StatusOK {
		t.Fatalf("tags status = %d", tagsResp.StatusCode)
	}
	var tags []store.TagCount
	decodeBody(t, tagsResp, &tags)
	if len(tags) != 2 {
		t.Fatalf("tags len = %d, want 2", len(tags))
	}

	statsResp := doJSON(t, srv, http.MethodGet, "/api/stats", nil)
	if statsResp.StatusCode != http.StatusOK {
		t.Fatalf("stats status = %d", statsResp.StatusCode)
	}
	var stats store.Stats
	decodeBody(t, statsResp, &stats)
	if stats.Notes != 2 {
		t.Fatalf("stats.Notes = %d, want 2", stats.Notes)
	}
	if stats.Tags != 2 {
		t.Fatalf("stats.Tags = %d, want 2", stats.Tags)
	}
}

func TestDeleteThenNotFound(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	createResp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "DeleteMe",
		"body":  "x",
	})
	var created store.Note
	decodeBody(t, createResp, &created)

	delResp := doJSON(t, srv, http.MethodDelete, "/api/notes/"+itoa(created.ID), nil)
	if delResp.StatusCode != http.StatusNoContent {
		t.Fatalf("delete status = %d, want 204", delResp.StatusCode)
	}
	delResp.Body.Close()

	getResp := doJSON(t, srv, http.MethodGet, "/api/notes/"+itoa(created.ID), nil)
	if getResp.StatusCode != http.StatusNotFound {
		t.Fatalf("get status = %d, want 404", getResp.StatusCode)
	}
	getResp.Body.Close()
}

func TestInvalidJSONReturns400(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	req, err := http.NewRequest(http.MethodPost, srv.URL+"/api/notes", bytes.NewReader([]byte("{not valid json")))
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := srv.Client().Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
}

func itoa(id int64) string {
	if id == 0 {
		return "0"
	}
	neg := id < 0
	if neg {
		id = -id
	}
	var buf [20]byte
	i := len(buf)
	for id > 0 {
		i--
		buf[i] = byte('0' + id%10)
		id /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
