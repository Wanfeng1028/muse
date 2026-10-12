package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/store"
)

// TestHTTPOk 验证 HTTP 200 正常返回时 Check 判定成功。
func TestHTTPOk(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
	}
	c := Check(m)

	if c.Ok != 1 {
		t.Fatalf("expected Ok=1, got %d (err=%q)", c.Ok, c.Error)
	}
	if !c.StatusCode.Valid || c.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode=200 valid, got valid=%v val=%d", c.StatusCode.Valid, c.StatusCode.Int64)
	}
	if c.LatencyMs < 0 {
		t.Fatalf("expected LatencyMs>=0, got %d", c.LatencyMs)
	}
	if c.Error != "" {
		t.Fatalf("expected empty Error, got %q", c.Error)
	}
}

// TestHTTPStatusMismatch 验证状态码不匹配时期望 200 但得到 500 判定失败。
func TestHTTPStatusMismatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
	}
	c := Check(m)

	if c.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d (err=%q)", c.Ok, c.Error)
	}
}

// TestHTTPTimeout 验证请求超时（handler sleep 2s，超时 1s）时判定失败且 Error 非空。
func TestHTTPTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     1,
	}
	c := Check(m)

	if c.Ok != 0 {
		t.Fatalf("expected Ok=0 on timeout, got %d", c.Ok)
	}
	if c.Error == "" {
		t.Fatalf("expected non-empty Error on timeout")
	}
}

// TestTCP 验证 TCP 端口连通性检查：监听端口成功，未监听端口失败。
func TestTCP(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer ln.Close()
	addr := ln.Addr().String()

	// 启动接受连接的循环，避免连接堆积。
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 5,
	}
	c := Check(m)
	if c.Ok != 1 {
		t.Fatalf("expected Ok=1 for listening port, got %d (err=%q)", c.Ok, c.Error)
	}

	// 找一个肯定未监听的端口。
	badTarget := "127.0.0.1:1"
	if l, err := net.Listen("tcp", badTarget); err == nil {
		l.Close()
		badTarget = "127.0.0.1:65000"
	}

	m2 := store.Monitor{
		Kind:       "tcp",
		Target:     badTarget,
		TimeoutSec: 5,
	}
	c2 := Check(m2)
	if c2.Ok != 0 {
		t.Fatalf("expected Ok=0 for closed port, got %d", c2.Ok)
	}
}
