package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

const (
	testVAPIDPublic  = "BCNhoeQXALENvz2Frbod6K-6gNUWaAZWrebUJECMHJSxSPdMOJE6FGFTZjP_riq_6BMcdTXLMsMptS3ZNwdV18s"
	testVAPIDPrivate = "NIHYpAwRN1MRUAijqBVxWGmgOtio6zFYjbnG-DR7eBQ"
	testVAPIDSubject = "mailto:test@example.com"
	testP256DH       = "dGVzdC1wMjU2ZGg"
	testAuth         = "dGVzdC1hdXRo"
)

func newWebPushTestServer(t *testing.T, vapid bool) (*httptest.Server, *store.Store) {
	t.Helper()
	if vapid {
		t.Setenv("SB_VAPID_PUBLIC_KEY", testVAPIDPublic)
		t.Setenv("SB_VAPID_PRIVATE_KEY", testVAPIDPrivate)
		t.Setenv("SB_VAPID_SUBJECT", testVAPIDSubject)
	}
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("打开测试库失败: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	mux := http.NewServeMux()
	RegisterPushRoutes(mux, st, config.Load())
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv, st
}

func doRequest(t *testing.T, method, url, user string, body any) *http.Response {
	t.Helper()
	var reader io.Reader
	if body != nil {
		buf, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("序列化请求体失败: %v", err)
		}
		reader = bytes.NewReader(buf)
	}
	req, err := http.NewRequest(method, url, reader)
	if err != nil {
		t.Fatalf("构造请求失败: %v", err)
	}
	if user != "" {
		req.Header.Set("X-User", user)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("发送请求失败: %v", err)
	}
	t.Cleanup(func() { _ = resp.Body.Close() })
	return resp
}

func decodeJSON(t *testing.T, resp *http.Response, out any) {
	t.Helper()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("读取响应体失败: %v", err)
	}
	if err := json.Unmarshal(data, out); err != nil {
		t.Fatalf("解析响应体失败: %v, 原文 %s", err, string(data))
	}
}

func TestPostSubscription(t *testing.T) {
	srv, _ := newWebPushTestServer(t, true)
	resp := doRequest(t, http.MethodPost, srv.URL+"/api/push/subscriptions", "alice", map[string]string{
		"endpoint": "https://push.example.com/a",
		"p256dh":   testP256DH,
		"auth":     testAuth,
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("期望状态码 201, 实际 %d", resp.StatusCode)
	}
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("读取响应体失败: %v", err)
	}
	if strings.Contains(string(data), testP256DH) {
		t.Fatalf("响应体不应包含 p256dh 原文, 实际 %s", string(data))
	}
	var view struct {
		ID           int64  `json:"id"`
		Endpoint     string `json:"endpoint"`
		CreatedAt    string `json:"createdAt"`
		P256DHMasked string `json:"p256dhMasked"`
		AuthMasked   string `json:"authMasked"`
	}
	if err := json.Unmarshal(data, &view); err != nil {
		t.Fatalf("解析响应失败: %v, 原文 %s", err, string(data))
	}
	if view.ID == 0 {
		t.Fatalf("返回的订阅 ID 不应为 0")
	}
	if view.CreatedAt == "" {
		t.Fatalf("返回的 createdAt 不应为空")
	}
	if view.P256DHMasked != "dGVz***" {
		t.Fatalf("p256dhMasked 期望 %q, 实际 %q", "dGVz***", view.P256DHMasked)
	}
	if view.AuthMasked != "dGVz***" {
		t.Fatalf("authMasked 期望 %q, 实际 %q", "dGVz***", view.AuthMasked)
	}
}

func TestPostSubscriptionNoVAPID(t *testing.T) {
	srv, _ := newWebPushTestServer(t, false)
	resp := doRequest(t, http.MethodPost, srv.URL+"/api/push/subscriptions", "alice", map[string]string{
		"endpoint": "https://push.example.com/a",
		"p256dh":   testP256DH,
		"auth":     testAuth,
	})
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("未配置 VAPID 时期望 503, 实际 %d", resp.StatusCode)
	}
}

func TestPostSubscriptionValidation(t *testing.T) {
	srv, _ := newWebPushTestServer(t, true)
	resp := doRequest(t, http.MethodPost, srv.URL+"/api/push/subscriptions", "alice", map[string]string{
		"endpoint": "http://push.example.com/a",
		"p256dh":   testP256DH,
		"auth":     testAuth,
	})
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("非法 endpoint 期望 400, 实际 %d", resp.StatusCode)
	}
}

