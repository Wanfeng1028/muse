package notify

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"net/http/httptest"
	"regexp"
	"sync/atomic"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/metrics"
	"sentinel/internal/store"
)

// TestBreakerOpensAndSkipsDelivery 覆盖熔断器开启→跳过投递→半开恢复的全链路。
func TestBreakerOpensAndSkipsDelivery(t *testing.T) {
	raw, st, mid := newQueueTestStore(t)
	defer raw.Close()

	// 用 atomic.Bool 控制下游健康状态，初始 500。
	var healthy atomic.Bool
	healthy.Store(false)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if healthy.Load() {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	q := &QueueSender{
		Store:          st,
		MaxAttempts:    5,
		BaseBackoffSec: 1,
		Breakers:       NewBreakerRegistry(2, 150*time.Millisecond),
	}

	// 入队 3 条，event 各不相同以满足幂等去重。
	events := []string{"down-1", "down-2", "down-3"}
	ids := make([]int64, 0, 3)
	for _, ev := range events {
		if err := q.EnqueueWebhook(mid, server.URL, ev, "n", "t", "2025-01-01T00:00:00Z", "boom"); err != nil {
			t.Fatalf("enqueue %s: %v", ev, err)
		}
	}
	// 从 store 取出最近 3 条 id（按入队顺序）。
	rows, err := raw.Query(`SELECT id FROM webhook_deliveries WHERE monitor_id =? ORDER BY id ASC`, mid)
	if err != nil {
		t.Fatalf("query ids: %v", err)
	}
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			t.Fatalf("scan id: %v", err)
		}
		ids = append(ids, id)
	}
	rows.Close()
	if len(ids) != 3 {
		t.Fatalf("期望 3 条记录，实际 %d", len(ids))
	}

	ctx := context.Background()

	// 第一次 ProcessDue：前 2 条实际投递并失败（阈值 2 → 第 2 次失败后熔断开启），
	// 第 3 条因熔断已开被整条跳过。
	if err := q.ProcessDue(ctx); err != nil {
		t.Fatalf("ProcessDue #1: %v", err)
	}

	d0, err := st.GetDelivery(ids[0])
	if err != nil {
		t.Fatalf("GetDelivery #0: %v", err)
	}
	if d0.Attempt != 1 || d0.Status != "retrying" {
		t.Fatalf("记录0 期望 attempt=1 retrying，实际 attempt=%d status=%s", d0.Attempt, d0.Status)
	}
	d1, err := st.GetDelivery(ids[1])
	if err != nil {
		t.Fatalf("GetDelivery #1: %v", err)
	}
	if d1.Attempt != 1 || d1.Status != "retrying" {
		t.Fatalf("记录1 期望 attempt=1 retrying，实际 attempt=%d status=%s", d1.Attempt, d1.Status)
	}
	d2, err := st.GetDelivery(ids[2])
	if err != nil {
		t.Fatalf("GetDelivery #2: %v", err)
	}
	if d2.Attempt != 0 || d2.Status != "pending" {
		t.Fatalf("记录2 期望被跳过 attempt=0 pending，实际 attempt=%d status=%s", d2.Attempt, d2.Status)
	}

	// 断言熔断器已 open。
	if got := q.Breakers.Get(server.URL).State(); got != BreakerOpen {
		t.Fatalf("期望熔断器 open，实际 %v", got)
	}

	// 把前 2 条捞回到期，再次 ProcessDue：仍被熔断跳过，attempt 保持不变。
	resetDueToPast(t, raw, ids[0])
	resetDueToPast(t, raw, ids[1])
	if err := q.ProcessDue(ctx); err != nil {
		t.Fatalf("ProcessDue #2: %v", err)
	}
	for i := 0; i < 2; i++ {
		d, err := st.GetDelivery(ids[i])
		if err != nil {
			t.Fatalf("GetDelivery #%d (2): %v", i, err)
		}
		if d.Attempt != 1 {
			t.Fatalf("记录%d 被熔断跳过期望 attempt=1，实际 %d", i, d.Attempt)
		}
	}

	// 等待超过 openTimeout（150ms），使用 500ms 提供 ≥3 倍裕量；下游恢复 200。
	time.Sleep(500 * time.Millisecond)
	healthy.Store(true)

	// 全部 3 条捞回到期，ProcessDue：半开探测成功 → 全部 done。
	resetDueToPast(t, raw, ids[0])
	resetDueToPast(t, raw, ids[1])
	resetDueToPast(t, raw, ids[2])
	if err := q.ProcessDue(ctx); err != nil {
		t.Fatalf("ProcessDue #3: %v", err)
	}
	for i, id := range ids {
		d, err := st.GetDelivery(id)
		if err != nil {
			t.Fatalf("GetDelivery #%d (3): %v", i, err)
		}
		if d.Status != "done" {
			t.Fatalf("记录%d 期望 done，实际 %s", i, d.Status)
		}
	}

	// 熔断器回到 closed。
	if got := q.Breakers.Get(server.URL).State(); got != BreakerClosed {
		t.Fatalf("期望熔断器 closed，实际 %v", got)
	}
}

