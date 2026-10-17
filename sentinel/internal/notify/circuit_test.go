package notify

import (
	"sync"
	"testing"
	"time"
)

// TestBreakerStateString 验证各状态字符串表示
func TestBreakerStateString(t *testing.T) {
	cases := []struct {
		state BreakerState
		want  string
	}{
		{BreakerClosed, "closed"},
		{BreakerOpen, "open"},
		{BreakerHalfOpen, "half-open"},
	}
	for _, c := range cases {
		if got := c.state.String(); got != c.want {
			t.Fatalf("State %d String()=%q, want %q", c.state, got, c.want)
		}
	}
}

// TestCircuitClosedToOpen 验证连续失败达到阈值后熔断器打开
func TestCircuitClosedToOpen(t *testing.T) {
	c := NewCircuitBreaker(3, time.Minute)
	for i := 0; i < 3; i++ {
		if !c.BeforeRequest() {
			t.Fatalf("第 %d 次请求前应为 closed 放行", i+1)
		}
		c.AfterRequest(false)
	}
	if c.State() != BreakerOpen {
		t.Fatalf("3 次失败后应为 open，实际 %v", c.State())
	}
	if c.BeforeRequest() {
		t.Fatalf("open 状态下 BeforeRequest 应返回 false")
	}
}

// TestCircuitSuccessResets 验证成功会清零失败计数
func TestCircuitSuccessResets(t *testing.T) {
	c := NewCircuitBreaker(3, time.Minute)
	c.AfterRequest(false)
	c.AfterRequest(false)
	c.AfterRequest(true)
	if c.State() != BreakerClosed {
		t.Fatalf("2 失败 1 成功后应仍为 closed，实际 %v", c.State())
	}
	c.AfterRequest(false)
	c.AfterRequest(false)
	if c.State() != BreakerClosed {
		t.Fatalf("成功清零后再 2 次失败应仍为 closed，实际 %v", c.State())
	}
	c.AfterRequest(false)
	if c.State() != BreakerOpen {
		t.Fatalf("第 3 次失败后应为 open，实际 %v", c.State())
	}
}

// TestCircuitHalfOpenRecovery 验证半开探测成功后恢复 closed
func TestCircuitHalfOpenRecovery(t *testing.T) {
	c := NewCircuitBreaker(1, 100*time.Millisecond)
	c.AfterRequest(false)
	if c.State() != BreakerOpen {
		t.Fatalf("1 次失败后应为 open，实际 %v", c.State())
	}
	time.Sleep(350 * time.Millisecond)
	if !c.BeforeRequest() {
		t.Fatalf("超时后半开探测应放行")
	}
	if c.State() != BreakerHalfOpen {
		t.Fatalf("探测期间应为 half-open，实际 %v", c.State())
	}
	c.AfterRequest(true)
	if c.State() != BreakerClosed {
		t.Fatalf("半开成功后应恢复 closed，实际 %v", c.State())
	}
	if !c.BeforeRequest() {
		t.Fatalf("closed 状态应放行")
	}
}

// TestCircuitHalfOpenFailureReopens 验证半开探测失败后重新打开
func TestCircuitHalfOpenFailureReopens(t *testing.T) {
	c := NewCircuitBreaker(1, 100*time.Millisecond)
	c.AfterRequest(false)
	if c.State() != BreakerOpen {
		t.Fatalf("应为 open，实际 %v", c.State())
	}
	time.Sleep(350 * time.Millisecond)
	if !c.BeforeRequest() {
		t.Fatalf("超时后应放行半开探测")
	}
	c.AfterRequest(false)
	if c.State() != BreakerOpen {
		t.Fatalf("半开失败后应重新 open，实际 %v", c.State())
	}
	if c.BeforeRequest() {
		t.Fatalf("重新计时未过超时应拒绝")
	}
}

