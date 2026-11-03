package handler

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// newNoRedirectClient 返回不自动跟随跳转的 http.Client，用于断言 302 语义。
func newNoRedirectClient() *http.Client {
	return &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

// newLimitsTestServer 创建带内存库的测试服务，同时返回 store 与 *sql.DB 供断言。
func newLimitsTestServer(t *testing.T) (*httptest.Server, *store.Store, *sql.DB) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open(:memory:) 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)
	cfg := newTestConfig(t)
	srv := httptest.NewServer(NewRouter(st, cfg))
	t.Cleanup(srv.Close)
	return srv, st, database
}

// getSlug 用不跟随跳转的 client 请求 /{slug}，返回响应与 Location。
func getSlug(t *testing.T, srv *httptest.Server, slug string) (*http.Response, string) {
	t.Helper()
	client := newNoRedirectClient()
	req, err := http.NewRequest(http.MethodGet, srv.URL+"/"+slug, nil)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	loc := resp.Header.Get("Location")
	return resp, loc
}

// 限次耗尽：max_visits=3，3 次 302，第 4/5 次 410 且含"访问上限"，DB 中 visits 恰好 3 行。
func TestLimits_Exhausted(t *testing.T) {
	srv, _, database := newLimitsTestServer(t)
	defer srv.Close()

	target := "https://example.com/exhausted"
	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":        target,
		"slug":       "exhaust3",
		"max_visits": 3,
	})
	id := int64(created["id"].(float64))
	slug := created["slug"].(string)

	for i := 0; i < 3; i++ {
		resp, loc := getSlug(t, srv, slug)
		if resp.StatusCode != http.StatusFound {
			t.Fatalf("第 %d 次 GET 期望 302，得到 %d", i+1, resp.StatusCode)
		}
		if loc != target {
			t.Fatalf("第 %d 次 Location 期望 %q，得到 %q", i+1, target, loc)
		}
		resp.Body.Close()
	}

	for i := 0; i < 2; i++ {
		resp, _ := getSlug(t, srv, slug)
		if resp.StatusCode != http.StatusGone {
			t.Fatalf("第 %d 次超额 GET 期望 410，得到 %d", i+1, resp.StatusCode)
		}
		body := readBody(t, resp)
		if !strings.Contains(body, "访问上限") {
			t.Fatalf("超额 body 期望包含 访问上限，得到 %q", body)
		}
	}

	var count int
	if err := database.QueryRow("SELECT COUNT(*) FROM visits WHERE link_id = ?", id).Scan(&count); err != nil {
		t.Fatalf("查询 visits 计数失败: %v", err)
	}
	if count != 3 {
		t.Fatalf("visits 行数期望 3，得到 %d", count)
	}

	var clicks int
	if err := database.QueryRow("SELECT clicks FROM links WHERE id = ?", id).Scan(&clicks); err != nil {
		t.Fatalf("查询 clicks 失败: %v", err)
	}
	if clicks != 3 {
		t.Fatalf("clicks 期望 3，得到 %d", clicks)
	}
}

// 过期：expires_at 为过去时间，GET → 410 且含"已过期"。
func TestLimits_Expired(t *testing.T) {
	srv, _, _ := newLimitsTestServer(t)
	defer srv.Close()

	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":        "https://example.com/expired",
		"slug":       "expired1",
		"expires_at": "2020-01-01T00:00:00Z",
	})
	slug := created["slug"].(string)

	resp, _ := getSlug(t, srv, slug)
	if resp.StatusCode != http.StatusGone {
		t.Fatalf("过期链 GET 期望 410，得到 %d", resp.StatusCode)
	}
	body := readBody(t, resp)
	if !strings.Contains(body, "已过期") {
		t.Fatalf("过期 body 期望包含 已过期，得到 %q", body)
	}
}

