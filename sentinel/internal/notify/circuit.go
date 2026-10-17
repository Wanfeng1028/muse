// 本文件实现 webhook 投递熔断：按下游 host 维度统计连续失败，
// 达到阈值后断开一段时间，避免对已死的下游持续打请求。
// 与指数退避正交：退避解决"何时再试"，熔断解决"下游已死时别再打它"。
package notify

import (
	"net/url"
	"strings"
	"sync"
	"time"
)

// BreakerState 熔断器状态。
type BreakerState int

const (
	BreakerClosed   BreakerState = iota // 闭合：正常投递
	BreakerOpen                         // 断开：熔断中，拒绝投递
	BreakerHalfOpen                     // 半开：放行一个探测请求
)

// String 返回 closed/open/half-open。
func (s BreakerState) String() string {
	switch s {
	case BreakerClosed:
		return "closed"
	case BreakerOpen:
		return "open"
	case BreakerHalfOpen:
		return "half-open"
	default:
		return "unknown"
	}
}

// CircuitBreaker 单个下游的熔断器；零值不可用，必须用 NewCircuitBreaker 构造。
type CircuitBreaker struct {
	mu sync.Mutex

	failureThreshold int
	openTimeout      time.Duration

	state         BreakerState
	failures      int
	openedAt      time.Time
	probeInFlight bool
}

// NewCircuitBreaker 构造熔断器。failureThreshold<=0 则用 5；openTimeout<=0 则用 5 分钟。
func NewCircuitBreaker(failureThreshold int, openTimeout time.Duration) *CircuitBreaker {
	if failureThreshold <= 0 {
		failureThreshold = 5
	}
	if openTimeout <= 0 {
		openTimeout = 5 * time.Minute
	}
	return &CircuitBreaker{
		failureThreshold: failureThreshold,
		openTimeout:      openTimeout,
		state:            BreakerClosed,
	}
}

// BeforeRequest 投递前调用：返回 true 表示允许投递，false 表示熔断中应跳过。
// open 状态下若已超过 openTimeout 则转入 half-open 并返回 true（放行探测）。
// half-open 下同时只允许一个在途探测请求，多余的返回 false。
func (c *CircuitBreaker) BeforeRequest() bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	switch c.state {
	case BreakerClosed:
		return true
	case BreakerOpen:
		if time.Since(c.openedAt) >= c.openTimeout {
			c.state = BreakerHalfOpen
			c.probeInFlight = true
			return true
		}
		return false
	case BreakerHalfOpen:
		if c.probeInFlight {
			return false
		}
		c.probeInFlight = true
		return true
	default:
		return false
	}
}

// AfterRequest 投递后调用：ok=true 记成功，ok=false 记失败。
// closed 下连续失败达阈值 → open（记录 openedAt）；成功则清零计数。
// half-open 下成功 → closed（清零）；失败 → open（重新计时）。
// open 下调用直接忽略（防御性）。
func (c *CircuitBreaker) AfterRequest(ok bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	switch c.state {
	case BreakerClosed:
		if ok {
			c.failures = 0
			return
		}
		c.failures++
		if c.failures >= c.failureThreshold {
			c.state = BreakerOpen
			c.openedAt = time.Now()
			c.probeInFlight = false
		}
	case BreakerHalfOpen:
		c.probeInFlight = false
		if ok {
			c.state = BreakerClosed
			c.failures = 0
			return
		}
		c.state = BreakerOpen
		c.openedAt = time.Now()
	case BreakerOpen:
		// 防御性：open 状态下忽略回调。
	}
}

// State 返回当前状态。
func (c *CircuitBreaker) State() BreakerState {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.state
}

// BreakerRegistry 按下游 host 持有熔断器；并发安全。
type BreakerRegistry struct {
	mu sync.Mutex

	failureThreshold int
	openTimeout      time.Duration
	breakers         map[string]*CircuitBreaker
}

// NewBreakerRegistry 构造注册表（参数语义同 NewCircuitBreaker）。
func NewBreakerRegistry(failureThreshold int, openTimeout time.Duration) *BreakerRegistry {
	if failureThreshold <= 0 {
		failureThreshold = 5
	}
	if openTimeout <= 0 {
		openTimeout = 5 * time.Minute
	}
	return &BreakerRegistry{
		failureThreshold: failureThreshold,
		openTimeout:      openTimeout,
		breakers:         make(map[string]*CircuitBreaker),
	}
}

// Get 按 URL 取或创建该下游 host 的熔断器。host 取 URL 的 hostname 小写；
// URL 解析失败时用整个 URL 字符串作 key（不崩溃）。
func (r *BreakerRegistry) Get(urlStr string) *CircuitBreaker {
	key := urlStr
	if u, err := url.Parse(urlStr); err == nil && u.Hostname() != "" {
		key = strings.ToLower(u.Hostname())
	}

	r.mu.Lock()
	defer r.mu.Unlock()
	if br, ok := r.breakers[key]; ok {
		return br
	}
	br := NewCircuitBreaker(r.failureThreshold, r.openTimeout)
	r.breakers[key] = br
	return br
}

// Snapshot 返回 host → 状态 的快照（用于指标导出）。
func (r *BreakerRegistry) Snapshot() map[string]BreakerState {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make(map[string]BreakerState, len(r.breakers))
	for host, br := range r.breakers {
		out[host] = br.State()
	}
	return out
}
