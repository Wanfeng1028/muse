package notify

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestNewWebPushSender_TrimAndDefaults(t *testing.T) {
	tests := []struct {
		name        string
		publicKey   string
		privateKey  string
		subject     string
		timeout     time.Duration
		wantErr     bool
		errContains string
		wantTimeout time.Duration
	}{
		{
			name:       "正常参数全部保留",
			publicKey:  "pub-key",
			privateKey: "priv-key",
			subject:    "mailto:a@b.com",
			timeout:    5 * time.Second,
			wantErr:    false,
		},
		{
			name:        "公钥前后空白 trim 后为空报错",
			publicKey:   "   ",
			privateKey:  "priv-key",
			subject:     "mailto:a@b.com",
			timeout:     5 * time.Second,
			wantErr:     true,
			errContains: "VAPID 公钥不能为空",
		},
		{
			name:        "私钥前后空白 trim 后为空报错",
			publicKey:   "pub-key",
			privateKey:  "\t\n",
			subject:     "mailto:a@b.com",
			timeout:     5 * time.Second,
			wantErr:     true,
			errContains: "VAPID 私钥不能为空",
		},
		{
			name:        "主题前后空白 trim 后为空报错",
			publicKey:   "pub-key",
			privateKey:  "priv-key",
			subject:     "  \n\t ",
			timeout:     5 * time.Second,
			wantErr:     true,
			errContains: "VAPID 主题不能为空",
		},
		{
			name:        "timeout 为 0 时使用默认 10 秒",
			publicKey:   "pub-key",
			privateKey:  "priv-key",
			subject:     "mailto:a@b.com",
			timeout:     0,
			wantErr:     false,
			wantTimeout: 10 * time.Second,
		},
		{
			name:        "timeout 为负数时使用默认 10 秒",
			publicKey:   "pub-key",
			privateKey:  "priv-key",
			subject:     "mailto:a@b.com",
			timeout:     -3 * time.Second,
			wantErr:     false,
			wantTimeout: 10 * time.Second,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sender, err := NewWebPushSender(tt.publicKey, tt.privateKey, tt.subject, tt.timeout)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("期望返回错误，实际为 nil")
				}
				if !strings.Contains(err.Error(), tt.errContains) {
					t.Fatalf("错误信息 = %q，期望包含 %q", err.Error(), tt.errContains)
				}
				if sender != nil {
					t.Fatalf("出错时应返回 nil sender，实际为 %+v", sender)
				}
				return
			}
			if err != nil {
				t.Fatalf("不期望错误，实际为 %v", err)
			}
			if sender == nil {
				t.Fatal("期望返回非 nil sender")
			}
			if sender.vapidPublicKey != strings.TrimSpace(tt.publicKey) {
				t.Errorf("vapidPublicKey = %q，期望 %q", sender.vapidPublicKey, strings.TrimSpace(tt.publicKey))
			}
			if sender.vapidPrivateKey != strings.TrimSpace(tt.privateKey) {
				t.Errorf("vapidPrivateKey = %q，期望 %q", sender.vapidPrivateKey, strings.TrimSpace(tt.privateKey))
			}
			if sender.subject != strings.TrimSpace(tt.subject) {
				t.Errorf("subject = %q，期望 %q", sender.subject, strings.TrimSpace(tt.subject))
			}
			if tt.wantTimeout > 0 && sender.timeout != tt.wantTimeout {
				t.Errorf("timeout = %v，期望 %v", sender.timeout, tt.wantTimeout)
			}
			if sender.timeout != tt.timeout && tt.wantTimeout == 0 {
				t.Errorf("timeout = %v，期望保留原值 %v", sender.timeout, tt.timeout)
			}
		})
	}
}

func TestWebPushSender_Name(t *testing.T) {
	sender, err := NewWebPushSender("pub", "priv", "mailto:a@b.com", time.Second)
	if err != nil {
		t.Fatalf("构造失败: %v", err)
	}
	got := sender.Name()
	if got != "webpush" {
		t.Fatalf("Name() = %q，期望 %q", got, "webpush")
	}
	if strings.TrimSpace(got) == "" {
		t.Fatal("Name() 不应为空")
	}
}

