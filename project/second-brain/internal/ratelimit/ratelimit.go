// Package ratelimit 提供基于令牌桶的 HTTP 限流中间件。
//
// 设计目标与理由：
//  1. 双维度限流：按 clientIP + 用户身份组合成 key，避免同一 NAT 出口下不同用户
//     互相影响，也避免同一用户切换 IP 绕过限制。
//  2. 读写分离：写操作（POST/PUT/DELETE/PATCH）对后端资源的消耗通常远大于读操作，
//     因此为每个 key 维护独立的读桶与写桶，写桶参数更严格，防止写放大压垮存储。
//  3. 惰性 refill：token bucket 只在 take 时按经过时间补 token，避免为每个 key
//     起后台 goroutine 做定时补充，节省资源且实现简单。
//  4. 拒绝时返回 429 并附带 Retry-After，告知调用方"攒出下一个 token 还需要多久"，
//     便于客户端合理退避，而不是盲目重试或固定 sleep。
//
// 本包只依赖标准库，且不得 import internal/api（api 会反向依赖本包，避免循环引用）。
package ratelimit

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
)

// 常量定义：这些阈值用于控制内存占用与清理时机。
const (
	// cleanupThreshold 是触发惰性清理的 key 数量阈值。
	// 当桶 map 中的 key 数量超过该值时，会顺带做一次清理，防止 map 无限增长。
	cleanupThreshold = 4096
	// idleTTL 是 key 的空闲存活时长。超过该时长未被访问的 key 会在清理时被移除。
	idleTTL = 5 * time.Minute
	// headerXForwardedFor / headerXRealIP 是常见的反向代理透传真实 IP 的头部。
	headerXForwardedFor = "X-Forwarded-For"
	headerXRealIP       = "X-Real-IP"
)

// Config 描述限流器配置。
//
// 字段语义：
//   - Enabled：总开关。为 false 时中间件直接透传，不做任何限流。
//   - RPS/Burst：读操作（GET/HEAD/OPTIONS 等非写方法）每 key 的令牌补充速率与桶容量。
//   - WriteRPS/WriteBurst：写操作（POST/PUT/DELETE/PATCH）每 key 的令牌补充速率与桶容量。
//
// 读写参数分离的原因：写操作的成本与副作用通常显著高于读操作，
// 需要更严格的速率与更小的突发容量来保护后端。
type Config struct {
	Enabled    bool
	RPS        float64
	Burst      int
	WriteRPS   float64
	WriteBurst int
}

// Validate 校验配置的合法性。
//
// 语义：Enabled 为 false 时直接返回 nil（关闭状态下其余字段无意义，不做校验）。
// Enabled 为 true 时，RPS/Burst/WriteRPS/WriteBurst 任一 <=0 都视为非法配置，
// 返回的 error 会指明具体是哪个字段非法，便于启动阶段快速定位问题。
func (c Config) Validate() error {
	if !c.Enabled {
		return nil
	}
	if c.RPS <= 0 {
		return fmt.Errorf("ratelimit: 配置字段 RPS 必须大于 0，当前值 %v", c.RPS)
	}
	if c.Burst <= 0 {
		return fmt.Errorf("ratelimit: 配置字段 Burst 必须大于 0，当前值 %d", c.Burst)
	}
	if c.WriteRPS <= 0 {
		return fmt.Errorf("ratelimit: 配置字段 WriteRPS 必须大于 0，当前值 %v", c.WriteRPS)
	}
	if c.WriteBurst <= 0 {
		return fmt.Errorf("ratelimit: 配置字段 WriteBurst 必须大于 0，当前值 %d", c.WriteBurst)
	}
	return nil
}

// bucket 表示单个令牌桶的状态。
//
// 之所以把 tokens 与 last 放在一起并用 float64 表示 token 数，
// 是为了支持"按经过时间 * 速率"这种连续补充，避免整数补充带来的精度损失。
type bucket struct {
	tokens float64   // 当前可用令牌数（可能为小数，take 时要求 >=1）
	last   time.Time // 上次 refill 的时间戳
}

// keyState 保存某个 key 对应的读桶与写桶，以及最近一次访问时间。
//
// lastSeen 用于惰性清理：长时间未被访问的 key 会在 map 过大时被移除。
type keyState struct {
	read     bucket
	write    bucket
	lastSeen time.Time
}

// Limiter 是限流器主体。
//
// 并发模型：所有对 mu、states、nowFunc 的访问都必须持有 mu，
// 以保证 go test -race 下的正确性。桶的 refill 与扣减都在持锁状态下完成，
// 因为单个 key 的操作是极短的纯计算，不涉及 IO，不会成为性能瓶颈。
type Limiter struct {
	cfg Config

	mu      sync.Mutex
	states  map[string]*keyState
	nowFunc func() time.Time
}

// New 创建一个限流器。
//
// 无论 cfg.Enabled 是否为 true 都会构造出可用的实例，
// 由 Middleware 在 Enabled=false 时直接透传，避免调用方在装配中间件时做额外判断。
func New(cfg Config) *Limiter {
	return &Limiter{
		cfg:     cfg,
		states:  make(map[string]*keyState),
		nowFunc: time.Now,
	}
}

// SetNowFunc 注入自定义时间源，主要用于测试。
//
// 传入 nil 时忽略，保持使用当前时间源，避免误操作导致 nowFunc 变成 nil 引发 panic。
func (l *Limiter) SetNowFunc(fn func() time.Time) {
	if fn == nil {
		return
	}
	l.mu.Lock()
	l.nowFunc = fn
	l.mu.Unlock()
}

