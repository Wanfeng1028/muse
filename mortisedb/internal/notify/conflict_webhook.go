package notify

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// ConflictWebhook 把冲突事件通过 HTTP POST 推给外部地址。
type ConflictWebhook struct {
	URL     string
	Timeout time.Duration
	client  *http.Client
}

// NewConflictWebhook 按 URL 和超时构造一个 webhook。URL 为空表示不启用。
func NewConflictWebhook(url string, timeout time.Duration) *ConflictWebhook {
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	return &ConflictWebhook{
		URL:     url,
		Timeout: timeout,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

// Send 把冲突 c 以 JSON POST 到 w.URL。字段名与 store.Conflict 的 json tag 一致。
// 非 2xx 返回错误，错误信息包含状态码和响应 body 前 200 字节。
func (w *ConflictWebhook) Send(c store.Conflict) error {
	if w == nil {
		return fmt.Errorf("conflict webhook is nil")
	}
	if w.URL == "" {
		return nil
	}

	payload, err := json.Marshal(c)
	if err != nil {
		return fmt.Errorf("marshal conflict: %w", err)
	}

	client := w.client
	if client == nil {
		timeout := w.Timeout
		if timeout <= 0 {
			timeout = 10 * time.Second
		}
		client = &http.Client{Timeout: timeout}
	}

	req, err := http.NewRequest(http.MethodPost, w.URL, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("post conflict webhook: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 200))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("conflict webhook status %d: %s", resp.StatusCode, string(body))
	}
	return nil
}
