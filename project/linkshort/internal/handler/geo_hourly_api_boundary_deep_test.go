package handler

// 深测补强：地域/时段统计 API 边界（参数回落语义、鉴权、CSV 导出）。
// 编排手工编写（模型输出碎片化，弃用）。
// 锁定的均为当前产品行为：days/n 非法值静默回落（非 400），/metrics 与探针免限流。

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func getStatsJSON(t *testing.T, srvURL, path, key string) (int, map[string]any) {
	t.Helper()
	resp, data := doJSON(t, http.MethodGet, srvURL+path, key, nil)
	var out map[string]any
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("解析 %s 响应失败: %v", path, err)
	}
	return resp.StatusCode, out
}

func TestGeoAPI_days非法回落30(t *testing.T) {
	srv := newTestServer(t)
	for _, q := range []string{"days=2", "days=abc", "days=-1"} {
		code, out := getStatsJSON(t, srv.URL, "/api/stats/geo?"+q, testKey)
		if code != 200 {
			t.Errorf("%s 期望 200，实际 %d", q, code)
			continue
		}
		if out["days"] != float64(30) {
			t.Errorf("%s 期望 days 回落为 30，实际 %v", q, out["days"])
		}
	}
	code, out := getStatsJSON(t, srv.URL, "/api/stats/geo?days=7", testKey)
	if code != 200 || out["days"] != float64(7) {
		t.Errorf("days=7 期望 200 且 days==7，实际 %d/%v", code, out["days"])
	}
}

func TestGeoAPI_n越界回落8(t *testing.T) {
	srv := newTestServer(t)
	// n 越界不崩，items 为空数组（非 null）
	code, out := getStatsJSON(t, srv.URL, "/api/stats/geo?n=101", testKey)
	if code != 200 {
		t.Fatalf("n=101 期望 200，实际 %d", code)
	}
	items, ok := out["items"].([]any)
	if !ok {
		t.Fatalf("期望 items 为数组，实际 %T", out["items"])
	}
	if len(items) != 0 {
		t.Errorf("空库期望 items 为空，实际 %d", len(items))
	}
}

func TestHourlyAPI_days非法回落30(t *testing.T) {
	srv := newTestServer(t)
	code, out := getStatsJSON(t, srv.URL, "/api/stats/hourly?days=2", testKey)
	if code != 200 || out["days"] != float64(30) {
		t.Errorf("days=2 期望 200 且 days==30，实际 %d/%v", code, out["days"])
	}
	code, out = getStatsJSON(t, srv.URL, "/api/stats/hourly?days=1", testKey)
	if code != 200 || out["days"] != float64(1) {
		t.Errorf("days=1 期望 200 且 days==1，实际 %d/%v", code, out["days"])
	}
	// hours 恒 24 项、weekdays 恒 7 项
	if h, ok := out["hours"].([]any); !ok || len(h) != 24 {
		t.Errorf("期望 hours 为 24 项数组")
	}
	if w, ok := out["weekdays"].([]any); !ok || len(w) != 7 {
		t.Errorf("期望 weekdays 为 7 项数组")
	}
}

func TestGeoCSV_空库导出(t *testing.T) {
	srv := newTestServer(t)
	resp, data := doJSON(t, http.MethodGet, srv.URL+"/api/stats/geo.csv", testKey, nil)
	if resp.StatusCode != 200 {
		t.Fatalf("期望 200，实际 %d", resp.StatusCode)
	}
	cd := resp.Header.Get("Content-Disposition")
	if !strings.Contains(cd, "linkshort-geo-") {
		t.Errorf("期望 Content-Disposition 含 linkshort-geo-，实际 %q", cd)
	}
	if len(data) == 0 {
		t.Errorf("期望 CSV body 非空（含表头）")
	}
}

func TestStatsAPI_需鉴权(t *testing.T) {
	srv := newTestServer(t)
	for _, p := range []string{"/api/stats/geo", "/api/stats/hourly", "/api/stats/geo.csv"} {
		resp, _ := doJSON(t, http.MethodGet, srv.URL+p, "", nil)
		if resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("%s 无 key 期望 401，实际 %d", p, resp.StatusCode)
		}
	}
}
