package metrics

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
)

func newTestRegistry() *Registry {
	return NewRegistry()
}

func countOccurrences(s, sub string) int {
	return strings.Count(s, sub)
}

func TestRegistryShortCodeCollisionOutcomeAggregation(t *testing.T) {
	r := newTestRegistry()

	r.IncRedirect("ok")
	r.IncRedirect("ok")
	r.IncRedirect("gone")
	r.IncRedirect("not_found")
	r.IncRedirect("error")
	r.IncRedirect("error")
	r.IncRedirect("error")

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)

	body := rec.Body.String()

	if got := countOccurrences(body, `linkshort_redirects_total{outcome="ok"} 2`); got != 1 {
		t.Fatalf("期望 outcome=ok 计数为 2 且只出现一次，实际匹配次数=%d，body=\n%s", got, body)
	}
	if got := countOccurrences(body, `linkshort_redirects_total{outcome="error"} 3`); got != 1 {
		t.Fatalf("期望 outcome=error 计数为 3 且只出现一次，实际匹配次数=%d，body=\n%s", got, body)
	}
	if got := countOccurrences(body, `linkshort_redirects_total{outcome="gone"} 1`); got != 1 {
		t.Fatalf("期望 outcome=gone 计数为 1，实际匹配次数=%d", got)
	}
	if got := countOccurrences(body, `linkshort_redirects_total{outcome="not_found"} 1`); got != 1 {
		t.Fatalf("期望 outcome=not_found 计数为 1，实际匹配次数=%d", got)
	}

	okIdx := strings.Index(body, `linkshort_redirects_total{outcome="ok"}`)
	errorIdx := strings.Index(body, `linkshort_redirects_total{outcome="error"}`)
	goneIdx := strings.Index(body, `linkshort_redirects_total{outcome="gone"}`)
	nfIdx := strings.Index(body, `linkshort_redirects_total{outcome="not_found"}`)
	if !(errorIdx < goneIdx && goneIdx < nfIdx && nfIdx < okIdx) {
		t.Fatalf("期望 outcome 按字典序 error<gone<not_found<ok 输出，实际位置 error=%d gone=%d not_found=%d ok=%d", errorIdx, goneIdx, nfIdx, okIdx)
	}
}

func TestRegistryBurnBoundaryExactCounts(t *testing.T) {
	r := newTestRegistry()

	r.IncBurned()
	r.IncBurnPurged()
	r.IncBurnPurged()
	r.IncBurned()
	r.IncBurned()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, "linkshort_burn_links_burned_total 3") {
		t.Fatalf("期望 burned 总数 3，body=\n%s", body)
	}
	if !strings.Contains(body, "linkshort_burn_links_purged_total 2") {
		t.Fatalf("期望 purged 总数 2，body=\n%s", body)
	}
	if got := countOccurrences(body, "linkshort_burn_links_burned_total 3"); got != 1 {
		t.Fatalf("burned 指标行应只出现一次，实际=%d", got)
	}
}

func TestRegistryLinksPurgedAccumulation(t *testing.T) {
	r := newTestRegistry()

	r.IncLinksPurged(1)
	r.IncLinksPurged(4)
	r.IncLinksPurged(0)
	r.IncLinksPurged(95)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, "linkshort_links_purged_total 100") {
		t.Fatalf("期望 links_purged_total 为 100，body=\n%s", body)
	}
	if got := countOccurrences(body, "linkshort_links_purged_total 100"); got != 1 {
		t.Fatalf("links_purged_total 指标行应只出现一次，实际=%d", got)
	}
}

func TestRegistryPasswordAttemptsAndFailAlerts(t *testing.T) {
	r := newTestRegistry()

	r.IncPasswordAttempt(true)
	r.IncPasswordAttempt(true)
	r.IncPasswordAttempt(false)
	r.IncPasswordAttempt(false)
	r.IncPasswordAttempt(false)
	r.IncPasswordFailAlert()
	r.IncPasswordFailAlert()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, `linkshort_password_attempts_total{result="ok"} 2`) {
		t.Fatalf("期望密码成功次数 2，body=\n%s", body)
	}
	if !strings.Contains(body, `linkshort_password_attempts_total{result="fail"} 3`) {
		t.Fatalf("期望密码失败次数 3，body=\n%s", body)
	}
	if !strings.Contains(body, "linkshort_password_fail_alerts_total 2") {
		t.Fatalf("期望密码失败告警次数 2，body=\n%s", body)
	}
	okIdx := strings.Index(body, `linkshort_password_attempts_total{result="ok"}`)
	failIdx := strings.Index(body, `linkshort_password_attempts_total{result="fail"}`)
	if !(okIdx < failIdx) {
		t.Fatalf("期望 result=ok 排在 result=fail 之前，实际 ok=%d fail=%d", okIdx, failIdx)
	}
}

