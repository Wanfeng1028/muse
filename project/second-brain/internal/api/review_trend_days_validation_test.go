package api

import (
	"net/http"
	"strings"
	"testing"
)

type trendDaysResponse struct {
	Days int `json:"days"`
}

type trendErrorResponse struct {
	Error string `json:"error"`
}

func TestReviewTrend_DaysValidation(t *testing.T) {
	ts, _ := newReviewTestServer(t)

	tests := []struct {
		name       string
		query      string
		wantStatus int
		wantDays   int
		wantErr    bool
	}{
		{name: "days=abc", query: "days=abc", wantStatus: http.StatusBadRequest, wantErr: true},
		{name: "days=1.5", query: "days=1.5", wantStatus: http.StatusBadRequest, wantErr: true},
		{name: "days=1x", query: "days=1x", wantStatus: http.StatusBadRequest, wantErr: true},
		{name: "no days param", query: "", wantStatus: http.StatusOK, wantDays: 7},
		{name: "days=1", query: "days=1", wantStatus: http.StatusOK, wantDays: 1},
		{name: "days=0", query: "days=0", wantStatus: http.StatusOK, wantDays: 7},
		{name: "days=1000", query: "days=1000", wantStatus: http.StatusOK, wantDays: 60},
		{name: "days=-5", query: "days=-5", wantStatus: http.StatusOK, wantDays: 7},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			url := ts.URL + "/api/review/trend"
			if tt.query != "" {
				url += "?" + tt.query
			}

			resp := doReviewJSON(t, http.MethodGet, url, nil)
			defer resp.Body.Close()
			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("status = %d, want %d", resp.StatusCode, tt.wantStatus)
			}

			if tt.wantErr {
				var body trendErrorResponse
				decodeReviewJSON(t, resp, &body)
				if !strings.Contains(body.Error, "days 参数非法") {
					t.Fatalf("error = %q, want contains %q", body.Error, "days 参数非法")
				}
			} else {
				var body trendDaysResponse
				decodeReviewJSON(t, resp, &body)
				if body.Days != tt.wantDays {
					t.Fatalf("days = %d, want %d", body.Days, tt.wantDays)
				}
			}
		})
	}
}
