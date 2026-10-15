// Package metrics 提供一个零外部依赖的 Prometheus 文本格式指标注册表。
// 仅暴露计数器与少量 gauge，避免引入 client_golang 等第三方依赖。
package metrics

import (
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

// Registry 是一个极简的指标注册表，内部用互斥锁保护各计数器。
type Registry struct {
	mu sync.Mutex

	// httpRequests 统计所有经过 middleware 的请求，key 为 method|route|status。
	httpRequests map[httpKey]int64
	// redirects 按 outcome 统计跳转结果。
	redirects map[string]int64
	// burnLinksBurned 统计成功执行 MarkBurned 的次数。
	burnLinksBurned int64

	// burnLinksPurged 统计 burn 销毁后彻底删除（purge）的次数。
	burnLinksPurged int64
	// rateLimitRejected 统计限流拒绝次数（供后续任务使用）。
	rateLimitRejected int64
	// startTime 记录进程启动的 unix 秒。
	startTime int64
}

type httpKey struct {
	method string
	route  string
	status string
}

// NewRegistry 创建一个新的指标注册表并记录启动时间。
func NewRegistry() *Registry {
	return &Registry{
		httpRequests: make(map[httpKey]int64),
		redirects:    make(map[string]int64),
		startTime:    time.Now().Unix(),
	}
}

// Default 是包级默认注册表，供全局使用。
var Default = NewRegistry()

// Middleware 返回一个 http middleware，捕获状态码并统计请求总数。
func (m *Registry) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ww := middleware.NewWrapResponseWriter(w, r.ProtoMajor)
		next.ServeHTTP(ww, r)

		method := r.Method
		route := "unknown"
		if rctx := chi.RouteContext(r.Context()); rctx != nil {
			if p := rctx.RoutePattern(); p != "" {
				route = p
			}
		}
		status := strconv.Itoa(ww.Status())

		m.mu.Lock()
		m.httpRequests[httpKey{method: method, route: route, status: status}]++
		m.mu.Unlock()
	})
}

// IncRedirect 记录一次跳转结果，outcome 取值 ok/gone/not_found/error。
func (m *Registry) IncRedirect(outcome string) {
	m.mu.Lock()
	m.redirects[outcome]++
	m.mu.Unlock()
}

// IncBurned 记录一次成功的阅后销毁。
func (m *Registry) IncBurned() {
	m.mu.Lock()
	m.burnLinksBurned++
	m.mu.Unlock()
}

// IncBurnPurged 记录一次 burn 销毁后的彻底删除。
func (m *Registry) IncBurnPurged() {
	m.mu.Lock()
	m.burnLinksPurged++
	m.mu.Unlock()
}

// IncRateLimitRejected 记录一次限流拒绝。
func (m *Registry) IncRateLimitRejected() {
	m.mu.Lock()
	m.rateLimitRejected++
	m.mu.Unlock()
}

// Handler 输出 Prometheus 文本格式的指标。
func (m *Registry) Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		m.mu.Lock()
		httpRequests := make(map[httpKey]int64, len(m.httpRequests))
		for k, v := range m.httpRequests {
			httpRequests[k] = v
		}
		redirects := make(map[string]int64, len(m.redirects))
		for k, v := range m.redirects {
			redirects[k] = v
		}
		burned := m.burnLinksBurned
		purged := m.burnLinksPurged
		rejected := m.rateLimitRejected
		startTime := m.startTime
		m.mu.Unlock()

		w.Header().Set("Content-Type", "text/plain; version=0.0.4")

		var b strings.Builder

		b.WriteString("# HELP linkshort_http_requests_total 所有经过 middleware 的 HTTP 请求总数。\n")
		b.WriteString("# TYPE linkshort_http_requests_total counter\n")
		keys := make([]httpKey, 0, len(httpRequests))
		for k := range httpRequests {
			keys = append(keys, k)
		}
		sort.Slice(keys, func(i, j int) bool {
			if keys[i].method != keys[j].method {
				return keys[i].method < keys[j].method
			}
			if keys[i].route != keys[j].route {
				return keys[i].route < keys[j].route
			}
			return keys[i].status < keys[j].status
		})
		for _, k := range keys {
			fmt.Fprintf(&b, "linkshort_http_requests_total{method=\"%s\",route=\"%s\",status=\"%s\"} %d\n",
				escapeLabel(k.method), escapeLabel(k.route), escapeLabel(k.status), httpRequests[k])
		}

		b.WriteString("# HELP linkshort_redirects_total 跳转结果总数，按 outcome 分组。\n")
		b.WriteString("# TYPE linkshort_redirects_total counter\n")
		outcomes := make([]string, 0, len(redirects))
		for k := range redirects {
			outcomes = append(outcomes, k)
		}
		sort.Strings(outcomes)
		for _, o := range outcomes {
			fmt.Fprintf(&b, "linkshort_redirects_total{outcome=\"%s\"} %d\n", escapeLabel(o), redirects[o])
		}

		b.WriteString("# HELP linkshort_burn_links_burned_total 成功执行阅后销毁的次数。\n")
		b.WriteString("# TYPE linkshort_burn_links_burned_total counter\n")
		fmt.Fprintf(&b, "linkshort_burn_links_burned_total %d\n", burned)

		b.WriteString("# HELP linkshort_burn_links_purged_total burn 销毁后彻底删除的次数。\n")
		b.WriteString("# TYPE linkshort_burn_links_purged_total counter\n")
		fmt.Fprintf(&b, "linkshort_burn_links_purged_total %d\n", purged)

		b.WriteString("# HELP linkshort_rate_limit_rejected_total 被限流拒绝的请求数。\n")
		b.WriteString("# TYPE linkshort_rate_limit_rejected_total counter\n")
		fmt.Fprintf(&b, "linkshort_rate_limit_rejected_total %d\n", rejected)

		b.WriteString("# HELP linkshort_process_start_time_seconds 进程启动的 unix 秒时间戳。\n")
		b.WriteString("# TYPE linkshort_process_start_time_seconds gauge\n")
		fmt.Fprintf(&b, "linkshort_process_start_time_seconds %d\n", startTime)

		_, _ = w.Write([]byte(b.String()))
	}
}

// escapeLabel 按 Prometheus 文本格式转义 label 值。
func escapeLabel(s string) string {
	s = strings.ReplaceAll(s, `\`, `\\`)
	s = strings.ReplaceAll(s, `"`, `\"`)
	s = strings.ReplaceAll(s, "\n", `\n`)
	return s
}
