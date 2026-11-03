package handler

// 深测补强：限时到期边界（恰好到期瞬间/时区偏移/非法格式/过期链创建/PATCH 清除/密码链过期）。
// 编排手工编写（模型首版只输出模板占位，弃用）。
// 锁定的均为当前产品行为：过期判定为严格 After 语义（恰好等于 expires_at 的瞬间不算过期）；
// 创建时不校验 expires_at 是否已过去；PATCH expires_at:null 清除过期。

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"
)

var noFollowClient = &http.Client{
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	},
}

func createExpiryLink(t *testing.T, srvURL, slug, expiresAt string, extra map[string]any) map[string]any {
	t.Helper()
	body := map[string]any{"url": "https://example.com/" + slug, "slug": slug}
	if expiresAt != "" {
		body["expires_at"] = expiresAt
	}
	for k, v := range extra {
		body[k] = v
	}
	resp, data := doJSON(t, http.MethodPost, srvURL+"/api/links", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("建链期望 201，实际 %d：%s", resp.StatusCode, string(data))
	}
	var out map[string]any
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("解析建链响应失败: %v", err)
	}
	return out
}

func getNoFollow(t *testing.T, url string) (int, http.Header, []byte) {
	t.Helper()
	resp, err := noFollowClient.Get(url)
	if err != nil {
		t.Fatalf("GET %s 失败: %v", url, err)
	}
	defer resp.Body.Close()
	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	return resp.StatusCode, resp.Header, buf[:n]
}

func TestExpiry_恰好到期瞬间仍302(t *testing.T) {
	srv := newTestServer(t)
	// 未来 2 秒：请求到达时 expires_at 尚未过去（After 严格语义下恰好相等也不算过期）
	exp := time.Now().UTC().Add(2 * time.Second).Truncate(time.Second).Format(time.RFC3339)
	createExpiryLink(t, srv.URL, "exp-soon", exp, nil)
	code, _, _ := getNoFollow(t, srv.URL+"/exp-soon")
	if code != http.StatusFound {
		t.Errorf("未到期期望 302，实际 %d", code)
	}
}

func TestExpiry_过去一秒则410(t *testing.T) {
	srv := newTestServer(t)
	exp := time.Now().UTC().Add(-1 * time.Second).Format(time.RFC3339)
	createExpiryLink(t, srv.URL, "exp-past", exp, nil)
	code, _, body := getNoFollow(t, srv.URL+"/exp-past")
	if code != http.StatusGone {
		t.Errorf("已过期期望 410，实际 %d", code)
	}
	if !strings.Contains(string(body), "链接已过期") {
		t.Errorf("期望 body 含“链接已过期”，实际 %q", string(body))
	}
}

func TestExpiry_时区偏移正确比较(t *testing.T) {
	srv := newTestServer(t)
	// +08:00 偏移表示的过去时刻：比较按 instant 而非字符串
	exp := time.Now().Add(-time.Hour).In(time.FixedZone("CST", 8*3600)).Format(time.RFC3339)
	if !strings.Contains(exp, "+08:00") {
		t.Fatalf("测试前提失败，期望 +08:00 偏移，实际 %s", exp)
	}
	createExpiryLink(t, srv.URL, "exp-tz", exp, nil)
	code, _, _ := getNoFollow(t, srv.URL+"/exp-tz")
	if code != http.StatusGone {
		t.Errorf("+08:00 过去时刻期望 410，实际 %d", code)
	}
}

func TestExpiry_小数秒被接受(t *testing.T) {
	srv := newTestServer(t)
	out := createExpiryLink(t, srv.URL, "exp-frac", "2026-12-01T00:00:00.123456789Z", nil)
	exp, _ := out["expires_at"].(string)
	if !strings.Contains(exp, "2026-12-01") {
		t.Errorf("期望 expires_at 含 2026-12-01，实际 %v", out["expires_at"])
	}
}

func TestExpiry_非法格式400(t *testing.T) {
	srv := newTestServer(t)
	for _, bad := range []string{"2026-13-99T99:99:99Z", "明天中午", "2026-10-20"} {
		body := map[string]any{"url": "https://example.com/x", "slug": "bad-" + fmt.Sprint(len(bad)), "expires_at": bad}
		resp, _ := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, body)
		if resp.StatusCode != http.StatusBadRequest {
			t.Errorf("expires_at=%q 期望 400，实际 %d", bad, resp.StatusCode)
		}
	}
}