// TestCircuitHalfOpenSingleProbe 验证半开期间只允许一个探测请求
func TestCircuitHalfOpenSingleProbe(t *testing.T) {
	c := NewCircuitBreaker(1, 100*time.Millisecond)
	c.AfterRequest(false)
	time.Sleep(350 * time.Millisecond)
	if !c.BeforeRequest() {
		t.Fatalf("第一次探测应放行")
	}
	if c.BeforeRequest() {
		t.Fatalf("在途探测只允许一个，第二次应拒绝")
	}
	c.AfterRequest(true)
	if c.State() != BreakerClosed {
		t.Fatalf("探测成功后应 closed，实际 %v", c.State())
	}
}

// TestCircuitOpenIgnoresAfterRequest 验证 open 状态下 AfterRequest 不改变状态
func TestCircuitOpenIgnoresAfterRequest(t *testing.T) {
	c := NewCircuitBreaker(1, time.Minute)
	c.AfterRequest(false)
	if c.State() != BreakerOpen {
		t.Fatalf("应为 open，实际 %v", c.State())
	}
	c.AfterRequest(true)
	if c.State() != BreakerOpen {
		t.Fatalf("open 状态下 AfterRequest(true) 不应改变状态，实际 %v", c.State())
	}
	if c.BeforeRequest() {
		t.Fatalf("open 状态下应拒绝请求")
	}
}

// TestBreakerRegistryGet 验证按 host 归一化获取熔断器
func TestBreakerRegistryGet(t *testing.T) {
	r := NewBreakerRegistry(5, time.Minute)
	a1 := r.Get("http://a.example/x")
	a2 := r.Get("http://a.example/x")
	if a1 != a2 {
		t.Fatalf("同一 URL 两次 Get 应返回同一指针")
	}
	b := r.Get("http://b.example/y")
	if a1 == b {
		t.Fatalf("不同 host 应返回不同指针")
	}
	a3 := r.Get("http://A.EXAMPLE/x")
	a4 := r.Get("http://a.example/y")
	if a3 != a4 {
		t.Fatalf("大小写 host 应归一到同一熔断器")
	}
	defer func() {
		if recover() != nil {
			t.Fatalf("非法 URL Get 不应 panic")
		}
	}()
	_ = r.Get(":://bad url")
}

// TestBreakerRegistrySnapshot 验证快照包含所有 host 及状态
func TestBreakerRegistrySnapshot(t *testing.T) {
	r := NewBreakerRegistry(1, time.Minute)
	cb1 := r.Get("http://a.example/x")
	_ = r.Get("http://b.example/y")
	snap := r.Snapshot()
	if len(snap) != 2 {
		t.Fatalf("快照应含 2 个 key，实际 %d", len(snap))
	}
	for k, v := range snap {
		if v != BreakerClosed {
			t.Fatalf("key %q 初始应为 closed，实际 %v", k, v)
		}
	}
	cb1.AfterRequest(false)
	snap = r.Snapshot()
	found := false
	for k, v := range snap {
		if v == BreakerOpen {
			found = true
		}
		_ = k
	}
	if !found {
		t.Fatalf("阈值达到后快照应含 open 状态")
	}
}

// TestCircuitConcurrent 验证并发调用不 panic、不死锁、状态合法
func TestCircuitConcurrent(t *testing.T) {
	c := NewCircuitBreaker(5, 50*time.Millisecond)
	var wg sync.WaitGroup
	for g := 0; g < 10; g++ {
		wg.Add(1)
		go func(seed int) {
			defer wg.Done()
			for i := 0; i < 200; i++ {
				if c.BeforeRequest() {
					c.AfterRequest((i+seed)%3 != 0)
				}
				if i%17 == 0 {
					time.Sleep(time.Millisecond)
				}
			}
		}(g)
	}
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		t.Fatalf("并发测试超时，可能死锁")
	}
	st := c.State()
	if st != BreakerClosed && st != BreakerOpen && st != BreakerHalfOpen {
		t.Fatalf("最终状态非法: %v", st)
	}
}
