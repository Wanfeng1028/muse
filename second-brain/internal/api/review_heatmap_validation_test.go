package api

import (
	"net/http"
	"strings"
	"testing"
)

func TestReviewHeatmap_DaysValidation(t *testing.T) {
	cases := []struct {
		name       string
		query      string
		wantStatus int
		wantDays   int
		wantLen    int
	}{
		{"days=abc", "?days=abc", 400, 0, 0},
		{"days=1.5", "?days=1.5", 400, 0, 0},
		{"days=1x", "?days=1x", 400, 0, 0},
		{"missing", "", 200, 365, 365},
		{"days=1", "?days=1", 200, 1, 1},
		{"days=0", "?days=0", 200, 365, 365},
		{"days=999", "?days=999", 200, 366, 366},
		{"days=-5", "?days=-5", 200, 365, 365},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			server, _ := newReviewTestServer(t)
			resp := doReviewJSON(t, http.MethodGet, server.URL+"/api/review/heatmap"+tc.query, nil)
			defer resp.Body.Close()

			if resp.StatusCode != tc.wantStatus {
				t.Errorf("status = %d, want %d", resp.StatusCode, tc.wantStatus)
				return
			}

			if tc.wantStatus == 400 {
				var e struct {
					Error string `json:"error"`
				}
				decodeReviewJSON(t, resp, &e)
				if !strings.Contains(e.Error, "days 参数非法") {
					t.Errorf("error = %q, want contains %q", e.Error, "days 参数非法")
				}
				return
			}

			var hr heatmapResp
			decodeReviewJSON(t, resp, &hr)
			if hr.Days != tc.wantDays {
				t.Errorf("Days = %d, want %d", hr.Days, tc.wantDays)
			}
			if len(hr.Heatmap) != tc.wantLen {
				t.Errorf("len(Heatmap) = %d, want %d", len(hr.Heatmap), tc.wantLen)
			}
		})
	}
}
