package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newDeepTestStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	t.Cleanup(func() { st.Close() })
	return st
}

func deepTestConfig(vapid bool) config.Config {
	cfg := config.Config{}
	if vapid {
		cfg.Push.VAPIDPublicKey = "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8"
		cfg.Push.VAPIDPrivateKey = "UUxI4O8-FbRouAevSmBQ6o18hgE4nSG3qwvJTfKc-ls"
		cfg.Push.VAPIDSubject = "mailto:test@example.com"
	}
	return cfg
}

func deepPostJSON(t *testing.T, h http.Handler, user string, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/api/push/subscriptions", bytes.NewBufferString(body))
	req.Header.Set("X-User", user)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func deepDo(t *testing.T, h http.Handler, method, target, user, body string) *httptest.ResponseRecorder {
	t.Helper()
	var reader *bytes.Buffer
	if body == "" {
		reader = bytes.NewBuffer(nil)
	} else {
		reader = bytes.NewBufferString(body)
	}
	req := httptest.NewRequest(method, target, reader)
	req.Header.Set("X-User", user)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestMaskKeyDeepBoundary(t *testing.T) {
	cases := []struct {
		name     string
		input    string
		expected string
	}{
		{"空串返回空串", "", ""},
		{"单字节返回三星", "a", "***"},
		{"四字节返回三星", "abcd", "***"},
		{"五字节保留前四", "abcde", "abcd***"},
		{"中文四字返回三星", "晚风测试", "***"},
		{"中文五字保留前四", "晚风测试晚", "晚风测试***"},
		{"中英混合五字符", "晚风ab", "***"},
		{"含代理对表情五 rune", "晚风🙂ab", "晚风🙂a***"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := maskKey(tc.input)
			if got != tc.expected {
				t.Fatalf("maskKey(%q) = %q, 期望 %q", tc.input, got, tc.expected)
			}
			if tc.input != "" && len([]rune(got)) < 3 {
				t.Fatalf("脱敏结果长度异常: %q", got)
			}
		})
	}
}

func TestToSubscriptionViewMasksSecretsDeep(t *testing.T) {
	sub := store.PushSubscription{
		ID:        42,
		Endpoint:  "https://push.example.com/sub/晚风",
		CreatedAt: "2024-02-29T23:59:59Z",
		P256DH:    "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFg",
		Auth:      "abcd",
	}
	view := toSubscriptionView(sub)
	if view.ID != 42 {
		t.Fatalf("ID = %d, 期望 42", view.ID)
	}
	if view.Endpoint != sub.Endpoint {
		t.Fatalf("Endpoint = %q, 期望 %q", view.Endpoint, sub.Endpoint)
	}
	if view.CreatedAt != "2024-02-29T23:59:59Z" {
		t.Fatalf("CreatedAt = %q, 期望 2024-02-29T23:59:59Z", view.CreatedAt)
	}
	if view.P256dhMasked != "BEl6***" {
		t.Fatalf("P256dhMasked = %q, 期望 BEl6***", view.P256dhMasked)
	}
	if view.AuthMasked != "***" {
		t.Fatalf("AuthMasked = %q, 期望 ***", view.AuthMasked)
	}
}

func TestPostSubscriptionMethodAndVAPIDDeep(t *testing.T) {
	st := newDeepTestStore(t)
	h := handlePostPushSubscription(st, deepTestConfig(true))

	rec := deepDo(t, h, http.MethodGet, "/api/push/subscriptions", "u1", "")
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("GET 状态码 = %d, 期望 405", rec.Code)
	}
	var errBody map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody["error"] != "方法不被允许" {
		t.Fatalf("错误信息 = %q, 期望 方法不被允许", errBody["error"])
	}

	noVapid := handlePostPushSubscription(st, deepTestConfig(false))
	rec2 := deepPostJSON(t, noVapid, "u1", `{"endpoint":"https://push.example.com/a","p256dh":"BEl6abcdefgh","auth":"auth1234"}`)
	if rec2.Code != http.StatusServiceUnavailable {
		t.Fatalf("未配置 VAPID 状态码 = %d, 期望 503", rec2.Code)
	}
	var errBody2 map[string]string
	if err := json.Unmarshal(rec2.Body.Bytes(), &errBody2); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody2["error"] != "浏览器推送未启用：服务器未配置 VAPID 密钥" {
		t.Fatalf("错误信息 = %q", errBody2["error"])
	}
}

