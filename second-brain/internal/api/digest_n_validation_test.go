package api

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

type digestItem struct {
	ID      int64    `json:"id"`
	Title   string   `json:"title"`
	Snippet string   `json:"snippet"`
	Tags    []string `json:"tags"`
	DueDate string   `json:"dueDate"`
}

type digestResponse struct {
	Error string       `json:"error,omitempty"`
	Notes []digestItem `json:"notes,omitempty"`
}

func TestDigest_NValidation_Invalid(t *testing.T) {
	srv, st := newReviewTestServer(t)

	if _, err := st.CreateNote(store.Note{Title: "d1", Body: "b"}); err != nil {
		t.Fatalf("seed d1 failed: %v", err)
	}
	if _, err := st.CreateNote(store.Note{Title: "d2", Body: "b"}); err != nil {
		t.Fatalf("seed d2 failed: %v", err)
	}
	if _, err := st.CreateNote(store.Note{Title: "d3", Body: "b"}); err != nil {
		t.Fatalf("seed d3 failed: %v", err)
	}

	t.Run("n=abc", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=abc", nil)
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if !strings.Contains(body.Error, "n 参数非法") {
			t.Fatalf("expected error containing 'n 参数非法', got %q", body.Error)
		}
	})

	t.Run("n=1.5", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=1.5", nil)
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if !strings.Contains(body.Error, "n 参数非法") {
			t.Fatalf("expected error containing 'n 参数非法', got %q", body.Error)
		}
	})

	t.Run("n=1x", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=1x", nil)
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if !strings.Contains(body.Error, "n 参数非法") {
			t.Fatalf("expected error containing 'n 参数非法', got %q", body.Error)
		}
	})

	t.Run("no n", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest", nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if len(body.Notes) != 3 {
			t.Fatalf("expected 3 notes, got %d", len(body.Notes))
		}
	})
}

func TestDigest_NValidation_Clamp(t *testing.T) {
	srv, st := newReviewTestServer(t)

	if _, err := st.CreateNote(store.Note{Title: "d1", Body: "b"}); err != nil {
		t.Fatalf("seed d1 failed: %v", err)
	}
	if _, err := st.CreateNote(store.Note{Title: "d2", Body: "b"}); err != nil {
		t.Fatalf("seed d2 failed: %v", err)
	}
	if _, err := st.CreateNote(store.Note{Title: "d3", Body: "b"}); err != nil {
		t.Fatalf("seed d3 failed: %v", err)
	}

	t.Run("n=1", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=1", nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if len(body.Notes) != 1 {
			t.Fatalf("expected 1 note, got %d", len(body.Notes))
		}
	})

	t.Run("n=0", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=0", nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if len(body.Notes) != 3 {
			t.Fatalf("expected 3 notes, got %d", len(body.Notes))
		}
	})

	t.Run("n=999", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=999", nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if len(body.Notes) != 3 {
			t.Fatalf("expected 3 notes, got %d", len(body.Notes))
		}
	})

	t.Run("n=-5", func(t *testing.T) {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/digest?n=-5", nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("expected 200, got %d", resp.StatusCode)
		}
		var body digestResponse
		decodeReviewJSON(t, resp, &body)
		if len(body.Notes) != 3 {
			t.Fatalf("expected 3 notes, got %d", len(body.Notes))
		}
	})
}
