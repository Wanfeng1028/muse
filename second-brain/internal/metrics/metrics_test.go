package metrics

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// renderBody 触发一次 Handler 请求，返回 exposition 文本内容。
// 断言均基于字符串片段匹配，避免浮点格式抖动带来的整段比较问题。
func renderBody(t *testing.T, reg *Registry) string {
	t.Helper()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	reg.Handler().ServeHTTP(rec, req)
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/plain") {
		t.Fatalf("Content-Type 不符合契约: %q", ct)
	}
	return rec.Body.String()
}

// TestExpositionHTTPRequests 覆盖计数器 HTTP 请求指标的 exposition 格式。
func TestExpositionHTTPRequests(t *testing.T) {
	reg := New()
	reg.IncHTTPRequest("GET", "/api/notes", 200)
	reg.IncHTTPRequest("GET", "/api/notes", 200)
	reg.IncHTTPRequest("GET", "/api/notes", 200)
	reg.IncHTTPRequest("POST", "/api/notes", 201)

	body := renderBody(t, reg)

	if !strings.Contains(body, "# TYPE http_requests_total counter") {
		t.Fatalf("缺少 counter 类型声明, 输出:\n%s", body)
	}
	if !strings.Contains(body, `http_requests_total{method="GET",route="/api/notes",status="200"} 3`) {
		t.Fatalf("缺少 GET 200 样本行, 输出:\n%s", body)
	}
	if !strings.Contains(body, `status="201"} 1`) {
		t.Fatalf("缺少 POST 201 样本行, 输出:\n%s", body)
	}
}

// TestExpositionLabelEscaping 覆盖 label 值中的引号与反斜杠转义。
func TestExpositionLabelEscaping(t *testing.T) {
	reg := New()
	reg.IncHTTPRequest("GET", `/api/a"b\c`, 200)

	body := renderBody(t, reg)

	if !strings.Contains(body, `route="/api/a\"b\\c"`) {
		t.Fatalf("label 转义不符合契约, 输出:\n%s", body)
	}
}

// TestHistogramBuckets 覆盖直方图桶累计、_sum 与 _count 行。
func TestHistogramBuckets(t *testing.T) {
	reg := New()
	reg.ObserveHTTPDuration("GET", "/api/notes", 0.01)
	reg.ObserveHTTPDuration("GET", "/api/notes", 0.2)
	reg.ObserveHTTPDuration("GET", "/api/notes", 5.0)

	body := renderBody(t, reg)

	// 桶累计断言：0.01 桶应包含第一个观测值。
	if !strings.Contains(body, `le="0.01"`) {
		t.Fatalf("缺少 le=0.01 桶, 输出:\n%s", body)
	}
	// 0.1 桶应累计前两个观测值（0.01 与 0.2 中的 0.01）。
	if !strings.Contains(body, `le="0.1"`) {
		t.Fatalf("缺少 le=0.1 桶, 输出:\n%s", body)
	}
	// +Inf 桶应等于观测总数。
	if !strings.Contains(body, `le="+Inf"`) {
		t.Fatalf("缺少 +Inf 桶, 输出:\n%s", body)
	}
	if !strings.Contains(body, "_sum") {
		t.Fatalf("缺少 _sum 行, 输出:\n%s", body)
	}
	if !strings.Contains(body, "_count") {
		t.Fatalf("缺少 _count 行, 输出:\n%s", body)
	}
	if !strings.Contains(body, `http_request_duration_seconds_count{method="GET",route="/api/notes"} 3`) {
		t.Fatalf("_count 不等于总数 3, 输出:\n%s", body)
	}
}

// TestGaugeFunc 覆盖 SetGaugeFunc 的正常、panic 与删除语义。
func TestGaugeFunc(t *testing.T) {
	reg := New()
	reg.SetGaugeFunc("notes_total", func() float64 { return 42 })

	body := renderBody(t, reg)
	if !strings.Contains(body, "notes_total 42") {
		t.Fatalf("gauge 未输出期望值, 输出:\n%s", body)
	}

	// panic 的 fn 应被捕获并输出 NaN，而非使 Handler 崩溃。
	reg.SetGaugeFunc("notes_total", func() float64 { panic("boom") })
	body = renderBody(t, reg)
	if !strings.Contains(body, "notes_total NaN") {
		t.Fatalf("panic 的 gauge 未输出 NaN, 输出:\n%s", body)
	}

	// nil 删除该 gauge，后续输出不应再出现 notes_total 行。
	reg.SetGaugeFunc("notes_total", nil)
	body = renderBody(t, reg)
	if strings.Contains(body, "notes_total ") {
		t.Fatalf("删除后仍出现 notes_total 行, 输出:\n%s", body)
	}
}