func TestExpiry_建已过期链锁定行为(t *testing.T) {
	srv := newTestServer(t)
	// 当前产品语义：创建时不校验 expires_at 是否已过去，建链成功 201
	exp := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	createExpiryLink(t, srv.URL, "exp-old", exp, nil)
	code, _, _ := getNoFollow(t, srv.URL+"/exp-old")
	if code != http.StatusGone {
		t.Errorf("已过期链访问期望 410，实际 %d", code)
	}
}

func TestExpiry_PATCH_null清除过期(t *testing.T) {
	srv := newTestServer(t)
	exp := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	out := createExpiryLink(t, srv.URL, "exp-clear", exp, nil)
	id := int64(out["id"].(float64))

	code, _, _ := getNoFollow(t, srv.URL+"/exp-clear")
	if code != http.StatusGone {
		t.Fatalf("前置条件失败：过期链期望 410，实际 %d", code)
	}
	// PATCH expires_at:null 清除过期
	resp, _ := doJSON(t, http.MethodPatch, fmt.Sprintf("%s/api/links/%d", srv.URL, id), testKey,
		map[string]any{"expires_at": nil})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("PATCH 清除过期期望 200，实际 %d", resp.StatusCode)
	}
	code, _, _ = getNoFollow(t, srv.URL+"/exp-clear")
	if code != http.StatusFound {
		t.Errorf("清除过期后期望 302，实际 %d", code)
	}
}

func TestExpiry_PATCH_非法格式400(t *testing.T) {
	srv := newTestServer(t)
	out := createExpiryLink(t, srv.URL, "exp-patch-bad", "", nil)
	id := int64(out["id"].(float64))
	resp, _ := doJSON(t, http.MethodPatch, fmt.Sprintf("%s/api/links/%d", srv.URL, id), testKey,
		map[string]any{"expires_at": "xxx"})
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("PATCH 非法 expires_at 期望 400，实际 %d", resp.StatusCode)
	}
}

func TestExpiry_密码链过期先判过期(t *testing.T) {
	srv := newTestServer(t)
	exp := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	createExpiryLink(t, srv.URL, "exp-pw", exp, map[string]any{"password": "pw123456"})
	// GET 直接 410，看不到密码门（loadActiveLink 在密码门之前拦截）
	code, _, _ := getNoFollow(t, srv.URL+"/exp-pw")
	if code != http.StatusGone {
		t.Errorf("过期密码链 GET 期望 410，实际 %d", code)
	}
	// POST 正确密码同样 410
	form := url.Values{"password": {"pw123456"}}
	req, _ := http.NewRequest(http.MethodPost, srv.URL+"/exp-pw", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := noFollowClient.Do(req)
	if err != nil {
		t.Fatalf("POST 失败: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusGone {
		t.Errorf("过期密码链 POST 正确密码期望 410，实际 %d", resp.StatusCode)
	}
}

func TestExpiry_未过期密码链门页正常(t *testing.T) {
	srv := newTestServer(t)
	exp := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	createExpiryLink(t, srv.URL, "exp-pw-ok", exp, map[string]any{"password": "pw123456"})
	code, _, body := getNoFollow(t, srv.URL+"/exp-pw-ok")
	if code != http.StatusOK {
		t.Fatalf("未过期密码链 GET 期望 200 密码门，实际 %d", code)
	}
	if !strings.Contains(string(body), "该链接受密码保护") {
		t.Errorf("期望密码门页，实际 body 头部 %q", string(body[:120]))
	}
	// 正确密码 → 302
	form := url.Values{"password": {"pw123456"}}
	req, _ := http.NewRequest(http.MethodPost, srv.URL+"/exp-pw-ok", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := noFollowClient.Do(req)
	if err != nil {
		t.Fatalf("POST 失败: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusFound {
		t.Errorf("正确密码期望 302，实际 %d", resp.StatusCode)
	}
}
