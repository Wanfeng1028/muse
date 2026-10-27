package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestStatsHourlyDaysValidation(t *testing.T) {
	srv := newTestServer(t)

	tests := []struct {
		name     string
		suffix   string
		wantCode int
		wantErr  string
	}{
		{"days=abc", "?days=abc", http.StatusBadRequest, "days 非法"},
		{"days=1.5", "?days=1.5", http.StatusBadRequest, "days 非法"},
		{"days=1x", "?days=1x", http.StatusBadRequest, "days 非法"},
		{"missing days", "", http.StatusOK, ""},
		{"days=2", "?days=2", http.StatusOK, ""},
		{"days=7", "?days=7", http.StatusOK, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			url := srv.URL + "/api/stats/hourly" + tt.suffix
			resp, body := doJSON(t, http.MethodGet, url, testKey, nil)
			defer resp.Body.Close()

			if resp.StatusCode != tt.wantCode {
				t.Fatalf("status = %d, want %d; body: %s", resp.StatusCode, tt.wantCode, string(body))
			}
			if tt.wantErr != "" && !strings.Contains(string(body), tt.wantErr) {
				t.Fatalf("body %q does not contain %q", string(body), tt.wantErr)
			}
		})
	}
}
