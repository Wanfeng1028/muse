package notify

import (
	"errors"
	"sync"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

// TestNewRateLimiterDisabled 校验非法参数一律返回 nil。
func TestNewRateLimiterDisabled(t *testing.T) {
	cases := []struct {
		name  string
		rps   float64
		burst int
	}{
		{"rps 为 0", 0, 10},
		{"burst 为 0", 10, 0},
		{"rps 为负", -1, 5},
		{"rps 与 burst 均为 0", 0, 0},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if l := NewRateLimiter(c.rps, c.burst); l != nil {
				t.Fatalf("NewRateLimiter(%v, %d) = %v, 期望 nil", c.rps, c.burst, l)
			}
		})
	}
}

// TestRateLimiterBurst 校验突发容量用尽后拒绝并计数。
func TestRateLimiterBurst(t *testing.T) {
	l := NewRateLimiter(1000, 3)
	if l == nil {
		t.Fatal("NewRateLimiter(1000, 3) 返回 nil")
	}
	for i := 0; i < 3; i++ {
		if !l.Allow() {
			t.Fatalf("第 %d 次 Allow 期望 true，实际 false", i+1)
		}
	}
	if l.Allow() {
		t.Fatal("第 4 次 Allow 期望 false，实际 true")
	}
	if got := l.Rejected(); got != 1 {
		t.Fatalf("Rejected() = %d, 期望 1", got)
	}
}

// TestRateLimiterRefill 校验令牌随时间补充。
func TestRateLimiterRefill(t *testing.T) {
	l := NewRateLimiter(20, 1)
	if l == nil {
		t.Fatal("NewRateLimiter(20, 1) 返回 nil")
	}
	if !l.Allow() {
		t.Fatal("第 1 次 Allow 期望 true，实际 false")
	}
	if l.Allow() {
		t.Fatal("第 2 次 Allow 期望 false，实际 true")
	}
	// 20rps 下 300ms 可补 6 个令牌，远超 1 个，裕量充足。
	time.Sleep(300 * time.Millisecond)
	if !l.Allow() {
		t.Fatal("等待补充后 Allow 期望 true，实际 false")
	}
}

// TestRateLimiterConcurrent 校验并发下无计数丢失。
func TestRateLimiterConcurrent(t *testing.T) {
	l := NewRateLimiter(100000, 1000)
	if l == nil {
		t.Fatal("NewRateLimiter(100000, 1000) 返回 nil")
	}
	const goroutines = 50
	const perGoroutine = 100
	var success int64
	var wg sync.WaitGroup
	var mu sync.Mutex
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			local := int64(0)
			for j := 0; j < perGoroutine; j++ {
				if l.Allow() {
					local++
				}
			}
			mu.Lock()
			success += local
			mu.Unlock()
		}()
	}
	wg.Wait()
	total := success + l.Rejected()
	if total != int64(goroutines*perGoroutine) {
		t.Fatalf("成功(%d)+拒绝(%d) = %d, 期望 %d", success, l.Rejected(), total, goroutines*perGoroutine)
	}
}

// TestEnqueueWebhookRateLimited 校验限流拒绝返回 ErrEnqueueRateLimited。
func TestEnqueueWebhookRateLimited(t *testing.T) {
	_, st, mid := newQueueTestStore(t)
	sender := &QueueSender{
		Store: st,
		// rps 极低（1000 秒回 1 个令牌），测试期间可视为不补充，保证确定性。
		Limiter: NewRateLimiter(0.001, 1),
	}
	if sender.Limiter == nil {
		t.Fatal("Limiter 为 nil")
	}
	err := sender.EnqueueWebhook(mid, "http://example.com/hook", "down-1", "m", "http://example.com", "2026-10-17T00:00:00Z", "")
	if err != nil {
		t.Fatalf("第 1 次 EnqueueWebhook 期望 nil，实际 %v", err)
	}
	err = sender.EnqueueWebhook(mid, "http://example.com/hook", "down-2", "m", "http://example.com", "2026-10-17T00:00:00Z", "")
	if !errors.Is(err, ErrEnqueueRateLimited) {
		t.Fatalf("第 2 次 EnqueueWebhook 期望 ErrEnqueueRateLimited，实际 %v", err)
	}
	if got := sender.Limiter.Rejected(); got != 1 {
		t.Fatalf("Rejected() = %d, 期望 1", got)
	}
}

// TestEnqueueWebhookNoLimiter 校验未配置限流器时不限流。
func TestEnqueueWebhookNoLimiter(t *testing.T) {
	_, st, mid := newQueueTestStore(t)
	sender := &QueueSender{Store: st}
	for i, ev := range []string{"ev-1", "ev-2", "ev-3"} {
		if err := sender.EnqueueWebhook(mid, "http://example.com/hook", ev, "m", "http://example.com", "2026-10-17T00:00:00Z", ""); err != nil {
			t.Fatalf("第 %d 次 EnqueueWebhook 期望 nil，实际 %v", i+1, err)
		}
	}
}

// 确保 sql 包被引用（newQueueTestStore 依赖 *sql.DB）。
var _ = db.Open
var _ = store.New