func TestPostSubscriptionInvalidJSONAndMissingFieldsDeep(t *testing.T) {
	st := newDeepTestStore(t)
	h := handlePostPushSubscription(st, deepTestConfig(true))

	rec := deepPostJSON(t, h, "u1", `{"endpoint":`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法 JSON 状态码 = %d, 期望 400", rec.Code)
	}
	var errBody map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody["error"] != "请求体不是合法 JSON" {
		t.Fatalf("错误信息 = %q", errBody["error"])
	}

	rec2 := deepPostJSON(t, h, "u1", `{"endpoint":"","p256dh":"","auth":""}`)
	if rec2.Code != http.StatusBadRequest {
		t.Fatalf("空字段状态码 = %d, 期望 400", rec2.Code)
	}
	var errBody2 map[string]string
	if err := json.Unmarshal(rec2.Body.Bytes(), &errBody2); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody2["error"] == "" {
		t.Fatalf("空字段应返回中文错误信息, 实际为空")
	}
}

func TestPostSubscriptionUpsertAndMaskDeep(t *testing.T) {
	st := newDeepTestStore(t)
	h := handlePostPushSubscription(st, deepTestConfig(true))

	body := `{"endpoint":"https://push.example.com/晚风/订阅","p256dh":"BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFg","auth":"auth1234"}`
	rec := deepPostJSON(t, h, "user-a", body)
	if rec.Code != http.StatusCreated {
		t.Fatalf("首次创建状态码 = %d, 期望 201, body=%s", rec.Code, rec.Body.String())
	}
	var view subscriptionView
	if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
		t.Fatalf("解析订阅视图失败: %v", err)
	}
	if view.ID <= 0 {
		t.Fatalf("首次创建 ID = %d, 期望 > 0", view.ID)
	}
	if view.Endpoint != "https://push.example.com/晚风/订阅" {
		t.Fatalf("Endpoint = %q", view.Endpoint)
	}
	if view.P256dhMasked != "BEl6***" {
		t.Fatalf("P256dhMasked = %q, 期望 BEl6***", view.P256dhMasked)
	}
	if view.AuthMasked != "auth***" {
		t.Fatalf("AuthMasked = %q, 期望 auth***", view.AuthMasked)
	}

	rec2 := deepPostJSON(t, h, "user-a", body)
	if rec2.Code != http.StatusCreated {
		t.Fatalf("重复提交状态码 = %d, 期望 201", rec2.Code)
	}
	var view2 subscriptionView
	if err := json.Unmarshal(rec2.Body.Bytes(), &view2); err != nil {
		t.Fatalf("解析订阅视图失败: %v", err)
	}
	if view2.ID != view.ID {
		t.Fatalf("重复提交 ID = %d, 期望 %d", view2.ID, view.ID)
	}
	if view2.CreatedAt != view.CreatedAt {
		t.Fatalf("重复提交 CreatedAt = %q, 期望 %q", view2.CreatedAt, view.CreatedAt)
	}
}

