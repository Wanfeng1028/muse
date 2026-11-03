package notify

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const webhookDefaultTimeout = 10 * time.Second

// WebhookSender 通过 HTTP POST 推送 JSON 通知。
type WebhookSender struct {
	url     string
	secret  string
	timeout time.Duration
	client  *http.Client
}

// NewWebhookSender 构造一个 webhook 发送器。timeout <= 0 时使用默认 10s。
func NewWebhookSender(url, secret string, timeout time.Duration) *WebhookSender {
	if timeout <= 0 {
		timeout = webhookDefaultTimeout
	}
	return &WebhookSender{
		url:     url,
		secret:  secret,
		timeout: timeout,
		client:  &http.Client{Timeout: timeout},
	}
}

// Name 实现 Sender 接口。
func (s *WebhookSender) Name() string { return "webhook" }

type webhookPayload struct {
	Event    string               `json:"event"`
	Date     string               `json:"date"`
	Subject  string               `json:"subject"`
	Text     string               `json:"text"`
	HTML     string               `json:"html"`
	DueCount int                  `json:"due_count"`
	Items    []webhookPayloadItem `json:"items"`
}

type webhookPayloadItem struct {
	Title       string   `json:"title"`
	Snippet     string   `json:"snippet"`
	Tags        []string `json:"tags"`
	DueDate     string   `json:"due_date"`
	OverdueDays int      `json:"overdue_days"`
}

// Send 实现 Sender 接口。
func (s *WebhookSender) Send(ctx context.Context, msg Message) error {
	items := make([]webhookPayloadItem, 0, len(msg.Items))
	for _, it := range msg.Items {
		items = append(items, webhookPayloadItem{
			Title:       it.Title,
			Snippet:     it.Snippet,
			Tags:        it.Tags,
			DueDate:     it.DueDate,
			OverdueDays: it.OverdueDays,
		})
	}
	payload := webhookPayload{
		Event:    "review.digest",
		Date:     time.Now().Format("2006-01-02"),
		Subject:  msg.Subject,
		Text:     msg.TextBody,
		HTML:     msg.HTMLBody,
		DueCount: msg.DueCount,
		Items:    items,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("notify: 序列化 webhook 负载失败: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("notify: 构造 webhook 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Event", "review.digest")
	if s.secret != "" {
		mac := hmac.New(sha256.New, []byte(s.secret))
		mac.Write(body)
		req.Header.Set("X-Signature", "sha256="+hex.EncodeToString(mac.Sum(nil)))
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("%w: webhook 请求失败: %v", ErrConn, err)
	}
	defer func() { _ = resp.Body.Close() }()

	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		snippet := string(respBody)
		if len(snippet) > 200 {
			snippet = snippet[:200]
		}
		snippet = strings.TrimSpace(snippet)
		return fmt.Errorf("notify: webhook 返回非 2xx 状态 %d: %s", resp.StatusCode, snippet)
	}
	return nil
}