func TestDeleteSubscription(t *testing.T) {
	srv, _ := newWebPushTestServer(t, true)
	endpoint := "https://push.example.com/del"
	postResp := doRequest(t, http.MethodPost, srv.URL+"/api/push/subscriptions", "alice", map[string]string{
		"endpoint": endpoint,
		"p256dh":   testP256DH,
		"auth":     testAuth,
	})
	if postResp.StatusCode != http.StatusCreated {
		t.Fatalf("预置订阅失败, 状态码 %d", postResp.StatusCode)
	}

	resp := doRequest(t, http.MethodDelete, srv.URL+"/api/push/subscriptions", "alice", map[string]string{"endpoint": endpoint})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("删除期望 200, 实际 %d", resp.StatusCode)
	}
	var del struct {
		Deleted bool `json:"deleted"`
	}
	decodeJSON(t, resp, &del)
	if !del.Deleted {
		t.Fatalf("首次删除应返回 deleted=true")
	}

	resp2 := doRequest(t, http.MethodDelete, srv.URL+"/api/push/subscriptions", "alice", map[string]string{"endpoint": endpoint})
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("重复删除期望 200, 实际 %d", resp2.StatusCode)
	}
	var del2 struct {
		Deleted bool `json:"deleted"`
	}
	decodeJSON(t, resp2, &del2)
	if del2.Deleted {
		t.Fatalf("重复删除应返回 deleted=false")
	}
}

func TestListIsolation(t *testing.T) {
	srv, _ := newWebPushTestServer(t, true)
	post := func(user, endpoint string) {
		t.Helper()
		resp := doRequest(t, http.MethodPost, srv.URL+"/api/push/subscriptions", user, map[string]string{
			"endpoint": endpoint,
			"p256dh":   testP256DH,
			"auth":     testAuth,
		})
		if resp.StatusCode != http.StatusCreated {
			t.Fatalf("用户 %s 写入订阅失败, 状态码 %d", user, resp.StatusCode)
		}
	}
	post("alice", "https://push.example.com/alice")
	post("bob", "https://push.example.com/bob")

	resp := doRequest(t, http.MethodGet, srv.URL+"/api/push/subscriptions", "alice", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("列出订阅期望 200, 实际 %d", resp.StatusCode)
	}
	var list []struct {
		Endpoint string `json:"endpoint"`
	}
	decodeJSON(t, resp, &list)
	if len(list) != 1 {
		t.Fatalf("alice 应只看到 1 条订阅, 实际 %d 条", len(list))
	}
	if list[0].Endpoint != "https://push.example.com/alice" {
		t.Fatalf("alice 不应看到 bob 的订阅, 实际 endpoint %q", list[0].Endpoint)
	}
}

func TestGetVAPIDPublicKey(t *testing.T) {
	srv, _ := newWebPushTestServer(t, true)
	resp := doRequest(t, http.MethodGet, srv.URL+"/api/push/vapid-public-key", "alice", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("配置 VAPID 时期望 200, 实际 %d", resp.StatusCode)
	}
	var key struct {
		PublicKey string `json:"publicKey"`
	}
	decodeJSON(t, resp, &key)
	if key.PublicKey != testVAPIDPublic {
		t.Fatalf("publicKey 期望 %q, 实际 %q", testVAPIDPublic, key.PublicKey)
	}

}

// TestGetVAPIDPublicKeyNoVAPID 未配置 VAPID 时公钥接口应返回 503。
// 注意：必须与配置了 VAPID 的用例拆成两个 Test 函数，因为 t.Setenv 的恢复
// 要等到整个 Test 函数结束，同一函数内无法先设后撤。
func TestGetVAPIDPublicKeyNoVAPID(t *testing.T) {
	srv, _ := newWebPushTestServer(t, false)
	resp := doRequest(t, http.MethodGet, srv.URL+"/api/push/vapid-public-key", "alice", nil)
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("未配置 VAPID 时期望 503, 实际 %d", resp.StatusCode)
	}
}

func TestListMasking(t *testing.T) {
	srv, _ := newWebPushTestServer(t, true)
	postResp := doRequest(t, http.MethodPost, srv.URL+"/api/push/subscriptions", "alice", map[string]string{
		"endpoint": "https://push.example.com/mask",
		"p256dh":   testP256DH,
		"auth":     testAuth,
	})
	if postResp.StatusCode != http.StatusCreated {
		t.Fatalf("预置订阅失败, 状态码 %d", postResp.StatusCode)
	}

	resp := doRequest(t, http.MethodGet, srv.URL+"/api/push/subscriptions", "alice", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("列出订阅期望 200, 实际 %d", resp.StatusCode)
	}
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("读取响应体失败: %v", err)
	}
	if strings.Contains(string(data), testP256DH) || strings.Contains(string(data), testAuth) {
		t.Fatalf("列表响应不应包含密钥原文, 实际 %s", string(data))
	}
	var list []struct {
		P256DHMasked string `json:"p256dhMasked"`
		AuthMasked   string `json:"authMasked"`
	}
	if err := json.Unmarshal(data, &list); err != nil {
		t.Fatalf("解析列表失败: %v, 原文 %s", err, string(data))
	}
	if len(list) != 1 {
		t.Fatalf("期望 1 条订阅, 实际 %d 条", len(list))
	}
	if list[0].P256DHMasked != "dGVz***" {
		t.Fatalf("p256dhMasked 期望 %q, 实际 %q", "dGVz***", list[0].P256DHMasked)
	}
	if list[0].AuthMasked != "dGVz***" {
		t.Fatalf("authMasked 期望 %q, 实际 %q", "dGVz***", list[0].AuthMasked)
	}
}
