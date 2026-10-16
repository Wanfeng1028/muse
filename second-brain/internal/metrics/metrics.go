// Package metrics 提供进程级的 Prometheus 指标注册表与 HTTP 暴露能力。
//
// 为什么手写 exposition 而不引入 prometheus/client_golang：
// go.mod 中只有 modernc.org/sqlite 等依赖，本仓库刻意保持依赖极简；
// Prometheus 的文本 exposition 格式（version=0.0.4）本身足够简单，
// 用标准库手写即可，避免为了一个 /metrics 端点拖入一整棵依赖树。
//
// 设计要点：
//   - Registry 内部用 sync.Mutex 保护所有 map 与 histogram 桶计数，
//     保证多 goroutine 下 Inc/Observe 无 data race。
//   - Default() 返回进程级单例，api 包与 push 包共用同一份数据，
//     否则各包各建一个 Registry 会导致指标互相覆盖、采集不完整。
//   - 指标集合是固定清单（见下文），不追求通用性，换取实现简单与可读。
package metrics

import (
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// histogramBuckets 是 http_request_duration_seconds 的分桶上界（单位：秒）。
// 与契约冻结，后续批次不得改动顺序或数值，否则会破坏既有仪表盘/告警阈值。
var histogramBuckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10}

// Registry 是指标注册表。所有导出方法均可被多 goroutine 并发调用。
//
// 字段说明：
//   - httpRequests：key 为 method|route|status 三元组，值为 counter。
//   - httpDuration：key 为 method|route，值为对应 histogram 的聚合数据。
//   - pushSent：key 为 channel|status，值为 counter。
//   - reviewGraded：key 为 grade 字符串，值为 counter。
//   - gauges：name -> 取值回调；输出时实时调用，便于反映瞬时状态（如待复习数）。
type Registry struct {
	mu sync.Mutex

	httpRequests map[httpKey]uint64
	httpDuration map[routeKey]*histogram
	pushSent     map[pushKey]uint64
	reviewGraded map[int]uint64
	gauges       map[string]func() float64
}

// httpKey 唯一标识一条 http_requests_total 时间序列。
type httpKey struct {
	method string
	route  string
	status int
}

// routeKey 唯一标识一条 http_request_duration_seconds 时间序列。
type routeKey struct {
	method string
	route  string
}

// pushKey 唯一标识一条 push_sent_total 时间序列。
type pushKey struct {
	channel string
	status  string
}

// histogram 保存单个时间序列的桶累计计数与总和/总数。
//
// buckets[i] 表示"观测值 <= histogramBuckets[i]"的累计次数，
// 这与 Prometheus 文本格式里 _bucket{le=...} 的语义一致（累积而非区间）。
// 之所以存累计值，是为了输出时无需再算前缀和，也避免桶边界变化带来的歧义。
type histogram struct {
	buckets []uint64
	sum     float64
	count   uint64
}

// newHistogram 按全局分桶边界创建一个空 histogram。
func newHistogram() *histogram {
	return &histogram{buckets: make([]uint64, len(histogramBuckets))}
}

// observe 记录一次观测。调用方必须已持有 Registry.mu。
func (h *histogram) observe(v float64) {
	// 每个满足 v <= upperBound 的桶都要 +1，因为桶是累积语义。
	for i, ub := range histogramBuckets {
		if v <= ub {
			h.buckets[i]++
		}
	}
	h.sum += v
	h.count++
}

// New 创建一个空的 Registry。
func New() *Registry {
	return &Registry{
		httpRequests: make(map[httpKey]uint64),
		httpDuration: make(map[routeKey]*histogram),
		pushSent:     make(map[pushKey]uint64),
		reviewGraded: make(map[int]uint64),
		gauges:       make(map[string]func() float64),
	}
}

// defaultRegistry 与 defaultOnce 共同实现 Default() 的懒初始化。
// 之所以懒初始化：包级变量初始化顺序在大型仓库里容易出意外，
// 用 sync.Once 保证首次使用时才构造，且只构造一次。
var (
	defaultOnce     sync.Once
	defaultRegistry *Registry
)