// 阅后即焚：burn=true，首次 302，第二次 410 且含"已阅销毁"，DB enabled=0。
func TestBurn_OneTime(t *testing.T) {
	srv, _, database := newLimitsTestServer(t)
	defer srv.Close()

	target := "https://example.com/burn"
	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":  target,
		"slug": "burnonce",
		"burn": true,
	})
	id := int64(created["id"].(float64))
	slug := created["slug"].(string)

	resp, loc := getSlug(t, srv, slug)
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("首次 GET 期望 302，得到 %d", resp.StatusCode)
	}
	if loc != target {
		t.Fatalf("首次 Location 期望 %q，得到 %q", target, loc)
	}
	resp.Body.Close()

	resp2, _ := getSlug(t, srv, slug)
	if resp2.StatusCode != http.StatusGone {
		t.Fatalf("第二次 GET 期望 410，得到 %d", resp2.StatusCode)
	}
	body := readBody(t, resp2)
	if !strings.Contains(body, "已阅销毁") {
		t.Fatalf("第二次 body 期望包含 已阅销毁，得到 %q", body)
	}

	var enabled int
	if err := database.QueryRow("SELECT enabled FROM links WHERE id = ?", id).Scan(&enabled); err != nil {
		t.Fatalf("查询 enabled 失败: %v", err)
	}
	if enabled != 0 {
		t.Fatalf("burn 后 enabled 期望 0，得到 %d", enabled)
	}
}

// 焚毁并彻底删除：burn=true&purge=true，首次 302，随后 GET /api/links/{id} → 404。
func TestBurn_Purge(t *testing.T) {
	srv, _, _ := newLimitsTestServer(t)
	defer srv.Close()

	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":   "https://example.com/purge",
		"slug":  "burnpurge",
		"burn":  true,
		"purge": true,
	})
	id := int64(created["id"].(float64))
	slug := created["slug"].(string)

	resp, _ := getSlug(t, srv, slug)
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("purge 链首次 GET 期望 302，得到 %d", resp.StatusCode)
	}
	resp.Body.Close()

	statusResp, _ := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+itoa(id), newTestConfig(t).AdminKey, nil)
	if statusResp.StatusCode != http.StatusNotFound {
		t.Fatalf("purge 后 GET /api/links/%d 期望 404，得到 %d", id, statusResp.StatusCode)
	}

}

// 并发抢最后 1 次：max_visits=1，20 并发 → 恰好 1 个 302、19 个 410，clicks==1。
func TestLimits_ConcurrentLastVisit(t *testing.T) {
	srv, _, database := newLimitsTestServer(t)
	defer srv.Close()

	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":        "https://example.com/race",
		"slug":       "race1",
		"max_visits": 1,
	})
	id := int64(created["id"].(float64))
	slug := created["slug"].(string)

	const workers = 20
	var wg sync.WaitGroup
	results := make([]int, workers)
	client := newNoRedirectClient()

	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			req, err := http.NewRequest(http.MethodGet, srv.URL+"/"+slug, nil)
			if err != nil {
				results[idx] = -1
				return
			}
			resp, err := client.Do(req)
			if err != nil {
				results[idx] = -1
				return
			}
			results[idx] = resp.StatusCode
			resp.Body.Close()
		}(i)
	}
	wg.Wait()

	ok := 0
	gone := 0
	for _, code := range results {
		switch code {
		case http.StatusFound:
			ok++
		case http.StatusGone:
			gone++
		}
	}
	if ok != 1 {
		t.Fatalf("并发期望恰好 1 个 302，得到 %d，全部结果=%v", ok, results)
	}
	if gone != workers-1 {
		t.Fatalf("并发期望 %d 个 410，得到 %d", workers-1, gone)
	}

	var clicks int
	if err := database.QueryRow("SELECT clicks FROM links WHERE id = ?", id).Scan(&clicks); err != nil {
		t.Fatalf("查询 clicks 失败: %v", err)
	}
	if clicks != 1 {
		t.Fatalf("clicks 期望 1，得到 %d", clicks)
	}
}

