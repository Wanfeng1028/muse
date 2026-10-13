package handler

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

const testKey = "test-key-123"

// newTestServer 创建带内存库与测试配置的 httptest.Server
func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open(:memory:) 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)
	cfg := &config.Config{AdminKey: testKey}
	srv := httptest.NewServer(NewRouter(st, cfg))
	t.Cleanup(srv.Close)
	return srv
}

// doJSON 发送 JSON 请求
func doJSON(t *testing.T, method, url, key string, body any) (*http.Response, []byte) {
	t.Helper()
	var reader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("json.Marshal 失败: %v", err)
		}
		reader = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, url, reader)
	if err != nil {
		t.Fatalf("http.NewRequest 失败: %v", err)
	}
	if key != "" {
		req.Header.Set("X-API-Key", key)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("请求 %s %s 失败: %v", method, url, err)
	}
	data, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	return resp, data
}

// TestAuth_无key返回401 验证鉴权
func TestAuth_无key返回401(t *testing.T) {
	srv := newTestServer(t)
	resp, _ := doJSON(t, http.MethodGet, srv.URL+"/api/links", "", nil)
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("无 key 访问 /api/links 期望 401，实际 %d", resp.StatusCode)
	}
}

// TestCreateLink_成功 验证带 key 建链返回 201 且 short_url 含 slug
func TestCreateLink_成功(t *testing.T) {
	srv := newTestServer(t)
	body := map[string]any{
		"url":   "https://example.com/target",
		"slug":  "my-slug",
		"title": "我的标题",
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("创建链接期望 201，实际 %d，body=%s", resp.StatusCode, string(data))
	}
	var out map[string]any
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("解析响应失败: %v，body=%s", err, string(data))
	}
	shortURL, _ := out["short_url"].(string)
	if !strings.Contains(shortURL, "my-slug") {
		t.Errorf("short_url 应包含 slug，实际 %q（完整响应=%s）", shortURL, string(data))
	}
}

// TestCreateLink_非法URL返回400 验证非法 URL
func TestCreateLink_非法URL返回400(t *testing.T) {
	srv := newTestServer(t)
	body := map[string]any{"url": "not-a-url"}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("非法 URL 期望 400，实际 %d，body=%s", resp.StatusCode, string(data))
	}
}

// TestCreateLink_非法slug返回400 验证非法 slug
func TestCreateLink_非法slug返回400(t *testing.T) {
	srv := newTestServer(t)
	body := map[string]any{"url": "https://example.com/x", "slug": "非法 slug!"}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, body)
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("非法 slug 期望 400，实际 %d，body=%s", resp.StatusCode, string(data))
	}
}

// TestRedirect_访问计数 验证 GET /{slug} 302 且点击计数
func TestRedirect_访问计数(t *testing.T) {
	srv := newTestServer(t)
	create := map[string]any{"url": "https://example.com/redirect", "slug": "redir-1"}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, create)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("创建链接失败: 状态 %d，body=%s", resp.StatusCode, string(data))
	}

	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	r, err := client.Get(srv.URL + "/redir-1")
	if err != nil {
		t.Fatalf("GET /redir-1 失败: %v", err)
	}
	r.Body.Close()
	if r.StatusCode != http.StatusFound {
		t.Fatalf("GET /redir-1 期望 302，实际 %d", r.StatusCode)
	}
	if loc := r.Header.Get("Location"); loc != "https://example.com/redirect" {
		t.Errorf("Location 期望 https://example.com/redirect，实际 %q", loc)
	}

	// 检查 clicks 变 1
	_, statsData := doJSON(t, http.MethodGet, srv.URL+"/api/stats/overview", testKey, nil)
	var stats map[string]any
	if err := json.Unmarshal(statsData, &stats); err != nil {
		t.Fatalf("解析 stats 失败: %v，body=%s", err, string(statsData))
	}
	tc, _ := stats["total_clicks"].(float64)
	if int(tc) != 1 {
		t.Errorf("访问后 total_clicks 期望 1，实际 %v（完整响应=%s）", stats["total_clicks"], string(statsData))
	}
}

// TestRedirect_禁用返回404 验证禁用链接
func TestRedirect_禁用返回404(t *testing.T) {
	srv := newTestServer(t)
	create := map[string]any{"url": "https://example.com/disabled", "slug": "dis-1"}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, create)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("创建链接失败: 状态 %d，body=%s", resp.StatusCode, string(data))
	}
	var created map[string]any
	if err := json.Unmarshal(data, &created); err != nil {
		t.Fatalf("解析创建响应失败: %v", err)
	}
	id := int64(created["id"].(float64))

	patch := map[string]any{"enabled": false}
	presp, pdata := doJSON(t, http.MethodPatch, srv.URL+"/api/links/"+itoa(id), testKey, patch)
	if presp.StatusCode != http.StatusOK && presp.StatusCode != http.StatusNoContent {
		t.Fatalf("禁用链接期望 2xx，实际 %d，body=%s", presp.StatusCode, string(pdata))
	}

	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	r, err := client.Get(srv.URL + "/dis-1")
	if err != nil {
		t.Fatalf("GET /dis-1 失败: %v", err)
	}
	r.Body.Close()
	if r.StatusCode != http.StatusNotFound {
		t.Errorf("禁用链接 GET 期望 404，实际 %d", r.StatusCode)
	}
}

