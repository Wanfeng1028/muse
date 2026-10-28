package handler

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestStatsGeoCSVLinkIDValidation(t *testing.T) {
	ts, _ := newGeoTestServer(t)

	tests := []struct {
		name     string
		suffix   string
		wantCode int
		wantErr  string
	}{
		{name: "link_id 非数字", suffix: "?link_id=abc", wantCode: http.StatusBadRequest, wantErr: "link_id 非法"},
		{name: "link_id 小数", suffix: "?link_id=1.5", wantCode: http.StatusBadRequest, wantErr: "link_id 非法"},
		{name: "link_id 字母混入", suffix: "?link_id=1x", wantCode: http.StatusBadRequest, wantErr: "link_id 非法"},
		{name: "不带参数", suffix: "", wantCode: http.StatusOK},
		{name: "link_id 负数钳制", suffix: "?link_id=-5", wantCode: http.StatusOK},
		{name: "link_id 为 1", suffix: "?link_id=1", wantCode: http.StatusOK},
		{name: "days 非数字回落", suffix: "?days=abc", wantCode: http.StatusOK},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := http.Get(ts.URL + "/api/stats/geo.csv" + tt.suffix)
			if err != nil {
				t.Fatalf("GET /api/stats/geo.csv%s failed: %v", tt.suffix, err)
			}
			defer resp.Body.Close()

			body, err := io.ReadAll(resp.Body)
			if err != nil {
				t.Fatalf("GET /api/stats/geo.csv%s: read body failed: %v", tt.suffix, err)
			}

			if resp.StatusCode != tt.wantCode {
				t.Fatalf("GET /api/stats/geo.csv%s: status = %d, want %d, body = %s", tt.suffix, resp.StatusCode, tt.wantCode, body)
			}

			if tt.wantErr != "" {
				if !strings.Contains(string(body), tt.wantErr) {
					t.Fatalf("GET /api/stats/geo.csv%s: body = %s, want contains %q", tt.suffix, body, tt.wantErr)
				}
			}
		})
	}
}
