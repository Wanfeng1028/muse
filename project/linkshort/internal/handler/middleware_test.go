package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"testing"
)

func noRedirectClient() *http.Client {
	return &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

func TestMetricsEndpointExposed(t *testing.T) {
	srv := newTestServer(t)

	resp, err := http.Get(srv.URL + "/metrics")
	if err != nil {
		t.Fatalf("GET /metrics 失败: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("读取 body 失败: %v", err)
	}
	if !strings.Contains(string(body), "linkshort_http_requests_total") {
		t.Fatalf("/metrics body missing linkshort_http_requests_total\nbody:\n%s", string(body))
	}
}

func TestMetricsCountsRedirects(t *testing.T) {
	srv := newTestServer(t)

	resp, raw := doJSON(t, "POST", srv.URL+"/api/links", testKey, map[string]any{
		"url": "https://example.com",
	})
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		t.Fatalf("create link status = %d, want 200/201, body: %s", resp.StatusCode, string(raw))
	}
	var created struct {
		Slug string `json:"slug"`
	}
	if err := json.Unmarshal(raw, &created); err != nil {
		t.Fatalf("解析创建响应失败: %v, body: %s", err, string(raw))
	}
	if created.Slug == "" {
		t.Fatalf("创建响应缺少 slug, body: %s", string(raw))
	}

	client := noRedirectClient()
	rresp, err := client.Get(srv.URL + "/" + created.Slug)
	if err != nil {
		t.Fatalf("GET /%s 失败: %v", created.Slug, err)
	}
	defer rresp.Body.Close()
	if rresp.StatusCode != http.StatusFound {
		t.Fatalf("redirect status = %d, want 302", rresp.StatusCode)
	}

	mresp, err := http.Get(srv.URL + "/metrics")
	if err != nil {
		t.Fatalf("GET /metrics 失败: %v", err)
	}
	defer mresp.Body.Close()
	mbody, err := io.ReadAll(mresp.Body)
	if err != nil {
		t.Fatalf("读取 /metrics body 失败: %v", err)
	}
	if !strings.Contains(string(mbody), `linkshort_redirects_total{outcome="ok"}`) {
		t.Fatalf("/metrics missing redirect ok counter\nbody:\n%s", string(mbody))
	}
}

func TestBurnIncrementsBurnedMetric(t *testing.T) {
	srv := newTestServer(t)

	resp, raw := doJSON(t, "POST", srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com",
		"burn": true,
	})
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		t.Fatalf("create burn link status = %d, want 200/201, body: %s", resp.StatusCode, string(raw))
	}
	var created struct {
		Slug string `json:"slug"`
	}
	if err := json.Unmarshal(raw, &created); err != nil {
		t.Fatalf("解析创建响应失败: %v, body: %s", err, string(raw))
	}
	if created.Slug == "" {
		t.Fatalf("创建响应缺少 slug, body: %s", string(raw))
	}

	client := noRedirectClient()
	rresp, err := client.Get(srv.URL + "/" + created.Slug)
	if err != nil {
		t.Fatalf("GET /%s 失败: %v", created.Slug, err)
	}
	defer rresp.Body.Close()
	if rresp.StatusCode != http.StatusFound {
		t.Fatalf("burn redirect status = %d, want 302", rresp.StatusCode)
	}

	mresp, err := http.Get(srv.URL + "/metrics")
	if err != nil {
		t.Fatalf("GET /metrics 失败: %v", err)
	}
	defer mresp.Body.Close()
	mbody, err := io.ReadAll(mresp.Body)
	if err != nil {
		t.Fatalf("读取 /metrics body 失败: %v", err)
	}

	re := regexp.MustCompile(`linkshort_burn_links_burned_total (\d+)`)
	m := re.FindStringSubmatch(string(mbody))
	if m == nil {
		t.Fatalf("/metrics missing linkshort_burn_links_burned_total\nbody:\n%s", string(mbody))
	}
	v, err := strconv.Atoi(m[1])
	if err != nil {
		t.Fatalf("解析 burned 计数失败: %v (value=%q)", err, m[1])
	}
	if v < 1 {
		t.Fatalf("linkshort_burn_links_burned_total = %d, want >= 1", v)
	}
}
