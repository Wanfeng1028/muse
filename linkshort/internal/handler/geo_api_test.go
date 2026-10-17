package handler

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// newGeoTestServer 起一个只挂 geo 两个路由的 chi server，配一个临时库。
func newGeoTestServer(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)

	r := chi.NewRouter()
	r.Route("/api", func(api chi.Router) {
		api.Get("/stats/geo", func(w http.ResponseWriter, req *http.Request) {
			handleStatsGeo(w, req, st)
		})
		api.Get("/stats/geo.csv", func(w http.ResponseWriter, req *http.Request) {
			handleExportGeoCSV(w, req, st)
		})
	})
	ts := httptest.NewServer(r)
	t.Cleanup(ts.Close)
	return ts, st
}

type geoStatsResp struct {
	Items       []map[string]any `json:"items"`
	UnknownPct  float64          `json:"unknown_pct"`
	TotalClicks int64            `json:"total_clicks"`
	TotalUV     int64            `json:"total_uv"`
	Days        int              `json:"days"`
}

func getGeoStats(t *testing.T, ts *httptest.Server, query string) (int, geoStatsResp, string) {
	t.Helper()
	resp, err := http.Get(ts.URL + "/api/stats/geo" + query)
	if err != nil {
		t.Fatalf("请求 /stats/geo 失败: %v", err)
	}
	defer resp.Body.Close()
	var body geoStatsResp
	raw := new(strings.Builder)
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("解析 JSON 失败: %v", err)
	}
	return resp.StatusCode, body, raw.String()
}

func TestGeoStats_NoData_EmptyItems(t *testing.T) {
	ts, _ := newGeoTestServer(t)

	status, body, _ := getGeoStats(t, ts, "")
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if body.Items == nil {
		t.Fatalf("items 不应为 nil")
	}
	if len(body.Items) != 0 {
		t.Fatalf("无数据时 items 长度 = %d, 期望 0", len(body.Items))
	}
	if body.TotalClicks != 0 {
		t.Fatalf("无数据时 total_clicks = %d, 期望 0", body.TotalClicks)
	}
	if body.TotalUV != 0 {
		t.Fatalf("无数据时 total_uv = %d, 期望 0", body.TotalUV)
	}
}

func TestGeoStats_CountryProvinceTopN_Correct(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)

	// 中国-广东 3 次，中国-北京 1 次，美国-加州 2 次
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")
	mustRecord(t, st, linkID, "CN", "中国", "广东", "广州")
	mustRecord(t, st, linkID, "CN", "中国", "北京", "北京")
	mustRecord(t, st, linkID, "US", "美国", "加州", "洛杉矶")
	mustRecord(t, st, linkID, "US", "美国", "加州", "旧金山")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&days=30&n=8", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if body.TotalClicks != 6 {
		t.Fatalf("total_clicks = %d, 期望 6", body.TotalClicks)
	}
	if len(body.Items) == 0 {
		t.Fatalf("items 不应为空")
	}
	// API 按城市粒度返回；按点击排序后，第一条应是深圳(2 次)
	first := body.Items[0]
	if first["country_code"] != "CN" {
		t.Fatalf("首条 country_code = %v, 期望 CN", first["country_code"])
	}
	if first["city"] != "深圳" {
		t.Fatalf("首条 city = %v, 期望 深圳", first["city"])
	}
	if toInt64(first["clicks"]) != 2 {
		t.Fatalf("深圳 clicks = %v, 期望 2", first["clicks"])
	}
}

func TestGeoStats_DaysZero_FallsBackTo30(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&days=0", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if body.Days != 30 {
		t.Fatalf("days = %d, 期望回退 30", body.Days)
	}
	if len(body.Items) != 1 {
		t.Fatalf("items 长度 = %d, 期望 1", len(body.Items))
	}
}

func TestGeoStats_DaysNegative_FallsBackTo30(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&days=-5", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if body.Days != 30 {
		t.Fatalf("days = %d, 期望回退 30", body.Days)
	}
	if body.TotalClicks != 1 {
		t.Fatalf("total_clicks = %d, 期望 1", body.TotalClicks)
	}
}

