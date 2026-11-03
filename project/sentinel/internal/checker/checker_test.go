package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

// TestCheckHTTPOK 使用 httptest 200 服务器期望 ok=1。
func TestCheckHTTPOK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	defer srv.Close()

	m := store.Monitor{
		ID:             1,
		Name:           "ok",
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
	}
	c := Check(m)
	if c.Ok != 1 {
		t.Fatalf("期望 ok=1, 实际 %d, err=%s", c.Ok, c.Error)
	}
	if !c.StatusCode.Valid || c.StatusCode.Int64 != 200 {
		t.Fatalf("期望 status=200, 实际 %+v", c.StatusCode)
	}
}

// TestCheckHTTPStatusMismatch 使用 500 服务器期望 ok=0。
func TestCheckHTTPStatusMismatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	m := store.Monitor{
		ID:             2,
		Name:           "bad",
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
	}
	c := Check(m)
	if c.Ok != 0 {
		t.Fatalf("期望 ok=0, 实际 %d", c.Ok)
	}
	if !c.StatusCode.Valid || c.StatusCode.Int64 != 500 {
		t.Fatalf("期望 status=500, 实际 %+v", c.StatusCode)
	}
}

// TestCheckWithRetryTimeout 服务器 sleep 3 秒，超时 1 秒，maxRetries=2 → ok=0, retries=2。
func TestCheckWithRetryTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(3 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		ID:             3,
		Name:           "slow",
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     1,
	}

	start := time.Now()
	c, retries := CheckWithRetry(m, 2)
	elapsed := time.Since(start)

	if c.Ok != 0 {
		t.Fatalf("期望 ok=0, 实际 %d", c.Ok)
	}
	if retries != 2 {
		t.Fatalf("期望 retries=2, 实际 %d", retries)
	}
	if elapsed >= 10*time.Second {
		t.Fatalf("总耗时过长: %v", elapsed)
	}
	if c.Error == "" {
		t.Fatalf("期望 Error 非空")
	}
}

// TestCheckWithRetryRefused 目标 127.0.0.1:1 几乎必定连接拒绝，maxRetries=1 → ok=0, retries=1。
func TestCheckWithRetryRefused(t *testing.T) {
	m := store.Monitor{
		ID:             4,
		Name:           "refused",
		Kind:           "http",
		Target:         "http://127.0.0.1:1",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     1,
	}

	c, retries := CheckWithRetry(m, 1)
	if c.Ok != 0 {
		t.Fatalf("期望 ok=0, 实际 %d", c.Ok)
	}
	if retries != 1 {
		t.Fatalf("期望 retries=1, 实际 %d", retries)
	}
	if c.Error == "" {
		t.Fatalf("期望 Error 非空")
	}
}

// TestCheckNoRetryOnStatusMismatch 500 服务器 + ExpectedStatus=200 + maxRetries=3 → retries=0。
func TestCheckNoRetryOnStatusMismatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	m := store.Monitor{
		ID:             5,
		Name:           "mismatch",
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
	}

	c, retries := CheckWithRetry(m, 3)
	if c.Ok != 0 {
		t.Fatalf("期望 ok=0, 实际 %d", c.Ok)
	}
	if retries != 0 {
		t.Fatalf("期望 retries=0, 实际 %d", retries)
	}
}

// TestCheckTCPOK 本地 TCP 监听期望 ok=1。
func TestCheckTCPOK(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	defer ln.Close()

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			_ = conn.Close()
		}
	}()

	addr := ln.Addr().String()
	if !strings.Contains(addr, ":") {
		t.Fatalf("地址异常: %s", addr)
	}

	m := store.Monitor{
		ID:         6,
		Name:       "tcp",
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 3,
	}
	c := Check(m)
	if c.Ok != 1 {
		t.Fatalf("期望 ok=1, 实际 %d, err=%s", c.Ok, c.Error)
	}
}
