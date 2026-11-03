package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestStatsDailyDaysValidation(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	tests := []struct {
		name     string
		suffix   string
		want     int
		wantBody string
	}{
		{name: "days_abc", suffix: "?days=abc", want: http.StatusBadRequest, wantBody: "days 非法"},
		{name: "days_float", suffix: "?days=1.5", want: http.StatusBadRequest, wantBody: "days 非法"},
		{name: "days_suffix", suffix: "?days=1x", want: http.StatusBadRequest, wantBody: "days 非法"},
		{name: "days_missing", suffix: "", want: http.StatusOK},
		{name: "days_zero_clamp", suffix: "?days=0", want: http.StatusOK},
		{name: "days_valid", suffix: "?days=7", want: http.StatusOK},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			url := srv.URL + "/api/stats/daily" + tt.suffix
			resp, body := doJSON(t, http.MethodGet, url, testKey, nil)
			defer resp.Body.Close()

			if resp.StatusCode != tt.want {
				t.Fatalf("status = %d, want %d", resp.StatusCode, tt.want)
			}
			if tt.wantBody != "" && !strings.Contains(string(body), tt.wantBody) {
				t.Fatalf("body %q does not contain %q", body, tt.wantBody)
			}
		})
	}
}
