package notify

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "sentinel_test.db")
	sqldb, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("打开测试数据库失败: %v", err)
	}
	t.Cleanup(func() {
		_ = sqldb.Close()
	})
	return store.New(sqldb)
}

func newQueueSender(t *testing.T) (*QueueSender, *store.Store) {
	t.Helper()
	st := newTestStore(t)
	q := &QueueSender{Store: st}
	return q, st
}

func newMonitor(t *testing.T, st *store.Store, name string) int64 {
	t.Helper()
	mid, err := st.CreateMonitor(store.Monitor{
		Name: name, Kind: "http", Target: "http://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	return mid
}

func TestBackoffForBoundary(t *testing.T) {
	q := &QueueSender{}
	cases := []struct {
		name    string
		attempt int
		base    int64
		wantMin time.Duration
		wantMax time.Duration
	}{
		{name: "attempt 小于 1 按 1 处理", attempt: 0, base: 0, wantMin: 60 * time.Second, wantMax: 120 * time.Second},
		{name: "attempt 1 默认 base 60", attempt: 1, base: 0, wantMin: 60 * time.Second, wantMax: 120 * time.Second},
		{name: "attempt 2 默认 base 60", attempt: 2, base: 0, wantMin: 120 * time.Second, wantMax: 180 * time.Second},
		{name: "attempt 3 默认 base 60", attempt: 3, base: 0, wantMin: 240 * time.Second, wantMax: 300 * time.Second},
		{name: "自定义 base 10", attempt: 2, base: 10, wantMin: 20 * time.Second, wantMax: 30 * time.Second},
		{name: "超过 24h 被钳制", attempt: 40, base: 60, wantMin: 24 * time.Hour, wantMax: 24 * time.Hour},
		{name: "极大 attempt 不溢出", attempt: 200, base: 60, wantMin: 24 * time.Hour, wantMax: 24 * time.Hour},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			q.BaseBackoffSec = tc.base
			got := q.BackoffFor(tc.attempt)
			if got < tc.wantMin {
				t.Fatalf("退避时长偏小: got=%v want>=%v", got, tc.wantMin)
			}
			if got > tc.wantMax {
				t.Fatalf("退避时长偏大: got=%v want<=%v", got, tc.wantMax)
			}
		})
	}
}

func TestEnqueueWebhookEmptyURL(t *testing.T) {
	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "empty-url")

	if err := q.EnqueueWebhook(mid, "", "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("空 URL 应返回 nil, got=%v", err)
	}
	if err := q.EnqueueWebhook(mid, "   ", "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("纯空格 URL 应返回 nil, got=%v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("空 URL 不应入队, got=%d", len(items))
	}
}

func TestEnqueueWebhookInvalidURLAndOverlong(t *testing.T) {
	q, st := newQueueSender(t)
	midInvalid := newMonitor(t, st, "invalid-url")
	midLong := newMonitor(t, st, "long-url")

	invalidURL := "ht tp://bad url"
	if err := q.EnqueueWebhook(midInvalid, invalidURL, "firing", "n", "t", "2024-01-01T00:00:00Z", "boom"); err != nil {
		t.Fatalf("非法 URL 入队应成功(仅做持久化), got=%v", err)
	}

	longURL := "http://example.com/" + string(make([]byte, 0))
	{
		buf := make([]byte, 8192)
		for i := range buf {
			buf[i] = 'a'
		}
		longURL = "http://example.com/" + string(buf)
	}
	if err := q.EnqueueWebhook(midLong, longURL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("超长 URL 入队应成功, got=%v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("应有 2 条投递记录, got=%d", len(items))
	}
	foundInvalid := false
	foundLong := false
	for _, it := range items {
		if it.URL == invalidURL {
			foundInvalid = true
		}
		if it.URL == longURL {
			foundLong = true
		}
	}
	if !foundInvalid {
		t.Fatalf("未找到非法 URL 记录")
	}
	if !foundLong {
		t.Fatalf("未找到超长 URL 记录")
	}
}

func TestEnqueueWebhookPayloadRoundTrip(t *testing.T) {
	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "payload-round-trip")

	url := "http://127.0.0.1:1/hook"
	err := q.EnqueueWebhook(mid, url, "firing", "cpu", "host-1", "2024-05-01T00:00:00Z", "high load")
	if err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("应有 1 条记录, got=%d", len(items))
	}
	d := items[0]
	if d.URL != url {
		t.Fatalf("URL 不匹配: got=%q want=%q", d.URL, url)
	}
	if d.Event != "firing" {
		t.Fatalf("Event 不匹配: got=%q", d.Event)
	}
	if d.MonitorID != mid {
		t.Fatalf("MonitorID 不匹配: got=%d want=%d", d.MonitorID, mid)
	}
	var p map[string]any
	if err := json.Unmarshal([]byte(d.Payload), &p); err != nil {
		t.Fatalf("payload 反序列化失败: %v", err)
	}
	if p["event"] != "firing" {
		t.Fatalf("payload.event 不匹配: %v", p["event"])
	}
	if p["name"] != "cpu" {
		t.Fatalf("payload.name 不匹配: %v", p["name"])
	}
	if p["service"] != "sentinel" {
		t.Fatalf("payload.service 不匹配: %v", p["service"])
	}
}