// 并发只焚毁一次：burn=true，10 并发 → 恰好 1 个 302、9 个 410。
func TestBurn_ConcurrentOnlyOnce(t *testing.T) {
	srv, _, database := newLimitsTestServer(t)
	defer srv.Close()

	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":  "https://example.com/burnrace",
		"slug": "burnrace1",
		"burn": true,
	})
	id := int64(created["id"].(float64))
	slug := created["slug"].(string)

	const workers = 10
	var wg sync.WaitGroup
	results := make([]int, workers)
	client := newNoRedirectClient()

	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			req, err := http.NewRequest(http.MethodGet, srv.URL+"/"+slug, nil)
			if err != nil {
				results[idx] = -1
				return
			}
			resp, err := client.Do(req)
			if err != nil {
				results[idx] = -1
				return
			}
			results[idx] = resp.StatusCode
			resp.Body.Close()
		}(i)
	}
	wg.Wait()

	ok := 0
	gone := 0
	for _, code := range results {
		switch code {
		case http.StatusFound:
			ok++
		case http.StatusGone:
			gone++
		}
	}
	if ok != 1 {
		t.Fatalf("并发 burn 期望恰好 1 个 302，得到 %d，全部结果=%v", ok, results)
	}
	if gone != workers-1 {
		t.Fatalf("并发 burn 期望 %d 个 410，得到 %d", workers-1, gone)
	}

	var enabled int
	if err := database.QueryRow("SELECT enabled FROM links WHERE id = ?", id).Scan(&enabled); err != nil {
		t.Fatalf("查询 enabled 失败: %v", err)
	}
	if enabled != 0 {
		t.Fatalf("并发 burn 后 enabled 期望 0，得到 %d", enabled)
	}
}

// burn 与 max_visits 同时设置：burn 胜出，第二次 410 含"已阅销毁"而非"访问上限"。
func TestLimits_BurnWinsOverMaxVisits(t *testing.T) {
	srv, _, _ := newLimitsTestServer(t)
	defer srv.Close()

	// API 只允许 burn + max_visits=1 的组合（max_visits=1 即一次性语义）
	target := "https://example.com/burnwins"
	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":        target,
		"slug":       "burnwins",
		"burn":       true,
		"max_visits": 1,
	})
	slug := created["slug"].(string)

	resp, loc := getSlug(t, srv, slug)
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("首次 GET 期望 302，得到 %d", resp.StatusCode)
	}
	if loc != target {
		t.Fatalf("首次 Location 期望 %q，得到 %q", target, loc)
	}
	resp.Body.Close()

	// burn 语义胜出：第二次是"已阅销毁"而不是"访问上限"
	resp2, _ := getSlug(t, srv, slug)
	if resp2.StatusCode != http.StatusGone {
		t.Fatalf("第二次 GET 期望 410，得到 %d", resp2.StatusCode)
	}
	body := readBody(t, resp2)
	if !strings.Contains(body, "已阅销毁") {
		t.Fatalf("第二次 body 期望包含 已阅销毁，得到 %q", body)
	}
	if strings.Contains(body, "访问上限") {
		t.Fatalf("第二次 body 不应包含 访问上限，得到 %q", body)
	}
}

func TestLimits_BurnWithMaxVisits5Rejected(t *testing.T) {
	srv, _, _ := newLimitsTestServer(t)
	defer srv.Close()

	// burn + max_visits=5 建链直接 400
	raw, _ := json.Marshal(map[string]any{
		"url":        "https://example.com/burnrej",
		"slug":       "burnrej",
		"burn":       true,
		"max_visits": 5,
	})
	resp, data := doReq(t, http.MethodPost, srv.URL+"/api/links", raw, map[string]string{
		"Content-Type": "application/json",
		"X-API-Key":    newTestConfig(t).AdminKey,
	})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("burn+max_visits=5 建链期望 400，得到 %d body=%s", resp.StatusCode, string(data))
	}
	if !strings.Contains(string(data), "不能与限次访问同时设置") {
		t.Fatalf("400 body 期望包含 不能与限次访问同时设置，得到 %q", string(data))
	}
}

// 未过期链正常跳转：expires_at 为未来时间 → 302。
func TestLimits_NotExpiredRedirects(t *testing.T) {
	srv, _, _ := newLimitsTestServer(t)
	defer srv.Close()

	target := "https://example.com/future"
	created := createLink(t, srv, newTestConfig(t), map[string]any{
		"url":        target,
		"slug":       "future1",
		"expires_at": "2999-01-01T00:00:00Z",
	})
	slug := created["slug"].(string)

	resp, loc := getSlug(t, srv, slug)
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("未过期链 GET 期望 302，得到 %d", resp.StatusCode)
	}
	if loc != target {
		t.Fatalf("Location 期望 %q，得到 %q", target, loc)
	}
	resp.Body.Close()
}
