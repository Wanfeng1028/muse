package checker

import (
	"net"
	"testing"
	"time"

	"sentinel/internal/store"
)

// TestR2_CheckWithRetryBackoffCap 验证 CheckWithRetry 的退避序列在 maxRetries=4 时
// 只经历 0.5s、1s、2s、4s 四次退避，总和约 7.5s。
// 若无 8s 钳制，第 5 次 attempt 前还会再等 8s（0.5+1+2+4+8=15.5s 起），
// 本测试验证前 4 次退避总和落在 [7s, 15s) 区间内，从而确认钳制逻辑不影响前 4 次退避。
func TestR2_CheckWithRetryBackoffCap(t *testing.T) {
	// 先监听再关闭，得到一个确定无人监听的 TCP 地址。
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen 失败: %v", err)
	}
	addr := ln.Addr().String()
	if err := ln.Close(); err != nil {
		t.Fatalf("close listener 失败: %v", err)
	}

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}

	start := time.Now()
	got, retries := CheckWithRetry(m, 4)
	elapsed := time.Since(start)

	if got.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
	if retries != 4 {
		t.Fatalf("期望 retries=4，实际 retries=%d", retries)
	}
	if elapsed < 7000*time.Millisecond {
		t.Fatalf("退避总耗时过短: %v，期望 >= 7s", elapsed)
	}
	if elapsed >= 15000*time.Millisecond {
		t.Fatalf("退避总耗时过长: %v，期望 < 15s（说明未在 4 次后退避后停止）", elapsed)
	}
}
