package checker

import (
	"database/sql"
	"io"
	"net"
	"net/http"
	"time"

	"sentinel/internal/store"
)

// utcNow 返回当前 UTC 时间的 RFC3339 字符串
func utcNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// Check 对给定的监控目标执行一次检查，返回检查结果
func Check(m store.Monitor) store.Check {
	c := store.Check{
		MonitorID: m.ID,
		CheckedAt: utcNow(),
	}
	switch m.Kind {
	case "tcp":
		checkTCP(&c, m)
	default:
		checkHTTP(&c, m)
	}
	return c
}

// checkHTTP 执行 HTTP/HTTPS 检查
func checkHTTP(c *store.Check, m store.Monitor) {
	client := &http.Client{
		Timeout: time.Duration(m.TimeoutSec) * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	var body io.Reader
	if m.Method == "POST" {
		body = http.NoBody
	}
	req, err := http.NewRequest(m.Method, m.Target, body)
	if err != nil {
		c.Ok = 0
		c.Error = err.Error()
		return
	}

	t0 := time.Now()
	resp, err := client.Do(req)
	latency := time.Since(t0).Milliseconds()
	c.LatencyMs = latency

	if err != nil {
		c.Ok = 0
		c.Error = err.Error()
		return
	}
	defer resp.Body.Close()

	sc := resp.StatusCode
	c.StatusCode = sql.NullInt64{Int64: int64(sc), Valid: true}
	if resp.StatusCode == m.ExpectedStatus {
		c.Ok = 1
	} else {
		c.Ok = 0
	}

	// https 目标记录证书剩余天数
	if len(m.Target) >= 8 && m.Target[:8] == "https://" && resp.TLS != nil {
		var minNotAfter time.Time
		first := true
		for _, pc := range resp.TLS.PeerCertificates {
			if first || pc.NotAfter.Before(minNotAfter) {
				minNotAfter = pc.NotAfter
				first = false
			}
		}
		if !first {
			days := int(minNotAfter.Sub(time.Now()).Hours() / 24)
			c.CertDaysLeft = sql.NullInt64{Int64: int64(days), Valid: true}
		}
	}
}

// checkTCP 执行 TCP 拨号检查
func checkTCP(c *store.Check, m store.Monitor) {
	timeout := time.Duration(m.TimeoutSec) * time.Second
	t0 := time.Now()
	conn, err := net.DialTimeout("tcp", m.Target, timeout)
	latency := time.Since(t0).Milliseconds()
	c.LatencyMs = latency

	if err != nil {
		c.Ok = 0
		c.Error = err.Error()
		return
	}
	c.Ok = 1
	conn.Close()
}