func TestProcessDueSuccessMarksDone(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "success-done")
	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 失败: %v", err)
	}
	if got := atomic.LoadInt32(&hits); got != 1 {
		t.Fatalf("期望请求 1 次, got=%d", got)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("成功后不应再有到期投递, got=%d", len(items))
	}
}

func TestProcessDueNetworkErrorMarksRetry(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "network-error-retry")
	q.BaseBackoffSec = 1
	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 失败: %v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("网络错误后应保留 1 条重试记录, got=%d", len(items))
	}
	if items[0].Attempt != 1 {
		t.Fatalf("Attempt 应为 1, got=%d", items[0].Attempt)
	}
	if items[0].LastError == "" {
		t.Fatalf("LastError 不应为空")
	}
}

func TestProcessDueNon2xxMarksRetry(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "non2xx-retry")
	q.BaseBackoffSec = 1
	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 失败: %v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("非 2xx 后应保留 1 条重试记录, got=%d", len(items))
	}
	if items[0].Attempt != 1 {
		t.Fatalf("Attempt 应为 1, got=%d", items[0].Attempt)
	}
}

func TestProcessDueMaxAttemptsMarksFailed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "max-attempts-failed")
	q.MaxAttempts = 2
	q.BaseBackoffSec = 1
	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("第一次 ProcessDue 失败: %v", err)
	}
	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("第一次捞取失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("第一次后应保留 1 条, got=%d", len(items))
	}

	if err := st.MarkDeliveryAttempt(items[0].ID, time.Now().UTC().Add(-time.Hour).Format(time.RFC3339), "test"); err != nil {
		t.Fatalf("回拨 next_retry_at 失败: %v", err)
	}
	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("第二次 ProcessDue 失败: %v", err)
	}
	items, err = st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("第二次捞取失败: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("达到 max_attempts 后不应再有到期记录, got=%d", len(items))
	}
}

func TestProcessDueProbeTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(15 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "probe-timeout")
	q.BaseBackoffSec = 1
	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	start := time.Now()
	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 失败: %v", err)
	}
	elapsed := time.Since(start)
	if elapsed >= 14*time.Second {
		t.Fatalf("探针超时未生效, 耗时=%v", elapsed)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("超时后应保留 1 条重试记录, got=%d", len(items))
	}
}

func TestProcessDueContextCanceled(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "ctx-canceled")
	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := q.ProcessDue(ctx)
	if err == nil {
		t.Fatalf("ctx 已取消应返回错误")
	}
	if err != context.Canceled {
		t.Fatalf("错误应为 context.Canceled, got=%v", err)
	}
}