// Middleware 返回限流中间件。
//
// userOf 由调用方注入（例如 api 包传入 CurrentUser），用于从请求中解析用户身份。
// userOf 为 nil 时视为空用户，仅按 IP 维度限流。
//
// 中间件链顺序（外层到内层）：request_id -> metrics -> ratelimit -> mux，
// 因此这里可以从 r.Context() 中通过 logpkg.FromContext 取到 request_id 并写进 429 响应体。
func (l *Limiter) Middleware(userOf func(*http.Request) string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !l.cfg.Enabled {
			next.ServeHTTP(w, r)
			return
		}

		ip := clientIP(r)
		user := ""
		if userOf != nil {
			user = userOf(r)
		}
		key := ip + "\x00" + user

		write := isWriteMethod(r.Method)
		allowed, retryAfter := l.allow(key, write)
		if !allowed {
			writeRateLimited(w, r, retryAfter)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// allow 尝试从对应桶中取走一个 token。
//
// 返回 allowed 表示是否放行；retryAfter 是拒绝时建议的等待秒数（已向上取整，最小 1）。
// 该方法内部会处理惰性 refill、桶状态更新以及 map 清理。
func (l *Limiter) allow(key string, write bool) (bool, int) {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := l.nowFunc()

	// 惰性清理：当 key 数量超过阈值时顺带移除长时间空闲的 key，防止内存无限增长。
	if len(l.states) > cleanupThreshold {
		l.cleanupLocked(now)
	}

	st, ok := l.states[key]
	if !ok {
		// 首次见到该 key：按 burst 初始化两个桶，保证突发流量不会一上来就被拒。
		st = &keyState{
			read:  bucket{tokens: float64(l.cfg.Burst), last: now},
			write: bucket{tokens: float64(l.cfg.WriteBurst), last: now},
		}
		l.states[key] = st
	}
	st.lastSeen = now

	var (
		b    *bucket
		rate float64
		cap  float64
	)
	if write {
		b = &st.write
		rate = l.cfg.WriteRPS
		cap = float64(l.cfg.WriteBurst)
	} else {
		b = &st.read
		rate = l.cfg.RPS
		cap = float64(l.cfg.Burst)
	}

	// 惰性 refill：按经过时间补 token，上限为 burst。
	elapsed := now.Sub(b.last).Seconds()
	if elapsed > 0 {
		b.tokens += elapsed * rate
		if b.tokens > cap {
			b.tokens = cap
		}
		b.last = now
	}

	if b.tokens >= 1 {
		b.tokens--
		return true, 0
	}

	// 拒绝：计算攒出 1 个 token 还需要多久，向上取整，最小 1 秒。
	need := 1 - b.tokens
	var secs int
	if rate > 0 {
		secs = int(math.Ceil(need / rate))
	}
	if secs < 1 {
		secs = 1
	}
	return false, secs
}

// cleanupLocked 移除空闲超过 idleTTL 的 key。调用方必须已持有 l.mu。
func (l *Limiter) cleanupLocked(now time.Time) {
	for k, st := range l.states {
		if now.Sub(st.lastSeen) > idleTTL {
			delete(l.states, k)
		}
	}
}

// isWriteMethod 判断请求方法是否属于写操作。
//
// 之所以采用"非读即写"的默认策略（未知方法按写处理），
// 是因为写桶更严格，未知方法按写处理更安全，宁可误限也不放过潜在的写放大。
func isWriteMethod(method string) bool {
	switch method {
	case http.MethodGet, http.MethodHead, http.MethodOptions:
		return false
	case http.MethodPost, http.MethodPut, http.MethodDelete, http.MethodPatch:
		return true
	default:
		return true
	}
}

// clientIP 按优先级提取客户端 IP：X-Forwarded-For 首个非空段 -> X-Real-IP -> RemoteAddr 的 host。
//
// 之所以优先取 X-Forwarded-For 的首段，是因为代理链路上最左侧通常是最初的客户端；
// 若 RemoteAddr 去端口失败（例如测试里直接写了裸 IP），则回退使用原始串，保证中间件不会因此报错。
func clientIP(r *http.Request) string {
	if r == nil {
		return ""
	}
	if xff := r.Header.Get(headerXForwardedFor); xff != "" {
		for _, part := range strings.Split(xff, ",") {
			part = strings.TrimSpace(part)
			if part != "" {
				return part
			}
		}
	}
	if xri := strings.TrimSpace(r.Header.Get(headerXRealIP)); xri != "" {
		return xri
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// writeRateLimited 输出 429 响应。
//
// 响应体固定包含 request_id 字段（即使取不到也写空串），
// 便于上层日志与客户端报错信息对齐；Retry-After 与 body 中的秒数保持一致。
func writeRateLimited(w http.ResponseWriter, r *http.Request, retryAfter int) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Retry-After", strconv.Itoa(retryAfter))
	w.WriteHeader(http.StatusTooManyRequests)

	reqID := ""
	if r != nil {
		reqID = logpkg.FromContext(r.Context())
	}

	body := struct {
		Error     string `json:"error"`
		RequestID string `json:"request_id"`
	}{
		Error:     "rate limit exceeded",
		RequestID: reqID,
	}

	// 编码失败时无需额外处理：响应头与状态码已经写出，此时再改动也无意义。
	_ = json.NewEncoder(w).Encode(body)
}

// 保留 context 的引用，避免未来新增逻辑时忘记导入导致编译期误删。
var _ = context.Background