func TestDeleteSubscriptionViaBodyAndQueryDeep(t *testing.T) {
	st := newDeepTestStore(t)
	cfg := deepTestConfig(true)
	post := handlePostPushSubscription(st, cfg)
	del := handleDeletePushSubscription(st, cfg)

	body := `{"endpoint":"https://push.example.com/del/晚风","p256dh":"BEl6abcdefghij","auth":"auth5678"}`
	if rec := deepPostJSON(t, post, "u-del", body); rec.Code != http.StatusCreated {
		t.Fatalf("准备订阅失败: %d %s", rec.Code, rec.Body.String())
	}

	rec := deepDo(t, del, http.MethodDelete, "/api/push/subscriptions", "u-del", body)
	if rec.Code != http.StatusOK {
		t.Fatalf("body 删除状态码 = %d, 期望 200, body=%s", rec.Code, rec.Body.String())
	}
	var ok map[string]bool
	if err := json.Unmarshal(rec.Body.Bytes(), &ok); err != nil {
		t.Fatalf("解析删除结果失败: %v", err)
	}
	if !ok["deleted"] {
		t.Fatalf("deleted = false, 期望 true")
	}

	if rec := deepPostJSON(t, post, "u-del", body); rec.Code != http.StatusCreated {
		t.Fatalf("重新准备订阅失败: %d", rec.Code)
	}
	target := "/api/push/subscriptions?endpoint=" + "https%3A%2F%2Fpush.example.com%2Fdel%2F%E6%99%9A%E9%A3%8E"
	rec2 := deepDo(t, del, http.MethodDelete, target, "u-del", "")
	if rec2.Code != http.StatusOK {
		t.Fatalf("query 删除状态码 = %d, 期望 200", rec2.Code)
	}
	var ok2 map[string]bool
	if err := json.Unmarshal(rec2.Body.Bytes(), &ok2); err != nil {
		t.Fatalf("解析删除结果失败: %v", err)
	}
	if !ok2["deleted"] {
		t.Fatalf("query deleted = false, 期望 true")
	}

	rec3 := deepDo(t, del, http.MethodDelete, "/api/push/subscriptions", "u-del", "")
	if rec3.Code != http.StatusBadRequest {
		t.Fatalf("缺少 endpoint 状态码 = %d, 期望 400", rec3.Code)
	}
	var errBody map[string]string
	if err := json.Unmarshal(rec3.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody["error"] != "缺少 endpoint 参数" {
		t.Fatalf("错误信息 = %q", errBody["error"])
	}
}

func TestDeleteSubscriptionMethodAndVAPIDDeep(t *testing.T) {
	st := newDeepTestStore(t)
	del := handleDeletePushSubscription(st, deepTestConfig(true))
	rec := deepDo(t, del, http.MethodPost, "/api/push/subscriptions", "u1", `{"endpoint":"https://push.example.com/a"}`)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("POST 状态码 = %d, 期望 405", rec.Code)
	}
	var errBody map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody["error"] != "方法不被允许" {
		t.Fatalf("错误信息 = %q", errBody["error"])
	}

	noVapid := handleDeletePushSubscription(st, deepTestConfig(false))
	rec2 := deepDo(t, noVapid, http.MethodDelete, "/api/push/subscriptions", "u1", `{"endpoint":"https://push.example.com/a"}`)
	if rec2.Code != http.StatusServiceUnavailable {
		t.Fatalf("未配置 VAPID 状态码 = %d, 期望 503", rec2.Code)
	}
	var errBody2 map[string]string
	if err := json.Unmarshal(rec2.Body.Bytes(), &errBody2); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody2["error"] != "浏览器推送未启用：服务器未配置 VAPID 密钥" {
		t.Fatalf("错误信息 = %q", errBody2["error"])
	}
}

