package api

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestReviewDigest_NValidation_Invalid(t *testing.T) {
	type digestResponse struct {
		Error string `json:"error"`
		Notes []struct {
			ID      int64    `json:"id"`
			Title   string   `json:"title"`
			Snippet string   `json:"snippet"`
			Tags    []string `json:"tags"`
			DueDate string   `json:"dueDate"`
		} `json:"notes"`
	}

	tests := []struct {
		name         string
		n            string
		wantStatus   int
		wantErrorMsg string
		wantNotes    int
	}{
		{name: "n_abc", n: "abc", wantStatus: http.StatusBadRequest, wantErrorMsg: "n 参数非法"},
		{name: "n_1.5", n: "1.5", wantStatus: http.StatusBadRequest, wantErrorMsg: "n 参数非法"},
		{name: "n_1x", n: "1x", wantStatus: http.StatusBadRequest, wantErrorMsg: "n 参数非法"},
		{name: "n_missing", wantStatus: http.StatusOK, wantNotes: 3},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv, st := newReviewTestServer(t)
			for _, title := range []string{"d1", "d2", "d3"} {
				if _, err := st.CreateNote(store.Note{Title: title, Body: "b"}); err != nil {
					t.Fatalf("CreateNote(%q) failed: %v", title, err)
				}
			}

			url := srv.URL + "/api/review/digest"
			if tt.n != "" {
				url += "?n=" + tt.n
			}

			resp := doReviewJSON(t, http.MethodGet, url, nil)

			var body digestResponse
			decodeReviewJSON(t, resp, &body)

			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("status code = %d, want %d", resp.StatusCode, tt.wantStatus)
			}

			if tt.wantErrorMsg != "" {
				if !strings.Contains(body.Error, tt.wantErrorMsg) {
					t.Fatalf("error = %q, want it to contain %q", body.Error, tt.wantErrorMsg)
				}
				return
			}

			if len(body.Notes) != tt.wantNotes {
				t.Fatalf("len(notes) = %d, want %d", len(body.Notes), tt.wantNotes)
			}
		})
	}
}
func TestReviewDigest_NValidation_Clamp(t *testing.T) {
	tests := []struct {
		name    string
		n       string
		wantLen int
	}{
		{"n=1", "1", 1},
		{"n=0", "0", 3},
		{"n=999", "999", 3},
		{"n=-5", "-5", 3},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ts, st := newReviewTestServer(t)
			defer ts.Close()

			st.CreateNote(store.Note{Title: "d1", Body: "b"})
			st.CreateNote(store.Note{Title: "d2", Body: "b"})
			st.CreateNote(store.Note{Title: "d3", Body: "b"})

			resp := doReviewJSON(t, http.MethodGet, ts.URL+"/api/review/digest?n="+tt.n, nil)

			if resp.StatusCode != 200 {
				t.Fatalf("status = %v, want 200", resp.StatusCode)
			}

			var body struct {
				Notes []struct {
					ID      int64    `json:"id"`
					Title   string   `json:"title"`
					Snippet string   `json:"snippet"`
					Tags    []string `json:"tags"`
					DueDate string   `json:"dueDate"`
				} `json:"notes"`
			}
			decodeReviewJSON(t, resp, &body)

			if len(body.Notes) != tt.wantLen {
				t.Errorf("len(notes) = %v, want %v", len(body.Notes), tt.wantLen)
			}
		})
	}
}