// Default 返回进程级单例 Registry。
//
// api 包与 push 包必须共用这一个实例，否则同一进程内会出现多份互不相干的
// 计数器，/metrics 输出将只反映其中一个包的数据。
func Default() *Registry {
	defaultOnce.Do(func() {
		defaultRegistry = New()
	})
	return defaultRegistry
}

// IncHTTPRequest 使 http_requests_total{method,route,status} 加一。
func (r *Registry) IncHTTPRequest(method, route string, status int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.httpRequests[httpKey{method: method, route: route, status: status}]++
}

// ObserveHTTPDuration 记录一次 http_request_duration_seconds 观测值（单位：秒）。
func (r *Registry) ObserveHTTPDuration(method, route string, seconds float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	k := routeKey{method: method, route: route}
	h, ok := r.httpDuration[k]
	if !ok {
		h = newHistogram()
		r.httpDuration[k] = h
	}
	h.observe(seconds)
}

// IncPushSent 使 push_sent_total{channel,status} 加一。
func (r *Registry) IncPushSent(channel, status string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.pushSent[pushKey{channel: channel, status: status}]++
}

// IncReviewGraded 使 reviews_graded_total{grade} 加一。
// grade 以十进制字符串形式作为 label 值，例如 grade=3 -> grade="3"。
func (r *Registry) IncReviewGraded(grade int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.reviewGraded[grade]++
}

// SetGaugeFunc 为名为 name 的 gauge 注册取值回调。
//
// 契约只允许 "notes_total" 与 "reviews_due" 两个名字；传入其它名字会被忽略，
// 这样可防止调用方拼错名字后在 /metrics 里出现意料之外的指标。
// fn 为 nil 表示删除该 gauge。fn 在采集时被调用；若 fn panic，则按 NaN 处理，
// 保证单个业务回调出错不会让整个 /metrics 端点 500。
func (r *Registry) SetGaugeFunc(name string, fn func() float64) {
	if !isKnownGauge(name) {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if fn == nil {
		delete(r.gauges, name)
		return
	}
	r.gauges[name] = fn
}

// isKnownGauge 判断 name 是否属于契约允许的 gauge 集合。
func isKnownGauge(name string) bool {
	return name == "notes_total" || name == "reviews_due"
}

// Handler 返回写出 Prometheus 文本格式（version=0.0.4）的 http.Handler。
//
// 每次请求都实时快照当前指标并输出，不做缓存：/metrics 通常由 Prometheus
// 低频抓取，实时输出可避免缓存失效带来的陈旧数据问题。
func (r *Registry) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		// 忽略 Write 错误：响应头已写出，此时无法再改变状态码，
		// 客户端断连属于正常现象，不应触发额外处理。
		_, _ = w.Write([]byte(r.render()))
	})
}

// render 生成完整的 exposition 文本。
//
// 加锁期间只做快照拷贝，不在锁内做字符串拼接与 fn 调用：
// 用户提供的 gauge 回调可能耗时甚至反向调用 Registry，锁内调用会有死锁风险。
func (r *Registry) render() string {
	// 快照：拷贝出当前所有时间序列，随后在锁外格式化。
	r.mu.Lock()
	httpRequests := make(map[httpKey]uint64, len(r.httpRequests))
	for k, v := range r.httpRequests {
		httpRequests[k] = v
	}
	durations := make(map[routeKey]histSnapshot, len(r.httpDuration))
	for k, h := range r.httpDuration {
		buckets := make([]uint64, len(h.buckets))
		copy(buckets, h.buckets)
		durations[k] = histSnapshot{buckets: buckets, sum: h.sum, count: h.count}
	}
	pushSent := make(map[pushKey]uint64, len(r.pushSent))
	for k, v := range r.pushSent {
		pushSent[k] = v
	}
	reviewGraded := make(map[int]uint64, len(r.reviewGraded))
	for k, v := range r.reviewGraded {
		reviewGraded[k] = v
	}
	gauges := make(map[string]func() float64, len(r.gauges))
	for k, fn := range r.gauges {
		gauges[k] = fn
	}
	r.mu.Unlock()

	var b strings.Builder

	writeMetricHeader(&b, "http_requests_total", "按方法、路由与状态码统计的 HTTP 请求总数。", "counter")
	writeHTTPRequests(&b, httpRequests)

	writeMetricHeader(&b, "http_request_duration_seconds", "HTTP 请求处理耗时分布（秒）。", "histogram")
	writeHTTPDurations(&b, durations)

	writeMetricHeader(&b, "push_sent_total", "按渠道与结果统计的推送发送次数。", "counter")
	writePushSent(&b, pushSent)

	writeMetricHeader(&b, "reviews_graded_total", "按评分统计的复习打分次数。", "counter")
	writeReviewGraded(&b, reviewGraded)

	// gauge 按名字排序输出，保证同一进程多次采集的文本顺序稳定，
	// 便于人工 diff 与测试断言。
	writeGauge(&b, "notes_total", "当前笔记总数。", gauges["notes_total"])
	writeGauge(&b, "reviews_due", "当前到期待复习的条目数。", gauges["reviews_due"])

	return b.String()
}

