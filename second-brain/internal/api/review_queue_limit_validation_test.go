package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func TestReviewQueue_LimitValidation(t *testing.T) {
	ts, _ := newReviewTestServer(t)
	defer ts.Close()

	tests := []struct {
		name       string
		query      string
		wantStatus int
		wantErr    string
	}{
		{name: "limit non-numeric", query: "?limit=abc", wantStatus: http.StatusBadRequest, wantErr: "limit 参数非法"},
		{name: "limit decimal", query: "?limit=1.5", wantStatus: http.StatusBadRequest, wantErr: "limit 参数非法"},
		{name: "limit mixed", query: "?limit=1x", wantStatus: http.StatusBadRequest, wantErr: "limit 参数非法"},
		{name: "limit omitted", query: "", wantStatus: http.StatusOK},
		{name: "limit valid", query: "?limit=2", wantStatus: http.StatusOK},
		{name: "limit clamped to default", query: "?limit=0", wantStatus: http.StatusOK},
		{name: "limit clamped to max", query: "?limit=999", wantStatus: http.StatusOK},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp := doReviewJSON(t, http.MethodGet, ts.URL+"/api/review/queue"+tt.query, nil)
			defer resp.Body.Close()
			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("status = %d, want %d", resp.StatusCode, tt.wantStatus)
			}
			if tt.wantErr == "" {
				return
			}
			var body struct {
				Error string `json:"error"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
				t.Fatalf("decode response body: %v", err)
			}
			if !strings.Contains(body.Error, tt.wantErr) {
				t.Errorf("error = %q, want contains %q", body.Error, tt.wantErr)
			}
		})
	}
}
