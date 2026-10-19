package api

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestReviewMasteryAPI(t *testing.T) {
	srv, st := newReviewTestServer(t)

	if _, err := st.CreateNote(store.Note{Title: "n1", Body: "b1", Tags: []string{"数学"}}); err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/mastery", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d, want 200", resp.StatusCode)
	}
	var body struct {
		Mastery []map[string]any `json:"mastery"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(body.Mastery) != 1 {
		t.Fatalf("len(mastery)=%d, want 1", len(body.Mastery))
	}
	if body.Mastery[0]["tag"] != "数学" {
		t.Fatalf("tag=%v, want 数学", body.Mastery[0]["tag"])
	}
}

func TestReviewMasteryAPIEmpty(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/mastery", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d, want 200", resp.StatusCode)
	}
	var body struct {
		Mastery []map[string]any `json:"mastery"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body.Mastery == nil || len(body.Mastery) != 0 {
		t.Fatalf("mastery=%v, want empty array", body.Mastery)
	}
}
