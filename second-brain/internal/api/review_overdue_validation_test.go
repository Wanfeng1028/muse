package api

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func TestReviewOverdue_LimitValidation(t *testing.T) {
	ts, st := newReviewTestServer(t)

	now := time.Now()
	seedOverdueReview(t, st, "Overdue Review 1", now.AddDate(0, 0, -3), store.DefaultUser)
	seedOverdueReview(t, st, "Overdue Review 2", now.AddDate(0, 0, -4), store.DefaultUser)

	baseURL := ts.URL + "/api/review/overdue"

	testCases := []struct {
		name           string
		query          string
		expectedStatus int
		expectedCount  int
		expectErrorMsg string
	}{
		{"limit invalid abc", "limit=abc", http.StatusBadRequest, 0, "limit 参数非法"},
		{"limit invalid 1.5", "limit=1.5", http.StatusBadRequest, 0, "limit 参数非法"},
		{"limit invalid 1x", "limit=1x", http.StatusBadRequest, 0, "limit 参数非法"},
		{"no limit", "", http.StatusOK, 2, ""},
		{"limit 1", "limit=1", http.StatusOK, 1, ""},
		{"limit 0", "limit=0", http.StatusOK, 2, ""},
		{"limit 999", "limit=999", http.StatusOK, 2, ""},
		{"limit -5", "limit=-5", http.StatusOK, 2, ""},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			t.Helper()
			url := baseURL
			if tc.query != "" {
				url += "?" + tc.query
			}
			resp := doReviewJSON(t, http.MethodGet, url, nil)

			if resp.StatusCode != tc.expectedStatus {
				t.Errorf("%s: expected status %d, got %d", tc.name, tc.expectedStatus, resp.StatusCode)
				return
			}

			if resp.StatusCode == http.StatusBadRequest {
				var errResp struct {
					Error string `json:"error"`
				}
				decodeReviewJSON(t, resp, &errResp)
				if !strings.Contains(errResp.Error, tc.expectErrorMsg) {
					t.Errorf("%s: expected error containing %q, got %q (query=%s)", tc.name, tc.expectErrorMsg, errResp.Error, tc.query)
				}
			} else {
				var items []overdueItem
				decodeReviewJSON(t, resp, &items)
				if len(items) != tc.expectedCount {
					t.Errorf("%s: expected %d items, got %d (query=%s)", tc.name, tc.expectedCount, len(items), tc.query)
				}
			}
		})
	}
}
