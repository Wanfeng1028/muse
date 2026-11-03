package notify

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func decodeWecomPayload(t *testing.T, r *http.Request) wecomPayload {
	t.Helper()
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		t.Fatalf("读取请求体失败: %v", err)
	}
	var p wecomPayload
	if err := json.Unmarshal(raw, &p); err != nil {
		t.Fatalf("解析请求体失败: %v, 原始内容: %s", err, string(raw))
	}
	return p
}

func writeWecomOK(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"errcode":0,"errmsg":"ok"}`))
}

func TestWeComSendMarkdown_EmptyWebhookSkips(t *testing.T) {
	n := WeComNotifier{Config: WeComConfig{WebhookURL: ""}}
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
	if err != nil {
		t.Fatalf("空 webhook 应返回 nil，实际: %v", err)
	}

	n2 := WeComNotifier{Config: WeComConfig{WebhookURL: "", MentionAll: true}}
	err2 := n2.SendMarkdown("recovered", "api", "http://example.com", "2024-01-01 00:00:00", "")
	if err2 != nil {
		t.Fatalf("空 webhook 且 MentionAll 应返回 nil，实际: %v", err2)
	}
}

func TestWeComSendMarkdown_InvalidURL(t *testing.T) {
	cases := []struct {
		name string
		url  string
	}{
		{"缺少协议", "://bad-url"},
		{"控制字符", "http://exa\x7fmple.com"},
		{"纯空格", "   "},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			n := WeComNotifier{Config: WeComConfig{WebhookURL: tc.url}}
			start := time.Now()
			err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
			elapsed := time.Since(start)
			if err == nil {
				t.Fatalf("非法 URL %q 应返回错误", tc.url)
			}
			if !strings.Contains(err.Error(), "企业微信 Webhook 发送失败") {
				t.Fatalf("错误信息应包含包装前缀，实际: %v", err)
			}
			if elapsed > 20*time.Second {
				t.Fatalf("非法 URL 不应长时间阻塞，耗时: %v", elapsed)
			}
		})
	}
}

func TestWeComSendMarkdown_Success(t *testing.T) {
	var got wecomPayload
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		if r.Method != http.MethodPost {
			t.Errorf("期望 POST，实际: %s", r.Method)
		}
		if ct := r.Header.Get("Content-Type"); ct != "application/json" {
			t.Errorf("期望 Content-Type application/json，实际: %s", ct)
		}
		got = decodeWecomPayload(t, r)
		writeWecomOK(w)
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: true}}
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "connection refused")
	if err != nil {
		t.Fatalf("发送失败: %v", err)
	}
	if atomic.LoadInt32(&hit) != 1 {
		t.Fatalf("期望请求 1 次，实际: %d", hit)
	}
	if got.MsgType != "markdown" {
		t.Fatalf("msgtype 期望 markdown，实际: %s", got.MsgType)
	}
	if got.Markdown.MentionedList == nil {
		t.Fatalf("MentionAll 为 true 时 mentioned_list 不应为 nil")
	}
	if len(*got.Markdown.MentionedList) != 1 || (*got.Markdown.MentionedList)[0] != "@all" {
		t.Fatalf("mentioned_list 期望 [@all]，实际: %v", *got.Markdown.MentionedList)
	}
	body := got.Markdown.Content
	for _, want := range []string{"@all\n", "## 告警：api 宕机", "> 监控名称：api", "> 目标：http://example.com", "> 时间：2024-01-01 00:00:00", "> 错误信息：connection refused"} {
		if !strings.Contains(body, want) {
			t.Fatalf("正文缺少 %q，实际正文:\n%s", want, body)
		}
	}
}

func TestWeComSendMarkdown_RecoveredOmitsErrorAndMention(t *testing.T) {
	var got wecomPayload
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = decodeWecomPayload(t, r)
		writeWecomOK(w)
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: false}}
	err := n.SendMarkdown("recovered", "db", "10.0.0.1:3306", "2024-02-02 12:00:00", "should not appear")
	if err != nil {
		t.Fatalf("发送失败: %v", err)
	}
	if got.Markdown.MentionedList != nil {
		t.Fatalf("MentionAll 为 false 时 mentioned_list 应为 nil，实际: %v", *got.Markdown.MentionedList)
	}
	if strings.Contains(got.Markdown.Content, "should not appear") {
		t.Fatalf("recovered 事件不应包含错误信息，实际正文:\n%s", got.Markdown.Content)
	}
	if strings.Contains(got.Markdown.Content, "@all") {
		t.Fatalf("MentionAll 为 false 时正文不应含 @all，实际正文:\n%s", got.Markdown.Content)
	}
	if !strings.Contains(got.Markdown.Content, "## 恢复：db 已恢复") {
		t.Fatalf("正文缺少恢复标题，实际正文:\n%s", got.Markdown.Content)
	}
	if !strings.Contains(got.Markdown.Content, "> 目标：10.0.0.1:3306") {
		t.Fatalf("正文缺少目标行，实际正文:\n%s", got.Markdown.Content)
	}
}

func TestWeComSendMarkdown_OversizeTarget(t *testing.T) {
	var got wecomPayload
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = decodeWecomPayload(t, r)
		writeWecomOK(w)
	}))
	defer srv.Close()

	long := strings.Repeat("目标", 20000)
	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL}}
	err := n.SendMarkdown("down", "api", long, "2024-01-01 00:00:00", "e")
	if err != nil {
		t.Fatalf("超长目标发送失败: %v", err)
	}
	if !strings.Contains(got.Markdown.Content, "> 目标："+long) {
		t.Fatalf("正文未完整包含超长目标，正文长度: %d", len(got.Markdown.Content))
	}
	if got.MsgType != "markdown" {
		t.Fatalf("msgtype 期望 markdown，实际: %s", got.MsgType)
	}
}

func TestWeComSendMarkdown_Non2xxRetriesThenFails(t *testing.T) {
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("server exploded"))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL}}
	start := time.Now()
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
	elapsed := time.Since(start)
	if err == nil {
		t.Fatalf("非 2xx 应返回错误")
	}
	if !strings.Contains(err.Error(), "非 2xx 状态码: 500") {
		t.Fatalf("错误信息应包含状态码，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "server exploded") {
		t.Fatalf("错误信息应包含响应体，实际: %v", err)
	}
	if got := atomic.LoadInt32(&hit); got != 3 {
		t.Fatalf("期望重试 3 次，实际: %d", got)
	}
	if elapsed < 3*time.Second {
		t.Fatalf("重试退避应至少累计 3 秒，实际: %v", elapsed)
	}
}

func TestWeComSendMarkdown_ErrcodeRetriesThenFails(t *testing.T) {
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"errcode":93000,"errmsg":"invalid webhook url"}`))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL}}
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
	if err == nil {
		t.Fatalf("errcode 非 0 应返回错误")
	}
	if !strings.Contains(err.Error(), "errcode: 93000") {
		t.Fatalf("错误信息应包含 errcode，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "invalid webhook url") {
		t.Fatalf("错误信息应包含 errmsg，实际: %v", err)
	}
	if got := atomic.LoadInt32(&hit); got != 3 {
		t.Fatalf("期望重试 3 次，实际: %d", got)
	}
}

