// Package ratelimit 提供基于令牌桶的 HTTP 限流中间件。
// 令牌桶算法说明：
//   - 每个 key 对应一个桶，桶容量为 burst；
//   - 每秒以 rps 的速率向桶中补充 token，最多补到 burst；
//   - 每次请求消耗 1 个 token，token 不足则拒绝（429）。
//
// 默认值建议：rps=20、burst=40，适合中小规模短链服务。
package ratelimit

import (
	"encoding/json"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/metrics"
)

// bucket 单个限流桶。
type bucket struct {
	tokens float64   // 当前可用 token 数
	last   time.Time // 上次补充时间
}

// Limiter 令牌桶限流器，按 IP + API Key 双维度限流。
type Limiter struct {
	mu      sync.Mutex
	buckets map[string]*bucket
	rps     float64
	burst   int
	enabled bool
	// IPFunc 取限流用的客户端 IP；为 nil 时回退到 RemoteAddr 去端口。
	// 调用方应传入信任代理感知的函数（如 handler.clientIP），不可直接信任 XFF。
	IPFunc func(r *http.Request) string
}

// New 创建限流器。
func New(rps float64, burst int, enabled bool) *Limiter {
	return &Limiter{
		buckets: make(map[string]*bucket),
		rps:     rps,
		burst:   burst,
		enabled: enabled,
	}
}

// Middleware 返回限流中间件。
func (l *Limiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !l.enabled {
			next.ServeHTTP(w, r)
			return
		}
		// 免限流路径。
		switch r.URL.Path {
		case "/metrics", "/api/health", "/api/readyz":
			next.ServeHTTP(w, r)
			return
		}
		key := l.clientKey(r)
		if !l.allow(key) {
			metrics.Default.IncRateLimitRejected()
			w.Header().Set("Retry-After", "1")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			_ = json.NewEncoder(w).Encode(map[string]string{"error": "rate limit exceeded"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

// clientKey 组装限流 key：clientIP + "|" + apiKey。
// 当未配置 AdminKey（本地开发模式）时，仅使用 clientIP。
func (l *Limiter) clientKey(r *http.Request) string {
	ip := l.ipOf(r)

	apiKey := r.Header.Get("X-API-Key")
	if apiKey == "" {
		apiKey = r.URL.Query().Get("key")
	}
	// apiKey 为空时 key 退化为 "ip|"，等价于纯 IP 维度。
	return ip + "|" + apiKey
}

// ipOf 取限流用的客户端 IP：优先用调用方注入的 IPFunc，否则回退 RemoteAddr 去端口。
func (l *Limiter) ipOf(r *http.Request) string {
	if l.IPFunc != nil {
		return l.IPFunc(r)
	}
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		return host
	}
	return r.RemoteAddr
}

// allow 尝试从桶中取一个 token。
func (l *Limiter) allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()

	// 惰性清理：桶数量过多时，删除 5 分钟未访问的桶。
	if len(l.buckets) > 4096 {
		for k, b := range l.buckets {
			if now.Sub(b.last) > 5*time.Minute {
				delete(l.buckets, k)
			}
		}
	}

	b, ok := l.buckets[key]
	if !ok {
		b = &bucket{tokens: float64(l.burst), last: now}
		l.buckets[key] = b
	} else {
		// 按经过时间补充 token。
		elapsed := now.Sub(b.last).Seconds()
		b.tokens += elapsed * l.rps
		if b.tokens > float64(l.burst) {
			b.tokens = float64(l.burst)
		}
		b.last = now
	}

	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}
