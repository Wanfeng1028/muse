package notify

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"sentinel/internal/log"
)

// Notifier 承载全局告警配置。
type Notifier struct {
	WebhookURL string       // 全局 Webhook 地址
	SMTP       SMTPConfig   // SMTP 邮件配置
	WeCom      WeComConfig  // 企业微信配置
	Channels   []string     // 全局默认渠道，如 []string{"webhook", "smtp", "wecom"}
	Queue      *QueueSender // 非空时 webhook 渠道走持久化队列异步投递
	SMS        SMSConfig    // 短信通道配置（模式/AK/全局号码），见 sms.go
	SMSSender  SmsSender    // 短信发送器；main.go 构造后注入，测试可注入 MockSmsSender
}

// payload 是发送到 Webhook 的 JSON 结构。
type payload struct {
	Event   string `json:"event"`
	Name    string `json:"name"`
	Target  string `json:"target"`
	At      string `json:"at"`
	ErrMsg  string `json:"err_msg,omitempty"`
	Service string `json:"service"`
}

// Send 发送事件通知。monitor 级 webhook 优先，全局回退；两者皆空则跳过。
// 最多 3 次尝试，退避 1s、2s、4s；最终失败返回 error。
func (n Notifier) Send(webhookURL, event, name, target, at, errMsg string) error {
	url := webhookURL
	if url == "" {
		url = n.WebhookURL
	}
	if url == "" {
		return nil
	}

	body, err := json.Marshal(payload{
		Event:   event,
		Name:    name,
		Target:  target,
		At:      at,
		ErrMsg:  errMsg,
		Service: "sentinel",
	})
	if err != nil {
		return fmt.Errorf("序列化通知失败: %w", err)
	}

	client := &http.Client{Timeout: 10 * time.Second}

	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("构造通知请求失败: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err == nil {
			_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<20))
			_ = resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				return nil
			}
			err = fmt.Errorf("非 2xx 状态码: %d", resp.StatusCode)
		}

		lastErr = err
		log.Logger().Warn("发送 Webhook 失败",
			"url", url,
			"attempt", attempt+1,
			"error", err,
		)

		if attempt < 2 {
			backoff := time.Duration(1<<uint(attempt)) * time.Second
			time.Sleep(backoff)
		}
	}

	return fmt.Errorf("Webhook 发送失败: %w", lastErr)
}
