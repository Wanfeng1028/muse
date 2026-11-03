
package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
"strings"
"strconv"
"sync"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/passalert"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

// newAlertTestServer 创建带密码告警配置的 httptest.Server。
func newAlertTestServer(t *testing.T, threshold int, webhookURL string) *httptest.Server {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open(:memory:) 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	st := store.New(database)
	cfg := &config.Config{
		AdminKey:                     testKey,
		PasswordFailAlertThreshold:   threshold,
		PasswordFailAlertWindow:      time.Minute,
		AlertWebhookURL:              webhookURL,
	}
	srv := httptest.NewServer(NewRouter(st, cfg))
	t.Cleanup(srv.Close)
	return srv
}

// createPasswordLink 通过 API 建一条带密码的短链，返回 slug。
func createPasswordLink(t *testing.T, srv *httptest.Server, targetURL, password string) string {
	t.Helper()
	resp, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      targetURL,
		"password": password,
	})
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		t.Fatalf("建带密码短链失败 status=%d body=%s", resp.StatusCode, string(body))
	}
	var created struct {
		Slug string `json:"slug"`
	}
	if err := json.Unmarshal(body, &created); err != nil {
		t.Fatalf("解析建链响应失败: %v body=%s", err, string(body))
	}
	if created.Slug == "" {
		t.Fatalf("建链响应缺少 slug: %s", string(body))
	}
	return created.Slug
}

// wrongPassword 提交一次错误密码，返回响应。
func wrongPassword(t *testing.T, srv *httptest.Server, slug string) *http.Response {
	t.Helper()
	form := url.Values{}
	form.Set("password", "definitely-wrong-password")
	return postForm(t, srv, "/"+slug, form)
}

func TestPasswordAlert_FiresWebhookOnce(t *testing.T) {
	defer passalert.Configure(10, 5*time.Minute)
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	var mu sync.Mutex
	var bodies []string
	hook := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		buf := make([]byte, 0)
		tmp := make([]byte, 1024)
		for {
			n, err := r.Body.Read(tmp)
			if n > 0 {
				buf = append(buf, tmp[:n]...)
			}
			if err != nil {
				break
			}
		}
		mu.Lock()
		bodies = append(bodies, string(buf))
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer hook.Close()

	srv := newAlertTestServer(t, 3, hook.URL)
	slug := createPasswordLink(t, srv, "https://example.com/secret", "correct-horse")

	// 前 2 次错误密码：未达阈值，不应触发 webhook。
	for i := 0; i < 2; i++ {
		resp := wrongPassword(t, srv, slug)
		_ = readBody(t, resp)
	}
	time.Sleep(300 * time.Millisecond)
	mu.Lock()
	if len(bodies) != 0 {
		n := len(bodies)
		mu.Unlock()
		t.Fatalf("未达阈值时不应触发 webhook，实际收到 %d 条", n)
	}
	mu.Unlock()

	// 第 3 次错误密码：跨越阈值，应触发 1 条 webhook。
	resp := wrongPassword(t, srv, slug)
	_ = readBody(t, resp)

	deadline := time.Now().Add(3 * time.Second)
	for {
		mu.Lock()
		n := len(bodies)
		mu.Unlock()
		if n >= 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("等待 webhook 超时，期望至少 1 条")
		}
		time.Sleep(20 * time.Millisecond)
	}

	mu.Lock()
	if len(bodies) != 1 {
		n := len(bodies)
		mu.Unlock()
		t.Fatalf("第 3 次错误密码后期望恰好 1 条 webhook，实际 %d", n)
	}
	first := bodies[0]
	mu.Unlock()

	if !strings.Contains(first, "password_fail_alert") {
		t.Errorf("webhook body 期望包含 password_fail_alert，实际 %s", first)
	}
	if !strings.Contains(first, slug) {
		t.Errorf("webhook body 期望包含 slug=%s，实际 %s", slug, first)
	}

	// 第 4 次错误密码：持续超阈值，不应重复触发。
	resp = wrongPassword(t, srv, slug)
	_ = readBody(t, resp)

	time.Sleep(300 * time.Millisecond)
	mu.Lock()
	finalN := len(bodies)
	mu.Unlock()
	if finalN != 1 {
		t.Fatalf("持续超阈值不应重复触发，期望仍为 1 条，实际 %d", finalN)
	}
}

func TestPasswordAlert_MetricsIncremented(t *testing.T) {
	defer passalert.Configure(10, 5*time.Minute)
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newAlertTestServer(t, 3, "")

	before := readMetricValue(t, srv, "linkshort_password_fail_alerts_total")

	slug := createPasswordLink(t, srv, "https://example.com/secret2", "correct-horse")

	for i := 0; i < 3; i++ {
		resp := wrongPassword(t, srv, slug)
		_ = readBody(t, resp)
	}

	// 等告警计数写入（异步/同步都兼容）。
	deadline := time.Now().Add(3 * time.Second)
	var after float64
	for {
		after = readMetricValue(t, srv, "linkshort_password_fail_alerts_total")
		if after >= before+1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("等待 metric 增长超时，before=%v after=%v", before, after)
		}
		time.Sleep(20 * time.Millisecond)
	}

	if after != before+1 {
		t.Fatalf("linkshort_password_fail_alerts_total 期望 %v，实际 %v", before+1, after)
	}
}

// readMetricValue 从 /metrics 读取指定指标的值。
func readMetricValue(t *testing.T, srv *httptest.Server, name string) float64 {
	t.Helper()
	resp, err := http.Get(srv.URL + "/metrics")
	if err != nil {
		t.Fatalf("请求 /metrics 失败: %v", err)
	}
	defer resp.Body.Close()
	buf := make([]byte, 0)
	tmp := make([]byte, 4096)
	for {
		n, err := resp.Body.Read(tmp)
		if n > 0 {
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			break
		}
	}
	text := string(buf)
	var val float64
	found := false
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, name) {
			fields := strings.Fields(line)
			if len(fields) >= 2 && fields[0] == name {
				if _, err := fmtSscan(fields[1], &val); err == nil {
					found = true
					break
				}
			}
		}
	}
	if !found {
		t.Fatalf("/metrics 中未找到指标 %s，内容:\n%s", name, text)
	}
	return val
}

// fmtSscan 用 strconv.ParseFloat 解析指标值。
func fmtSscan(s string, out *float64) (int, error) {
v, err:= strconv.ParseFloat(s, 64)
	if err != nil {
		return 0, err
	}
	*out = v
	return 1, nil
}