func TestWeComSendMarkdown_RetryThenSucceed(t *testing.T) {
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cur := atomic.AddInt32(&hit, 1)
		if cur < 3 {
			w.WriteHeader(http.StatusBadGateway)
			_, _ = w.Write([]byte("bad gateway"))
			return
		}
		writeWecomOK(w)
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL}}
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
	if err != nil {
		t.Fatalf("第三次应成功，实际: %v", err)
	}
	if got := atomic.LoadInt32(&hit); got != 3 {
		t.Fatalf("期望请求 3 次，实际: %d", got)
	}
}

func TestWeComSendMarkdown_MalformedJSONResponse(t *testing.T) {
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{not-json`))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL}}
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
	if err == nil {
		t.Fatalf("响应非法 JSON 应返回错误")
	}
	if !strings.Contains(err.Error(), "解析企业微信响应失败") {
		t.Fatalf("错误信息应包含解析失败前缀，实际: %v", err)
	}
	if got := atomic.LoadInt32(&hit); got != 3 {
		t.Fatalf("期望重试 3 次，实际: %d", got)
	}
}

func TestWeComSendMarkdown_ConnectionRefused(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		writeWecomOK(w)
	}))
	url := srv.URL
	srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: url}}
	start := time.Now()
	err := n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
	elapsed := time.Since(start)
	if err == nil {
		t.Fatalf("连接被拒绝应返回错误")
	}
	if !strings.Contains(err.Error(), "企业微信 Webhook 发送失败") {
		t.Fatalf("错误信息应包含包装前缀，实际: %v", err)
	}
	if elapsed < 3*time.Second {
		t.Fatalf("重试退避应至少累计 3 秒，实际: %v", elapsed)
	}
}

func TestWeComSendMarkdown_ConcurrentIdempotent(t *testing.T) {
	var hit int32
	var bodies []string
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		p := decodeWecomPayload(t, r)
		mu.Lock()
		bodies = append(bodies, p.Markdown.Content)
		mu.Unlock()
		writeWecomOK(w)
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: true}}

	const goroutines = 20
	var wg sync.WaitGroup
	errs := make([]error, goroutines)
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func(idx int) {
			defer wg.Done()
			errs[idx] = n.SendMarkdown("down", "api", "http://example.com", "2024-01-01 00:00:00", "boom")
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("第 %d 个 goroutine 发送失败: %v", i, err)
		}
	}
	if got := atomic.LoadInt32(&hit); got != goroutines {
		t.Fatalf("期望请求 %d 次，实际: %d", goroutines, got)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(bodies) != goroutines {
		t.Fatalf("期望记录 %d 条正文，实际: %d", goroutines, len(bodies))
	}
	for i, b := range bodies {
		if !strings.Contains(b, "## 告警：api 宕机") {
			t.Fatalf("第 %d 条正文缺少标题，实际:\n%s", i, b)
		}
		if !strings.Contains(b, "> 错误信息：boom") {
			t.Fatalf("第 %d 条正文缺少错误信息，实际:\n%s", i, b)
		}
	}
}

func TestWeComSendMarkdown_EmptyFieldsStillValidPayload(t *testing.T) {
	var got wecomPayload
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = decodeWecomPayload(t, r)
		writeWecomOK(w)
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL}}
	err := n.SendMarkdown("down", "", "", "", "")
	if err != nil {
		t.Fatalf("空字段发送失败: %v", err)
	}
	if got.MsgType != "markdown" {
		t.Fatalf("msgtype 期望 markdown，实际: %s", got.MsgType)
	}
	body := got.Markdown.Content
	if !strings.Contains(body, "## 告警： 宕机") {
		t.Fatalf("空 name 标题格式不符，实际正文:\n%s", body)
	}
	if !strings.Contains(body, "> 监控名称：\n") {
		t.Fatalf("空 name 行缺失，实际正文:\n%s", body)
	}
	if strings.Contains(body, "> 错误信息") {
		t.Fatalf("空 errMsg 不应出现错误信息行，实际正文:\n%s", body)
	}
	if got.Markdown.MentionedList != nil {
		t.Fatalf("MentionAll 为 false 时 mentioned_list 应为 nil")
	}
	_ = fmt.Sprintf("%v", got)
}