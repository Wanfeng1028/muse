package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newTestConfig(t *testing.T) *config.Config {
	t.Helper()
	cfg := &config.Config{}
	cfg.AdminKey = "test-admin-key"
	cfg.BaseURL = "http://short.test"
	cfg.RateLimitEnabled = false
	cfg.RateLimitRPS = 1000
	cfg.RateLimitBurst = 1000
	cfg.BurnPurgeAfterDestroy = false
	cfg.PurgeInterval = time.Hour
	cfg.PurgeRetentionDays = 30
	cfg.PasswordFailAlertThreshold = 5
	cfg.PasswordFailAlertWindow = time.Minute
	return cfg
}

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	database, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("打开测试库失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return store.New(database)
}

func newDeepTestServer(t *testing.T, st *store.Store, cfg *config.Config) *httptest.Server {
	t.Helper()
	h := NewRouter(st, cfg)
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv
}

func doReq(t *testing.T, method, rawURL string, body []byte, headers map[string]string) (*http.Response, []byte) {
	t.Helper()
	var reader *bytes.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequest(method, rawURL, reader)
	if err != nil {
		t.Fatalf("构造请求失败: %v", err)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	client := &http.Client{Timeout: 10 * time.Second, CheckRedirect: func(r *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	}}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("发请求失败: %v", err)
	}
	defer resp.Body.Close()
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(resp.Body); err != nil {
		t.Fatalf("读响应体失败: %v", err)
	}
	return resp, buf.Bytes()
}

func createLink(t *testing.T, srv *httptest.Server, cfg *config.Config, payload map[string]any) map[string]any {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("序列化 payload 失败: %v", err)
	}
	resp, body := doReq(t, http.MethodPost, srv.URL+"/api/links", raw, map[string]string{
		"Content-Type": "application/json",
		"X-API-Key":    cfg.AdminKey,
	})
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		t.Fatalf("创建链接失败 status=%d body=%s", resp.StatusCode, string(body))
	}
	var out map[string]any
	if err := json.Unmarshal(body, &out); err != nil {
		t.Fatalf("解析创建响应失败: %v body=%s", err, string(body))
	}
	return out
}