func TestSendToSubscription_Validation(t *testing.T) {
	sender, err := NewWebPushSender("pub", "priv", "mailto:a@b.com", 50*time.Millisecond)
	if err != nil {
		t.Fatalf("构造失败: %v", err)
	}

	tests := []struct {
		name        string
		target      WebPushTarget
		errContains string
	}{
		{
			name:        "endpoint 非 https 前缀被拒绝",
			target:      WebPushTarget{Endpoint: "http://example.com/push", P256DH: "p", Auth: "a"},
			errContains: "endpoint 必须以 https:// 开头",
		},
		{
			name:        "endpoint 为 ftp 被拒绝",
			target:      WebPushTarget{Endpoint: "ftp://example.com/push", P256DH: "p", Auth: "a"},
			errContains: "endpoint 必须以 https:// 开头",
		},
		{
			name:        "endpoint 为空被拒绝",
			target:      WebPushTarget{Endpoint: "", P256DH: "p", Auth: "a"},
			errContains: "endpoint 必须以 https:// 开头",
		},
		{
			name:        "p256dh 为空被拒绝",
			target:      WebPushTarget{Endpoint: "https://example.com/push", P256DH: "", Auth: "a"},
			errContains: "p256dh 不能为空",
		},
		{
			name:        "p256dh 全空白被拒绝",
			target:      WebPushTarget{Endpoint: "https://example.com/push", P256DH: "   \t", Auth: "a"},
			errContains: "p256dh 不能为空",
		},
		{
			name:        "auth 为空被拒绝",
			target:      WebPushTarget{Endpoint: "https://example.com/push", P256DH: "p", Auth: ""},
			errContains: "auth 不能为空",
		},
		{
			name:        "auth 全空白被拒绝",
			target:      WebPushTarget{Endpoint: "https://example.com/push", P256DH: "p", Auth: "  \n"},
			errContains: "auth 不能为空",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx := context.Background()
			err := sender.SendToSubscription(ctx, tt.target, "标题", "正文", "https://example.com")
			if err == nil {
				t.Fatalf("期望返回错误，实际为 nil")
			}
			if !strings.Contains(err.Error(), tt.errContains) {
				t.Fatalf("错误信息 = %q，期望包含 %q", err.Error(), tt.errContains)
			}
			if errors.Is(err, ErrSubscriptionGone) {
				t.Fatalf("校验错误不应是 ErrSubscriptionGone，实际为 %v", err)
			}
		})
	}
}

