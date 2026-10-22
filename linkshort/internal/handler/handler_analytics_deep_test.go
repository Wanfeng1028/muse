package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
)

// 这个文件专门测统计相关接口的细节：daily、referers、ua、参数兜底、overview 和非法 id。

type c2DailyItem struct {
	Date   string `json:"date"`
	Clicks int    `json:"clicks"`
}

type c2NamedCount struct {
	Name   string `json:"name"`
	Clicks int    `json:"clicks"`
}

type c2DailyResponse struct {
	Items []c2DailyItem `json:"items"`
}

type c2ReferersResponse struct {
	Items []c2NamedCount `json:"items"`
}

type c2UAResponse struct {
	LinkID   int            `json:"link_id"`
	Total    int            `json:"total"`
	Bots     int            `json:"bots"`
	Devices  []c2NamedCount `json:"devices"`
	Browsers []c2NamedCount `json:"browsers"`
	OS       []c2NamedCount `json:"os"`
}

type c2OverviewResponse struct {
	Links        int `json:"links"`
	EnabledLinks int `json:"enabled_links"`
	TotalClicks  int `json:"total_clicks"`
	TodayClicks  int `json:"today_clicks"`
}

// c2Decode 用来把接口返回的 JSON 解到结构体里，失败直接挂测试。
func c2Decode(t *testing.T, body []byte, v any) {
	t.Helper()
	if err := json.Unmarshal(body, v); err != nil {
		t.Fatalf("解析 JSON 失败: %v, body=%s", err, body)
	}
}

// c2MakeLink 按测试名生成唯一 slug，然后建一条链接，返回 slug 和 id 字符串。
func c2MakeLink(t *testing.T, srv *httptest.Server) (string, string) {
	t.Helper()

	raw := strings.ToLower(t.Name())
	var b strings.Builder
	for _, r := range raw {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		} else {
			b.WriteByte('-')
		}
	}
	slug := "c2-" + b.String()

	resp, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]string{
		"url":  "https://example.com/x",
		"slug": slug,
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("建链状态码 = %d, 想 201, body=%s", resp.StatusCode, body)
	}

	var created map[string]any
	c2Decode(t, body, &created)

	idVal, ok := created["id"].(float64)
	if !ok || idVal <= 0 {
		t.Fatalf("建链返回 id 不对: %v", created["id"])
	}
	slugVal, ok := created["slug"].(string)
	if !ok || slugVal != slug {
		t.Fatalf("建链返回 slug = %v, 想 %s", created["slug"], slug)
	}

	id := strconv.FormatFloat(idVal, 'f', -1, 64)
	return slug, id
}

// c2Visit 模拟一次真实跳转访问，带上 Referer 和 User-Agent，并拿 302。
func c2Visit(t *testing.T, srvURL, slug, referer, ua string) {
	t.Helper()

	req, err := http.NewRequest(http.MethodGet, srvURL+"/"+slug, nil)
	if err != nil {
		t.Fatalf("构造访问请求失败: %v", err)
	}
	req.Header.Set("Referer", referer)
	req.Header.Set("User-Agent", ua)

	client := &http.Client{
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("访问 slug=%s 失败: %v", slug, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusFound {
		t.Fatalf("访问 slug=%s 状态码 = %d, 想 302", slug, resp.StatusCode)
	}
}

// c2SumNamed 把一个 name/clicks 数组里的 clicks 加起来。
func c2SumNamed(items []c2NamedCount) int {
	sum := 0
	for _, item := range items {
		sum += item.Clicks
	}
	return sum
}

func TestAnalyticsDailyCounts(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	slug, id := c2MakeLink(t, srv)

	refererA := "https://a.example/"
	refererB := "https://b.example/"
	uaA := "c2-ua-a/1.0"
	uaB := "c2-ua-b/2.0"

	for i := 0; i < 2; i++ {
		c2Visit(t, srv.URL, slug, refererA, uaA)
		c2Visit(t, srv.URL, slug, refererB, uaB)
	}

	resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id+"/daily?days=1", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("daily 状态码 = %d, 想 200, body=%s", resp.StatusCode, body)
	}

	var out c2DailyResponse
	c2Decode(t, body, &out)

	total := 0
	for _, item := range out.Items {
		if item.Date == "" {
			t.Fatalf("daily items 里有 date 为空: %+v", out.Items)
		}
		total += item.Clicks
	}

	if total != 4 {
		t.Fatalf("daily clicks 合计 = %d, 想 4", total)
	}
}

func TestAnalyticsReferersTopN(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	slug, id := c2MakeLink(t, srv)

	refererA := "https://a.example/"
	refererB := "https://b.example/"
	uaA := "c2-ua-a/1.0"
	uaB := "c2-ua-b/2.0"

	for i := 0; i < 2; i++ {
		c2Visit(t, srv.URL, slug, refererA, uaA)
		c2Visit(t, srv.URL, slug, refererB, uaB)
	}

	resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id+"/referers?n=10", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("referers 状态码 = %d, 想 200, body=%s", resp.StatusCode, body)
	}

	var out c2ReferersResponse
	c2Decode(t, body, &out)

	got := make(map[string]int, len(out.Items))
	for _, item := range out.Items {
		got[item.Name] += item.Clicks
	}

	if got[refererA] != 2 {
		t.Fatalf("referer %s clicks = %d, 想 2", refererA, got[refererA])
	}
	if got[refererB] != 2 {
		t.Fatalf("referer %s clicks = %d, 想 2", refererB, got[refererB])
	}
}

