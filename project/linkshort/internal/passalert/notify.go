package passalert

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
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
	Scope         string `json:"scope"`
	IPHash        string `json:"ip_hash,omitempty"`
	Time          string `json:"time"`
}

// HashIP 返回 IP 的 SHA-256 哈希前 16 个十六进制字符。
func HashIP(ip string) string {
	if ip == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(ip))
	return hex.EncodeToString(sum[:8])
}

// webhookHost 返回 webhook URL 的 Host。
func webhookHost(raw string) string {
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return "(url 解析失败)"
	}
	return u.Host
}

// sendAlert 把密码失败高告警 POST 到 webhookURL。
func sendAlert(webhookURL string, p AlertPayload, logID string) {
	if webhookURL == "" {
		return
	}
	body, err := json.Marshal(p)
	if err != nil {
		log.Printf("[passalert] webhook 告警序列化失败 scope=%s", p.Scope)
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, webhookURL, bytes.NewReader(body))
	if err != nil {
		log.Printf("[passalert] webhook 告警请求构造失败 target=%s id=%s", webhookHost(webhookURL), logID)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		log.Printf("[passalert] webhook 告警发送失败 target=%s id=%s", webhookHost(webhookURL), logID)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("[passalert] webhook 告警发送失败 status=%d target=%s id=%s", resp.StatusCode, webhookHost(webhookURL), logID)
	}
}

// NotifyPasswordFailAlert 把密码失败高告警 POST 到 webhookURL。
// webhookURL 为空直接返回；HTTP 10 秒超时；成功/失败都只记 log，不返回 error（调用方用 go 异步调用，失败不影响主流程）。
func NotifyPasswordFailAlert(webhookURL, host, slug string, failCount int, window time.Duration, threshold int) {
	payload := AlertPayload{
		Source:        "linkshort",
		Event:         "password_fail_alert",
		Host:          host,
		Slug:          slug,
		FailCount:     failCount,
		WindowSeconds: int64(window.Seconds()),
		Threshold:     threshold,
		Scope:         "slug",
		Time:          time.Now().UTC().Format(time.RFC3339),
	}
	sendAlert(webhookURL, payload, slug)
}

// NotifyPasswordFailAlertIP 把密码失败高告警 POST 到 webhookURL，并使用 IP 哈希作为标识。
func NotifyPasswordFailAlertIP(webhookURL, host, ip string, failCount int, window time.Duration, threshold int) {
	ipHash := HashIP(ip)
	payload := AlertPayload{
		Source:        "linkshort",
		Event:         "password_fail_alert",
		Host:          host,
		Slug:          "",
		FailCount:     failCount,
		WindowSeconds: int64(window.Seconds()),
		Threshold:     threshold,
		Scope:         "ip",
		IPHash:        ipHash,
		Time:          time.Now().UTC().Format(time.RFC3339),
	}
	sendAlert(webhookURL, payload, ipHash)
}
