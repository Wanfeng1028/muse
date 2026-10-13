package checker

import (
	"database/sql"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"

	"sentinel/internal/store"
)

// Check 对单个监控目标执行一次检查。
// 支持 HTTP 与 TCP 两类；HTTP 会尝试读取 TLS 证书剩余天数。
func Check(m store.Monitor) store.Check {
	timeout := time.Duration(m.TimeoutSec) * time.Second
	if timeout <= 0 {
		timeout = 10 * time.Second
	}

	kind := strings.ToLower(strings.TrimSpace(m.Kind))
	if kind == "" {
		kind = "http"
	}

	switch kind {
	case "tcp":
		return checkTCP(m, timeout)
	default:
		return checkHTTP(m, timeout)
	}
}

// checkHTTP 执行 HTTP(S) 检查。
func checkHTTP(m store.Monitor, timeout time.Duration) store.Check {
	now := time.Now()
	c := store.Check{
		MonitorID: m.ID,
		CheckedAt: now.UTC().Format(time.RFC3339),
	}

	method := strings.ToUpper(strings.TrimSpace(m.Method))
	if method == "" {
		method = http.MethodGet
	}

	client := &http.Client{
		Timeout: timeout,
	}

	req, err := http.NewRequest(method, m.Target, nil)
	if err != nil {
		c.Ok = 0
		c.Error = fmt.Sprintf("构造请求失败: %v", err)
		return c
	}
	req.Header.Set("User-Agent", "sentinel/1.0")

	start := time.Now()
	resp, err := client.Do(req)
	latency := time.Since(start).Milliseconds()
	if latency < 0 {
		latency = 0
	}
	c.LatencyMs = latency

	if err != nil {
		c.Ok = 0
		c.Error = err.Error()
		return c
	}
	defer resp.Body.Close()
	// 丢弃响应体，避免连接无法复用。
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<20))

	c.StatusCode = sql.NullInt64{Int64: int64(resp.StatusCode), Valid: true}

	if resp.TLS != nil && len(resp.TLS.PeerCertificates) > 0 {
		leaf := resp.TLS.PeerCertificates[0]
		days := int(time.Until(leaf.NotAfter).Hours() / 24)
		if days < 0 {
			days = 0
		}
		c.CertDaysLeft = sql.NullInt64{Int64: int64(days), Valid: true}
	}

	expected := m.ExpectedStatus
	if expected <= 0 {
		expected = 200
	}
	if resp.StatusCode != expected {
		c.Ok = 0
		c.Error = fmt.Sprintf("状态码不符: 期望 %d, 实际 %d", expected, resp.StatusCode)
		return c
	}

	c.Ok = 1
	return c
}

// checkTCP 执行 TCP 连通性检查。
func checkTCP(m store.Monitor, timeout time.Duration) store.Check {
	now := time.Now()
	c := store.Check{
		MonitorID: m.ID,
		CheckedAt: now.UTC().Format(time.RFC3339),
	}

	start := time.Now()
	conn, err := net.DialTimeout("tcp", m.Target, timeout)
	latency := time.Since(start).Milliseconds()
	if latency < 0 {
		latency = 0
	}
	c.LatencyMs = latency

	if err != nil {
		c.Ok = 0
		c.Error = err.Error()
		return c
	}
	_ = conn.Close()

	c.Ok = 1
	return c
}

// CheckWithRetry 在 transport 层失败（无状态码）时进行重试。
// 最多执行 1+maxRetries 次；退避 500ms、1s、2s、4s… 上限 8s。
// 返回最后一次结果与实际重试次数。
func CheckWithRetry(m store.Monitor, maxRetries int) (store.Check, int) {
	if maxRetries < 0 {
		maxRetries = 0
	}

	var last store.Check
	retries := 0

	for attempt := 0; ; attempt++ {
		last = Check(m)

		// 有状态码（HTTP 状态码不符）不重试，直接返回。
		if last.StatusCode.Valid {
			return last, retries
		}
		// 成功（理论上无状态码的成功只出现在 TCP，也一并视为完成）。
		if last.Ok == 1 {
			return last, retries
		}
		// 没有 Error 说明是未知情况，不再重试。
		if last.Error == "" {
			return last, retries
		}

		if attempt >= maxRetries {
			return last, retries
		}

		// 退避：500ms << attempt，上限 8s。
		backoff := 500 * time.Millisecond << uint(attempt)
		if backoff > 8*time.Second {
			backoff = 8 * time.Second
		}
		time.Sleep(backoff)
		retries++
	}
}
