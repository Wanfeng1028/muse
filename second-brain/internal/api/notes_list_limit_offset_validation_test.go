package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestNotesList_LimitOffsetValidation(t *testing.T) {
	ts, st := newReviewTestServer(t)

	notes := []store.Note{
		{Title: "n1", Body: "b1"},
		{Title: "n2", Body: "b2"},
		{Title: "n3", Body: "b3"},
	}
	for _, note := range notes {
		if _, err := st.CreateNote(note); err != nil {
			t.Fatalf("seed note %q: %v", note.Title, err)
		}
	}

	tests := []struct {
		name       string
		query      string
		wantStatus int
		wantCount  int
		wantErr    string
	}{
		{"limit abc", "limit=abc", http.StatusBadRequest, 0, "limit 参数非法"},
		{"limit 1.5", "limit=1.5", http.StatusBadRequest, 0, "limit 参数非法"},
		{"limit 1x", "limit=1x", http.StatusBadRequest, 0, "limit 参数非法"},
		{"offset abc", "offset=abc", http.StatusBadRequest, 0, "offset 参数非法"},
		{"offset 1.5", "offset=1.5", http.StatusBadRequest, 0, "offset 参数非法"},
		{"offset 1x", "offset=1x", http.StatusBadRequest, 0, "offset 参数非法"},
		{"no params", "", http.StatusOK, 3, ""},
		{"limit empty", "limit=", http.StatusOK, 3, ""},
		{"offset empty", "offset=", http.StatusOK, 3, ""},
		{"limit 2", "limit=2", http.StatusOK, 2, ""},
		{"offset 1", "offset=1", http.StatusOK, 2, ""},
		{"limit negative", "limit=-5", http.StatusBadRequest, 0, "limit 参数非法"},
		{"offset negative", "offset=-10", http.StatusBadRequest, 0, "offset 参数非法"},
		{"limit huge", "limit=100000", http.StatusOK, 3, ""},
		{"limit and offset", "limit=1&offset=1", http.StatusOK, 1, ""},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			url := ts.URL + "/api/notes"
			if tt.query != "" {
				url += "?" + tt.query
			}

			resp := doReviewJSON(t, http.MethodGet, url, nil)
			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("status = %d, want %d", resp.StatusCode, tt.wantStatus)
			}

			if tt.wantStatus == http.StatusBadRequest {
				var body struct {
					Error string `json:"error"`
				}
				decodeReviewJSON(t, resp, &body)
				if !strings.Contains(body.Error, tt.wantErr) {
					t.Fatalf("error = %q, want contains %q", body.Error, tt.wantErr)
				}
				return
			}

			var got []store.Note
			if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
				t.Fatalf("decode notes: %v", err)
			}
			resp.Body.Close()

			if len(got) != tt.wantCount {
				t.Fatalf("len(notes) = %d, want %d", len(got), tt.wantCount)
			}
		})
	}
}