func TestListSubscriptionsMultiUserIsolationDeep(t *testing.T) {
	st := newDeepTestStore(t)
	cfg := deepTestConfig(true)
	post := handlePostPushSubscription(st, cfg)
	list := handleListPushSubscriptions(st, cfg)

	a1 := `{"endpoint":"https://push.example.com/ua/1","p256dh":"BEl6aaaa1111","auth":"authaaaa"}`
	a2 := `{"endpoint":"https://push.example.com/ua/2","p256dh":"BEl6bbbb2222","auth":"authbbbb"}`
	b1 := `{"endpoint":"https://push.example.com/ub/1","p256dh":"BEl6cccc3333","auth":"authcccc"}`

	for _, b := range []string{a1, a2, b1} {
		user := "user-a"
		if b == b1 {
			user = "user-b"
		}
		if rec := deepPostJSON(t, post, user, b); rec.Code != http.StatusCreated {
			t.Fatalf("准备订阅失败 user=%s: %d %s", user, rec.Code, rec.Body.String())
		}
	}

	rec := deepDo(t, list, http.MethodGet, "/api/push/subscriptions", "user-a", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("user-a 列表状态码 = %d, 期望 200", rec.Code)
	}
	var viewsA []subscriptionView
	if err := json.Unmarshal(rec.Body.Bytes(), &viewsA); err != nil {
		t.Fatalf("解析 user-a 列表失败: %v", err)
	}
	if len(viewsA) != 2 {
		t.Fatalf("user-a 订阅数 = %d, 期望 2", len(viewsA))
	}
	for _, v := range viewsA {
		if v.Endpoint != a1[15:len(a1)-40] && v.Endpoint != "https://push.example.com/ua/1" && v.Endpoint != "https://push.example.com/ua/2" {
			if v.Endpoint != "https://push.example.com/ua/1" && v.Endpoint != "https://push.example.com/ua/2" {
				t.Fatalf("user-a 出现非本人 endpoint: %q", v.Endpoint)
			}
		}
		if v.P256dhMasked == "" || v.AuthMasked == "" {
			t.Fatalf("user-a 脱敏字段为空: %+v", v)
		}
	}

	rec2 := deepDo(t, list, http.MethodGet, "/api/push/subscriptions", "user-b", "")
	if rec2.Code != http.StatusOK {
		t.Fatalf("user-b 列表状态码 = %d, 期望 200", rec2.Code)
	}
	var viewsB []subscriptionView
	if err := json.Unmarshal(rec2.Body.Bytes(), &viewsB); err != nil {
		t.Fatalf("解析 user-b 列表失败: %v", err)
	}
	if len(viewsB) != 1 {
		t.Fatalf("user-b 订阅数 = %d, 期望 1", len(viewsB))
	}
	if viewsB[0].Endpoint != "https://push.example.com/ub/1" {
		t.Fatalf("user-b endpoint = %q, 期望 https://push.example.com/ub/1", viewsB[0].Endpoint)
	}
}

func TestListSubscriptionsMethodAndVAPIDDeep(t *testing.T) {
	st := newDeepTestStore(t)
	list := handleListPushSubscriptions(st, deepTestConfig(true))
	rec := deepDo(t, list, http.MethodPost, "/api/push/subscriptions", "u1", "")
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("POST 状态码 = %d, 期望 405", rec.Code)
	}
	var errBody map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody["error"] != "方法不被允许" {
		t.Fatalf("错误信息 = %q", errBody["error"])
	}

	noVapid := handleListPushSubscriptions(st, deepTestConfig(false))
	rec2 := deepDo(t, noVapid, http.MethodGet, "/api/push/subscriptions", "u1", "")
	if rec2.Code != http.StatusServiceUnavailable {
		t.Fatalf("未配置 VAPID 状态码 = %d, 期望 503", rec2.Code)
	}
	var errBody2 map[string]string
	if err := json.Unmarshal(rec2.Body.Bytes(), &errBody2); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody2["error"] != "浏览器推送未启用：服务器未配置 VAPID 密钥" {
		t.Fatalf("错误信息 = %q", errBody2["error"])
	}
}

