package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestStatsGeoLinkIDValidation(t *testing.T) {
	srv := newTestServer(t)

	tests := []struct {
		name     string
		suffix   string
		wantCode int
		wantErr  string
	}{
		{name: "link_id 非数字", suffix: "?link_id=abc", wantCode: http.StatusBadRequest, wantErr: "link_id 非法"},
		{name: "link_id 小数", suffix: "?link_id=1.5", wantCode: http.StatusBadRequest, wantErr: "link_id 非法"},
		{name: "link_id 带字母", suffix: "?link_id=1x", wantCode: http.StatusBadRequest, wantErr: "link_id 非法"},
		{name: "不带参数", suffix: "", wantCode: http.StatusOK},
		{name: "link_id 负数", suffix: "?link_id=-5", wantCode: http.StatusOK},
		{name: "days 正常", suffix: "?days=2", wantCode: http.StatusOK},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/stats/geo"+tt.suffix, testKey, nil)
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
