package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestPushHistoryLimitValidation(t *testing.T) {
	tests := []struct {
		name       string
		query      string
		seedUsers  []string
		wantStatus int
		wantError  string
		wantCount  int
	}{
		{
			name:       "limit=abc 返回 400",
			query:      "?limit=abc",
			wantStatus: http.StatusBadRequest,
			wantError:  "limit 参数非法",
		},
		{
			name:       "limit=1.5 返回 400",
			query:      "?limit=1.5",
			wantStatus: http.StatusBadRequest,
			wantError:  "limit 参数非法",
		},
		{
			name:       "limit=1x 返回 400",
			query:      "?limit=1x",
			wantStatus: http.StatusBadRequest,
			wantError:  "limit 参数非法",
		},
		{
			name:       "不传 limit 返回 200",
			query:      "",
			wantStatus: http.StatusOK,
			wantCount:  0,
		},
		{
			name:       "limit=1 且库里有 2 条记录时只返回 1 条",
			query:      "?limit=1&user=alice",
			seedUsers:  []string{"alice", "bob"},
			wantStatus: http.StatusOK,
			wantCount:  1,
		},
		{
			name:       "limit=0 返回 200（store 钳制为 50，返回全部）",
			query:      "?limit=0",
			seedUsers:  []string{"alice", "bob"},
			wantStatus: http.StatusOK,
			wantCount:  2,
		},
		{
			name:       "limit=999 返回 200（store 钳制为 200，返回全部）",
			query:      "?limit=999",
			seedUsers:  []string{"alice", "bob"},
			wantStatus: http.StatusOK,
			wantCount:  2,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv, st := newReviewTestServer(t)
			defer srv.Close()

			for _, user := range tt.seedUsers {
				st.RecordPushFor(time.Now().Format("2006-01-02"), "webhook", user, "sent", "")
			}

			resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/push/history"+tt.query, nil)

			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("status = %d, want %d", resp.StatusCode, tt.wantStatus)
			}

			if tt.wantError != "" {
				var errResp struct {
					Error string `json:"error"`
				}
				decodeReviewJSON(t, resp, &errResp)
				if !strings.Contains(errResp.Error, tt.wantError) {
					t.Fatalf("error = %q, want contains %q", errResp.Error, tt.wantError)
				}
				return
			}

			var records []map[string]interface{}
			if err := json.NewDecoder(resp.Body).Decode(&records); err != nil {
				t.Fatalf("decode records failed: %v", err)
			}
			if len(records) != tt.wantCount {
				t.Fatalf("len(records) = %d, want %d", len(records), tt.wantCount)
			}
		})
	}
}
