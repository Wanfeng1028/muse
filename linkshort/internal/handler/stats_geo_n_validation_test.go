package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestStatsGeoNValidation(t *testing.T) {
	srv := newTestServer(t)

	tests := []struct {
		name     string
		suffix   string
		wantCode int
		wantErr  string
	}{
		{"n=abc", "?n=abc", http.StatusBadRequest, "n 非法"},
		{"n=1.5", "?n=1.5", http.StatusBadRequest, "n 非法"},
		{"n=1x", "?n=1x", http.StatusBadRequest, "n 非法"},
		{"missing n", "", http.StatusOK, ""},
		{"n=0", "?n=0", http.StatusOK, ""},
		{"n=8", "?n=8", http.StatusOK, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			url := srv.URL + "/api/stats/geo" + tt.suffix
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
