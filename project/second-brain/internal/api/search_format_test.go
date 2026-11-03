package api

import (
	"net/http"
	"testing"
)

func TestSearchFormatDefaultShape(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "测试笔记",
		"body":  "这是关于复习方法的笔记",
	})
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		t.Fatalf("create note status = %d", resp.StatusCode)
	}
	resp.Body.Close()

	resp = doJSON(t, srv, http.MethodGet, "/api/search?q=复习方法", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("search status = %d", resp.StatusCode)
	}
	var got map[string]any
	decodeBody(t, resp, &got)
	for _, key := range []string{"query", "terms", "notes", "meta"} {
		if _, ok := got[key]; !ok {
			t.Fatalf("default response missing key %q: %#v", key, got)
		}
	}
}

func TestSearchFormatLegacyReturnsArray(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "测试笔记",
		"body":  "这是关于复习方法的笔记",
	})
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		t.Fatalf("create note status = %d", resp.StatusCode)
	}
	resp.Body.Close()

	resp = doJSON(t, srv, http.MethodGet, "/api/search?q=复习方法&format=legacy", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("search status = %d", resp.StatusCode)
	}
	var got []map[string]any
	decodeBody(t, resp, &got)
	if len(got) != 1 {
		t.Fatalf("legacy result length = %d, want 1", len(got))
	}
	if _, ok := got[0]["title"]; !ok {
		t.Fatalf("legacy result missing title: %#v", got[0])
	}
}

func TestSearchFormatObjectMatchesDefault(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodPost, "/api/notes", map[string]any{
		"title": "测试笔记",
		"body":  "这是关于复习方法的笔记",
	})
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		t.Fatalf("create note status = %d", resp.StatusCode)
	}
	resp.Body.Close()

	resp = doJSON(t, srv, http.MethodGet, "/api/search?q=复习方法&format=object", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("search status = %d", resp.StatusCode)
	}
	var got map[string]any
	decodeBody(t, resp, &got)
	for _, key := range []string{"query", "terms", "notes", "meta"} {
		if _, ok := got[key]; !ok {
			t.Fatalf("format=object response missing key %q: %#v", key, got)
		}
	}
}

func TestSearchFormatInvalidReturns400(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/search?q=复习方法&format=xml", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("invalid format status = %d, want 400", resp.StatusCode)
	}
}

func TestSearchFormatLegacyEmptyQuery(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	resp := doJSON(t, srv, http.MethodGet, "/api/search?format=legacy", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("empty legacy search status = %d", resp.StatusCode)
	}
	var got []any
	decodeBody(t, resp, &got)
	if len(got) != 0 {
		t.Fatalf("empty legacy result length = %d, want 0", len(got))
	}
}