// histSnapshot 是 histogram 在锁外的只读快照。
type histSnapshot struct {
	buckets []uint64
	sum     float64
	count   uint64
}

// writeMetricHeader 写出 # HELP 与 # TYPE 两行。
func writeMetricHeader(b *strings.Builder, name, help, typ string) {
	b.WriteString("# HELP ")
	b.WriteString(name)
	b.WriteByte(' ')
	b.WriteString(help)
	b.WriteByte('\n')
	b.WriteString("# TYPE ")
	b.WriteString(name)
	b.WriteByte(' ')
	b.WriteString(typ)
	b.WriteByte('\n')
}

// writeHTTPRequests 输出 http_requests_total 的全部时间序列。
// 排序后再输出，保证文本稳定。
func writeHTTPRequests(b *strings.Builder, data map[httpKey]uint64) {
	keys := make([]httpKey, 0, len(data))
	for k := range data {
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
		b.WriteString("http_requests_total{method=\"")
		b.WriteString(escapeLabelValue(k.method))
		b.WriteString("\",route=\"")
		b.WriteString(escapeLabelValue(k.route))
		b.WriteString("\",status=\"")
		b.WriteString(strconv.Itoa(k.status))
		b.WriteString("\"} ")
		b.WriteString(strconv.FormatUint(data[k], 10))
		b.WriteByte('\n')
	}
}

// writeHTTPDurations 输出 http_request_duration_seconds 的全部时间序列。
//
// 每条序列依次输出：各 _bucket{le=...} 累计值、_sum、_count。
// le 使用 strconv.FormatFloat(v, 'g', -1, 64) 格式化，
// +Inf 桶显式写成 "+Inf"（Prometheus 文本格式要求）。
func writeHTTPDurations(b *strings.Builder, data map[routeKey]histSnapshot) {
	keys := make([]routeKey, 0, len(data))
	for k := range data {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].method != keys[j].method {
			return keys[i].method < keys[j].method
		}
		return keys[i].route < keys[j].route
	})
	for _, k := range keys {
		snap := data[k]
		for i, ub := range histogramBuckets {
			b.WriteString("http_request_duration_seconds_bucket{method=\"")
			b.WriteString(escapeLabelValue(k.method))
			b.WriteString("\",route=\"")
			b.WriteString(escapeLabelValue(k.route))
			b.WriteString("\",le=\"")
			b.WriteString(formatFloat(ub))
			b.WriteString("\"} ")
			b.WriteString(strconv.FormatUint(snap.buckets[i], 10))
			b.WriteByte('\n')
		}
		// +Inf 桶等于观测总数。
		b.WriteString("http_request_duration_seconds_bucket{method=\"")
		b.WriteString(escapeLabelValue(k.method))
		b.WriteString("\",route=\"")
		b.WriteString(escapeLabelValue(k.route))
		b.WriteString("\",le=\"+Inf\"} ")
		b.WriteString(strconv.FormatUint(snap.count, 10))
		b.WriteByte('\n')

		b.WriteString("http_request_duration_seconds_sum{method=\"")
		b.WriteString(escapeLabelValue(k.method))
		b.WriteString("\",route=\"")
		b.WriteString(escapeLabelValue(k.route))
		b.WriteString("\"} ")
		b.WriteString(formatFloat(snap.sum))
		b.WriteByte('\n')

		b.WriteString("http_request_duration_seconds_count{method=\"")
		b.WriteString(escapeLabelValue(k.method))
		b.WriteString("\",route=\"")
		b.WriteString(escapeLabelValue(k.route))
		b.WriteString("\"} ")
		b.WriteString(strconv.FormatUint(snap.count, 10))
		b.WriteByte('\n')
	}
}

