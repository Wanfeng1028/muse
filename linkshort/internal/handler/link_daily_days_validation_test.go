package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestLinkDailyDaysValidation(t *testing.T) {
	srv := newTestServer(t)

	tests := []struct {
		name       string
		urlSuffix  string
		wantStatus int
		wantBody   string
	}{
		{
			name:       "days_abc",
			urlSuffix:  "?days=abc",
			wantStatus: http.StatusBadRequest,
			wantBody:   "days 非法",
		},
		{
			name:       "days_float",
			urlSuffix:  "?days=1.5",
			wantStatus: http.StatusBadRequest,
			wantBody:   "days 非法",
		},
		{
			name:       "days_suffix",
			urlSuffix:  "?days=1x",
			wantStatus: http.StatusBadRequest,
			wantBody:   "days 非法",
		},
		{
			name:       "days_missing",
			urlSuffix:  "",
			wantStatus: http.StatusOK,
			wantBody:   "",
		},
		{
			name:       "days_zero_clamp",
			urlSuffix:  "?days=0",
			wantStatus: http.StatusOK,
			wantBody:   "",
		},
		{
			name:       "days_valid",
			urlSuffix:  "?days=7",
			wantStatus: http.StatusOK,
			wantBody:   "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, id := c2MakeLink(t, srv)
			url := srv.URL + "/api/links/" + id + "/daily" + tt.urlSuffix
			resp, body := doJSON(t, http.MethodGet, url, testKey, nil)
			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("[%s] status: got %d, want %d, body: %s", tt.name, resp.StatusCode, tt.wantStatus, string(body))
			}
			if tt.wantBody != "" && !strings.Contains(string(body), tt.wantBody) {
				t.Fatalf("[%s] body: got %s, want contains %q", tt.name, string(body), tt.wantBody)
			}
		})
	}
}
