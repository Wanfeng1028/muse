package notify

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// 覆盖 Send 的核心边界与失败注入场景。
// 注意：Send 内部退避 1s/2s/4s，为避免测试过慢，这里把整体测试超时控制在合理范围。
// 只针对 Send 的 webhook 通路；非 2xx 与网络错误会走满 3 次尝试。

func TestSend_SkipWhenAllURLsEmpty(t *testing.T) {
	n := Notifier{}
	err := n.Send("", "test_event", "svc", "tgt", "2024-01-01T00:00:00Z", "")
	if err != nil {
		t.Fatalf("两者皆空时应跳过并返回 nil，实际: %v", err)
	}

	// 全局为空时也必须跳过。
	n2 := Notifier{WebhookURL: ""}
	if err := n2.Send("", "evt", "svc", "tgt", "at", ""); err != nil {
		t.Fatalf("全局 webhook 为空时应跳过并返回 nil，实际: %v", err)
	}
}

func TestSend_InvalidURLReturnsError(t *testing.T) {
	// 非法 URL（含控制字符）会被 http.NewRequest 拒绝，应立即返回错误。
	n := Notifier{}
	start := time.Now()
	err := n.Send("http://\x00bad", "evt", "svc", "tgt", "at", "")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("非法 URL 应返回错误")
	}
	if !strings.Contains(err.Error(), "构造通知请求失败") {
		t.Fatalf("错误信息应包含构造失败提示，实际: %v", err)
	}
	// 构造失败属于立即返回，不应触发退避重试。
	if elapsed >= time.Second {
		t.Fatalf("构造失败不应重试等待，实际耗时: %v", elapsed)
	}
}

func TestSend_OverlongTargetAndErrMsg(t *testing.T) {
	var got payload
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &got)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	longTarget := strings.Repeat("目", 5000)
	longErr := strings.Repeat("错", 5000)
	n := Notifier{}
	if err := n.Send(srv.URL, "evt_long", "svc_long", longTarget, "at_long", longErr); err != nil {
		t.Fatalf("超长字段应仍能发送成功，实际: %v", err)
	}

	if atomic.LoadInt32(&hit) != 1 {
		t.Fatalf("应只发一次请求，实际: %d", hit)
	}
	if got.Target != longTarget {
		t.Fatalf("target 应完整透传，长度=%d 期望=%d", len(got.Target), len(longTarget))
	}
	if got.ErrMsg != longErr {
		t.Fatalf("err_msg 应完整透传，长度=%d 期望=%d", len(got.ErrMsg), len(longErr))
	}
}

func TestSend_MonitorURLOverridesGlobal(t *testing.T) {
	var globalHit, monitorHit int32
	global := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&globalHit, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer global.Close()
	monitor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&monitorHit, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer monitor.Close()

	n := Notifier{WebhookURL: global.URL}
	if err := n.Send(monitor.URL, "evt", "svc", "tgt", "at", ""); err != nil {
		t.Fatalf("monitor 级 webhook 应成功，实际: %v", err)
	}
	if atomic.LoadInt32(&monitorHit) != 1 {
		t.Fatalf("monitor webhook 应被调用一次，实际: %d", monitorHit)
	}
	if atomic.LoadInt32(&globalHit) != 0 {
		t.Fatalf("全局 webhook 不应被调用，实际: %d", globalHit)
	}
}

func TestSend_FallsBackToGlobalWhenMonitorEmpty(t *testing.T) {
	var globalHit int32
	global := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&globalHit, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer global.Close()

	n := Notifier{WebhookURL: global.URL}
	if err := n.Send("", "evt", "svc", "tgt", "at", ""); err != nil {
		t.Fatalf("应回退到全局 webhook 并成功，实际: %v", err)
	}
	if atomic.LoadInt32(&globalHit) != 1 {
		t.Fatalf("全局 webhook 应被调用一次，实际: %d", globalHit)
	}
}

func TestSend_PayloadFieldsAndContentType(t *testing.T) {
	var got payload
	var ctype string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctype = r.Header.Get("Content-Type")
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &got)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{}
	err := n.Send(srv.URL, "cpu_high", "node-1", "10.0.0.1", "2024-05-01T10:00:00Z", "负载过高")
	if err != nil {
		t.Fatalf("发送应成功，实际: %v", err)
	}
	if ctype != "application/json" {
		t.Fatalf("Content-Type 应为 application/json，实际: %q", ctype)
	}
	if got.Event != "cpu_high" || got.Name != "node-1" || got.Target != "10.0.0.1" {
		t.Fatalf("字段不匹配: %+v", got)
	}
	if got.At != "2024-05-01T10:00:00Z" || got.ErrMsg != "负载过高" {
		t.Fatalf("at/err_msg 不匹配: %+v", got)
	}
	if got.Service != "sentinel" {
		t.Fatalf("service 应为 sentinel，实际: %q", got.Service)
	}
}

