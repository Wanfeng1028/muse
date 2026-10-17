package ratelimit

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/metrics"
)

func newRequest(method, target, remoteAddr, apiKey string) *http.Request {
	req := httptest.NewRequest(method, target, nil)
	req.RemoteAddr = remoteAddr
	if apiKey != "" {
		req.Header.Set("X-API-Key", apiKey)
	}
	return req
}

func serve(l *Limiter, req *http.Request) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	l.Middleware(next).ServeHTTP(rec, req)
	return rec
}

// 用例 1：burst 内放行，超出后 429。
func TestLimiterBurstThenReject(t *testing.T) {
	l := New(1, 3, true)
	req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.1:1234", "")

	for i := 0; i < 3; i++ {
		rec := serve(l, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("第 %d 次请求应放行，实际状态码 %d", i+1, rec.Code)
		}
		if rec.Body.String() != "ok" {
			t.Fatalf("第 %d 次响应体应为 ok，实际 %q", i+1, rec.Body.String())
		}
	}

	rec := serve(l, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("超出 burst 应返回 429，实际 %d", rec.Code)
	}
	if got := rec.Header().Get("Retry-After"); got != "1" {
		t.Fatalf("Retry-After 应为 1，实际 %q", got)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("429 响应体应为 JSON，解析失败：%v", err)
	}
	if body["error"] != "rate limit exceeded" {
		t.Fatalf("429 error 字段应为 rate limit exceeded，实际 %q", body["error"])
	}
}

// 用例 2：按时间补充 token，等一段时间后又能放行。
func TestLimiterTokenRefill(t *testing.T) {
	l := New(50, 1, true)
	req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.2:1234", "")

	first := serve(l, req)
	if first.Code != http.StatusOK {
		t.Fatalf("首次请求应放行，实际 %d", first.Code)
	}
	second := serve(l, req)
	if second.Code != http.StatusTooManyRequests {
		t.Fatalf("token 耗尽后应返回 429，实际 %d", second.Code)
	}

	time.Sleep(60 * time.Millisecond)

	third := serve(l, req)
	if third.Code != http.StatusOK {
		t.Fatalf("补充 token 后应放行，实际 %d", third.Code)
	}
	if third.Body.String() != "ok" {
		t.Fatalf("补充后响应体应为 ok，实际 %q", third.Body.String())
	}
}

// 用例 3：不同 clientIP 的桶互相独立。
func TestLimiterClientIPIsolation(t *testing.T) {
	l := New(1, 1, true)

	reqA := newRequest(http.MethodGet, "/api/shorten", "10.0.0.3:1111", "")
	reqB := newRequest(http.MethodGet, "/api/shorten", "10.0.0.4:2222", "")

	recA1 := serve(l, reqA)
	if recA1.Code != http.StatusOK {
		t.Fatalf("IP A 首次应放行，实际 %d", recA1.Code)
	}
	recA2 := serve(l, reqA)
	if recA2.Code != http.StatusTooManyRequests {
		t.Fatalf("IP A 第二次应被限流，实际 %d", recA2.Code)
	}

	recB1 := serve(l, reqB)
	if recB1.Code != http.StatusOK {
		t.Fatalf("IP B 首次应放行，实际 %d", recB1.Code)
	}
	if recB1.Body.String() != "ok" {
		t.Fatalf("IP B 首次响应体应为 ok，实际 %q", recB1.Body.String())
	}
}

// 用例 4：同一 IP 不同 API Key 的桶互相独立。
func TestLimiterAPIKeyIsolation(t *testing.T) {
	l := New(1, 1, true)

	reqK1 := newRequest(http.MethodGet, "/api/shorten", "10.0.0.5:3333", "key-1")
	reqK2 := newRequest(http.MethodGet, "/api/shorten", "10.0.0.5:3333", "key-2")

	rec1 := serve(l, reqK1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("key-1 首次应放行，实际 %d", rec1.Code)
	}
	rec2 := serve(l, reqK1)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("key-1 第二次应被限流，实际 %d", rec2.Code)
	}

	rec3 := serve(l, reqK2)
	if rec3.Code != http.StatusOK {
		t.Fatalf("key-2 首次应放行，实际 %d", rec3.Code)
	}
	if rec3.Body.String() != "ok" {
		t.Fatalf("key-2 响应体应为 ok，实际 %q", rec3.Body.String())
	}
}

// 用例 5：query key 作为 API Key 回退。
func TestLimiterQueryKeyFallback(t *testing.T) {
	l := New(1, 1, true)

	reqQ := newRequest(http.MethodGet, "/api/shorten?key=qkey-1", "10.0.0.6:4444", "")

	rec1 := serve(l, reqQ)
	if rec1.Code != http.StatusOK {
		t.Fatalf("query key 首次应放行，实际 %d", rec1.Code)
	}
	rec2 := serve(l, reqQ)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("query key 第二次应被限流，实际 %d", rec2.Code)
	}

	reqHeader := newRequest(http.MethodGet, "/api/shorten?key=qkey-1", "10.0.0.6:4444", "qkey-1")
	rec3 := serve(l, reqHeader)
	if rec3.Code != http.StatusTooManyRequests {
		t.Fatalf("header 与 query 相同 key 应共用桶被限流，实际 %d", rec3.Code)
	}
	if got := rec3.Header().Get("Content-Type"); got != "application/json" {
		t.Fatalf("429 Content-Type 应为 application/json，实际 %q", got)
	}
}