// TestLimiterAndBreakerCoexist 验证限流拒绝可被 metrics 观测，且不计入熔断失败。
func TestLimiterAndBreakerCoexist(t *testing.T) {
	raw, st, mid := newQueueTestStore(t)
	defer raw.Close()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	q := &QueueSender{
		Store: st,
		// rps 极低（1000 秒回 1 个令牌），测试期间可视为不补充，保证确定性。
		Limiter:  NewRateLimiter(0.001, 1),
		Breakers: NewBreakerRegistry(5, time.Minute),
	}

	re := regexp.MustCompile(`sentinel_webhook_enqueue_rejected_total (\d+)`)
	before := extractCounter(t, re, metrics.Default.RenderPrometheus())

	// 第一条：令牌桶 burst=1，应通过。
	if err := q.EnqueueWebhook(mid, server.URL, "down-a", "n", "t", "2025-01-01T00:00:00Z", "boom"); err != nil {
		t.Fatalf("EnqueueWebhook down-a 期望 nil，实际 %v", err)
	}
	// 第二条：桶已空，应被限流拒绝。
	if err := q.EnqueueWebhook(mid, server.URL, "down-b", "n", "t", "2025-01-01T00:00:00Z", "boom"); err != ErrEnqueueRateLimited {
		t.Fatalf("EnqueueWebhook down-b 期望 ErrEnqueueRateLimited，实际 %v", err)
	}

	after := extractCounter(t, re, metrics.Default.RenderPrometheus())
	if after-before != 1 {
		t.Fatalf("期望 enqueue_rejected 增量 1，实际 before=%d after=%d", before, after)
	}

	// 限流拒绝不计入熔断失败，熔断器仍为 closed。
	if got := q.Breakers.Get(server.URL).State(); got != BreakerClosed {
		t.Fatalf("期望熔断器 closed，实际 %v", got)
	}
}

// TestManualRetryOrthogonalToBreaker 验证手动重试与熔断器状态正交。
func TestManualRetryOrthogonalToBreaker(t *testing.T) {
	raw, st, mid := newQueueTestStore(t)
	defer raw.Close()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	q := &QueueSender{
		Store:       st,
		MaxAttempts: 1,
		Breakers:    NewBreakerRegistry(1, time.Hour),
	}

	if err := q.EnqueueWebhook(mid, server.URL, "down-x", "n", "t", "2025-01-01T00:00:00Z", "boom"); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	var id int64
	if err := raw.QueryRow(`SELECT id FROM webhook_deliveries WHERE monitor_id =? ORDER BY id DESC LIMIT 1`, mid).Scan(&id); err != nil {
		t.Fatalf("query id: %v", err)
	}

	ctx := context.Background()

	// 一次失败即达 MaxAttempts=1 → dead；同时阈值 1 触发熔断 open。
	if err := q.ProcessDue(ctx); err != nil {
		t.Fatalf("ProcessDue #1: %v", err)
	}
	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery (1): %v", err)
	}
	if d.Status != "dead" {
		t.Fatalf("期望 dead，实际 %s", d.Status)
	}
	if got := q.Breakers.Get(server.URL).State(); got != BreakerOpen {
		t.Fatalf("期望熔断器 open，实际 %v", got)
	}

	// 手动重试：store 层不受熔断影响，dead → pending。
	if err := st.RetryDelivery(id); err != nil {
		t.Fatalf("RetryDelivery 期望 nil，实际 %v", err)
	}
	d, err = st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery (2): %v", err)
	}
	if d.Status != "pending" {
		t.Fatalf("手动重试后期望 pending，实际 %s", d.Status)
	}

	// 再次 ProcessDue：仍被熔断跳过，status 保持 pending，attempt 保持 0。
	if err := q.ProcessDue(ctx); err != nil {
		t.Fatalf("ProcessDue #2: %v", err)
	}
	d, err = st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery (3): %v", err)
	}
	if d.Status != "pending" {
		t.Fatalf("熔断跳过后期望 pending，实际 %s", d.Status)
	}
	if d.Attempt != 0 {
		t.Fatalf("熔断跳过后期望 attempt=0，实际 %d", d.Attempt)
	}
}

// extractCounter 从 Prometheus 文本中提取指定正则的第一个捕获组整数值。
func extractCounter(t *testing.T, re *regexp.Regexp, text string) int {
	t.Helper()
	m := re.FindStringSubmatch(text)
	if m == nil || len(m) < 2 {
		t.Fatalf("metrics 文本中未找到匹配 %q：\n%s", re.String(), text)
	}
	var v int
	if _, err := fmt.Sscanf(m[1], "%d", &v); err != nil {
		t.Fatalf("解析计数器 %q 失败：%v", m[1], err)
	}
	return v
}

// 说明：本测试文件复用 queue_test.go 中的 newQueueTestStore / resetDueToPast；
// 上面为保持单文件可读性，未重复定义这两个 helper。
var _ = sql.ErrNoRows
var _ = db.Open
var _ = store.Delivery{}
