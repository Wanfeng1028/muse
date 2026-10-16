
// Package passalert 按 slug 统计短链密码失败次数，
// 在滑动窗口内计数达到阈值时触发一次告警。
// 仅在计数从阈值下方跨越到阈值及以上的瞬间返回 true，
// 持续超阈值不会重复触发，直到计数回落到阈值下方重新布防。
package passalert

import (
	"sync"
	"time"
)

// Tracker 按 slug 记录密码失败事件，并维护滑动窗口内的计数与告警布防状态。
type Tracker struct {
	mu        sync.Mutex
	threshold int
	window    time.Duration
	events    map[string][]time.Time
	armed     map[string]bool
}

// NewTracker 创建一个 Tracker；threshold<=0 时回落为 10，window<=0 时回落为 5 分钟。
func NewTracker(threshold int, window time.Duration) *Tracker {
	if threshold <= 0 {
		threshold = 10
	}
	if window <= 0 {
		window = 5 * time.Minute
	}
	return &Tracker{
		threshold: threshold,
		window:    window,
		events:    make(map[string][]time.Time),
		armed:     make(map[string]bool),
	}
}

// RecordFail 记录一次 slug 的密码失败事件。
// 返回 true 表示本次失败使计数从阈值下方跨越到阈值及以上，应当触发告警。
func (t *Tracker) RecordFail(slug string, now time.Time) bool {
	if slug == "" {
		return false
	}
	t.mu.Lock()
	defer t.mu.Unlock()

	cutoff := now.Add(-t.window)
	events := t.events[slug]
	trimmed := events[:0]
	for _, ts := range events {
		if ts.After(cutoff) {
			trimmed = append(trimmed, ts)
		}
	}
	trimmed = append(trimmed, now)
	t.events[slug] = trimmed

	count := len(trimmed)
	if count >= t.threshold {
		armed, ok := t.armed[slug]
		if !ok {
			armed = true
		}
		if armed {
			t.armed[slug] = false
			return true
		}
		return false
	}
	t.armed[slug] = true
	return false
}

// FailCount 返回 slug 在当前窗口内的密码失败次数，不记录新事件。
func (t *Tracker) FailCount(slug string, now time.Time) int {
	t.mu.Lock()
	defer t.mu.Unlock()

	cutoff := now.Add(-t.window)
	events := t.events[slug]
	count := 0
	for _, ts := range events {
		if ts.After(cutoff) {
			count++
		}
	}
	return count
}

// Reset 清空所有事件与布防状态，主要用于测试。
func (t *Tracker) Reset() {
	t.mu.Lock()
	t.events = make(map[string][]time.Time)
	t.armed = make(map[string]bool)
	t.mu.Unlock()
}

// Default 是包级默认 Tracker，阈值为 10，窗口为 5 分钟。
var Default = NewTracker(10, 5*time.Minute)

// Configure 按配置重建包级默认 Tracker，服务启动时调用一次。
func Configure(threshold int, window time.Duration) {
	Default = NewTracker(threshold, window)
}