func TestGeoStats_DaysHuge_FallsBackTo30(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&days=100000", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if body.Days != 30 {
		t.Fatalf("days = %d, 期望回退 30", body.Days)
	}
	if body.TotalClicks != 1 {
		t.Fatalf("total_clicks = %d, 期望 1", body.TotalClicks)
	}
}

func TestGeoStats_DaysSeven_Kept(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&days=7", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if body.Days != 7 {
		t.Fatalf("days = %d, 期望 7", body.Days)
	}
	if body.TotalClicks != 1 {
		t.Fatalf("total_clicks = %d, 期望 1", body.TotalClicks)
	}
}

func TestGeoStats_CountryFilter(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")
	mustRecord(t, st, linkID, "US", "美国", "加州", "洛杉矶")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&country=CN", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if len(body.Items) != 1 {
		t.Fatalf("过滤后 items 长度 = %d, 期望 1", len(body.Items))
	}
	if body.Items[0]["country_code"] != "CN" {
		t.Fatalf("过滤后 country_code = %v, 期望 CN", body.Items[0]["country_code"])
	}
	if body.Items[0]["province"] != "广东" {
		t.Fatalf("过滤后 province = %v, 期望 广东", body.Items[0]["province"])
	}
}

func TestGeoStats_NTruncation(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	// 造 5 个不同省份，每个 1 次
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")
	mustRecord(t, st, linkID, "CN", "中国", "北京", "北京")
	mustRecord(t, st, linkID, "CN", "中国", "上海", "上海")
	mustRecord(t, st, linkID, "CN", "中国", "浙江", "杭州")
	mustRecord(t, st, linkID, "CN", "中国", "江苏", "南京")

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&n=2", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if len(body.Items) != 2 {
		t.Fatalf("n=2 时 items 长度 = %d, 期望 2", len(body.Items))
	}
	if body.TotalClicks != 5 {
		t.Fatalf("total_clicks = %d, 期望 5", body.TotalClicks)
	}
}

func TestGeoStats_NZero_FallsBackTo8(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	for i := 0; i < 10; i++ {
		mustRecord(t, st, linkID, "CN", "中国", "省份"+string(rune('A'+i)), "城市")
	}

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&n=0", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if len(body.Items) != 8 {
		t.Fatalf("n=0 回退 8 时 items 长度 = %d, 期望 8", len(body.Items))
	}
	if body.TotalClicks != 10 {
		t.Fatalf("total_clicks = %d, 期望 10", body.TotalClicks)
	}
}

func TestGeoStats_NTooLarge_FallsBackTo8(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	for i := 0; i < 10; i++ {
		mustRecord(t, st, linkID, "CN", "中国", "省份"+string(rune('A'+i)), "城市")
	}

	status, body, _ := getGeoStats(t, ts, fmt.Sprintf("?link_id=%d&n=101", linkID))
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	if len(body.Items) != 8 {
		t.Fatalf("n=101 回退 8 时 items 长度 = %d, 期望 8", len(body.Items))
	}
	if body.TotalClicks != 10 {
		t.Fatalf("total_clicks = %d, 期望 10", body.TotalClicks)
	}
}

func TestGeoStats_UnknownPctFieldPresent(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")

	status, body, _ := getGeoStats(t, ts, "?link_id=1")
	if status != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", status)
	}
	// unknown_pct 字段存在，且有数据时非负
	if body.UnknownPct < 0 {
		t.Fatalf("unknown_pct = %f, 不应为负", body.UnknownPct)
	}
	if body.UnknownPct > 100 {
		t.Fatalf("unknown_pct = %f, 不应大于 100", body.UnknownPct)
	}
	if body.TotalClicks != 1 {
		t.Fatalf("total_clicks = %d, 期望 1", body.TotalClicks)
	}
}

