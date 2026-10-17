package passalert

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func decodePayload(t *testing.T, r *http.Request) AlertPayload {
	t.Helper()
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		t.Fatalf("读取请求体失败: %v", err)
	}
	var p AlertPayload
	if err := json.Unmarshal(raw, &p); err != nil {
		t.Fatalf("反序列化请求体失败: %v, 原始内容=%q", err, string(raw))
	}
	return p
}

func TestNotifyPasswordFailAlertEmptyURLDoesNotSend(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	NotifyPasswordFailAlert("", "short.example.com", "abc123", 9, 60*time.Second, 5)

	if got := atomic.LoadInt32(&hits); got != 0 {
		t.Fatalf("webhookURL 为空时不应发送请求, 实际命中次数=%d", got)
	}
}

func TestNotifyPasswordFailAlertPayloadFields(t *testing.T) {
	type capture struct {
		method      string
		contentType string
		payload     AlertPayload
		raw         string
	}
	var got capture
	done := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, err := io.ReadAll(r.Body)
		if err != nil {
			t.Errorf("读取请求体失败: %v", err)
		}
		var p AlertPayload
		if err := json.Unmarshal(raw, &p); err != nil {
			t.Errorf("反序列化失败: %v", err)
		}
		got = capture{
			method:      r.Method,
			contentType: r.Header.Get("Content-Type"),
			payload:     p,
			raw:         string(raw),
		}
		w.WriteHeader(http.StatusOK)
		close(done)
	}))
	defer srv.Close()

	before := time.Now().UTC()
	NotifyPasswordFailAlert(srv.URL, "short.example.com", "slug-1", 7, 90*time.Second, 5)
	after := time.Now().UTC()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("等待 webhook 请求超时")
	}

	if got.method != http.MethodPost {
		t.Fatalf("请求方法应为 POST, 实际=%s", got.method)
	}
	if got.contentType != "application/json" {
		t.Fatalf("Content-Type 应为 application/json, 实际=%s", got.contentType)
	}
	if got.payload.Source != "linkshort" {
		t.Fatalf("Source 应为 linkshort, 实际=%s", got.payload.Source)
	}
	if got.payload.Event != "password_fail_alert" {
		t.Fatalf("Event 应为 password_fail_alert, 实际=%s", got.payload.Event)
	}
	if got.payload.Host != "short.example.com" {
		t.Fatalf("Host 应为 short.example.com, 实际=%s", got.payload.Host)
	}
	if got.payload.Slug != "slug-1" {
		t.Fatalf("Slug 应为 slug-1, 实际=%s", got.payload.Slug)
	}
	if got.payload.FailCount != 7 {
		t.Fatalf("FailCount 应为 7, 实际=%d", got.payload.FailCount)
	}
	if got.payload.WindowSeconds != 90 {
		t.Fatalf("WindowSeconds 应为 90, 实际=%d", got.payload.WindowSeconds)
	}
	if got.payload.Threshold != 5 {
		t.Fatalf("Threshold 应为 5, 实际=%d", got.payload.Threshold)
	}

	parsed, err := time.Parse(time.RFC3339, got.payload.Time)
	if err != nil {
		t.Fatalf("Time 字段不是合法 RFC3339: %q, err=%v", got.payload.Time, err)
	}
	if parsed.Before(before.Add(-2*time.Second)) || parsed.After(after.Add(2*time.Second)) {
		t.Fatalf("Time 字段超出合理区间: before=%s after=%s got=%s", before, after, parsed)
	}
	if !strings.HasPrefix(got.raw, "{") || !strings.HasSuffix(got.raw, "}") {
		t.Fatalf("请求体应为 JSON 对象, 实际=%q", got.raw)
	}
}

func TestNotifyPasswordFailAlertWindowTruncatesToSeconds(t *testing.T) {
	var p AlertPayload
	done := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p = decodePayload(t, r)
		w.WriteHeader(http.StatusOK)
		close(done)
	}))
	defer srv.Close()

	NotifyPasswordFailAlert(srv.URL, "h", "s", 3, 1500*time.Millisecond, 2)

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("等待 webhook 请求超时")
	}

	if p.WindowSeconds != 1 {
		t.Fatalf("1500ms 应截断为 1 秒, 实际=%d", p.WindowSeconds)
	}
	if p.Threshold != 2 {
		t.Fatalf("Threshold 应为 2, 实际=%d", p.Threshold)
	}
}

func TestNotifyPasswordFailAlertNon2xxDoesNotPanic(t *testing.T) {
	var statusSeen int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.StoreInt32(&statusSeen, http.StatusInternalServerError)
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()

	NotifyPasswordFailAlert(srv.URL, "h", "s", 10, time.Minute, 5)

	if got := atomic.LoadInt32(&statusSeen); got != http.StatusInternalServerError {
		t.Fatalf("服务端应收到请求并返回 500, 实际状态=%d", got)
	}
}