func TestRegistryBackupHealthTransitions(t *testing.T) {
	r := newTestRegistry()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, "linkshort_backup_health_status 0") {
		t.Fatalf("默认应为降级状态 0，body=\n%s", body)
	}
	if !strings.Contains(body, "linkshort_backup_last_success_timestamp 0") {
		t.Fatalf("默认最近成功时间戳应为 0，body=\n%s", body)
	}

	ts := int64(1730000000)
	r.SetBackupHealth(true, ts)

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body = rec.Body.String()

	if !strings.Contains(body, "linkshort_backup_health_status 1") {
		t.Fatalf("健康备份后应为 1，body=\n%s", body)
	}
	if !strings.Contains(body, "linkshort_backup_last_success_timestamp 1730000000") {
		t.Fatalf("期望最近成功时间戳 1730000000，body=\n%s", body)
	}

	r.SetBackupHealth(false, ts+600)

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body = rec.Body.String()

	if !strings.Contains(body, "linkshort_backup_health_status 0") {
		t.Fatalf("降级后应为 0，body=\n%s", body)
	}
	if !strings.Contains(body, "linkshort_backup_last_success_timestamp 1730000600") {
		t.Fatalf("期望时间戳更新为 1730000600，body=\n%s", body)
	}
}

func TestRegistryRateLimitRejected(t *testing.T) {
	r := newTestRegistry()

	for i := 0; i < 7; i++ {
		r.IncRateLimitRejected()
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, "linkshort_rate_limit_rejected_total 7") {
		t.Fatalf("期望限流拒绝 7 次，body=\n%s", body)
	}
	if got := countOccurrences(body, "linkshort_rate_limit_rejected_total 7"); got != 1 {
		t.Fatalf("限流指标行应只出现一次，实际=%d", got)
	}
}

func TestRegistryMiddlewareCapturesRouteAndStatus(t *testing.T) {
	r := newTestRegistry()

	router := chi.NewRouter()
	router.Use(r.Middleware)
	router.Get("/s/{code}", func(w http.ResponseWriter, req *http.Request) {
		w.WriteHeader(http.StatusFound)
	})
	router.Get("/missing", func(w http.ResponseWriter, req *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	})

	srv := httptest.NewServer(router)
	defer srv.Close()

	resp1, err := http.Get(srv.URL + "/s/abc123")
	if err != nil {
		t.Fatalf("请求 /s/abc123 失败: %v", err)
	}
	resp1.Body.Close()
	resp2, err := http.Get(srv.URL + "/missing")
	if err != nil {
		t.Fatalf("请求 /missing 失败: %v", err)
	}
	resp2.Body.Close()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, `linkshort_http_requests_total{method="GET",route="/s/{code}",status="302"} 1`) {
		t.Fatalf("期望记录 /s/{code} 302，body=\n%s", body)
	}
	if !strings.Contains(body, `linkshort_http_requests_total{method="GET",route="/missing",status="404"} 1`) {
		t.Fatalf("期望记录 /missing 404，body=\n%s", body)
	}
	if got := countOccurrences(body, `linkshort_http_requests_total{method="GET",route="/s/{code}",status="302"} 1`); got != 1 {
		t.Fatalf("路由指标行应只出现一次，实际=%d", got)
	}
}