// TestRedirect_过期返回410 验证过期链接
func TestRedirect_过期返回410(t *testing.T) {
	srv := newTestServer(t)
	past := time.Now().UTC().Add(-time.Hour)
	create := map[string]any{
		"url":        "https://example.com/expired",
		"slug":       "exp-1",
		"expires_at": past.Format(time.RFC3339),
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, create)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("创建过期链接失败: 状态 %d，body=%s", resp.StatusCode, string(data))
	}

	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	r, err := client.Get(srv.URL + "/exp-1")
	if err != nil {
		t.Fatalf("GET /exp-1 失败: %v", err)
	}
	r.Body.Close()
	if r.StatusCode != http.StatusGone {
		t.Errorf("过期链接 GET 期望 410，实际 %d", r.StatusCode)
	}
}

// TestRedirect_未知slug返回404 验证未知 slug
func TestRedirect_未知slug返回404(t *testing.T) {
	srv := newTestServer(t)
	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	r, err := client.Get(srv.URL + "/no-such-slug")
	if err != nil {
		t.Fatalf("GET /no-such-slug 失败: %v", err)
	}
	r.Body.Close()
	if r.StatusCode != http.StatusNotFound {
		t.Errorf("未知 slug 期望 404，实际 %d", r.StatusCode)
	}
}

// TestPatchAndDelete 验证 PATCH 改标题/开关以及 DELETE 后 GET 404
func TestPatchAndDelete(t *testing.T) {
	srv := newTestServer(t)
	create := map[string]any{"url": "https://example.com/patch", "slug": "patch-1", "title": "旧标题"}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, create)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("创建链接失败: 状态 %d，body=%s", resp.StatusCode, string(data))
	}
	var created map[string]any
	if err := json.Unmarshal(data, &created); err != nil {
		t.Fatalf("解析创建响应失败: %v", err)
	}
	id := int64(created["id"].(float64))

	patch := map[string]any{"title": "新标题", "enabled": false}
	presp, pdata := doJSON(t, http.MethodPatch, srv.URL+"/api/links/"+itoa(id), testKey, patch)
	if presp.StatusCode != http.StatusOK && presp.StatusCode != http.StatusNoContent {
		t.Fatalf("PATCH 期望 2xx，实际 %d，body=%s", presp.StatusCode, string(pdata))
	}

	// 确认标题已修改
	g, gdata := doJSON(t, http.MethodGet, srv.URL+"/api/links", testKey, nil)
	if g.StatusCode != http.StatusOK {
		t.Fatalf("GET /api/links 失败: %d", g.StatusCode)
	}
	if !strings.Contains(string(gdata), "新标题") {
		t.Errorf("列表未包含修改后的标题: %s", string(gdata))
	}

	// DELETE
	dresp, ddata := doJSON(t, http.MethodDelete, srv.URL+"/api/links/"+itoa(id), testKey, nil)
	if dresp.StatusCode != http.StatusNoContent {
		t.Fatalf("DELETE 期望 204，实际 %d，body=%s", dresp.StatusCode, string(ddata))
	}

	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	r, err := client.Get(srv.URL + "/patch-1")
	if err != nil {
		t.Fatalf("GET /patch-1 失败: %v", err)
	}
	r.Body.Close()
	if r.StatusCode != http.StatusNotFound {
		t.Errorf("删除后 GET 期望 404，实际 %d", r.StatusCode)
	}
}

// TestQRCode_输出PNG 验证二维码接口
func TestQRCode_输出PNG(t *testing.T) {
	srv := newTestServer(t)
	create := map[string]any{"url": "https://example.com/qr", "slug": "qr-1"}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, create)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("创建链接失败: 状态 %d，body=%s", resp.StatusCode, string(data))
	}
	var created map[string]any
	if err := json.Unmarshal(data, &created); err != nil {
		t.Fatalf("解析创建响应失败: %v", err)
	}
	id := int64(created["id"].(float64))

	req, err := http.NewRequest(http.MethodGet, srv.URL+"/api/links/"+itoa(id)+"/qrcode.png", nil)
	if err != nil {
		t.Fatalf("构造请求失败: %v", err)
	}
	req.Header.Set("X-API-Key", testKey)
	r, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("请求 qrcode.png 失败: %v", err)
	}
	defer r.Body.Close()
	if r.StatusCode != http.StatusOK {
		t.Fatalf("qrcode.png 期望 200，实际 %d", r.StatusCode)
	}
	ct := r.Header.Get("Content-Type")
	if !strings.Contains(ct, "image/png") {
		t.Errorf("Content-Type 期望包含 image/png，实际 %q", ct)
	}
	body, _ := io.ReadAll(r.Body)
	magic := []byte{0x89, 0x50, 0x4E, 0x47}
	if len(body) < 4 || !bytes.Equal(body[:4], magic) {
		t.Errorf("qrcode.png 响应体不是 PNG: 前几字节=% x", body[:min(4, len(body))])
	}
}

// TestStatsOverview_字段齐全 验证统计接口字段
func TestStatsOverview_字段齐全(t *testing.T) {
	srv := newTestServer(t)
	resp, data := doJSON(t, http.MethodGet, srv.URL+"/api/stats/overview", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("GET /api/stats/overview 期望 200，实际 %d，body=%s", resp.StatusCode, string(data))
	}
	var stats map[string]any
	if err := json.Unmarshal(data, &stats); err != nil {
		t.Fatalf("解析 stats 失败: %v，body=%s", err, string(data))
	}
	for _, key := range []string{"links", "enabled_links", "total_clicks", "today_clicks"} {
		if _, ok := stats[key]; !ok {
			t.Errorf("stats 缺少字段 %q，完整响应=%s", key, string(data))
		}
	}
}

// itoa 简易 int64 转字符串，避免额外引入 strconv
func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

// min 简易 min
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