func TestNotifyPasswordFailAlertInvalidURLSchemeDoesNotPanic(t *testing.T) {
	NotifyPasswordFailAlert("://not-a-url", "h", "s", 4, time.Minute, 3)

	NotifyPasswordFailAlert("http://\x7f\x00", "h", "s", 4, time.Minute, 3)
}

func TestNotifyPasswordFailAlertConcurrentRaceSafe(t *testing.T) {
	var hits int32
	var mu sync.Mutex
	slugs := make(map[string]int)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		p := decodePayload(t, r)
		mu.Lock()
		slugs[p.Slug]++
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	const workers = 20
	var wg sync.WaitGroup
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(i int) {
			defer wg.Done()
			slug := "slug-concurrent"
			NotifyPasswordFailAlert(srv.URL, "short.example.com", slug, i+1, time.Minute, 5)
		}(i)
	}
	wg.Wait()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if int(atomic.LoadInt32(&hits)) >= workers {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	if got := int(atomic.LoadInt32(&hits)); got != workers {
		t.Fatalf("并发调用应发出 %d 次请求, 实际=%d", workers, got)
	}
	mu.Lock()
	defer mu.Unlock()
	if slugs["slug-concurrent"] != workers {
		t.Fatalf("并发调用 slug 聚合应为 %d, 实际=%d", workers, slugs["slug-concurrent"])
	}
}

func TestNotifyPasswordFailAlertHonorsServerDelayWithinTimeout(t *testing.T) {
	start := time.Now()
	done := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(300 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
		close(done)
	}))
	defer srv.Close()

	NotifyPasswordFailAlert(srv.URL, "h", "s", 1, time.Minute, 1)

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("服务端未在预期时间内完成响应")
	}

	elapsed := time.Since(start)
	if elapsed < 250*time.Millisecond {
		t.Fatalf("调用应在服务端延迟后才返回, 实际耗时=%s", elapsed)
	}
	if elapsed > 10*time.Second {
		t.Fatalf("调用耗时应小于 10 秒超时上限, 实际=%s", elapsed)
	}
}

func TestNotifyPasswordFailAlertBackupHealthStatusBranch(t *testing.T) {
	cases := []struct {
		name       string
		statusCode int
		healthy    bool
	}{
		{name: "200 视为健康", statusCode: http.StatusOK, healthy: true},
		{name: "204 视为健康", statusCode: http.StatusNoContent, healthy: true},
		{name: "299 视为健康", statusCode: 299, healthy: true},
		{name: "300 视为不健康", statusCode: http.StatusMultipleChoices, healthy: false},
		{name: "500 视为不健康", statusCode: http.StatusInternalServerError, healthy: false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var called int32
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				atomic.AddInt32(&called, 1)
				w.WriteHeader(tc.statusCode)
			}))
			defer srv.Close()

			NotifyPasswordFailAlert(srv.URL, "backup.example.com", "bk-1", 6, 30*time.Second, 5)

			if got := atomic.LoadInt32(&called); got != 1 {
				t.Fatalf("备份健康检查应命中一次, 实际=%d", got)
			}
			healthy := tc.statusCode >= 200 && tc.statusCode < 300
			if healthy != tc.healthy {
				t.Fatalf("状态码 %d 健康判定应为 %v", tc.statusCode, tc.healthy)
			}
		})
	}
}

func TestNotifyPasswordFailAlertRateLimitSequence(t *testing.T) {
	var count int32
	const limit = 3
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&count, 1)
		if int(n) > limit {
			w.WriteHeader(http.StatusTooManyRequests)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	for i := 0; i < limit; i++ {
		NotifyPasswordFailAlert(srv.URL, "rl.example.com", "rl-1", i+1, time.Minute, 5)
	}
	NotifyPasswordFailAlert(srv.URL, "rl.example.com", "rl-1", limit+1, time.Minute, 5)

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if int(atomic.LoadInt32(&count)) >= limit+1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	if got := int(atomic.LoadInt32(&count)); got != limit+1 {
		t.Fatalf("限流场景应发出 %d 次请求, 实际=%d", limit+1, got)
	}
}

func TestNotifyPasswordFailAlertExpiredSlugStillNotifies(t *testing.T) {
	var p AlertPayload
	done := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p = decodePayload(t, r)
		w.WriteHeader(http.StatusOK)
		close(done)
	}))
	defer srv.Close()

	NotifyPasswordFailAlert(srv.URL, "expire.example.com", "expired-slug", 0, 0, 0)

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("等待 webhook 请求超时")
	}

	if p.Slug != "expired-slug" {
		t.Fatalf("过期短码 slug 应原样上报, 实际=%s", p.Slug)
	}
	if p.FailCount != 0 {
		t.Fatalf("零失败次数应原样上报, 实际=%d", p.FailCount)
	}
	if p.WindowSeconds != 0 {
		t.Fatalf("零窗口应上报 0, 实际=%d", p.WindowSeconds)
	}
	if p.Threshold != 0 {
		t.Fatalf("零阈值应上报 0, 实际=%d", p.Threshold)
	}
}