// TestHandler_Deep_SlugCollisionOnCreate 验证短码碰撞时创建请求不会覆盖已有链接。
func TestHandler_Deep_SlugCollisionOnCreate(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	first := createLink(t, srv, cfg, map[string]any{
		"slug": "collide1",
		"url":  "https://example.com/one",
	})
	if first["slug"] != "collide1" {
		t.Fatalf("第一次创建 slug 不符: %v", first["slug"])
	}

	resp, body := doReq(t, http.MethodPost, srv.URL+"/api/links", mustJSON(t, map[string]any{
		"slug": "collide1",
		"url":  "https://example.com/two",
	}), map[string]string{
		"Content-Type": "application/json",
		"X-API-Key":    cfg.AdminKey,
	})
	if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusCreated {
		t.Fatalf("重复 slug 创建应当失败, 实际 status=%d body=%s", resp.StatusCode, string(body))
	}

	getResp, getBody := doReq(t, http.MethodGet, srv.URL+"/api/links/"+deepItoa(int64(first["id"].(float64))), nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if getResp.StatusCode != http.StatusOK {
		t.Fatalf("读取原链接失败 status=%d body=%s", getResp.StatusCode, string(getBody))
	}
	var got map[string]any
	if err := json.Unmarshal(getBody, &got); err != nil {
		t.Fatalf("解析原链接失败: %v", err)
	}
	if got["url"] != "https://example.com/one" {
		t.Fatalf("原链接 url 被覆盖: %v", got["url"])
	}
	if got["slug"] != "collide1" {
		t.Fatalf("原链接 slug 不符: %v", got["slug"])
	}
}

// TestHandler_Deep_ExpiredLinkRedirectRejected 验证过期链接跳转被拒且返回错误 JSON。
func TestHandler_Deep_ExpiredLinkRedirectRejected(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	past := time.Now().Add(-2 * time.Hour).UTC().Format(time.RFC3339)
	created := createLink(t, srv, cfg, map[string]any{
		"slug":       "expired1",
		"url":        "https://example.com/expired",
		"expires_at": past,
	})
	if created["slug"] != "expired1" {
		t.Fatalf("创建过期链接 slug 不符: %v", created["slug"])
	}

	resp, body := doReq(t, http.MethodGet, srv.URL+"/expired1", nil, nil)
	if resp.StatusCode == http.StatusFound || resp.StatusCode == http.StatusMovedPermanently {
		t.Fatalf("过期链接不应跳转, status=%d", resp.StatusCode)
	}
	if resp.StatusCode != http.StatusGone && resp.StatusCode != http.StatusNotFound {
		t.Fatalf("过期链接期望 410 或 404, 实际 %d body=%s", resp.StatusCode, string(body))
	}
	if !strings.Contains(string(body), "error") {
		t.Fatalf("过期链接响应体应包含 error 字段, 实际: %s", string(body))
	}
}

// TestHandler_Deep_MaxVisitsBurnBoundary 验证限次链接在边界次数后焚毁并拒绝后续访问。
func TestHandler_Deep_MaxVisitsBurnBoundary(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	created := createLink(t, srv, cfg, map[string]any{
		"slug":       "burn2",
		"url":        "https://example.com/burn",
		"max_visits": 2,
		"burn":       true,
	})
	if created["slug"] != "burn2" {
		t.Fatalf("创建焚毁链接 slug 不符: %v", created["slug"])
	}

	for i := 0; i < 2; i++ {
		resp, body := doReq(t, http.MethodGet, srv.URL+"/burn2", nil, nil)
		if resp.StatusCode != http.StatusFound {
			t.Fatalf("第 %d 次访问应跳转, status=%d body=%s", i+1, resp.StatusCode, string(body))
		}
		loc := resp.Header.Get("Location")
		if loc != "https://example.com/burn" {
			t.Fatalf("第 %d 次跳转地址不符: %s", i+1, loc)
		}
	}

	resp, body := doReq(t, http.MethodGet, srv.URL+"/burn2", nil, nil)
	if resp.StatusCode == http.StatusFound {
		t.Fatalf("超过次数后不应再跳转, status=%d", resp.StatusCode)
	}
	if !strings.Contains(string(body), "error") {
		t.Fatalf("超过次数后响应体应包含 error, 实际: %s", string(body))
	}

	getResp, getBody := doReq(t, http.MethodGet, srv.URL+"/api/links/"+deepItoa(int64(created["id"].(float64))), nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if getResp.StatusCode != http.StatusOK {
		t.Fatalf("读取焚毁链接失败 status=%d body=%s", getResp.StatusCode, string(getBody))
	}
	var got map[string]any
	if err := json.Unmarshal(getBody, &got); err != nil {
		t.Fatalf("解析焚毁链接失败: %v", err)
	}
	if got["enabled"] != false {
		t.Fatalf("焚毁后 enabled 应为 false, 实际: %v", got["enabled"])
	}
	clicks, ok := got["clicks"].(float64)
	if !ok {
		t.Fatalf("clicks 字段类型不符: %T", got["clicks"])
	}
	if int(clicks) < 2 {
		t.Fatalf("焚毁后点击数应至少 2, 实际: %v", clicks)
	}
}

// TestHandler_Deep_BurnRemainingAndPurgeFlag 验证焚毁链接 remaining 与 purge_after_burn 字段聚合正确。
func TestHandler_Deep_BurnRemainingAndPurgeFlag(t *testing.T) {
	cfg := newTestConfig(t)
	cfg.BurnPurgeAfterDestroy = true
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	created := createLink(t, srv, cfg, map[string]any{
		"slug":            "burnflag1",
		"url":             "https://example.com/burnflag",
		"burn":            true,
		"purge_after_burn": true,
	})
	if created["slug"] != "burnflag1" {
		t.Fatalf("创建链接 slug 不符: %v", created["slug"])
	}
	if created["burn"] != true {
		t.Fatalf("burn 字段应为 true, 实际: %v", created["burn"])
	}
	if created["purge_after_burn"] != true {
		t.Fatalf("purge_after_burn 字段应为 true, 实际: %v", created["purge_after_burn"])
	}
	remaining, ok := created["remaining"].(float64)
	if !ok {
		t.Fatalf("remaining 字段类型不符: %T", created["remaining"])
	}
	if int(remaining) != 1 {
		t.Fatalf("未访问前 burn 链接 remaining 应为 1, 实际: %v", remaining)
	}

	metaResp, metaBody := doReq(t, http.MethodGet, srv.URL+"/api/meta", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if metaResp.StatusCode != http.StatusOK {
		t.Fatalf("读取 meta 失败 status=%d body=%s", metaResp.StatusCode, string(metaBody))
	}
	var meta map[string]any
	if err := json.Unmarshal(metaBody, &meta); err != nil {
		t.Fatalf("解析 meta 失败: %v", err)
	}
	if meta["burn_purge_after_destroy"] != true {
		t.Fatalf("meta burn_purge_after_destroy 应为 true, 实际: %v", meta["burn_purge_after_destroy"])
	}
	if meta["base_url"] != "http://short.test" {
		t.Fatalf("meta base_url 不符: %v", meta["base_url"])
	}
}

// TestHandler_Deep_RedirectRecordsVisitProfile 验证跳转后访问画像聚合进统计接口。
func TestHandler_Deep_RedirectRecordsVisitProfile(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	created := createLink(t, srv, cfg, map[string]any{
		"slug": "profile1",
		"url":  "https://example.com/profile",
	})
	slug := created["slug"].(string)

	for i := 0; i < 3; i++ {
		req, err := http.NewRequest(http.MethodGet, srv.URL+"/"+slug, nil)
		if err != nil {
			t.Fatalf("构造跳转请求失败: %v", err)
		}
		req.Header.Set("Referer", "https://ref.example.com/page")
		req.Header.Set("User-Agent", "MuseDeepTest/1.0")
		client := &http.Client{Timeout: 10 * time.Second, CheckRedirect: func(r *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		}}
		resp, err := client.Do(req)
		if err != nil {
			t.Fatalf("跳转请求失败: %v", err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusFound {
			t.Fatalf("第 %d 次跳转 status=%d", i+1, resp.StatusCode)
		}
	}

	topResp, topBody := doReq(t, http.MethodGet, srv.URL+"/api/stats/top-referers", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if topResp.StatusCode != http.StatusOK {
		t.Fatalf("读取 top-referers 失败 status=%d body=%s", topResp.StatusCode, string(topBody))
	}
	if !strings.Contains(string(topBody), "ref.example.com") {
		t.Fatalf("top-referers 应聚合到 ref.example.com, 实际: %s", string(topBody))
	}

	overviewResp, overviewBody := doReq(t, http.MethodGet, srv.URL+"/api/stats/overview", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if overviewResp.StatusCode != http.StatusOK {
		t.Fatalf("读取 overview 失败 status=%d body=%s", overviewResp.StatusCode, string(overviewBody))
	}
	var overview map[string]any
	if err := json.Unmarshal(overviewBody, &overview); err != nil {
		t.Fatalf("解析 overview 失败: %v", err)
	}
	total, ok := overview["total_clicks"].(float64)
	if !ok {
		if raw, exists := overview["clicks"]; exists {
			total, ok = raw.(float64)
		}
	}
	if !ok {
		t.Fatalf("overview 缺少点击数字段, 实际: %s", string(overviewBody))
	}
	if int(total) < 3 {
		t.Fatalf("overview 总点击应至少 3, 实际: %v", total)
	}
}

// TestHandler_Deep_RateLimitBlocksBurst 验证开启限流后突发请求被 429 拦截。
func TestHandler_Deep_RateLimitBlocksBurst(t *testing.T) {
	cfg := newTestConfig(t)
	cfg.RateLimitEnabled = true
	cfg.RateLimitRPS = 1
	cfg.RateLimitBurst = 2
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	client := &http.Client{Timeout: 10 * time.Second, CheckRedirect: func(r *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	}}

	var tooMany, okCount int
	for i := 0; i < 12; i++ {
		req, err := http.NewRequest(http.MethodGet, srv.URL+"/api/health", nil)
		if err != nil {
			t.Fatalf("构造健康请求失败: %v", err)
		}
		req.Header.Set("X-API-Key", cfg.AdminKey)
		req.Header.Set("X-Forwarded-For", "203.0.113.77")
		resp, err := client.Do(req)
		if err != nil {
			t.Fatalf("健康请求失败: %v", err)
		}
		resp.Body.Close()
		switch resp.StatusCode {
		case http.StatusTooManyRequests:
			tooMany++
		case http.StatusOK:
			okCount++
		}
	}
	if tooMany == 0 {
		t.Fatalf("限流开启后应出现 429, okCount=%d", okCount)
	}
	if okCount == 0 {
		t.Fatalf("限流不应把突发内所有请求都拦掉, okCount=%d tooMany=%d", okCount, tooMany)
	}

	metricsResp, metricsBody := doReq(t, http.MethodGet, srv.URL+"/metrics", nil, nil)
	if metricsResp.StatusCode != http.StatusOK {
		t.Fatalf("/metrics 免限流应可访问, status=%d body=%s", metricsResp.StatusCode, string(metricsBody))
	}
	if !strings.Contains(string(metricsBody), "muse") && !strings.Contains(string(metricsBody), "http") {
		t.Fatalf("/metrics 响应不含指标内容: %s", string(metricsBody))
	}
}

// TestHandler_Deep_ReadyzAndHealthSplit 验证存活探针与就绪探针在存储不可用时的差异。
func TestHandler_Deep_ReadyzAndHealthSplit(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	healthResp, healthBody := doReq(t, http.MethodGet, srv.URL+"/api/health", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if healthResp.StatusCode != http.StatusOK {
		t.Fatalf("/api/health 应 200, 实际 %d body=%s", healthResp.StatusCode, string(healthBody))
	}
	var health map[string]any
	if err := json.Unmarshal(healthBody, &health); err != nil {
		t.Fatalf("解析 health 失败: %v", err)
	}
	if health["ok"] != true {
		t.Fatalf("health.ok 应为 true, 实际: %v", health["ok"])
	}

	readyResp, readyBody := doReq(t, http.MethodGet, srv.URL+"/api/readyz", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if readyResp.StatusCode != http.StatusOK {
		t.Fatalf("/api/readyz 在库可用时应 200, 实际 %d body=%s", readyResp.StatusCode, string(readyBody))
	}
	if !strings.Contains(strings.ToLower(string(readyBody)), "ok") {
		t.Fatalf("readyz 响应应包含 ok, 实际: %s", string(readyBody))
	}


	healthAfterResp, healthAfterBody := doReq(t, http.MethodGet, srv.URL+"/api/health", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if healthAfterResp.StatusCode != http.StatusOK {
		t.Fatalf("库关闭后 /api/health 仍应 200, 实际 %d body=%s", healthAfterResp.StatusCode, string(healthAfterBody))
	}

	readyAfterResp, readyAfterBody := doReq(t, http.MethodGet, srv.URL+"/api/readyz", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if readyAfterResp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("库关闭后 /api/readyz 应 503, 实际 %d body=%s", readyAfterResp.StatusCode, string(readyAfterBody))
	}
	if !strings.Contains(string(readyAfterBody), "error") {
		t.Fatalf("readyz 503 响应体应包含 error, 实际: %s", string(readyAfterBody))
	}
}

// TestHandler_Deep_BackupHealthMissingDir 验证备份目录缺失时备份健康判定为不健康。
func TestHandler_Deep_BackupHealthMissingDir(t *testing.T) {
	cfg := newTestConfig(t)
	missing := filepath.Join(t.TempDir(), "no-such-backup-dir")
	cfg.BackupDir = missing
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	resp, body := doReq(t, http.MethodGet, srv.URL+"/api/backup/health", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if resp.StatusCode != http.StatusServiceUnavailable && resp.StatusCode != http.StatusOK {
		t.Fatalf("备份健康接口意外状态 %d body=%s", resp.StatusCode, string(body))
	}
	var got map[string]any
	if err := json.Unmarshal(body, &got); err != nil {
		t.Fatalf("解析备份健康响应失败: %v body=%s", err, string(body))
	}
	healthy, ok := got["healthy"].(bool)
	if !ok {
		t.Fatalf("备份健康响应缺少 healthy 布尔字段: %s", string(body))
	}
	if healthy {
		t.Fatalf("备份目录缺失时 healthy 应为 false, 实际: %v", healthy)
	}
	if got["dir"] != missing {
		t.Fatalf("备份健康响应 dir 不符: %v", got["dir"])
	}
}

// TestHandler_Deep_BackupHealthStaleAndFresh 验证备份健康判定区分过期与新鲜备份。
func TestHandler_Deep_BackupHealthStaleAndFresh(t *testing.T) {
	cfg := newTestConfig(t)
	dir := t.TempDir()
	cfg.BackupDir = dir
	cfg.BackupMaxAgeDays = 7
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	oldFile := filepath.Join(dir, "muse-old.db")
	if err := os.WriteFile(oldFile, []byte("old-backup"), 0o600); err != nil {
		t.Fatalf("写入旧备份失败: %v", err)
	}
	oldTime := time.Now().Add(-6 * time.Hour)
	if err := os.Chtimes(oldFile, oldTime, oldTime); err != nil {
		t.Fatalf("调整旧备份时间失败: %v", err)
	}

	resp, body := doReq(t, http.MethodGet, srv.URL+"/api/backup/health", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if resp.StatusCode != http.StatusServiceUnavailable && resp.StatusCode != http.StatusOK {
		t.Fatalf("备份健康接口意外状态 %d body=%s", resp.StatusCode, string(body))
	}
	var stale map[string]any
	if err := json.Unmarshal(body, &stale); err != nil {
		t.Fatalf("解析过期备份响应失败: %v body=%s", err, string(body))
	}
	if stale["healthy"] != false {
		t.Fatalf("只有过期备份时 healthy 应为 false, 实际: %v body=%s", stale["healthy"], string(body))
	}

	newFile := filepath.Join(dir, "muse-new.db")
	if err := os.WriteFile(newFile, []byte("new-backup"), 0o600); err != nil {
		t.Fatalf("写入新备份失败: %v", err)
	}

	resp2, body2 := doReq(t, http.MethodGet, srv.URL+"/api/backup/health", nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("存在新鲜备份时应 200, 实际 %d body=%s", resp2.StatusCode, string(body2))
	}
	var fresh map[string]any
	if err := json.Unmarshal(body2, &fresh); err != nil {
		t.Fatalf("解析新鲜备份响应失败: %v body=%s", err, string(body2))
	}
	if fresh["healthy"] != true {
		t.Fatalf("存在新鲜备份时 healthy 应为 true, 实际: %v body=%s", fresh["healthy"], string(body2))
	}
	if fresh["dir"] != dir {
		t.Fatalf("新鲜备份响应 dir 不符: %v", fresh["dir"])
	}
}

// TestHandler_Deep_ConcurrentRedirectCounts 验证并发跳转下点击数不被丢失且 race 安全。
func TestHandler_Deep_ConcurrentRedirectCounts(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	created := createLink(t, srv, cfg, map[string]any{
		"slug": "concurrent1",
		"url":  "https://example.com/concurrent",
	})
	slug := created["slug"].(string)

	const workers = 10
	var wg sync.WaitGroup
	var mu sync.Mutex
	okCount := 0
	client := &http.Client{Timeout: 10 * time.Second, CheckRedirect: func(r *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	}}
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			req, err := http.NewRequest(http.MethodGet, srv.URL+"/"+slug, nil)
			if err != nil {
				return
			}
			resp, err := client.Do(req)
			if err != nil {
				return
			}
			resp.Body.Close()
			if resp.StatusCode == http.StatusFound {
				mu.Lock()
				okCount++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()

	if okCount != workers {
		t.Fatalf("并发跳转成功数应为 %d, 实际 %d", workers, okCount)
	}

	getResp, getBody := doReq(t, http.MethodGet, srv.URL+"/api/links/"+deepItoa(int64(created["id"].(float64))), nil, map[string]string{
		"X-API-Key": cfg.AdminKey,
	})
	if getResp.StatusCode != http.StatusOK {
		t.Fatalf("读取并发链接失败 status=%d body=%s", getResp.StatusCode, string(getBody))
	}
	var got map[string]any
	if err := json.Unmarshal(getBody, &got); err != nil {
		t.Fatalf("解析并发链接失败: %v", err)
	}
	clicks, ok := got["clicks"].(float64)
	if !ok {
		t.Fatalf("clicks 类型不符: %T", got["clicks"])
	}
	if int(clicks) != workers {
		t.Fatalf("并发跳转点击数应为 %d, 实际 %v", workers, clicks)
	}
}

// TestHandler_Deep_PasswordUnlockFlow 验证带密码链接的跳转与解锁路径。
func TestHandler_Deep_PasswordUnlockFlow(t *testing.T) {
	cfg := newTestConfig(t)
	st := newTestStore(t)
	srv := newDeepTestServer(t, st, cfg)

	created := createLink(t, srv, cfg, map[string]any{
		"slug":     "locked1",
		"url":      "https://example.com/locked",
		"password": "s3cret-pass",
	})
	if created["has_password"] != true {
		t.Fatalf("has_password 应为 true, 实际: %v", created["has_password"])
	}
	slug := created["slug"].(string)

	resp, body := doReq(t, http.MethodGet, srv.URL+"/"+slug, nil, nil)
	if resp.StatusCode == http.StatusFound {
		t.Fatalf("带密码链接直接 GET 不应跳转, status=%d", resp.StatusCode)
	}
	if resp.StatusCode != http.StatusUnauthorized && resp.StatusCode != http.StatusForbidden {
		t.Fatalf("带密码链接直接 GET 期望 401/403, 实际 %d body=%s", resp.StatusCode, string(body))
	}

	form := url.Values{}
	form.Set("password", "s3cret-pass")
	postResp, postBody := doReq(t, http.MethodPost, srv.URL+"/"+slug, []byte(form.Encode()), map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	})
	if postResp.StatusCode != http.StatusFound {
		t.Fatalf("正确密码解锁应跳转, 实际 %d body=%s", postResp.StatusCode, string(postBody))
	}
	if loc := postResp.Header.Get("Location"); loc != "https://example.com/locked" {
		t.Fatalf("解锁后跳转地址不符: %s", loc)
	}

	badResp, badBody := doReq(t, http.MethodPost, srv.URL+"/"+slug, []byte("password=wrong"), map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	})
	if badResp.StatusCode == http.StatusFound {
		t.Fatalf("错误密码不应跳转, status=%d", badResp.StatusCode)
	}
	if !strings.Contains(string(badBody), "error") && badResp.StatusCode != http.StatusUnauthorized && badResp.StatusCode != http.StatusForbidden {
		t.Fatalf("错误密码响应不符: status=%d body=%s", badResp.StatusCode, string(badBody))
	}
}

func mustJSON(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("序列化失败: %v", err)
	}
	return b
}

func deepItoa(v int64) string {
	return strings.TrimSpace(jsonNumberString(v))
}

func jsonNumberString(v int64) string {
	b, _ := json.Marshal(v)
	return string(b)
}