func TestGetVAPIDPublicKeyDeep(t *testing.T) {
	cfg := deepTestConfig(true)
	h := handleGetVAPIDPublicKey(cfg)

	rec := deepDo(t, h, http.MethodGet, "/api/push/vapid-public-key", "u1", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("状态码 = %d, 期望 200", rec.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if body["publicKey"] != cfg.Push.VAPIDPublicKey {
		t.Fatalf("publicKey = %q, 期望 %q", body["publicKey"], cfg.Push.VAPIDPublicKey)
	}
	if body["publicKey"] == "" {
		t.Fatalf("publicKey 不应为空")
	}

	rec2 := deepDo(t, h, http.MethodPost, "/api/push/vapid-public-key", "u1", "")
	if rec2.Code != http.StatusMethodNotAllowed {
		t.Fatalf("POST 状态码 = %d, 期望 405", rec2.Code)
	}
	var errBody map[string]string
	if err := json.Unmarshal(rec2.Body.Bytes(), &errBody); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody["error"] != "方法不被允许" {
		t.Fatalf("错误信息 = %q", errBody["error"])
	}

	noVapid := handleGetVAPIDPublicKey(deepTestConfig(false))
	rec3 := deepDo(t, noVapid, http.MethodGet, "/api/push/vapid-public-key", "u1", "")
	if rec3.Code != http.StatusServiceUnavailable {
		t.Fatalf("未配置 VAPID 状态码 = %d, 期望 503", rec3.Code)
	}
	var errBody3 map[string]string
	if err := json.Unmarshal(rec3.Body.Bytes(), &errBody3); err != nil {
		t.Fatalf("解析错误体失败: %v", err)
	}
	if errBody3["error"] != "浏览器推送未启用：服务器未配置 VAPID 密钥" {
		t.Fatalf("错误信息 = %q", errBody3["error"])
	}
}

func TestRegisterPushSubscriptionRoutesDeep(t *testing.T) {
	st := newDeepTestStore(t)
	cfg := deepTestConfig(true)
	mux := http.NewServeMux()
	RegisterPushSubscriptionRoutes(mux, st, cfg)

	rec := deepDo(t, mux, http.MethodGet, "/api/push/vapid-public-key", "u1", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("注册路由 GET vapid 状态码 = %d, 期望 200", rec.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if body["publicKey"] != cfg.Push.VAPIDPublicKey {
		t.Fatalf("publicKey = %q, 期望 %q", body["publicKey"], cfg.Push.VAPIDPublicKey)
	}

	rec2 := deepPostJSON(t, mux, "u1", `{"endpoint":"https://push.example.com/reg/晚风","p256dh":"BEl6abcdefghij","auth":"auth9999"}`)
	if rec2.Code != http.StatusCreated {
		t.Fatalf("注册路由 POST 状态码 = %d, 期望 201, body=%s", rec2.Code, rec2.Body.String())
	}
	var view subscriptionView
	if err := json.Unmarshal(rec2.Body.Bytes(), &view); err != nil {
		t.Fatalf("解析订阅视图失败: %v", err)
	}
	if view.ID <= 0 {
		t.Fatalf("注册路由返回 ID = %d, 期望 > 0", view.ID)
	}
	if view.P256dhMasked != "BEl6***" {
		t.Fatalf("P256dhMasked = %q, 期望 BEl6***", view.P256dhMasked)
	}

	rec3 := deepDo(t, mux, http.MethodGet, "/api/push/subscriptions", "u1", "")
	if rec3.Code != http.StatusOK {
		t.Fatalf("注册路由 GET 列表状态码 = %d, 期望 200", rec3.Code)
	}
	var views []subscriptionView
	if err := json.Unmarshal(rec3.Body.Bytes(), &views); err != nil {
		t.Fatalf("解析列表失败: %v", err)
	}
	if len(views) != 1 {
		t.Fatalf("注册路由列表长度 = %d, 期望 1", len(views))
	}
	if views[0].Endpoint != "https://push.example.com/reg/晚风" {
		t.Fatalf("列表 endpoint = %q", views[0].Endpoint)
	}
}
