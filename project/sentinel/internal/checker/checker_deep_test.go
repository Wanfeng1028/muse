package checker

import (
	"database/sql"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestCheck_边界_空目标返回错误(t *testing.T) {
	m := store.Monitor{ID: 1, Kind: "http", Target: "", TimeoutSec: 2}
	c := Check(m)
	if c.MonitorID != 1 {
		t.Fatalf("MonitorID 应为 1, 实际 %d", c.MonitorID)
	}
	if c.Ok != 0 {
		t.Fatalf("空目标 Ok 应为 0, 实际 %d", c.Ok)
	}
	if c.Error == "" {
		t.Fatalf("空目标应带错误信息")
	}
	if c.StatusCode.Valid {
		t.Fatalf("空目标不应有状态码")
	}
}

func TestCheck_边界_非法URL返回错误(t *testing.T) {
	cases := []struct {
		name   string
		target string
	}{
		{"带控制字符", "http://exa\x7fmple.com"},
		{"只有scheme", "http://"},
		{"非法协议字符", "ht tp://example.com"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			m := store.Monitor{ID: 2, Kind: "http", Target: tc.target, TimeoutSec: 2}
			c := Check(m)
			if c.MonitorID != 2 {
				t.Fatalf("MonitorID 应为 2, 实际 %d", c.MonitorID)
			}
			if c.Ok != 0 {
				t.Fatalf("非法 URL Ok 应为 0, 实际 %d", c.Ok)
			}
			if c.Error == "" {
				t.Fatalf("非法 URL 应带错误信息")
			}
			if c.LatencyMs < 0 {
				t.Fatalf("LatencyMs 不应为负, 实际 %d", c.LatencyMs)
			}
		})
	}
}

func TestCheck_边界_超长目标返回错误(t *testing.T) {
	long := "http://" + strings.Repeat("a", 70000) + ".com"
	m := store.Monitor{ID: 3, Kind: "http", Target: long, TimeoutSec: 2}
	c := Check(m)
	if c.MonitorID != 3 {
		t.Fatalf("MonitorID 应为 3, 实际 %d", c.MonitorID)
	}
	if c.Ok != 0 {
		t.Fatalf("超长目标 Ok 应为 0, 实际 %d", c.Ok)
	}
	if c.Error == "" {
		t.Fatalf("超长目标应带错误信息")
	}
	if c.StatusCode.Valid {
		t.Fatalf("超长目标不应有状态码")
	}
}

func TestCheck_失败注入_探针超时(t *testing.T) {
	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer slow.Close()

	m := store.Monitor{ID: 4, Kind: "http", Target: slow.URL, TimeoutSec: 1, ExpectedStatus: 200}
	c := Check(m)
	if c.MonitorID != 4 {
		t.Fatalf("MonitorID 应为 4, 实际 %d", c.MonitorID)
	}
	if c.Ok != 0 {
		t.Fatalf("超时 Ok 应为 0, 实际 %d", c.Ok)
	}
	if c.Error == "" {
		t.Fatalf("超时应有错误信息")
	}
	if c.LatencyMs < 0 {
		t.Fatalf("LatencyMs 不应为负, 实际 %d", c.LatencyMs)
	}
}

func TestCheck_失败注入_网络错误(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{ID: 5, Kind: "tcp", Target: addr, TimeoutSec: 1}
	c := Check(m)
	if c.MonitorID != 5 {
		t.Fatalf("MonitorID 应为 5, 实际 %d", c.MonitorID)
	}
	if c.Ok != 0 {
		t.Fatalf("网络错误 Ok 应为 0, 实际 %d", c.Ok)
	}
	if c.Error == "" {
		t.Fatalf("网络错误应有错误信息")
	}
	if c.LatencyMs < 0 {
		t.Fatalf("LatencyMs 不应为负, 实际 %d", c.LatencyMs)
	}
}

func TestCheckWithRetry_失败注入_探针超时重试次数(t *testing.T) {
	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(1500 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer slow.Close()

	m := store.Monitor{ID: 6, Kind: "http", Target: slow.URL, TimeoutSec: 1, ExpectedStatus: 200}
	start := time.Now()
	c, retries := CheckWithRetry(m, 1)
	elapsed := time.Since(start)

	if retries != 1 {
		t.Fatalf("maxRetries=1 应重试 1 次, 实际 %d", retries)
	}
	if c.Ok != 0 {
		t.Fatalf("超时 Ok 应为 0, 实际 %d", c.Ok)
	}
	if c.Error == "" {
		t.Fatalf("超时应有错误信息")
	}
	if elapsed < 500*time.Millisecond {
		t.Fatalf("退避应至少 500ms, 实际 %v", elapsed)
	}
}

func TestCheckWithRetry_幂等_状态码不符不重试(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTeapot)
	}))
	defer srv.Close()

	m := store.Monitor{ID: 7, Kind: "http", Target: srv.URL, TimeoutSec: 2, ExpectedStatus: 200}
	c, retries := CheckWithRetry(m, 3)
	if retries != 0 {
		t.Fatalf("有状态码不应重试, 实际 %d", retries)
	}
	if c.Ok != 0 {
		t.Fatalf("状态码不符 Ok 应为 0, 实际 %d", c.Ok)
	}
	if !c.StatusCode.Valid {
		t.Fatalf("应保留状态码")
	}
	if c.StatusCode.Int64 != 418 {
		t.Fatalf("状态码应为 418, 实际 %d", c.StatusCode.Int64)
	}
}

