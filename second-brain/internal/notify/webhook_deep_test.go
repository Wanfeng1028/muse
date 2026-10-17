package notify

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func decodePayload(t *testing.T, body []byte) webhookPayload {
	t.Helper()
	var p webhookPayload
	if err := json.Unmarshal(body, &p); err != nil {
		t.Fatalf("解析 webhook 负载失败: %v", err)
	}
	return p
}

func TestWebhookSenderSendSignatureAndPayload(t *testing.T) {
	const secret = "s3cr3t-key"
	cases := []struct {
		name       string
		secret     string
		wantSig    bool
		wantEvent  string
		wantDue    int
		wantTitles []string
	}{
		{
			name:       "带密钥的单个条目",
			secret:     secret,
			wantSig:    true,
			wantEvent:  "review.digest",
			wantDue:    1,
			wantTitles: []string{"复习卡片A"},
		},
		{
			name:       "无密钥时不带签名头",
			secret:     "",
			wantSig:    false,
			wantEvent:  "review.digest",
			wantDue:    2,
			wantTitles: []string{"甲", "乙"},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var gotBody []byte
			var gotSig string
			var gotContentType string
			var gotEvent string
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				gotBody, _ = io.ReadAll(r.Body)
				gotSig = r.Header.Get("X-Signature")
				gotContentType = r.Header.Get("Content-Type")
				gotEvent = r.Header.Get("X-Event")
				w.WriteHeader(http.StatusOK)
			}))
			defer ts.Close()

			items := make([]DigestItem, 0, len(tc.wantTitles))
			for _, title := range tc.wantTitles {
				items = append(items, DigestItem{Title: title})
			}
			sender := NewWebhookSender(ts.URL, tc.secret, 5*time.Second)
			err := sender.Send(context.Background(), Message{
				Subject:  "今日复习",
				TextBody: "纯文本正文",
				HTMLBody: "<p>富文本正文</p>",
				DueCount: tc.wantDue,
				Items:    items,
			})
			if err != nil {
				t.Fatalf("Send 返回错误: %v", err)
			}
			if gotContentType != "application/json" {
				t.Fatalf("Content-Type = %q, 期望 application/json", gotContentType)
			}
			if gotEvent != tc.wantEvent {
				t.Fatalf("X-Event = %q, 期望 %q", gotEvent, tc.wantEvent)
			}

			if tc.wantSig {
				mac := hmac.New(sha256.New, []byte(tc.secret))
				mac.Write(gotBody)
				want := "sha256=" + hex.EncodeToString(mac.Sum(nil))
				if gotSig != want {
					t.Fatalf("X-Signature = %q, 期望 %q", gotSig, want)
				}
			} else if gotSig != "" {
				t.Fatalf("无密钥时 X-Signature 应为空, 实际 %q", gotSig)
			}

			p := decodePayload(t, gotBody)
			if p.Event != tc.wantEvent {
				t.Fatalf("payload.Event = %q, 期望 %q", p.Event, tc.wantEvent)
			}
			if p.Subject != "今日复习" || p.Text != "纯文本正文" || p.HTML != "<p>富文本正文</p>" {
				t.Fatalf("payload 文本字段不匹配: %+v", p)
			}
			if p.DueCount != tc.wantDue {
				t.Fatalf("payload.DueCount = %d, 期望 %d", p.DueCount, tc.wantDue)
			}
			if len(p.Items) != len(tc.wantTitles) {
				t.Fatalf("payload.Items 长度 = %d, 期望 %d", len(p.Items), len(tc.wantTitles))
			}
			for i, want := range tc.wantTitles {
				if p.Items[i].Title != want {
					t.Fatalf("payload.Items[%d].Title = %q, 期望 %q", i, p.Items[i].Title, want)
				}
			}
		})
	}
}

