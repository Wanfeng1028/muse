// Package notify 负责 webhook 通知的同步发送与持久化队列投递。
package notify

import (
	"errors"
	"sync"
	"time"
)

// ErrEnqueueRateLimited 入队被限流器拒绝时 EnqueueWebhook 返回的哨兵错误。
var ErrEnqueueRateLimited = errors.New("webhook 入队被限流拒绝")

// RateLimiter 令牌桶限流器；零值不可用，必须用 NewRateLimiter 构造。
// 入队发生在调度器后台 goroutine，没有 HTTP 请求上下文可返回 429，
// 因此超限策略为丢弃+计数+warn 日志，调用方会把 ErrEnqueueRateLimited 记入 errs 返回。
type RateLimiter struct {
	mu       sync.Mutex
	rps      float64
	burst    float64
	tokens   float64
	last     time.Time
	rejected int64
}

// NewRateLimiter 构造限流器。rps<=0 或 burst<=0 时返回 nil，表示禁用限流。
func NewRateLimiter(rps float64, burst int) *RateLimiter {
	if rps <= 0 || burst <= 0 {
		return nil
	}
	return &RateLimiter{
		rps:    rps,
		burst:  float64(burst),
		tokens: float64(burst),
		last:   time.Now(),
	}
}

// Allow 尝试取一个令牌：成功返回 true；桶空返回 false 并累计一次拒绝。
func (l *RateLimiter) Allow() bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(l.last).Seconds()
	if elapsed > 0 {
		l.tokens += elapsed * l.rps
		if l.tokens > l.burst {
			l.tokens = l.burst
		}
		l.last = now
	}
	if l.tokens >= 1 {
		l.tokens--
		return true
	}
	l.rejected++
	return false
}

// Rejected 返回累计被拒绝次数。
func (l *RateLimiter) Rejected() int64 {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.rejected
}