func TestAnalyticsUAGrouping(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	slug, id := c2MakeLink(t, srv)

	refererA := "https://a.example/"
	refererB := "https://b.example/"
	uaA := "c2-ua-a/1.0"
	uaB := "c2-ua-b/2.0"

	for i := 0; i < 2; i++ {
		c2Visit(t, srv.URL, slug, refererA, uaA)
		c2Visit(t, srv.URL, slug, refererB, uaB)
	}

	resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id+"/ua", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("ua 状态码 = %d, 想 200, body=%s", resp.StatusCode, body)
	}

	var out c2UAResponse
	c2Decode(t, body, &out)

	if out.Total != 4 {
		t.Fatalf("ua total = %d, 想 4", out.Total)
	}

	deviceSum := c2SumNamed(out.Devices)
	browserSum := c2SumNamed(out.Browsers)
	osSum := c2SumNamed(out.OS)

	if deviceSum != 4 {
		t.Fatalf("devices clicks 合计 = %d, 想 4", deviceSum)
	}
	if browserSum != 4 {
		t.Fatalf("browsers clicks 合计 = %d, 想 4", browserSum)
	}
	if osSum != 4 {
		t.Fatalf("os clicks 合计 = %d, 想 4", osSum)
	}
}

func TestAnalyticsParamClamp(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	_, id := c2MakeLink(t, srv)

	urls := []string{
		srv.URL + "/api/links/" + id + "/daily?days=0",
		srv.URL + "/api/links/" + id + "/daily?days=999",
		srv.URL + "/api/links/" + id + "/referers?n=0",
		srv.URL + "/api/links/" + id + "/referers?n=200",
	}

	for _, u := range urls {
		resp, body := doJSON(t, http.MethodGet, u, testKey, nil)
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("请求 %s 状态码 = %d, 想 200, body=%s", u, resp.StatusCode, body)
		}
	}
}

func TestAnalyticsOverview(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	slug, _ := c2MakeLink(t, srv)

	for i := 0; i < 4; i++ {
		c2Visit(t, srv.URL, slug, "https://overview.example/", "c2-overview-ua/1.0")
	}

	resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/stats/overview", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("overview 状态码 = %d, 想 200, body=%s", resp.StatusCode, body)
	}

	var out c2OverviewResponse
	c2Decode(t, body, &out)

	if out.TotalClicks < 4 {
		t.Fatalf("overview total_clicks = %d, 想 >= 4", out.TotalClicks)
	}
	if out.TodayClicks < 4 {
		t.Fatalf("overview today_clicks = %d, 想 >= 4", out.TodayClicks)
	}
}

func TestAnalyticsInvalidID(t *testing.T) {
	srv := newTestServer(t)
	defer srv.Close()

	_, _ = c2MakeLink(t, srv)

	resp, body := doJSON(t, http.MethodGet, srv.URL+"/api/links/abc/daily", testKey, nil)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("非法 id daily 状态码 = %d, 想 400, body=%s", resp.StatusCode, body)
	}
}
