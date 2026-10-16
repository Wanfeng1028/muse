// internal/push/retry_integration_test.go
package push

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// TestWebhookRetryOverHTTP_SucceedsAfterTwoFailures 用真实 httptest 服务器
// 验证：前两次 500，第三次 200，重试包装器最终成功，且真实发生了重试。
func TestWebhookRetryOverHTTP_SucceedsAfterTwoFailures(t *testing.T) {
	var count atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := count.Add(1)
		if n <= 2 {
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte("boom"))
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	sender := notify.NewWebhookSender(srv.URL, "", 5*time.Second)
	wrapped := WrapWithRetry(sender, RetryPolicy{
		MaxRetries:  5,
		BaseBackoff: 20 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0.1,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	err := wrapped.Send(ctx, notify.Message{
		To:       "x@y.z",
		Subject:  "冒烟",
		TextBody: "hi",
	})
	if err != nil {
		t.Fatalf("期望发送成功，实际得到错误: %v", err)
	}

	if got := count.Load(); got != 3 {
		t.Fatalf("期望服务器收到 3 次请求（含 2 次重试），实际为 %d", got)
	}
}

// TestWebhookRetryOverHTTP_ExhaustsToDeadLetter 用真实 httptest 服务器
// 验证：持续 503 触发重试耗尽，落库为 failed_permanent，且写入幂等。
func TestWebhookRetryOverHTTP_ExhaustsToDeadLetter(t *testing.T) {
	var count atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count.Add(1)
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte("unavailable"))
	}))
	defer srv.Close()

	sender := notify.NewWebhookSender(srv.URL, "", 5*time.Second)
	wrapped := WrapWithRetry(sender, RetryPolicy{
		MaxRetries:  2,
		BaseBackoff: 20 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	err := wrapped.Send(ctx, notify.Message{
		To:       "x@y.z",
		Subject:  "冒烟",
		TextBody: "hi",
	})
	if err == nil {
		t.Fatal("期望重试耗尽返回错误，实际为 nil")
	}

	var rex *RetryExhaustedError
	if !errors.As(err, &rex) {
		t.Fatalf("期望错误为 *RetryExhaustedError，实际为 %T: %v", err, err)
	}
	if rex.Attempts != 3 {
		t.Fatalf("期望总尝试次数为 3，实际为 %d", rex.Attempts)
	}
	if got := count.Load(); got != 3 {
		t.Fatalf("期望服务器收到 3 次请求，实际为 %d", got)
	}

	// 真实打开测试库并记录死信。
	st, err := store.Open(filepath.Join(t.TempDir(), "t.db"))
	if err != nil {
		t.Fatalf("打开测试库失败: %v", err)
	}
	defer st.Close()

	dateKey := "2026-10-16"
	const channel = "webhook"
	const user = "local"

	if err := RecordDeadLetter(st, dateKey, channel, user, rex.LastErr); err != nil {
		t.Fatalf("RecordDeadLetter 首次调用失败: %v", err)
	}

	status, found := st.PushLogStatus(dateKey, channel, user)
	if !found {
		t.Fatalf("期望在 PushLogStatus 中查到记录，实际未找到")
	}
	if status != "failed_permanent" {
		t.Fatalf("期望状态为 failed_permanent，实际为 %q", status)
	}

	entries, err := st.ListPushLogFor(10, user)
	if err != nil {
		t.Fatalf("ListPushLogFor 调用失败: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("期望首次写入后恰好 1 条记录，实际为 %d", len(entries))
	}
	detail := entries[0].Detail
	if !strings.Contains(detail, "503") {
		t.Fatalf("期望 Detail 含 \"503\"，实际为 %q", detail)
	}
	if !strings.Contains(detail, "重试耗尽") {
		t.Fatalf("期望 Detail 含 \"重试耗尽\"，实际为 %q", detail)
	}

	// 再次记录换 error 文本，验证幂等：仍只有 1 条记录。
	if err := RecordDeadLetter(st, dateKey, channel, user, fmt.Errorf("另一段错误文本 999")); err != nil {
		t.Fatalf("RecordDeadLetter 二次调用失败: %v", err)
	}
	entries2, err := st.ListPushLogFor(10, user)
	if err != nil {
		t.Fatalf("二次 ListPushLogFor 调用失败: %v", err)
	}
	if len(entries2) != 1 {
		t.Fatalf("期望幂等后仍只有 1 条记录，实际为 %d", len(entries2))
	}
}