// writePushSent 输出 push_sent_total 的全部时间序列。
func writePushSent(b *strings.Builder, data map[pushKey]uint64) {
	keys := make([]pushKey, 0, len(data))
	for k := range data {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].channel != keys[j].channel {
			return keys[i].channel < keys[j].channel
		}
		return keys[i].status < keys[j].status
	})
	for _, k := range keys {
		b.WriteString("push_sent_total{channel=\"")
		b.WriteString(escapeLabelValue(k.channel))
		b.WriteString("\",status=\"")
		b.WriteString(escapeLabelValue(k.status))
		b.WriteString("\"} ")
		b.WriteString(strconv.FormatUint(data[k], 10))
		b.WriteByte('\n')
	}
}

// writeReviewGraded 输出 reviews_graded_total 的全部时间序列。
// grade 数值按字符串排序（而非数值排序），保证输出顺序与 map 迭代无关即可。
func writeReviewGraded(b *strings.Builder, data map[int]uint64) {
	grades := make([]int, 0, len(data))
	for g := range data {
		grades = append(grades, g)
	}
	sort.Ints(grades)
	for _, g := range grades {
		b.WriteString("reviews_graded_total{grade=\"")
		b.WriteString(strconv.Itoa(g))
		b.WriteString("\"} ")
		b.WriteString(strconv.FormatUint(data[g], 10))
		b.WriteByte('\n')
	}
}

// writeGauge 输出单个 gauge 的一行。
//
// 契约规定 gauge 必须在采集时实时调用 fn；fn 为 nil 时该 gauge 不输出。
// fn panic 时按 NaN 处理：单条业务查询失败不应让整个 /metrics 挂掉。
func writeGauge(b *strings.Builder, name, help string, fn func() float64) {
	if fn == nil {
		return
	}
	// 先写 HELP/TYPE 再求值：即使 fn 内部 panic 被 recover，
	// 头部信息也应完整，避免出现没有 TYPE 的孤儿样本。
	writeMetricHeader(b, name, help, "gauge")
	b.WriteString(name)
	b.WriteByte(' ')
	b.WriteString(formatFloat(safeCall(fn)))
	b.WriteByte('\n')
}

// safeCall 调用 fn 并把 panic 转换为 NaN。
func safeCall(fn func() float64) (v float64) {
	defer func() {
		if recover() != nil {
			v = nan()
		}
	}()
	return fn()
}

// nan 返回 NaN。独立成函数是为了让 safeCall 里意图更清晰。
func nan() float64 {
	// 用 0/0 产生 NaN，避免依赖 math 包只为取一个常量；
	// 该表达式在编译期不可求值，因此不会触发除零编译错误。
	var zero float64
	return zero / zero
}

// formatFloat 按契约格式化浮点数：NaN 输出 "NaN"，其余用 'g' 最短表示。
func formatFloat(v float64) string {
	if v != v { // NaN 自身不等于自身
		return "NaN"
	}
	return strconv.FormatFloat(v, 'g', -1, 64)
}