func TestEnqueueWebhookConcurrentIdempotency(t *testing.T) {
	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "concurrent-idempotency")

	const workers = 8
	const perWorker = 5
	url := "http://127.0.0.1:1/hook"

	var wg sync.WaitGroup
	errCh := make(chan error, workers*perWorker)
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perWorker; j++ {
				if err := q.EnqueueWebhook(mid, url, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
					errCh <- err
					return
				}
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("并发入队失败: %v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 1000)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("并发幂等入队应仅保留 1 行: got=%d", len(items))
	}

	seen := make(map[int64]bool)
	for _, it := range items {
		seen[it.ID] = true
	}
	if len(seen) != len(items) {
		t.Fatalf("投递记录 ID 存在重复: unique=%d total=%d", len(seen), len(items))
	}
}

func TestProcessDueConcurrentClaimNoDoubleDelivery(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	const n = 20
	for i := 0; i < n; i++ {
		mid := newMonitor(t, st, fmt.Sprintf("concurrent-claim-%d", i))
		if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
			t.Fatalf("入队失败: %v", err)
		}
	}

	var wg sync.WaitGroup
	errCh := make(chan error, 4)
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := q.ProcessDue(context.Background()); err != nil {
				errCh <- err
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("并发 ProcessDue 失败: %v", err)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 1000)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("全部成功后不应再有到期记录, got=%d", len(items))
	}
	if got := atomic.LoadInt32(&hits); got != n {
		t.Fatalf("期望请求 %d 次, got=%d", n, got)
	}
}

func TestBreakerStatesNilAndSnapshot(t *testing.T) {
	q, _ := newQueueSender(t)

	if got := q.BreakerStates(); got != nil {
		t.Fatalf("未配置熔断注册表时应返回 nil, got=%v", got)
	}

	q.Breakers = NewBreakerRegistry(3, time.Second)
	q.Breakers.Get("http://a.example.com/hook")
	q.Breakers.Get("http://b.example.com/hook")

	states := q.BreakerStates()
	if states == nil {
		t.Fatalf("配置熔断注册表后不应返回 nil")
	}
	if len(states) != 2 {
		t.Fatalf("熔断状态条目数不匹配: got=%d want=2", len(states))
	}
	for host, st := range states {
		if st != 0 {
			t.Fatalf("新建熔断器状态应为闭合(0): host=%s state=%d", host, st)
		}
	}
}

func TestProcessDueBreakerOpenSkipsDelivery(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	mid := newMonitor(t, st, "breaker-open")
	q.BaseBackoffSec = 1
	q.Breakers = NewBreakerRegistry(1, time.Hour)
	br := q.Breakers.Get(srv.URL)
	br.AfterRequest(false)

	if err := q.EnqueueWebhook(mid, srv.URL, "firing", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("入队失败: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 失败: %v", err)
	}
	if got := atomic.LoadInt32(&hits); got != 0 {
		t.Fatalf("熔断打开时不应发起请求, got=%d", got)
	}

	now := time.Now().UTC().Add(time.Hour).Format(time.RFC3339)
	items, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("捞取到期投递失败: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("熔断跳过应保留记录, got=%d", len(items))
	}
}

func TestProcessDueDBFailureReturnsError(t *testing.T) {
	q, st := newQueueSender(t)
	if err := st.Close(); err != nil {
		t.Fatalf("关闭数据库失败: %v", err)
	}

	err := q.ProcessDue(context.Background())
	if err == nil {
		t.Fatalf("数据库关闭后 ProcessDue 应返回错误")
	}
	want := "捞取到期投递失败"
	if !contains(err.Error(), want) {
		t.Fatalf("错误信息应包含 %q, got=%q", want, err.Error())
	}
}

func TestRunStopsOnContextCancel(t *testing.T) {
	q, _ := newQueueSender(t)
	q.TickSec = 1

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		q.Run(ctx)
		close(done)
	}()

	time.Sleep(100 * time.Millisecond)
	cancel()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatalf("Run 未在 ctx 取消后及时返回")
	}
}

func contains(s, sub string) bool {
	return len(sub) == 0 || (len(s) >= len(sub) && indexOf(s, sub) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

var _ = fmt.Sprintf
var _ = os.Getenv