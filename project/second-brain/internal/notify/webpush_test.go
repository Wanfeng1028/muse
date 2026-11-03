package notify

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"encoding/base64"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

const (
	testVAPIDPublic  = "BCNhoeQXALENvz2Frbod6K-6gNUWaAZWrebUJECMHJSxSPdMOJE6FGFTZjP_riq_6BMcdTXLMsMptS3ZNwdV18s"
	testVAPIDPrivate = "NIHYpAwRN1MRUAijqBVxWGmgOtio6zFYjbnG-DR7eBQ"
	testVAPIDSubject = "mailto:test@example.com"
)

func withInsecureTransport(t *testing.T) {
	t.Helper()
	orig := http.DefaultTransport
	http.DefaultTransport = &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}
	t.Cleanup(func() { http.DefaultTransport = orig })
}

// testP256DH 生成一个真实的 P-256 公钥点（65 字节 uncompressed 格式的 base64url）。
// Web Push 加密要求 p256dh 是曲线上的有效点，纯随机字节会被拒绝。
func testP256DH(t *testing.T) string {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("生成测试密钥失败: %v", err)
	}
	return base64.RawURLEncoding.EncodeToString(elliptic.Marshal(elliptic.P256(), key.X, key.Y))
}

func randomB64(t *testing.T, n int) string {
	t.Helper()
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		t.Fatalf("生成随机字节失败: %v", err)
	}
	return base64.RawURLEncoding.EncodeToString(buf)
}

func newTestSender(t *testing.T) *WebPushSender {
	t.Helper()
	sender, err := NewWebPushSender(testVAPIDPublic, testVAPIDPrivate, testVAPIDSubject, 5*time.Second)
	if err != nil {
		t.Fatalf("构造 sender 失败: %v", err)
	}
	return sender
}

func newTarget(t *testing.T, endpoint string) WebPushTarget {
	t.Helper()
	return WebPushTarget{
		Endpoint: endpoint,
		P256DH:   testP256DH(t),
		Auth:     randomB64(t, 16),
	}
}

func TestSendSuccess(t *testing.T) {
	withInsecureTransport(t)
	type captured struct {
		auth    string
		enc     string
		bodyLen int
	}
	got := make(chan captured, 1)
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		got <- captured{
			auth:    r.Header.Get("Authorization"),
			enc:     r.Header.Get("Content-Encoding"),
			bodyLen: len(body),
		}
		w.WriteHeader(http.StatusCreated)
	}))
	t.Cleanup(srv.Close)

	sender := newTestSender(t)
	target := newTarget(t, srv.URL)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := sender.SendToSubscription(ctx, target, "标题", "正文", "https://example.com"); err != nil {
		t.Fatalf("发送应成功, 实际错误: %v", err)
	}

	select {
	case c := <-got:
		if !strings.HasPrefix(strings.ToLower(c.auth), "vapid ") {
			t.Fatalf("Authorization 头应以 vapid 开头, 实际 %q", c.auth)
		}
		if c.enc != "aes128gcm" {
			t.Fatalf("Content-Encoding 期望 %q, 实际 %q", "aes128gcm", c.enc)
		}
		if c.bodyLen == 0 {
			t.Fatalf("请求体不应为空")
		}
	case <-time.After(3 * time.Second):
		t.Fatalf("mock 服务未收到请求")
	}
}

func TestSendGone(t *testing.T) {
	withInsecureTransport(t)
	for _, code := range []int{http.StatusGone, http.StatusNotFound} {
		srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(code)
		}))
		sender := newTestSender(t)
		target := newTarget(t, srv.URL)
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		err := sender.SendToSubscription(ctx, target, "标题", "正文", "https://example.com")
		cancel()
		srv.Close()
		if !errors.Is(err, ErrSubscriptionGone) {
			t.Fatalf("状态码 %d 应返回 ErrSubscriptionGone, 实际 %v", code, err)
		}
	}
}

func TestSendServerError(t *testing.T) {
	withInsecureTransport(t)
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)

	sender := newTestSender(t)
	target := newTarget(t, srv.URL)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	err := sender.SendToSubscription(ctx, target, "标题", "正文", "https://example.com")
	if err == nil {
		t.Fatalf("500 响应应返回错误, 实际 nil")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Fatalf("错误信息应包含状态码 500, 实际 %q", err.Error())
	}
}

func TestNewSenderValidation(t *testing.T) {
	cases := []struct {
		name       string
		publicKey  string
		privateKey string
		subject    string
	}{
		{"空公钥", "   ", testVAPIDPrivate, testVAPIDSubject},
		{"空私钥", testVAPIDPublic, "", testVAPIDSubject},
		{"空主题", testVAPIDPublic, testVAPIDPrivate, "  "},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, err := NewWebPushSender(c.publicKey, c.privateKey, c.subject, 5*time.Second); err == nil {
				t.Fatalf("非法参数 %q 应返回错误, 实际 nil", c.name)
			}
		})
	}

	if _, err := NewWebPushSender(testVAPIDPublic, testVAPIDPrivate, testVAPIDSubject, 0); err != nil {
		t.Fatalf("timeout=0 应构造成功, 实际错误: %v", err)
	}
}
