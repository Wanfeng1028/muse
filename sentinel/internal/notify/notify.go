package notify

import (
	"bytes"
	"encoding/json"
	"log"
	"net/http"
	"time"
)

// Notifier 负责发送 webhook 通知
// WebhookURL 为全局默认的 webhook 地址
type Notifier struct {
	WebhookURL string
}

// Send 发送 webhook 通知
// webhookURL 非空时优先使用，否则回退到 n.WebhookURL
// 两者都为空时直接返回
// 失败仅记录日志，不重试
func (n Notifier) Send(webhookURL, event, name, target, at, errMsg string) {
	url := webhookURL
	if url == "" {
		url = n.WebhookURL
	}
	if url == "" {
		return
	}

	// 构造通知负载
	payload := map[string]string{
		"event":   event,
		"monitor": name,
		"target":  target,
		"at":      at,
		"error":   errMsg,
	}

	// 序列化为 JSON
	body, err := json.Marshal(payload)
	if err != nil {
		log.Printf("notify: 序列化 payload 失败: %v", err)
		return
	}

	// 5 秒超时的 HTTP 客户端
	client := http.Client{Timeout: 5 * time.Second}
	resp, err := client.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		log.Printf("notify: 发送 webhook 失败 url=%s err=%v", url, err)
		return
	}
	defer resp.Body.Close()

	// 非 2xx 也记录日志
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("notify: webhook 返回非 2xx url=%s status=%d", url, resp.StatusCode)
	}
}