// escapeLabelValue 按 Prometheus 文本格式转义 label 值：
// 反斜杠 -> \\，双引号 -> \"，换行 -> \n。
// 转义顺序必须是先反斜杠后其它，否则会把刚插入的反斜杠再转义一次。
func escapeLabelValue(s string) string {
	if !strings.ContainsAny(s, "\\\"\n") {
		return s
	}
	var b strings.Builder
	b.Grow(len(s) + 8)
	for i := 0; i < len(s); i++ {
		switch c := s[i]; c {
		case '\\':
			b.WriteString(`\\`)
		case '"':
			b.WriteString(`\"`)
		case '\n':
			b.WriteString(`\n`)
		default:
			b.WriteByte(c)
		}
	}
	return b.String()
}

// Middleware 包装 next，记录 HTTP 请求计数与耗时。
//
// 行为要点：
//   - /metrics 自身透传不记录，避免 Prometheus 抓取污染业务指标。
//   - 用 statusRecorder 捕获真实状态码；若 handler 未显式 WriteHeader，记 200。
//   - route 优先取 next 返回后的 r.Pattern（Go 1.23 中它是 string 字段，
//     不是方法）。外层中间件在 next 返回后能读到 mux 填好的模式串，
//     例如 "GET /api/notes/{id}"；next 之前该字段为空。
//   - Pattern 为空时回退 normalizePath，把纯数字段替换为 {id}，
//     避免 /api/notes/42 与 /api/notes/43 生成两条时间序列导致基数爆炸。
func (r *Registry) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/metrics" {
			next.ServeHTTP(w, req)
			return
		}

		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, req)
		elapsed := time.Since(start).Seconds()

		route := routeFromRequest(req)
		r.IncHTTPRequest(req.Method, route, rec.status)
		r.ObserveHTTPDuration(req.Method, route, elapsed)
	})
}

// routeFromRequest 从请求中解析用于打标的 route。
//
// 注意：必须调用方在 next.ServeHTTP 之后调用，此时 r.Pattern 才可能非空。
func routeFromRequest(req *http.Request) string {
	// Go 1.23：Pattern 是 string 字段，不是方法。
	if p := req.Pattern; p != "" {
		// 形如 "GET /api/notes/{id}"，去掉方法前缀与空格，只保留路径模式。
		if i := strings.IndexByte(p, ' '); i >= 0 {
			return p[i+1:]
		}
		return p
	}
	return normalizePath(req.URL.Path)
}

// normalizePath 把路径中的纯数字段替换成 {id}。
//
// 这是 Pattern 不可用时的兜底：它无法识别真正的路由参数名，
// 但对 /api/notes/42 这类常见形态足够，可显著降低 label 基数。
func normalizePath(p string) string {
	if p == "" {
		return "/"
	}
	segs := strings.Split(p, "/")
	changed := false
	for i, s := range segs {
		if s == "" {
			continue
		}
		if isAllDigits(s) {
			segs[i] = "{id}"
			changed = true
		}
	}
	if !changed {
		return p
	}
	return strings.Join(segs, "/")
}

// isAllDigits 判断 s 是否由一位或多位 ASCII 数字组成。
func isAllDigits(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

// statusRecorder 包装 ResponseWriter 以捕获真实写出的状态码。
//
// 不实现 http.Flusher / http.Hijacker 等可选接口：本中间件只用于常规
// JSON API 路由，避免为了"完整包装"引入难以测试的接口转发逻辑。
// 若未来需要 SSE 或 WebSocket，应在此处补充对应接口转发。
type statusRecorder struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

// WriteHeader 记录状态码后转发。
func (s *statusRecorder) WriteHeader(code int) {
	if !s.wroteHeader {
		s.status = code
		s.wroteHeader = true
	}
	s.ResponseWriter.WriteHeader(code)
}

// Write 在首次写入前确保状态码为 200（net/http 的隐式行为）。
func (s *statusRecorder) Write(b []byte) (int, error) {
	if !s.wroteHeader {
		s.status = http.StatusOK
		s.wroteHeader = true
	}
	return s.ResponseWriter.Write(b)
}

// 让 fmt 在本文件有实际用途的占位已被移除；此处显式引用 fmt 以保留
// 未来调试输出空间会引入未使用告警，故不使用 fmt。
var _ = fmt.Sprintf