func TestWebhookSenderSendOverdueDaysRoundTrip(t *testing.T) {
	var gotBody []byte
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	sender := NewWebhookSender(ts.URL, "k", time.Second)
	err := sender.Send(context.Background(), Message{
		Subject:  "逾期提醒",
		DueCount: 3,
		Items: []DigestItem{
			{Title: "昨天到期", Snippet: "内容1", Tags: []string{"工作", "紧急"}, DueDate: "2024-02-28", OverdueDays: 1},
			{Title: "闰日到期", Snippet: "内容2", Tags: []string{"个人"}, DueDate: "2024-02-29", OverdueDays: 2},
			{Title: "很久之前", Snippet: "内容3", Tags: []string{}, DueDate: "2023-01-01", OverdueDays: 424},
		},
	})
	if err != nil {
		t.Fatalf("Send 返回错误: %v", err)
	}

	p := decodePayload(t, gotBody)
	if len(p.Items) != 3 {
		t.Fatalf("payload.Items 长度 = %d, 期望 3", len(p.Items))
	}
	if p.Items[0].DueDate != "2024-02-28" || p.Items[0].OverdueDays != 1 {
		t.Fatalf("第一条不匹配: %+v", p.Items[0])
	}
	if p.Items[1].DueDate != "2024-02-29" || p.Items[1].OverdueDays != 2 {
		t.Fatalf("闰日条目不匹配: %+v", p.Items[1])
	}
	if p.Items[2].OverdueDays != 424 {
		t.Fatalf("payload.Items[2].OverdueDays = %d, 期望 424", p.Items[2].OverdueDays)
	}
	if len(p.Items[2].Tags) != 0 {
		t.Fatalf("payload.Items[2].Tags 长度 = %d, 期望 0", len(p.Items[2].Tags))
	}
}

func TestWebhookSenderSendNon2xxError(t *testing.T) {
	cases := []struct {
		name      string
		status    int
		bodyText  string
		wantInMsg string
	}{
		{name: "500 服务端错误", status: http.StatusInternalServerError, bodyText: "内部爆炸", wantInMsg: "内部爆炸"},
		{name: "429 限流", status: http.StatusTooManyRequests, bodyText: "慢点", wantInMsg: "慢点"},
		{name: "401 未授权", status: http.StatusUnauthorized, bodyText: "bad token", wantInMsg: "bad token"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(tc.bodyText))
			}))
			defer ts.Close()

			sender := NewWebhookSender(ts.URL, "", time.Second)
			err := sender.Send(context.Background(), Message{Subject: "s"})
			if err == nil {
				t.Fatalf("期望非 2xx 返回错误, 实际 nil")
			}
			msg := err.Error()
			if !strings.Contains(msg, "webhook 返回非 2xx 状态") {
				t.Fatalf("错误信息缺少状态描述: %q", msg)
			}
			if !strings.Contains(msg, tc.wantInMsg) {
				t.Fatalf("错误信息缺少响应体片段 %q, 实际 %q", tc.wantInMsg, msg)
			}
		})
	}
}

func TestWebhookSenderSendTruncatesLongErrorBody(t *testing.T) {
	longBody := strings.Repeat("x", 500)
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(longBody))
	}))
	defer ts.Close()

	sender := NewWebhookSender(ts.URL, "", time.Second)
	err := sender.Send(context.Background(), Message{Subject: "s"})
	if err == nil {
		t.Fatalf("期望错误, 实际 nil")
	}
	msg := err.Error()
	idx := strings.LastIndex(msg, ": ")
	if idx < 0 {
		t.Fatalf("错误信息格式异常: %q", msg)
	}
	snippet := msg[idx+2:]
	if len(snippet) != 200 {
		t.Fatalf("错误响应体片段长度 = %d, 期望 200", len(snippet))
	}
	if strings.TrimSpace(snippet) != snippet {
		t.Fatalf("错误响应体片段未去除空白: %q", snippet)
	}
}

func TestWebhookSenderSendContextCanceled(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(500 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	sender := NewWebhookSender(ts.URL, "", 5*time.Second)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := sender.Send(ctx, Message{Subject: "s"})
	if err == nil {
		t.Fatalf("已取消的 context 期望返回错误, 实际 nil")
	}
	if !strings.Contains(err.Error(), "webhook 请求失败") {
		t.Fatalf("错误信息缺少请求失败描述: %q", err.Error())
	}
}

func TestWebhookSenderSendTimeout(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(300 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	sender := NewWebhookSender(ts.URL, "", 50*time.Millisecond)
	start := time.Now()
	err := sender.Send(context.Background(), Message{Subject: "s"})
	elapsed := time.Since(start)
	if err == nil {
		t.Fatalf("超时场景期望返回错误, 实际 nil")
	}
	if elapsed > 250*time.Millisecond {
		t.Fatalf("超时耗时 %v, 说明没有按 50ms 生效", elapsed)
	}
	if !strings.Contains(err.Error(), "webhook 请求失败") {
		t.Fatalf("错误信息缺少请求失败描述: %q", err.Error())
	}
}

func TestNewWebhookSenderDefaultTimeout(t *testing.T) {
	cases := []struct {
		name        string
		in          time.Duration
		wantTimeout time.Duration
	}{
		{name: "零值使用默认", in: 0, wantTimeout: webhookDefaultTimeout},
		{name: "负值使用默认", in: -3 * time.Second, wantTimeout: webhookDefaultTimeout},
		{name: "正值保持原样", in: 7 * time.Second, wantTimeout: 7 * time.Second},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := NewWebhookSender("http://example.invalid", "sec", tc.in)
			if s.timeout != tc.wantTimeout {
				t.Fatalf("timeout = %v, 期望 %v", s.timeout, tc.wantTimeout)
			}
			if s.client == nil {
				t.Fatalf("client 不应为 nil")
			}
			if s.client.Timeout != tc.wantTimeout {
				t.Fatalf("client.Timeout = %v, 期望 %v", s.client.Timeout, tc.wantTimeout)
			}
			if s.Name() != "webhook" {
				t.Fatalf("Name() = %q, 期望 webhook", s.Name())
			}
		})
	}
}