func TestRegistryConcurrentIncrementsRaceSafe(t *testing.T) {
	r := newTestRegistry()

	const workers = 32
	const perWorker = 200
	var wg sync.WaitGroup
	wg.Add(workers)

	for i := 0; i < workers; i++ {
		go func() {
			defer wg.Done()
			for j := 0; j < perWorker; j++ {
				r.IncRedirect("ok")
				r.IncBurned()
				r.IncBurnPurged()
				r.IncLinksPurged(1)
				r.IncRateLimitRejected()
				r.IncPasswordAttempt(true)
				r.IncPasswordFailAlert()
			}
		}()
	}
	wg.Wait()

	total := int64(workers * perWorker)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, `linkshort_redirects_total{outcome="ok"} `+itoa(total)) {
		t.Fatalf("期望并发后 redirects ok=%d，body=\n%s", total, body)
	}
	if !strings.Contains(body, "linkshort_burn_links_burned_total "+itoa(total)) {
		t.Fatalf("期望并发后 burned=%d，body=\n%s", total, body)
	}
	if !strings.Contains(body, "linkshort_burn_links_purged_total "+itoa(total)) {
		t.Fatalf("期望并发后 purged=%d，body=\n%s", total, body)
	}
	if !strings.Contains(body, "linkshort_links_purged_total "+itoa(total)) {
		t.Fatalf("期望并发后 links_purged=%d，body=\n%s", total, body)
	}
	if !strings.Contains(body, "linkshort_rate_limit_rejected_total "+itoa(total)) {
		t.Fatalf("期望并发后 rate_limit_rejected=%d，body=\n%s", total, body)
	}
	if !strings.Contains(body, `linkshort_password_attempts_total{result="ok"} `+itoa(total)) {
		t.Fatalf("期望并发后 password ok=%d，body=\n%s", total, body)
	}
	if !strings.Contains(body, "linkshort_password_fail_alerts_total "+itoa(total)) {
		t.Fatalf("期望并发后 password_fail_alerts=%d，body=\n%s", total, body)
	}
}

func TestRegistryHandlerContentTypeAndEscaping(t *testing.T) {
	r := newTestRegistry()

	r.IncRedirect("bad\"quote")
	r.IncRedirect("back\\slash")

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)

	if ct := rec.Header().Get("Content-Type"); ct != "text/plain; version=0.0.4" {
		t.Fatalf("期望 Content-Type=text/plain; version=0.0.4，实际=%q", ct)
	}

	body := rec.Body.String()

	if !strings.Contains(body, `linkshort_redirects_total{outcome="bad\"quote"} 1`) {
		t.Fatalf("期望转义双引号，body=\n%s", body)
	}
	if !strings.Contains(body, `linkshort_redirects_total{outcome="back\\slash"} 1`) {
		t.Fatalf("期望转义反斜杠，body=\n%s", body)
	}
}

func TestRegistryStartTimeStable(t *testing.T) {
	before := time.Now().Unix()
	r := NewRegistry()
	after := time.Now().Unix()

	if r.startTime < before || r.startTime > after {
		t.Fatalf("startTime 应在 [%d,%d] 之间，实际=%d", before, after, r.startTime)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, "linkshort_process_start_time_seconds "+itoa(r.startTime)) {
		t.Fatalf("期望暴露 start_time_seconds=%d，body=\n%s", r.startTime, body)
	}

	time.Sleep(2 * time.Millisecond)

	rec = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodGet, "/metrics", nil)
	r.Handler()(rec, req)
	body = rec.Body.String()

	if !strings.Contains(body, "linkshort_process_start_time_seconds "+itoa(r.startTime)) {
		t.Fatalf("start_time_seconds 应保持稳定=%d，body=\n%s", r.startTime, body)
	}
}

func TestDefaultRegistryIsUsable(t *testing.T) {
	if Default == nil {
		t.Fatal("包级默认注册表 Default 不应为 nil")
	}

	Default.IncRedirect("ok")
	Default.IncBurned()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	Default.Handler()(rec, req)
	body := rec.Body.String()

	if !strings.Contains(body, `linkshort_redirects_total{outcome="ok"}`) {
		t.Fatalf("默认注册表应输出 redirects 指标，body=\n%s", body)
	}
	if !strings.Contains(body, "linkshort_burn_links_burned_total") {
		t.Fatalf("默认注册表应输出 burned 指标，body=\n%s", body)
	}
	if !strings.Contains(body, "# TYPE linkshort_redirects_total counter") {
		t.Fatalf("默认注册表应输出 TYPE 行，body=\n%s", body)
	}
}

func itoa(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var buf [20]byte
	i := len(buf)
	for v > 0 {
		i--
		buf[i] = byte('0' + v%10)
		v /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
