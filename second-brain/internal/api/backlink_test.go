package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// createNoteAPI 经真实 HTTP 建一篇笔记，返回其 id。
func createNoteAPI(t *testing.T, srv *httptest.Server, title, body string) int64 {
	t.Helper()
	resp := doJSON(t, srv, "POST", "/api/notes", map[string]string{"title": title, "body": body})
	if resp.StatusCode != http.StatusCreated {
		b, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		t.Fatalf("POST /api/notes status = %d, want 201; body = %s", resp.StatusCode, string(b))
	}
	var n store.Note
	decodeBody(t, resp, &n)
	if n.ID == 0 {
		t.Fatalf("created note id = 0")
	}
	return n.ID
}

func TestBacklinks_HasReferrer(t *testing.T) {
	srv := newTestServer(t)

	betaID := createNoteAPI(t, srv, "Beta", "target body")
	createNoteAPI(t, srv, "Alpha", "see [[Beta]] for details")

	resp, err := http.Get(srv.URL + fmt.Sprintf("/api/notes/%d/backlinks", betaID))
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, body = %s", resp.StatusCode, string(body))
	}

	var got []store.Backlink
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1; got = %+v", len(got), got)
	}
	if got[0].Title != "Alpha" {
		t.Errorf("title = %q, want %q", got[0].Title, "Alpha")
	}
	if got[0].TargetTitle != "Beta" {
		t.Errorf("targetTitle = %q, want %q", got[0].TargetTitle, "Beta")
	}
	if !strings.Contains(got[0].Snippet, "[[Beta]]") {
		t.Errorf("snippet = %q, want to contain %q", got[0].Snippet, "[[Beta]]")
	}
}

func TestBacklinks_NoReferrer(t *testing.T) {
	srv := newTestServer(t)

	id := createNoteAPI(t, srv, "Lonely", "no links here")

	resp, err := http.Get(srv.URL + fmt.Sprintf("/api/notes/%d/backlinks", id))
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, body = %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	trimmed := strings.TrimSpace(string(body))
	if trimmed != "[]" {
		t.Fatalf("body = %q, want %q", trimmed, "[]")
	}
}

func TestBacklinks_NotFound(t *testing.T) {
	srv := newTestServer(t)

	resp, err := http.Get(srv.URL + "/api/notes/999999/backlinks")
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNotFound {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want %d; body = %s", resp.StatusCode, http.StatusNotFound, string(body))
	}
}

func TestBacklinks_InvalidID(t *testing.T) {
	srv := newTestServer(t)

	resp, err := http.Get(srv.URL + "/api/notes/abc/backlinks")
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want non-200; body = %s", resp.StatusCode, string(body))
	}
}