func TestWebhookSenderSendDateIsToday(t *testing.T) {
	var gotBody []byte
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	sender := NewWebhookSender(ts.URL, "", time.Second)
	err := sender.Send(context.Background(), Message{Subject: "s", DueCount: 0})
	if err != nil {
		t.Fatalf("Send 返回错误: %v", err)
	}

	p := decodePayload(t, gotBody)
	want := time.Now().Format("2006-01-02")
	if p.Date != want {
		t.Fatalf("payload.Date = %q, 期望 %q", p.Date, want)
	}
	if _, err := time.Parse("2006-01-02", p.Date); err != nil {
		t.Fatalf("payload.Date 不是合法日期: %v", err)
	}
}

func TestWebhookSenderSendTagsAreIndependent(t *testing.T) {
	var gotBody []byte
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	tagsA := []string{"[[双链]]", "中文标题"}
	tagsB := []string{"a", "b", "c"}
	sender := NewWebhookSender(ts.URL, "", time.Second)
	err := sender.Send(context.Background(), Message{
		Subject: "s",
		Items: []DigestItem{
			{Title: "第一条", Tags: tagsA},
			{Title: "第二条", Tags: tagsB},
		},
	})
	if err != nil {
		t.Fatalf("Send 返回错误: %v", err)
	}

	p := decodePayload(t, gotBody)
	if len(p.Items) != 2 {
		t.Fatalf("payload.Items 长度 = %d, 期望 2", len(p.Items))
	}
	if len(p.Items[0].Tags) != 2 || p.Items[0].Tags[0] != "[[双链]]" || p.Items[0].Tags[1] != "中文标题" {
		t.Fatalf("第一条 Tags 不匹配: %+v", p.Items[0].Tags)
	}
	if len(p.Items[1].Tags) != 3 {
		t.Fatalf("第二条 Tags 长度 = %d, 期望 3", len(p.Items[1].Tags))
	}
	if strings.Join(p.Items[1].Tags, ",") != "a,b,c" {
		t.Fatalf("第二条 Tags = %v, 期望 [a b c]", p.Items[1].Tags)
	}
}

func TestWebhookSenderSendJSONEscaping(t *testing.T) {
	var gotBody []byte
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	tricky := "标题\"引号\\反斜杠\n换行\t制表"
	sender := NewWebhookSender(ts.URL, "", time.Second)
	err := sender.Send(context.Background(), Message{
		Subject: tricky,
		Items:   []DigestItem{{Title: tricky, Snippet: tricky}},
	})
	if err != nil {
		t.Fatalf("Send 返回错误: %v", err)
	}

	p := decodePayload(t, gotBody)
	if p.Subject != tricky {
		t.Fatalf("payload.Subject = %q, 期望 %q", p.Subject, tricky)
	}
	if p.Items[0].Title != tricky {
		t.Fatalf("payload.Items[0].Title = %q, 期望 %q", p.Items[0].Title, tricky)
	}
	if p.Items[0].Snippet != tricky {
		t.Fatalf("payload.Items[0].Snippet = %q, 期望 %q", p.Items[0].Snippet, tricky)
	}
}

func TestWebhookSenderSendEmptyItems(t *testing.T) {
	var gotBody []byte
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	sender := NewWebhookSender(ts.URL, "", time.Second)
	err := sender.Send(context.Background(), Message{Subject: "空", DueCount: 0})
	if err != nil {
		t.Fatalf("Send 返回错误: %v", err)
	}

	p := decodePayload(t, gotBody)
	if p.Items == nil {
		t.Fatalf("payload.Items 不应为 nil, 应为空数组")
	}
	if len(p.Items) != 0 {
		t.Fatalf("payload.Items 长度 = %d, 期望 0", len(p.Items))
	}
	if p.DueCount != 0 {
		t.Fatalf("payload.DueCount = %d, 期望 0", p.DueCount)
	}
}