// TestPushSentAndReviewGraded 覆盖推送与复习评分计数器的标签格式。
func TestPushSentAndReviewGraded(t *testing.T) {
	reg := New()
	reg.IncPushSent("smtp", "sent")
	reg.IncPushSent("smtp", "failed_permanent")
	reg.IncReviewGraded(4)

	body := renderBody(t, reg)

	if !strings.Contains(body, `push_sent_total{channel="smtp",status="sent"} 1`) {
		t.Fatalf("缺少 push sent 样本行, 输出:\n%s", body)
	}
	if !strings.Contains(body, `status="failed_permanent"} 1`) {
		t.Fatalf("缺少 push failed_permanent 样本行, 输出:\n%s", body)
	}
	if !strings.Contains(body, `reviews_graded_total{grade="4"} 1`) {
		t.Fatalf("缺少 reviews_graded 样本行, 输出:\n%s", body)
	}
}

// TestMiddlewareRouteLabel 覆盖 Go 1.23 ServeMux 的 Pattern 路由标签与回退逻辑。
func TestMiddlewareRouteLabel(t *testing.T) {
	reg := New()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /items/{id}", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	handler := reg.Middleware(mux)

	// 命中已注册模式，route 应取自 Pattern 去掉方法前缀。
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/items/42", nil))
	body := renderBody(t, reg)
	if !strings.Contains(body, `route="/items/{id}"`) {
		t.Fatalf("缺少 Pattern 路由标签, 输出:\n%s", body)
	}
	if !strings.Contains(body, `status="200"`) {
		t.Fatalf("缺少 status=200, 输出:\n%s", body)
	}

	// 未注册路径返回 404，Pattern 为空时回退把数字段替换为 {id}。
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/nope/7", nil))
	body = renderBody(t, reg)
	if !strings.Contains(body, `route="/nope/{id}"`) {
		t.Fatalf("缺少回退路由标签, 输出:\n%s", body)
	}
}

// TestMiddlewareSkipsMetricsPath 覆盖 /metrics 路径直接透传、不记录样本。
func TestMiddlewareSkipsMetricsPath(t *testing.T) {
	reg := New()
	mux := http.NewServeMux()
	mux.Handle("/metrics", reg.Handler())

	handler := reg.Middleware(mux)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))

	body := renderBody(t, reg)
	if strings.Contains(body, `route="/metrics"`) {
		t.Fatalf("/metrics 不应被记录, 输出:\n%s", body)
	}
}

// TestConcurrentUse 覆盖并发读写安全性（需配合 -race 运行）。
func TestConcurrentUse(t *testing.T) {
	reg := New()
	const goroutines = 50
	const iterations = 200

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				reg.IncHTTPRequest("GET", "/api/notes", 200)
				reg.ObserveHTTPDuration("GET", "/api/notes", 0.2)
				reg.IncPushSent("smtp", "sent")
				reg.IncReviewGraded(4)
				reg.SetGaugeFunc("notes_total", func() float64 { return 42 })
			}
		}()
	}
	wg.Wait()

	body := renderBody(t, reg)
	total := goroutines * iterations

	if !strings.Contains(body, `http_requests_total{method="GET",route="/api/notes",status="200"} 10000`) {
		t.Fatalf("并发后请求计数不等于 %d, 输出:\n%s", total, body)
	}
	if !strings.Contains(body, `push_sent_total{channel="smtp",status="sent"} 10000`) {
		t.Fatalf("并发后推送计数不等于 %d, 输出:\n%s", total, body)
	}
	if !strings.Contains(body, `reviews_graded_total{grade="4"} 10000`) {
		t.Fatalf("并发后评分计数不等于 %d, 输出:\n%s", total, body)
	}
	if !strings.Contains(body, `http_request_duration_seconds_count{method="GET",route="/api/notes"} 10000`) {
		t.Fatalf("并发后直方图 _count 不等于 %d, 输出:\n%s", total, body)
	}
}

// 确保 io 被使用（renderBody 未直接引用时保留导入占位）。
var _ = io.Discard
