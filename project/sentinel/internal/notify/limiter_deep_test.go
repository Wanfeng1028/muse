package notify

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestNewRateLimiterDisablesOnNonPositiveInput(t *testing.T) {
	cases := []struct {
		name  string
		rps   float64
		burst int
	}{
		{"rps为零", 0, 10},
		{"rps为负", -1, 10},
		{"burst为零", 10, 0},
		{"burst为负", 10, -5},
		{"rps和burst都非法", -3.5, -7},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := NewRateLimiter(tc.rps, tc.burst)
			if got != nil {
				t.Fatalf("NewRateLimiter(%v, %d) = %v, 期望 nil", tc.rps, tc.burst, got)
			}
		})
	}
}

func TestNewRateLimiterEnablesOnPositiveInput(t *testing.T) {
	l := NewRateLimiter(100, 5)
	if l == nil {
		t.Fatal("NewRateLimiter(100, 5) = nil, 期望非 nil")
	}
	if l.rps != 100 {
		t.Fatalf("rps = %v, 期望 100", l.rps)
	}
	if l.burst != 5 {
		t.Fatalf("burst = %v, 期望 5", l.burst)
	}
	if l.tokens != 5 {
		t.Fatalf("初始 tokens = %v, 期望 5", l.tokens)
	}
	if l.Rejected() != 0 {
		t.Fatalf("初始 Rejected() = %d, 期望 0", l.Rejected())
	}
}

func TestAllowConsumesFullBurstThenRejects(t *testing.T) {
	l := NewRateLimiter(0.0001, 3)
	for i := 0; i < 3; i++ {
		if !l.Allow() {
			t.Fatalf("第 %d 次 Allow() = false, 期望 true", i+1)
		}
	}
	if l.Allow() {
		t.Fatal("桶空后 Allow() = true, 期望 false")
	}
	if l.Allow() {
		t.Fatal("桶空后第二次 Allow() = true, 期望 false")
	}
	if got := l.Rejected(); got != 2 {
		t.Fatalf("Rejected() = %d, 期望 2", got)
	}
}

func TestAllowRefillsOverTime(t *testing.T) {
	l := NewRateLimiter(200, 1)
	if !l.Allow() {
		t.Fatal("首次 Allow() = false, 期望 true")
	}
	if l.Allow() {
		t.Fatal("刚耗尽时 Allow() = true, 期望 false")
	}
	if l.Rejected() != 1 {
		t.Fatalf("Rejected() = %d, 期望 1", l.Rejected())
	}
	time.Sleep(50 * time.Millisecond)
	if !l.Allow() {
		t.Fatal("等待 50ms 后 Allow() = false, 期望 true")
	}
	if got := l.Rejected(); got != 1 {
		t.Fatalf("补充后 Rejected() = %d, 期望仍为 1", got)
	}
}

func TestAllowRefillCappedAtBurst(t *testing.T) {
	l := NewRateLimiter(100, 2)
	if !l.Allow() || !l.Allow() {
		t.Fatal("前两次 Allow() 应为 true")
	}
	if l.Allow() {
		t.Fatal("耗尽后 Allow() = true, 期望 false")
	}
	time.Sleep(30 * time.Millisecond)
	if !l.Allow() {
		t.Fatal("补充后 Allow() = false, 期望 true")
	}
	if !l.Allow() {
		t.Fatal("补充后第二次 Allow() = false, 期望 true")
	}
	if l.Allow() {
		t.Fatal("补充后第三次 Allow() = true, 期望 false, 说明 tokens 超过 burst 上限")
	}
}

func TestRejectedAccumulatesAcrossManyRejects(t *testing.T) {
	l := NewRateLimiter(0.0001, 1)
	if !l.Allow() {
		t.Fatal("首次 Allow() = false, 期望 true")
	}
	const extra = 100
	for i := 0; i < extra; i++ {
		if l.Allow() {
			t.Fatalf("第 %d 次超限 Allow() = true, 期望 false", i+1)
		}
	}
	if got := l.Rejected(); got != extra {
		t.Fatalf("Rejected() = %d, 期望 %d", got, extra)
	}
}

func TestAllowIsIdempotentOnRejection(t *testing.T) {
	l := NewRateLimiter(0.0001, 1)
	if !l.Allow() {
		t.Fatal("首次 Allow() = false, 期望 true")
	}
	first := l.Allow()
	second := l.Allow()
	third := l.Allow()
	if first || second || third {
		t.Fatalf("连续三次超限结果 = (%v,%v,%v), 期望全 false", first, second, third)
	}
	if got := l.Rejected(); got != 3 {
		t.Fatalf("Rejected() = %d, 期望 3", got)
	}
}

func TestAllowRepeatedWithdrawAfterRefillIsStable(t *testing.T) {
	l := NewRateLimiter(500, 2)
	success := 0
	attempts := 0
	deadline := time.Now().Add(200 * time.Millisecond)
	for time.Now().Before(deadline) && success < 4 {
		attempts++
		if l.Allow() {
			success++
		}
	}
	if success < 4 {
		t.Fatalf("在 200ms 内仅成功 %d 次, 期望至少 4 次 (尝试 %d 次)", success, attempts)
	}
	if l.Rejected() < 0 {
		t.Fatalf("Rejected() = %d, 期望非负", l.Rejected())
	}
}

func TestAllowConcurrentGoroutinesRespectBurst(t *testing.T) {
	const burst = 50
	l := NewRateLimiter(0.0001, burst)
	const workers = 16
	var allowed int64
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < 10; j++ {
				if l.Allow() {
					atomic.AddInt64(&allowed, 1)
				}
			}
		}()
	}
	close(start)
	wg.Wait()
	if allowed > int64(burst) {
		t.Fatalf("并发下成功次数 = %d, 超过 burst = %d", allowed, burst)
	}
	if allowed != int64(burst) {
		t.Fatalf("并发下成功次数 = %d, 期望恰好 %d (无补充)", allowed, burst)
	}
	wantRejected := int64(workers*10) - int64(burst)
	if got := l.Rejected(); got != wantRejected {
		t.Fatalf("Rejected() = %d, 期望 %d", got, wantRejected)
	}
}

func TestRejectedConcurrentReadConsistency(t *testing.T) {
	l := NewRateLimiter(0.0001, 1)
	if !l.Allow() {
		t.Fatal("首次 Allow() = false, 期望 true")
	}
	const workers = 8
	const perWorker = 25
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < perWorker; j++ {
				l.Allow()
				_ = l.Rejected()
			}
		}()
	}
	close(start)
	wg.Wait()
	want := int64(workers * perWorker)
	if got := l.Rejected(); got != want {
		t.Fatalf("并发后 Rejected() = %d, 期望 %d", got, want)
	}
}

func TestConcurrentAllowAndRejectedNoRace(t *testing.T) {
	l := NewRateLimiter(1000, 20)
	const workers = 12
	var wg sync.WaitGroup
	start := make(chan struct{})
	var totalAllowed int64
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for j := 0; j < 50; j++ {
				if l.Allow() {
					atomic.AddInt64(&totalAllowed, 1)
				}
				_ = l.Rejected()
			}
		}()
	}
	close(start)
	wg.Wait()
	if totalAllowed < int64(20) {
		t.Fatalf("totalAllowed = %d, 期望至少 burst = 20", totalAllowed)
	}
	if got := l.Rejected(); got < 0 {
		t.Fatalf("Rejected() = %d, 期望非负", got)
	}
}