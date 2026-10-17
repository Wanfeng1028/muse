// Package metrics 提供轻量的进程内指标收集与 Prometheus 文本格式导出。
// 使用原子计数器记录关键计数，HTTP 请求按 (method,path,status) 维度统计。
package metrics

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
)

// RenderQueueBacklog 输出 webhook 投递队列积压的 Prometheus 文本指标。
// pending 与 retrying 分别为处于 pending 与 retrying 状态的投递数量。
func RenderQueueBacklog(pending, retrying int64) string {
	var b strings.Builder
	b.WriteString("# HELP sentinel_webhook_queue_backlog Number of webhook deliveries waiting in the queue, by status.\n")
	b.WriteString("# TYPE sentinel_webhook_queue_backlog gauge\n")
	fmt.Fprintf(&b, "sentinel_webhook_queue_backlog{status=\"pending\"} %d\n", pending)
	fmt.Fprintf(&b, "sentinel_webhook_queue_backlog{status=\"retrying\"} %d\n", retrying)
	return b.String()
}

// Registry 保存所有指标的原子计数器与互斥保护的 map。
type Registry struct {
	checksTotal     atomic.Int64
	checksFailed    atomic.Int64
	checksRetried   atomic.Int64
	webhooksSent    atomic.Int64
	webhookFailed   atomic.Int64
	enqueueRejected atomic.Int64

	checkLatencyMs atomic.Int64

	mu          sync.Mutex
	httpReqs    map[httpKey]int64
	httpLatency map[string]int64 // key = method + " " + path
}

type httpKey struct {
	method string
	path   string
	status int
}

// New 创建一个新的 Registry。
func New() *Registry {
	return &Registry{
		httpReqs:    make(map[httpKey]int64),
		httpLatency: make(map[string]int64),
	}
}

// Default 是全局默认 Registry 单例。
var Default = New()

// RecordCheck 记录一次检查结果。
func (m *Registry) RecordCheck(ok bool, latencyMs int64, retried bool) {
	m.checksTotal.Add(1)
	if !ok {
		m.checksFailed.Add(1)
	}
	if retried {
		m.checksRetried.Add(1)
	}
	if latencyMs > 0 {
		m.checkLatencyMs.Add(latencyMs)
	}
}

// RecordWebhook 记录一次 webhook 发送结果。
func (m *Registry) RecordWebhook(ok bool) {
	m.webhooksSent.Add(1)
	if !ok {
		m.webhookFailed.Add(1)
	}
}

// RecordEnqueueRejected 记录一次 webhook 入队被限流器拒绝。
func (m *Registry) RecordEnqueueRejected() {
	m.enqueueRejected.Add(1)
}

// RecordHTTP 记录一次 HTTP 请求。
func (m *Registry) RecordHTTP(method, path string, status int, latencyMs int64) {
	norm := normalizePath(path)
	m.mu.Lock()
	m.httpReqs[httpKey{method: method, path: norm, status: status}]++
	m.httpLatency[method+" "+norm] += latencyMs
	m.mu.Unlock()
}

var (
	idSegmentRE = regexp.MustCompile(`^\d+$`)
)

// normalizePath 将路径中的数字段替换为 :id，避免基数爆炸。
func normalizePath(path string) string {
	if path == "" {
		return "/"
	}
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	// 去掉查询串（若存在）。
	if i := strings.IndexByte(path, '?'); i >= 0 {
		path = path[:i]
	}
	parts := strings.Split(path, "/")
	for i, p := range parts {
		if p == "" {
			continue
		}
		if idSegmentRE.MatchString(p) {
			parts[i] = ":id"
		}
	}
	return strings.Join(parts, "/")
}

// Snapshot 返回当前指标的只读快照，键使用 snake_case。
func (m *Registry) Snapshot() map[string]interface{} {
	snap := map[string]interface{}{
		"checks_total":     m.checksTotal.Load(),
		"check_failures":   m.checksFailed.Load(),
		"check_retries":    m.checksRetried.Load(),
		"webhooks_sent":    m.webhooksSent.Load(),
		"webhook_failures": m.webhookFailed.Load(),
		"check_latency_ms": m.checkLatencyMs.Load(),
	}

	m.mu.Lock()
	http := make(map[string]int64, len(m.httpReqs))
	for k, v := range m.httpReqs {
		key := fmt.Sprintf("%s %s %d", k.method, k.path, k.status)
		http[key] = v
	}
	lat := make(map[string]int64, len(m.httpLatency))
	for k, v := range m.httpLatency {
		lat[k] = v
	}
	m.mu.Unlock()

	snap["http_requests"] = http
	snap["http_latency_ms"] = lat
	return snap
}

// RenderPrometheus 输出 Prometheus 文本格式。
func (m *Registry) RenderPrometheus() string {
	var b strings.Builder

	writeCounter := func(name, help string, value int64) {
		fmt.Fprintf(&b, "# HELP %s %s\n", name, help)
		fmt.Fprintf(&b, "# TYPE %s counter\n", name)
		fmt.Fprintf(&b, "%s %d\n", name, value)
	}

	writeCounter("sentinel_checks_total", "Total number of checks executed.", m.checksTotal.Load())
	writeCounter("sentinel_check_failures_total", "Total number of failed checks.", m.checksFailed.Load())
	writeCounter("sentinel_check_retries_total", "Total number of retried checks.", m.checksRetried.Load())
	writeCounter("sentinel_webhooks_sent_total", "Total number of webhook deliveries attempted.", m.webhooksSent.Load())
	writeCounter("sentinel_webhook_failures_total", "Total number of webhook delivery failures.", m.webhookFailed.Load())
	writeCounter("sentinel_webhook_enqueue_rejected_total", "Total number of webhook enqueue requests rejected by the rate limiter.", m.enqueueRejected.Load())

	m.mu.Lock()
	keys := make([]httpKey, 0, len(m.httpReqs))
	for k := range m.httpReqs {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].method != keys[j].method {
			return keys[i].method < keys[j].method
		}
		if keys[i].path != keys[j].path {
			return keys[i].path < keys[j].path
		}
		return keys[i].status < keys[j].status
	})
	values := make([]int64, len(keys))
	for i, k := range keys {
		values[i] = m.httpReqs[k]
	}
	m.mu.Unlock()

	fmt.Fprintf(&b, "# HELP sentinel_http_requests_total Total number of HTTP requests.\n")
	fmt.Fprintf(&b, "# TYPE sentinel_http_requests_total counter\n")
	for i, k := range keys {
		fmt.Fprintf(&b, "sentinel_http_requests_total{method=%q,path=%q,status=\"%d\"} %d\n",
			k.method, k.path, k.status, values[i])
	}

	return b.String()
}

// RenderBreakerStates 输出各下游熔断状态的 Prometheus 文本指标。
// states 为 host → 状态码（0=闭合，1=断开，2=半开）；空 map 时只输出 HELP/TYPE 头。
func RenderBreakerStates(states map[string]int) string {
	var b strings.Builder
	b.WriteString("# HELP sentinel_webhook_breaker_state Circuit breaker state per downstream host (0=closed, 1=open, 2=half-open).\n")
	b.WriteString("# TYPE sentinel_webhook_breaker_state gauge\n")
	hosts := make([]string, 0, len(states))
	for h := range states {
		hosts = append(hosts, h)
	}
	sort.Strings(hosts)
	for _, h := range hosts {
		fmt.Fprintf(&b, "sentinel_webhook_breaker_state{host=%q} %d\n", h, states[h])
	}
	return b.String()
}
