package api

import (
	"net/http"
	"strings"
	"testing"
)

func TestReviewForecast_DaysValidation(t *testing.T) {
	ts, _ := newReviewTestServer(t)
	defer ts.Close()

	tests := []struct {
		name         string
		query        string
		wantStatus   int
		wantDays     int
		wantForecast int
		wantErr      string
	}{
		{name: "days=abc 返回 400", query: "?days=abc", wantStatus: http.StatusBadRequest, wantErr: "days 参数非法"},
		{name: "days=1.5 返回 400", query: "?days=1.5", wantStatus: http.StatusBadRequest, wantErr: "days 参数非法"},
		{name: "days=1x 返回 400", query: "?days=1x", wantStatus: http.StatusBadRequest, wantErr: "days 参数非法"},
		{name: "不传 days 默认 7", query: "", wantStatus: http.StatusOK, wantDays: 7, wantForecast: 7},
		{name: "days=1 返回 1 天", query: "?days=1", wantStatus: http.StatusOK, wantDays: 1, wantForecast: 1},
		{name: "days=0 钳制为 7", query: "?days=0", wantStatus: http.StatusOK, wantDays: 7, wantForecast: 7},
		{name: "days=99 钳制为 30", query: "?days=99", wantStatus: http.StatusOK, wantDays: 30, wantForecast: 30},
		{name: "days=-5 钳制为 7", query: "?days=-5", wantStatus: http.StatusOK, wantDays: 7, wantForecast: 7},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp := doReviewJSON(t, http.MethodGet, ts.URL+"/api/review/forecast"+tt.query, nil)
			defer resp.Body.Close()

			if resp.StatusCode != tt.wantStatus {
				t.Errorf("状态码 = %d, 期望 %d", resp.StatusCode, tt.wantStatus)
				return
			}

			if tt.wantStatus == http.StatusBadRequest {
				var errResp struct {
					Error string `json:"error"`
				}
				decodeReviewJSON(t, resp, &errResp)
				if !strings.Contains(errResp.Error, tt.wantErr) {
					t.Errorf("错误信息 = %q, 期望包含 %q", errResp.Error, tt.wantErr)
				}
				return
			}

			var got reviewForecastResponse
			decodeReviewJSON(t, resp, &got)
			if got.Days != tt.wantDays {
				t.Errorf("Days = %d, 期望 %d", got.Days, tt.wantDays)
			}
			if len(got.Forecast) != tt.wantForecast {
				t.Errorf("Forecast 长度 = %d, 期望 %d", len(got.Forecast), tt.wantForecast)
			}
		})
	}
}