// 生产默认验证 TLS 证书, httptest.NewTLSServer 使用自签名证书,
// 因此握手失败、请求被拒绝是预期行为, 该测试验证此安全默认。
func TestCheck_TLS自签名证书被拒绝(t *testing.T) {
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{ID: 8, Kind: "http", Target: srv.URL, TimeoutSec: 3, ExpectedStatus: 200}
	c := Check(m)
	if c.MonitorID != 8 {
		t.Fatalf("MonitorID 应为 8, 实际 %d", c.MonitorID)
	}
	if c.Ok != 0 {
		t.Fatalf("自签名证书应被拒绝 Ok 应为 0, 实际 %d", c.Ok)
	}
	if !strings.Contains(c.Error, "certificate") {
		t.Fatalf("错误应包含 certificate, 实际 %q", c.Error)
	}
	if c.StatusCode.Valid {
		t.Fatalf("握手失败无响应, StatusCode 不应有效, 实际 %d", c.StatusCode.Int64)
	}
	if c.LatencyMs < 0 {
		t.Fatalf("LatencyMs 不应为负, 实际 %d", c.LatencyMs)
	}
	if c.CheckedAt == "" {
		t.Fatalf("CheckedAt 不应为空")
	}
}

func TestCheck_成功_TCP连通(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	defer ln.Close()
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	m := store.Monitor{ID: 9, Kind: "tcp", Target: ln.Addr().String(), TimeoutSec: 2}
	c := Check(m)
	if c.MonitorID != 9 {
		t.Fatalf("MonitorID 应为 9, 实际 %d", c.MonitorID)
	}
	if c.Ok != 1 {
		t.Fatalf("TCP 成功 Ok 应为 1, 实际 %d, err=%s", c.Ok, c.Error)
	}
	if c.LatencyMs < 0 {
		t.Fatalf("LatencyMs 不应为负, 实际 %d", c.LatencyMs)
	}
	if c.CheckedAt == "" {
		t.Fatalf("CheckedAt 不应为空")
	}
}

func TestCheck_幂等_同目标重复检查结果一致(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{ID: 10, Kind: "http", Target: srv.URL, TimeoutSec: 2, ExpectedStatus: 200}
	first := Check(m)
	second := Check(m)
	if first.Ok != second.Ok {
		t.Fatalf("两次 Ok 应一致: %d vs %d", first.Ok, second.Ok)
	}
	if first.StatusCode != second.StatusCode {
		t.Fatalf("两次状态码应一致: %v vs %v", first.StatusCode, second.StatusCode)
	}
	if first.MonitorID != second.MonitorID {
		t.Fatalf("两次 MonitorID 应一致: %d vs %d", first.MonitorID, second.MonitorID)
	}
	if first.Ok != 1 {
		t.Fatalf("Ok 应为 1, 实际 %d", first.Ok)
	}
}

func TestCheck_并发_多goroutine结果独立(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	const n = 20
	results := make([]store.Check, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		i := i
		go func() {
			defer wg.Done()
			m := store.Monitor{ID: int64(i + 1), Kind: "http", Target: srv.URL, TimeoutSec: 5, ExpectedStatus: 200}
			results[i] = Check(m)
		}()
	}
	wg.Wait()

	for i := 0; i < n; i++ {
		c := results[i]
		if c.MonitorID != int64(i+1) {
			t.Fatalf("第 %d 个 MonitorID 应为 %d, 实际 %d", i, i+1, c.MonitorID)
		}
		if c.Ok != 1 {
			t.Fatalf("第 %d 个 Ok 应为 1, 实际 %d, err=%s", i, c.Ok, c.Error)
		}
		if !c.StatusCode.Valid {
			t.Fatalf("第 %d 个应有状态码", i)
		}
		if c.StatusCode.Int64 != 200 {
			t.Fatalf("第 %d 个状态码应为 200, 实际 %d", i, c.StatusCode.Int64)
		}
	}
}

func TestCheck_表驱动_Kind与默认值(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("默认方法应为 GET, 实际 %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cases := []struct {
		name         string
		kind         string
		method       string
		target       string
		expectedOK   int
		expectedCode int64
		hasCode      bool
	}{
		{"kind为空走http", "", "", srv.URL, 1, 200, true},
		{"kind大写HTTP", "HTTP", "", srv.URL, 1, 200, true},
		{"method小写get", "http", "get", srv.URL, 1, 200, true},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			m := store.Monitor{ID: 11, Kind: tc.kind, Method: tc.method, Target: tc.target, TimeoutSec: 3}
			c := Check(m)
			if c.MonitorID != 11 {
				t.Fatalf("MonitorID 应为 11, 实际 %d", c.MonitorID)
			}
			if c.Ok != tc.expectedOK {
				t.Fatalf("Ok 应为 %d, 实际 %d, err=%s", tc.expectedOK, c.Ok, c.Error)
			}
			if c.StatusCode.Valid != tc.hasCode {
				t.Fatalf("StatusCode.Valid 应为 %v, 实际 %v", tc.hasCode, c.StatusCode.Valid)
			}
			if tc.hasCode && c.StatusCode.Int64 != tc.expectedCode {
				t.Fatalf("状态码应为 %d, 实际 %d", tc.expectedCode, c.StatusCode.Int64)
			}
		})
	}
}

var _ = fmt.Sprintf
var _ = sql.NullInt64{}