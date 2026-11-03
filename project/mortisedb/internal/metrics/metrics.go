// Package metrics 提供极简的 Prometheus text exposition 实现（仅标准库）。
// 支持 CounterVec / GaugeVec / SummaryVec，并发安全，输出 text/plain; version=0.0.4。
package metrics

import (
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

// BuildVersion 为暴露给 /metrics 的版本号，可由 api 层在初始化时覆盖。
var BuildVersion = "1.1.0"

// metricType 指标类型。
type metricType string

const (
	typeCounter metricType = "counter"
	typeGauge   metricType = "gauge"
	typeSummary metricType = "summary"
)

// metric 单个指标元数据与系列。
type metric struct {
	name   string
	help   string
	typ    metricType
	labels []string

	mu sync.Mutex
	// counter/gauge：labelKey -> 值
	values map[string]float64
	// summary：labelKey -> count, sum
	counts map[string]float64
	sums   map[string]float64
	// 系列出现顺序（保持输出稳定）
	order []string
}

// Registry 指标注册表。
type Registry struct {
	mu      sync.RWMutex
	metrics map[string]*metric
	order   []string
	start   time.Time
}

var (
	defaultRegistry *Registry
	defaultOnce     sync.Once
)

// Default 返回全局默认注册表。
func Default() *Registry {
	defaultOnce.Do(func() {
		defaultRegistry = NewRegistry()
	})
	return defaultRegistry
}

// NewRegistry 创建空注册表。
func NewRegistry() *Registry {
	return &Registry{
		metrics: make(map[string]*metric),
		start:   time.Now(),
	}
}

// StartTime 返回注册表创建时间。
func (r *Registry) StartTime() time.Time { return r.start }

// register 注册或返回已有指标。
func (r *Registry) register(name, help string, typ metricType, labels []string) *metric {
	r.mu.Lock()
	defer r.mu.Unlock()
	if m, ok := r.metrics[name]; ok {
		return m
	}
	m := &metric{
		name:   name,
		help:   help,
		typ:    typ,
		labels: labels,
		values: make(map[string]float64),
		counts: make(map[string]float64),
		sums:   make(map[string]float64),
	}
	r.metrics[name] = m
	r.order = append(r.order, name)
	return m
}

// RegisterCounter 注册 Counter（不存在则创建）。
func (r *Registry) RegisterCounter(name, help string, labels ...string) {
	r.register(name, help, typeCounter, labels)
}

// RegisterGauge 注册 Gauge（不存在则创建）。
func (r *Registry) RegisterGauge(name, help string, labels ...string) {
	r.register(name, help, typeGauge, labels)
}

// RegisterSummary 注册 Summary（count + sum）。
func (r *Registry) RegisterSummary(name, help string, labels ...string) {
	r.register(name, help, typeSummary, labels)
}

// labelKey 生成稳定的 label key。
func labelKey(values []string) string {
	return strings.Join(values, "\x00")
}

// valuesFromKey 反解 label key（用于输出）。
func valuesFromKey(key string, n int) []string {
	if n == 0 {
		return nil
	}
	return strings.Split(key, "\x00")
}

// escapeLabelValue 转义 Prometheus label 值中的 \、"、\n。
func escapeLabelValue(v string) string {
	var b strings.Builder
	for _, r := range v {
		switch r {
		case '\\':
			b.WriteString(`\\`)
		case '"':
			b.WriteString(`\"`)
		case '\n':
			b.WriteString(`\n`)
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

// formatLabels 输出 {a="1",b="2"} 形式的 label 集合。
func (m *metric) formatLabels(values []string) string {
	if len(m.labels) == 0 {
		return ""
	}
	var b strings.Builder
	b.WriteByte('{')
	for i, name := range m.labels {
		if i > 0 {
			b.WriteByte(',')
		}
		v := ""
		if i < len(values) {
			v = values[i]
		}
		b.WriteString(name)
		b.WriteString(`="`)
		b.WriteString(escapeLabelValue(v))
		b.WriteString(`"`)
	}
	b.WriteByte('}')
	return b.String()
}

// Inc 递增 Counter，缺省值 0 起。
func (r *Registry) Inc(name string, labels ...string) {
	r.Add(name, 1, labels...)
}

// Add 为 Counter/Gauge 增加值。
func (r *Registry) Add(name string, delta float64, labels ...string) {
	r.mu.RLock()
	m, ok := r.metrics[name]
	r.mu.RUnlock()
	if !ok {
		return
	}
	key := labelKey(labels)
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, seen := m.values[key]; !seen {
		m.order = append(m.order, key)
	}
	m.values[key] += delta
}

// Set 设置 Gauge 值。
func (r *Registry) Set(name string, value float64, labels ...string) {
	r.mu.RLock()
	m, ok := r.metrics[name]
	r.mu.RUnlock()
	if !ok {
		return
	}
	key := labelKey(labels)
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, seen := m.values[key]; !seen {
		m.order = append(m.order, key)
	}
	m.values[key] = value
}

// Observe 记录一次 Summary 观测值。
func (r *Registry) Observe(name string, value float64, labels ...string) {
	r.mu.RLock()
	m, ok := r.metrics[name]
	r.mu.RUnlock()
	if !ok {
		return
	}
	key := labelKey(labels)
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, seen := m.counts[key]; !seen {
		m.order = append(m.order, key)
	}
	m.counts[key]++
	m.sums[key] += value
}

// Render 输出 Prometheus text exposition 文本。
func (r *Registry) Render() string {
	r.mu.RLock()
	names := append([]string(nil), r.order...)
	metricsCopy := make(map[string]*metric, len(names))
	for _, n := range names {
		metricsCopy[n] = r.metrics[n]
	}
	r.mu.RUnlock()

	var b strings.Builder
	for _, name := range names {
		m := metricsCopy[name]
		if m == nil {
			continue
		}
		fmt.Fprintf(&b, "# HELP %s %s\n", m.name, m.help)
		fmt.Fprintf(&b, "# TYPE %s %s\n", m.name, m.typ)

		m.mu.Lock()
		keys := append([]string(nil), m.order...)
		values := make(map[string]float64, len(m.values))
		for k, v := range m.values {
			values[k] = v
		}
		counts := make(map[string]float64, len(m.counts))
		for k, v := range m.counts {
			counts[k] = v
		}
		sums := make(map[string]float64, len(m.sums))
		for k, v := range m.sums {
			sums[k] = v
		}
		m.mu.Unlock()

		sort.Strings(keys)

		switch m.typ {
		case typeCounter, typeGauge:
			for _, key := range keys {
				lbl := m.formatLabels(valuesFromKey(key, len(m.labels)))
				fmt.Fprintf(&b, "%s%s %s\n", m.name, lbl, formatFloat(values[key]))
			}
		case typeSummary:
			for _, key := range keys {
				lbl := m.formatLabels(valuesFromKey(key, len(m.labels)))
				// Summary 输出 _count 与 _sum 两个序列
				fmt.Fprintf(&b, "%s_count%s %s\n", m.name, lbl, formatFloat(counts[key]))
				fmt.Fprintf(&b, "%s_sum%s %s\n", m.name, lbl, formatFloat(sums[key]))
			}
		}
	}
	return b.String()
}

// formatFloat 以人类可读形式输出浮点值。
func formatFloat(v float64) string {
	if v == float64(int64(v)) {
		return fmt.Sprintf("%d", int64(v))
	}
	return fmt.Sprintf("%g", v)
}

// ---- 便捷方法：注册并初始化所有标准指标 ----

// RegisterStandard 注册 MortiseDB 标准指标集（幂等）。
func (r *Registry) RegisterStandard() {
	r.RegisterGauge("mortise_build_info", "构建版本信息，值恒为 1", "version")
	r.Set("mortise_build_info", 1, BuildVersion)

	r.RegisterCounter("mortise_sync_rows_total", "同步行数（按源/表/操作分类）", "source", "table", "op")
	r.RegisterCounter("mortise_sync_runs_total", "同步运行次数", "job", "status")
	r.RegisterGauge("mortise_sync_last_duration_seconds", "最近一次同步耗时（秒）", "source")

	r.RegisterSummary("mortise_view_duration_seconds", "视图执行耗时（秒）", "view")
	r.RegisterGauge("mortise_view_last_duration_seconds", "最近一次视图执行耗时（秒）", "view")
	r.RegisterCounter("mortise_view_refresh_total", "物化视图刷新次数", "view", "status")
	r.RegisterSummary("mortise_view_refresh_duration_seconds", "物化视图刷新耗时（秒）", "view")
	r.RegisterGauge("mortise_view_last_refresh_rows", "物化视图上次刷新行数", "view")

	r.RegisterGauge("mortise_watermark_lag_seconds", "水位线滞后秒数（抓取时计算）", "source", "table")

	r.RegisterGauge("mortise_conflicts_pending", "待处理冲突数（抓取时计算）")
	r.RegisterCounter("mortise_conflicts_total", "累计记录的冲突数")

	r.RegisterCounter("mortise_http_requests_total", "HTTP 请求总数", "method", "route", "status")
	r.RegisterSummary("mortise_http_request_duration_seconds", "HTTP 请求耗时（秒）", "method", "route")

	r.RegisterGauge("mortise_db_size_bytes", "数据库文件大小（字节）")
	r.RegisterGauge("mortise_uptime_seconds", "进程运行秒数")
}
