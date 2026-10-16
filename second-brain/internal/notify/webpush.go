package notify

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	webpush "github.com/SherClockHolmes/webpush-go"
)

// ErrSubscriptionGone 表示推送服务返回 410 Gone 或 404 Not Found，订阅已失效。
var ErrSubscriptionGone = errors.New("webpush: subscription gone")

// WebPushTarget 是 Web Push 的发送目标，用本地结构体承载以避免 notify 依赖 store 包。
type WebPushTarget struct {
	Endpoint string
	P256DH   string
	Auth     string
}

// WebPushSender 基于 VAPID 的 Web Push 发送器。
type WebPushSender struct {
	vapidPublicKey  string
	vapidPrivateKey string
	subject         string
	timeout         time.Duration
}

// NewWebPushSender 构造 Web Push 发送器，三个密钥/主题字段 trim 后必须非空。
func NewWebPushSender(publicKey, privateKey, subject string, timeout time.Duration) (*WebPushSender, error) {
	publicKey = strings.TrimSpace(publicKey)
	privateKey = strings.TrimSpace(privateKey)
	subject = strings.TrimSpace(subject)
	if publicKey == "" {
		return nil, errors.New("webpush: VAPID 公钥不能为空")
	}
	if privateKey == "" {
		return nil, errors.New("webpush: VAPID 私钥不能为空")
	}
	if subject == "" {
		return nil, errors.New("webpush: VAPID 主题不能为空")
	}
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	return &WebPushSender{
		vapidPublicKey:  publicKey,
		vapidPrivateKey: privateKey,
		subject:         subject,
		timeout:         timeout,
	}, nil
}

// Name 返回通道名称。
func (s *WebPushSender) Name() string {
	return "webpush"
}

// webPushPayload 是发送给前端 Service Worker 的载荷结构。
type webPushPayload struct {
	Title string `json:"title"`
	Body  string `json:"body"`
	URL   string `json:"url"`
	Tag   string `json:"tag"`
}

// SendToSubscription 向单个订阅发送通知。返回 ErrSubscriptionGone 表示订阅已失效。
func (s *WebPushSender) SendToSubscription(ctx context.Context, target WebPushTarget, title, body, url string) error {
	if !strings.HasPrefix(target.Endpoint, "https://") {
		return errors.New("webpush: endpoint 必须以 https:// 开头")
	}
	if strings.TrimSpace(target.P256DH) == "" {
		return errors.New("webpush: p256dh 不能为空")
	}
	if strings.TrimSpace(target.Auth) == "" {
		return errors.New("webpush: auth 不能为空")
	}

	payload, err := json.Marshal(webPushPayload{
		Title: title,
		Body:  body,
		URL:   url,
		Tag:   "review-digest",
	})
	if err != nil {
		return fmt.Errorf("webpush: 序列化载荷失败: %w", err)
	}

	sub := &webpush.Subscription{
		Endpoint: target.Endpoint,
		Keys: webpush.Keys{
			P256dh: target.P256DH,
			Auth:   target.Auth,
		},
	}
	opts := &webpush.Options{
		Subscriber:      s.subject,
		VAPIDPublicKey:  s.vapidPublicKey,
		VAPIDPrivateKey: s.vapidPrivateKey,
		TTL:             30,
	}

	// webpush.SendNotification 不接受 context，用 goroutine + select 实现超时控制，避免无限阻塞。
	done := make(chan error, 1)
	go func() {
		resp, err := webpush.SendNotification(payload, sub, opts)
		if resp != nil {
			defer resp.Body.Close()
		}
		if err != nil {
			done <- err
			return
		}
		if resp == nil {
			done <- errors.New("webpush: 空响应")
			return
		}
		if resp.StatusCode == 410 || resp.StatusCode == 404 {
			done <- ErrSubscriptionGone
			return
		}
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			done <- fmt.Errorf("webpush: 推送服务返回状态码 %d", resp.StatusCode)
			return
		}
		done <- nil
	}()

	select {
	case <-ctx.Done():
		return errors.New("webpush: 发送超时")
	case err := <-done:
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
				return errors.New("webpush: 发送超时")
			}
			return err
		}
		return nil
	}
}