func TestSend_Non2xxRetriesThenFails(t *testing.T) {
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	n := Notifier{}
	start := time.Now()
	err := n.Send(srv.URL, "evt", "svc", "tgt", "at", "")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("持续 500 应最终返回错误")
	}
	if !strings.Contains(err.Error(), "Webhook 发送失败") {
		t.Fatalf("错误信息应包含最终失败提示，实际: %v", err)
	}
	if atomic.LoadInt32(&hit) != 3 {
		t.Fatalf("应尝试 3 次，实际: %d", hit)
	}
	// 退避 1s + 2s，总耗时至少约 3s。
	if elapsed < 3*time.Second {
		t.Fatalf("重试应包含退避等待，实际耗时: %v", elapsed)
	}
}

func TestSend_NetworkErrorRetriesThenFails(t *testing.T) {
	// 关闭的 server 会立即拒绝连接，触发网络错误。
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	closedURL := srv.URL
	srv.Close()

	n := Notifier{}
	start := time.Now()
	err := n.Send(closedURL, "evt", "svc", "tgt", "at", "")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("连接被拒应返回错误")
	}
	if !strings.Contains(err.Error(), "Webhook 发送失败") {
		t.Fatalf("错误信息应包含最终失败提示，实际: %v", err)
	}
	if elapsed < 3*time.Second {
		t.Fatalf("网络错误应走满退避，实际耗时: %v", elapsed)
	}
}

func TestSend_ProbeTimeout(t *testing.T) {
	// 探针接口故意超过 client 10s 超时。为控制测试时长，这里用阻塞 11s 的 handler。
	// 只发一次真实请求并验证最终失败，避免 3 次尝试叠加成 30s+。
	var hit int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		time.Sleep(11 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{}
	start := time.Now()
	err := n.Send(srv.URL, "evt", "svc", "tgt", "at", "")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("探针超时应返回错误")
	}
	if !strings.Contains(err.Error(), "Webhook 发送失败") {
		t.Fatalf("错误信息应包含最终失败提示，实际: %v", err)
	}
	if atomic.LoadInt32(&hit) != 3 {
		t.Fatalf("超时后应尝试 3 次，实际: %d", hit)
	}
	// 10s 超时 * 3 + 1s + 2s 退避 >= 33s。
	if elapsed < 30*time.Second {
		t.Fatalf("超时重试总耗时异常，实际: %v", elapsed)
	}
}

func TestSend_ConcurrentRequests(t *testing.T) {
	var hit int32
	var mu sync.Mutex
	seen := make(map[string]int)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hit, 1)
		body, _ := io.ReadAll(r.Body)
		var p payload
		_ = json.Unmarshal(body, &p)
		mu.Lock()
		seen[p.Target]++
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{}
	const workers = 16
	var wg sync.WaitGroup
	errs := make([]error, workers)
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			target := fmt.Sprintf("host-%02d", idx)
			errs[idx] = n.Send(srv.URL, "evt", "svc", target, "at", "")
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("并发 worker %d 失败: %v", i, err)
		}
	}
	if atomic.LoadInt32(&hit) != workers {
		t.Fatalf("应收到 %d 次请求，实际: %d", workers, hit)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(seen) != workers {
		t.Fatalf("应看到 %d 个不同 target，实际: %d", workers, len(seen))
	}
	for i := 0; i < workers; i++ {
		target := fmt.Sprintf("host-%02d", i)
		if seen[target] != 1 {
			t.Fatalf("target=%s 应只出现一次，实际: %d", target, seen[target])
		}
	}
}

func TestSend_IdempotentOnRetrySuccess(t *testing.T) {
	// 第一次返回 500，第二次返回 200；验证重试后成功且请求体一致。
	var hit int32
	var bodies []payload
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cur := atomic.AddInt32(&hit, 1)
		body, _ := io.ReadAll(r.Body)
		var p payload
		_ = json.Unmarshal(body, &p)
		mu.Lock()
		bodies = append(bodies, p)
		mu.Unlock()
		if cur == 1 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{}
	if err := n.Send(srv.URL, "evt_idem", "svc", "tgt", "at", "err"); err != nil {
		t.Fatalf("重试后应成功，实际: %v", err)
	}
	if atomic.LoadInt32(&hit) != 2 {
		t.Fatalf("应请求 2 次，实际: %d", hit)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(bodies) != 2 {
		t.Fatalf("应记录 2 次请求体，实际: %d", len(bodies))
	}
	if bodies[0] != bodies[1] {
		t.Fatalf("重试请求体应完全一致，第一次=%+v 第二次=%+v", bodies[0], bodies[1])
	}
	if bodies[0].Event != "evt_idem" || bodies[0].Service != "sentinel" {
		t.Fatalf("请求体字段异常: %+v", bodies[0])
	}
}

// 用 context 保证测试进程退出时不会长时间挂起。
var _ = context.Background