func TestExportGeoCSV_HeaderAndRowCount(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")
	mustRecord(t, st, linkID, "US", "美国", "加州", "洛杉矶")

	resp, err := http.Get(ts.URL + "/api/stats/geo.csv?link_id=1&days=30")
	if err != nil {
		t.Fatalf("请求 geo.csv 失败: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", resp.StatusCode)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.HasPrefix(ct, "text/csv") {
		t.Fatalf("Content-Type = %q, 期望 text/csv 前缀", ct)
	}

	records, err := csv.NewReader(resp.Body).ReadAll()
	if err != nil {
		t.Fatalf("解析 CSV 失败: %v", err)
	}
	if len(records) != 3 {
		t.Fatalf("CSV 行数(含表头) = %d, 期望 3", len(records))
	}
	header := records[0]
	header[0] = strings.TrimPrefix(header[0], "\ufeff") // 导出带 BOM 供 Excel 识别，断言时去掉
	wantHeader := []string{"国家代码", "国家", "省份", "城市", "点击", "独立访客"}
	if len(header) != len(wantHeader) {
		t.Fatalf("表头列数 = %d, 期望 %d", len(header), len(wantHeader))
	}
	for i := range wantHeader {
		if header[i] != wantHeader[i] {
			t.Fatalf("表头第 %d 列 = %q, 期望 %q", i, header[i], wantHeader[i])
		}
	}
}

func TestExportGeoCSV_NoData_HeaderOnly(t *testing.T) {
	ts, _ := newGeoTestServer(t)

	resp, err := http.Get(ts.URL + "/api/stats/geo.csv?link_id=1")
	if err != nil {
		t.Fatalf("请求 geo.csv 失败: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", resp.StatusCode)
	}
	records, err := csv.NewReader(resp.Body).ReadAll()
	if err != nil {
		t.Fatalf("解析 CSV 失败: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("无数据时 CSV 行数 = %d, 期望仅表头 1 行", len(records))
	}
	if strings.TrimPrefix(records[0][0], "\ufeff") != "国家代码" {
		t.Fatalf("表头首列 = %q, 期望 国家代码", records[0][0])
	}
	if len(records[0]) != 6 {
		t.Fatalf("表头列数 = %d, 期望 6", len(records[0]))
	}
}

func TestExportGeoCSV_DaysInvalid_FallsBackTo30(t *testing.T) {
	ts, st := newGeoTestServer(t)
	linkID := mustCreateLink(t, st)
	mustRecord(t, st, linkID, "CN", "中国", "广东", "深圳")

	resp, err := http.Get(ts.URL + "/api/stats/geo.csv?link_id=1&days=999")
	if err != nil {
		t.Fatalf("请求 geo.csv 失败: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", resp.StatusCode)
	}
	cd := resp.Header.Get("Content-Disposition")
	if !strings.Contains(cd, "linkshort-geo-30d.csv") {
		t.Fatalf("Content-Disposition = %q, 期望含 linkshort-geo-30d.csv", cd)
	}
	records, err := csv.NewReader(resp.Body).ReadAll()
	if err != nil {
		t.Fatalf("解析 CSV 失败: %v", err)
	}
	if len(records) != 2 {
		t.Fatalf("CSV 行数(含表头) = %d, 期望 2", len(records))
	}
}


// mustCreateLink 建一条测试短链并返回其 id（visits 表有外键约束，不能用虚构 id）。
func mustCreateLink(t *testing.T, st *store.Store) int64 {
	t.Helper()
	id, err := st.CreateLink("geo-test", "https://example.com/", "geo 测试", nil)
	if err != nil {
		t.Fatalf("CreateLink 失败: %v", err)
	}
	return id
}

// mustRecord 是测试辅助，把一次访问打进库。
var recordSeq int64

func mustRecord(t *testing.T, st *store.Store, linkID int64, cc, cn, province, city string) {
	t.Helper()
	recordSeq++
	if err := st.RecordVisitGeo(linkID, fmt.Sprintf("hash-%d", recordSeq), "ua", "referer", cc, cn, province, city); err != nil {
		t.Fatalf("RecordVisitGeo 失败: %v", err)
	}
}

// toInt64 把 JSON 解出来的数字统一成 int64（encoding/json 会把数字解成 float64）。
func toInt64(v any) int64 {
	switch x := v.(type) {
	case float64:
		return int64(x)
	case int64:
		return x
	case int:
		return int64(x)
	default:
		return -1
	}
}