// 用例 6：免限流路径直接放行且不消耗 token。
func TestLimiterBypassPaths(t *testing.T) {
	l := New(1, 1, true)
	paths := []string{"/metrics", "/api/health", "/api/readyz"}

	for _, p := range paths {
		for i := 0; i < 5; i++ {
			req := newRequest(http.MethodGet, p, "10.0.0.7:5555", "")
			rec := serve(l, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("路径 %s 第 %d 次应放行，实际 %d", p, i+1, rec.Code)
			}
			if rec.Body.String() != "ok" {
				t.Fatalf("路径 %s 响应体应为 ok，实际 %q", p, rec.Body.String())
			}
		}
	}

	req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.7:5555", "")
	rec := serve(l, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("免限流路径未消耗 token，业务路径首次应放行，实际 %d", rec.Code)
	}
	rec2 := serve(l, req)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("业务路径第二次应被限流，实际 %d", rec2.Code)
	}
}

// 用例 7：enabled=false 时全部放行。
func TestLimiterDisabled(t *testing.T) {
	l := New(1, 1, false)

	for i := 0; i < 20; i++ {
		req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.8:6666", "")
		rec := serve(l, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("禁用限流时第 %d 次应放行，实际 %d", i+1, rec.Code)
		}
		if rec.Body.String() != "ok" {
			t.Fatalf("禁用限流时响应体应为 ok，实际 %q", rec.Body.String())
		}
	}

	if len(l.buckets) != 0 {
		t.Fatalf("禁用限流时不应创建桶，实际桶数量 %d", len(l.buckets))
	}
}

// 用例 8：429 时 metrics 计数器递增。
func TestLimiterMetricsRejected(t *testing.T) {
	l := New(1, 0, true)
	req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.9:7777", "")

	before := metrics.Default.RateLimitRejectedCount()

	rec := serve(l, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("burst=0 时请求应被限流，实际 %d", rec.Code)
	}

	after := metrics.Default.RateLimitRejectedCount()
	if after != before+1 {
		t.Fatalf("限流拒绝计数应增加 1，before=%d after=%d", before, after)
	}
	if after <= 0 {
		t.Fatalf("限流拒绝计数应为正数，实际 %d", after)
	}
}

// 用例 9：并发访问同一 key 不会超发 token。
func TestLimiterConcurrentSameKey(t *testing.T) {
	l := New(0.0001, 5, true)

	const goroutines = 40
	var wg sync.WaitGroup
	var mu sync.Mutex
	allowed := 0
	rejected := 0

	start := make(chan struct{})
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.10:8888", "")
			rec := serve(l, req)
			mu.Lock()
			if rec.Code == http.StatusOK {
				allowed++
			} else if rec.Code == http.StatusTooManyRequests {
				rejected++
			}
			mu.Unlock()
		}()
	}
	close(start)
	wg.Wait()

	if allowed != 5 {
		t.Fatalf("并发下应恰好放行 5 次，实际 %d", allowed)
	}
	if rejected != goroutines-5 {
		t.Fatalf("并发下应拒绝 %d 次，实际 %d", goroutines-5, rejected)
	}
}

// 用例 10：惰性清理删除 5 分钟未访问的桶。
func TestLimiterLazyCleanup(t *testing.T) {
	l := New(100, 10, true)

	l.mu.Lock()
	for i := 0; i < 4097; i++ {
		key := "stale-key-" + string(rune('a'+i%26)) + string(rune('0'+i%10)) + "-" + strconv.Itoa(i)
		l.buckets[key] = &bucket{tokens: 1, last: time.Now().Add(-10 * time.Minute)}
	}
	l.buckets["fresh-key"] = &bucket{tokens: 1, last: time.Now()}
	l.mu.Unlock()

	req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.11:9999", "")
	rec := serve(l, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("清理后新请求应放行，实际 %d", rec.Code)
	}

	l.mu.Lock()
	_, freshExists := l.buckets["fresh-key"]
	staleCount := 0
	for k := range l.buckets {
		if len(k) > 10 && k[:10] == "stale-key-" {
			staleCount++
		}
	}
	l.mu.Unlock()

	if !freshExists {
		t.Fatalf("未过期的 fresh-key 桶不应被删除")
	}
	if staleCount != 0 {
		t.Fatalf("过期桶应被全部删除，实际残留 %d 个", staleCount)
	}
}

// 用例 11：RemoteAddr 无端口时按原样作为 IP。
func TestLimiterRemoteAddrNoPort(t *testing.T) {
	l := New(1, 1, true)

	req := newRequest(http.MethodGet, "/api/shorten", "10.0.0.12", "")
	rec1 := serve(l, req)
	if rec1.Code != http.StatusOK {
		t.Fatalf("无端口 RemoteAddr 首次应放行，实际 %d", rec1.Code)
	}
	rec2 := serve(l, req)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("无端口 RemoteAddr 第二次应被限流，实际 %d", rec2.Code)
	}

	l.mu.Lock()
	_, ok := l.buckets["10.0.0.12|"]
	l.mu.Unlock()
	if !ok {
		t.Fatalf("桶 key 应为 10.0.0.12|，未找到对应桶")
	}
}

// 用例 12：不同端口的同 IP 共用桶（SplitHostPort 归一化）。
func TestLimiterSameIPDifferentPortSharesBucket(t *testing.T) {
	l := New(1, 1, true)

	reqA := newRequest(http.MethodGet, "/api/shorten", "10.0.0.13:1000", "")
	reqB := newRequest(http.MethodGet, "/api/shorten", "10.0.0.13:2000", "")

	rec1 := serve(l, reqA)
	if rec1.Code != http.StatusOK {
		t.Fatalf("IP 首次应放行，实际 %d", rec1.Code)
	}
	rec2 := serve(l, reqB)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("同 IP 不同端口应共用桶被限流，实际 %d", rec2.Code)
	}

	l.mu.Lock()
	count := len(l.buckets)
	l.mu.Unlock()
	if count != 1 {
		t.Fatalf("同 IP 不同端口应只有一个桶，实际 %d", count)
	}
}