func TestSendToSubscription_ContextAlreadyCanceled(t *testing.T) {
	sender, err := NewWebPushSender("pub", "priv", "mailto:a@b.com", time.Second)
	if err != nil {
		t.Fatalf("构造失败: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	target := WebPushTarget{
		Endpoint: "https://example.com/push",
		P256DH:   "p256dh-value",
		Auth:     "auth-value",
	}
	err = sender.SendToSubscription(ctx, target, "标题", "正文", "https://example.com")
	if err == nil {
		t.Fatalf("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "发送超时") {
		t.Fatalf("错误信息 = %q，期望包含 %q", err.Error(), "发送超时")
	}
	if !strings.Contains(err.Error(), "webpush") {
		t.Fatalf("错误信息 = %q，期望包含包名前缀 %q", err.Error(), "webpush")
	}
}

func TestSendToSubscription_ContextDeadlineExceeded(t *testing.T) {
	sender, err := NewWebPushSender("pub", "priv", "mailto:a@b.com", time.Second)
	if err != nil {
		t.Fatalf("构造失败: %v", err)
	}
	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()

	target := WebPushTarget{
		Endpoint: "https://example.com/push",
		P256DH:   "p256dh-value",
		Auth:     "auth-value",
	}
	err = sender.SendToSubscription(ctx, target, "标题", "正文", "https://example.com")
	if err == nil {
		t.Fatalf("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "发送超时") {
		t.Fatalf("错误信息 = %q，期望包含 %q", err.Error(), "发送超时")
	}
	if errors.Is(err, ErrSubscriptionGone) {
		t.Fatalf("超时错误不应是 ErrSubscriptionGone，实际为 %v", err)
	}
}

func TestWebPushPayload_JSONFields(t *testing.T) {
	payload := webPushPayload{
		Title: "复习提醒",
		Body:  "今天有 3 张卡片要复习",
		URL:   "https://example.com/review",
		Tag:   "review-digest",
	}
	if payload.Title != "复习提醒" {
		t.Errorf("Title = %q，期望 %q", payload.Title, "复习提醒")
	}
	if payload.Body != "今天有 3 张卡片要复习" {
		t.Errorf("Body = %q，期望 %q", payload.Body, "今天有 3 张卡片要复习")
	}
	if payload.URL != "https://example.com/review" {
		t.Errorf("URL = %q，期望 %q", payload.URL, "https://example.com/review")
	}
	if payload.Tag != "review-digest" {
		t.Errorf("Tag = %q，期望 %q", payload.Tag, "review-digest")
	}
}

func TestErrSubscriptionGone_Message(t *testing.T) {
	if ErrSubscriptionGone == nil {
		t.Fatal("ErrSubscriptionGone 不应为 nil")
	}
	want := "webpush: subscription gone"
	if ErrSubscriptionGone.Error() != want {
		t.Fatalf("ErrSubscriptionGone.Error() = %q，期望 %q", ErrSubscriptionGone.Error(), want)
	}
	if !errors.Is(ErrSubscriptionGone, ErrSubscriptionGone) {
		t.Fatal("errors.Is(ErrSubscriptionGone, ErrSubscriptionGone) 应为 true")
	}
}

func TestWebPushTarget_FieldsPreserved(t *testing.T) {
	target := WebPushTarget{
		Endpoint: "https://fcm.googleapis.com/fcm/send/abc",
		P256DH:   "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
		Auth:     "tBHItJI5svbpez7KI4CCXg",
	}
	if target.Endpoint != "https://fcm.googleapis.com/fcm/send/abc" {
		t.Errorf("Endpoint = %q，字段未保留", target.Endpoint)
	}
	if !strings.HasPrefix(target.P256DH, "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM") {
		t.Errorf("P256DH 字段未保留，实际 = %q", target.P256DH)
	}
	if target.Auth != "tBHItJI5svbpez7KI4CCXg" {
		t.Errorf("Auth = %q，字段未保留", target.Auth)
	}
}

func TestNewWebPushSender_TrimKeepsInnerWhitespace(t *testing.T) {
	sender, err := NewWebPushSender("  pub key with space  ", "  priv key  ", "  mailto:a@b.com  ", 2*time.Second)
	if err != nil {
		t.Fatalf("构造失败: %v", err)
	}
	if sender.vapidPublicKey != "pub key with space" {
		t.Errorf("vapidPublicKey = %q，期望 %q", sender.vapidPublicKey, "pub key with space")
	}
	if sender.vapidPrivateKey != "priv key" {
		t.Errorf("vapidPrivateKey = %q，期望 %q", sender.vapidPrivateKey, "priv key")
	}
	if sender.subject != "mailto:a@b.com" {
		t.Errorf("subject = %q，期望 %q", sender.subject, "mailto:a@b.com")
	}
	if sender.timeout != 2*time.Second {
		t.Errorf("timeout = %v，期望 %v", sender.timeout, 2*time.Second)
	}
}

func TestSendToSubscription_EndpointPrefixBoundary(t *testing.T) {
	sender, err := NewWebPushSender("pub", "priv", "mailto:a@b.com", 20*time.Millisecond)
	if err != nil {
		t.Fatalf("构造失败: %v", err)
	}

	tests := []struct {
		name        string
		endpoint    string
		errContains string
	}{
		{
			name:        "https 全小写通过前缀校验",
			endpoint:    "https://example.com/push",
			errContains: "",
		},
		{
			name:        "HTTPS 全大写不通过前缀校验",
			endpoint:    "HTTPS://example.com/push",
			errContains: "endpoint 必须以 https:// 开头",
		},
		{
			name:        "https 前有多余空格不通过前缀校验",
			endpoint:    " https://example.com/push",
			errContains: "endpoint 必须以 https:// 开头",
		},
		{
			name:        "https 后无冒号斜杠不通过前缀校验",
			endpoint:    "https//example.com",
			errContains: "endpoint 必须以 https:// 开头",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx := context.Background()
			target := WebPushTarget{Endpoint: tt.endpoint, P256DH: "p", Auth: "a"}
			err := sender.SendToSubscription(ctx, target, "标题", "正文", "https://example.com")
			if tt.errContains == "" {
				if err != nil && strings.Contains(err.Error(), "endpoint 必须以 https:// 开头") {
					t.Fatalf("https 小写不应被前缀校验拒绝，实际错误 = %v", err)
				}
				return
			}
			if err == nil {
				t.Fatalf("期望返回错误，实际为 nil")
			}
			if !strings.Contains(err.Error(), tt.errContains) {
				t.Fatalf("错误信息 = %q，期望包含 %q", err.Error(), tt.errContains)
			}
		})
	}
}
