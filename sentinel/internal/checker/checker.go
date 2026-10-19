package checker

import (
	"context"
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
	// 读取响应体供关键字断言使用，同时避免连接无法复用。
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))

	c.StatusCode = sql.NullInt64{Int64: int64(resp.StatusCode), Valid: true}

	if resp.TLS != nil && len(resp.TLS.PeerCertificates) > 0 {
		leaf := resp.TLS.PeerCertificates[0]
		days := int(time.Until(leaf.NotAfter).Hours() / 24)
		if days < 0 {
			days = 0
		}
		c.CertDaysLeft = sql.NullInt64{Int64: int64(days), Valid: true}
	}

	if m.CertWarnDays > 0 && c.CertDaysLeft.Valid && c.CertDaysLeft.Int64 < int64(m.CertWarnDays) {
		c.Ok = 0
		c.Error = fmt.Sprintf("证书将于 %d 天后过期，低于预警阈值 %d 天", c.CertDaysLeft.Int64, m.CertWarnDays)
		return c
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

	if m.Keyword != "" {
		if kerr := AssertKeyword(body, m.Keyword, m.KeywordMode); kerr != nil {
			c.Ok = 0
			c.Error = kerr.Error()
			return c
		}
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

// checkHTTPCtx 执行可被 ctx 中断的 HTTP(S) 检查。
// 语义与 checkHTTP 完全一致，额外通过 req.WithContext(ctx) 让请求可取消；
// 同时保留 client.Timeout 作为双保险。
func checkHTTPCtx(ctx context.Context, m store.Monitor, timeout time.Duration) store.Check {
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
	req = req.WithContext(ctx)

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
	// 读取响应体供关键字断言使用，同时避免连接无法复用。
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))

	c.StatusCode = sql.NullInt64{Int64: int64(resp.StatusCode), Valid: true}

	if resp.TLS != nil && len(resp.TLS.PeerCertificates) > 0 {
		leaf := resp.TLS.PeerCertificates[0]
		days := int(time.Until(leaf.NotAfter).Hours() / 24)
		if days < 0 {
			days = 0
		}
		c.CertDaysLeft = sql.NullInt64{Int64: int64(days), Valid: true}
	}

	if m.CertWarnDays > 0 && c.CertDaysLeft.Valid && c.CertDaysLeft.Int64 < int64(m.CertWarnDays) {
		c.Ok = 0
		c.Error = fmt.Sprintf("证书将于 %d 天后过期，低于预警阈值 %d 天", c.CertDaysLeft.Int64, m.CertWarnDays)
		return c
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

	if m.Keyword != "" {
		if kerr := AssertKeyword(body, m.Keyword, m.KeywordMode); kerr != nil {
			c.Ok = 0
			c.Error = kerr.Error()
			return c
		}
	}

	c.Ok = 1
	return c
}

// checkTCPCtx 执行可被 ctx 中断的 TCP 连通性检查。
// 语义与 checkTCP 完全一致，额外通过 DialContext 让拨号可取消；
// 同时保留 Dialer.Timeout 作为双保险。
func checkTCPCtx(ctx context.Context, m store.Monitor, timeout time.Duration) store.Check {
	now := time.Now()
	c := store.Check{
		MonitorID: m.ID,
		CheckedAt: now.UTC().Format(time.RFC3339),
	}

	start := time.Now()
	dialer := &net.Dialer{Timeout: timeout}
	conn, err := dialer.DialContext(ctx, "tcp", m.Target)
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

// checkCtx 对单个监控目标执行一次可被 ctx 中断的检查。
func checkCtx(ctx context.Context, m store.Monitor) store.Check {
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
		return checkTCPCtx(ctx, m, timeout)
	default:
		return checkHTTPCtx(ctx, m, timeout)
	}
}

// CheckWithRetry 在 transport 层失败（无状态码）时进行重试。
// 最多执行 1+maxRetries 次；退避 500ms、1s、2s、4s… 上限 8s。
// 返回最后一次结果与实际重试次数。
func CheckWithRetry(m store.Monitor, maxRetries int) (store.Check, int) {
	return CheckWithRetryCtx(context.Background(), m, maxRetries)
}

// CheckWithRetryCtx 语义与 CheckWithRetry 完全一致，额外接受 ctx 用于中断：
//   - 每次 attempt 前若 ctx 已取消/超时，则不再发起新请求；
//   - 退避等待期间 ctx 取消会立即返回。
//
// 首次 attempt 前即被取消时，返回一个 Ok=0、Error 含 "context" 字样的 Check。
func CheckWithRetryCtx(ctx context.Context, m store.Monitor, maxRetries int) (store.Check, int) {
	if maxRetries < 0 {
		maxRetries = 0
	}

	var last store.Check
	retries := 0
	attempted := false

	for attempt := 0; ; attempt++ {
		if err := ctx.Err(); err != nil {
			if !attempted {
				return store.Check{
					MonitorID: m.ID,
					CheckedAt: time.Now().UTC().Format(time.RFC3339),
					Ok:        0,
					Error:     fmt.Sprintf("context 已取消: %v", err),
				}, retries
			}
			return last, retries
		}

		last = checkCtx(ctx, m)
		attempted = true

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

		// 退避：500ms << attempt，上限 8s；期间可被 ctx 中断。
		backoff := 500 * time.Millisecond << uint(attempt)
		if backoff > 8*time.Second {
			backoff = 8 * time.Second
		}
		select {
		case <-ctx.Done():
			return last, retries
		case <-time.After(backoff):
		}
		retries++
	}
}
