package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestStatsHourlyLinkIDValidation(t *testing.T) {
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
			resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/stats/hourly"+tt.suffix, testKey, nil)
			if resp.StatusCode != tt.wantCode {
				t.Fatalf("GET /api/stats/hourly%s 状态码 = %d, 期望 %d", tt.suffix, resp.StatusCode, tt.wantCode)
			}
			if tt.wantErr != "" && !strings.Contains(string(body), tt.wantErr) {
				t.Fatalf("GET /api/stats/hourly%s 响应体 %q 不含 %q", tt.suffix, body, tt.wantErr)
			}
		})
	}
}
