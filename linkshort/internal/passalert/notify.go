
package passalert

import (
	"bytes"
	"context"
	"encoding/json"
	"log"
	"net/http"
	"net/url"
	"time"
)

// AlertPayload 是密码失败高告警 webhook 的请求体。
type AlertPayload struct {
	Source        string `json:"source"`
	Event         string `json:"event"`
	Host          string `json:"host"`
	Slug          string `json:"slug"`
	FailCount     int    `json:"fail_count"`
	WindowSeconds int64  `json:"window_seconds"`
	Threshold     int    `json:"threshold"`
	Time          string `json:"time"`
}

// NotifyPasswordFailAlert 把密码失败高告警 POST 到 webhookURL。
// webhookURL 为空直接返回；HTTP 10 秒超时；成功/失败都只记 log，不返回 error（调用方用 go 异步调用，失败不影响主流程）。
func NotifyPasswordFailAlert(webhookURL, host, slug string, failCount int, window time.Duration, threshold int) {
	if webhookURL == "" {
		return
	}
	payload := AlertPayload{
		Source:        "linkshort",
		Event:         "password_fail_alert",
		Host:          host,
		Slug:          slug,
		FailCount:     failCount,
		WindowSeconds: int64(window.Seconds()),
		Threshold:     threshold,
		Time:          time.Now().UTC().Format(time.RFC3339),
	}
	body, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[passalert] webhook 告警序列化失败 slug=%s err=%v", slug, err)
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, webhookURL, bytes.NewReader(body))
	if err != nil {
		log.Printf("[passalert] webhook 告警请求构造失败 slug=%s err=%v", slug, err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		log.Printf("[passalert] webhook 告警发送失败 slug=%s err=%v", slug, err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		u, perr := url.Parse(webhookURL)
		target := "(url 解析失败)"
		if perr == nil {
			target = u.Host
		}
		log.Printf("[passalert] webhook 告警发送失败 status=%d url=%s", resp.StatusCode, target)
	}
}
