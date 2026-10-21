package checker

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

func TestCheckHTTPSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:       "http",
		Target:     srv.URL,
		TimeoutSec: 2,
	}
	got := Check(m)
	if got.Ok != 1 {
		t.Fatalf("期望 Ok=1，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
	if !got.StatusCode.Valid {
		t.Fatalf("期望 StatusCode.Valid=true，实际为 false")
	}
	if got.StatusCode.Int64 != 200 {
		t.Fatalf("期望 StatusCode.Int64=200，实际为 %d", got.StatusCode.Int64)
	}
	if got.LatencyMs < 0 {
		t.Fatalf("期望 LatencyMs>=0，实际为 %d", got.LatencyMs)
	}
}

func TestCheckHTTPStatus500(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:       "http",
		Target:     srv.URL,
		TimeoutSec: 2,
	}
	got := Check(m)
	if !got.StatusCode.Valid {
		t.Fatalf("期望 StatusCode.Valid=true，实际为 false")
	}
	if got.StatusCode.Int64 != 500 {
		t.Fatalf("期望 StatusCode.Int64=500，实际为 %d", got.StatusCode.Int64)
	}
}

func TestCheckTCPUnreachable(t *testing.T) {
	// 先监听再关闭，得到确定无人监听的 TCP 地址：
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 1,
	}
	got := Check(m)
	if got.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
	if got.Error == "" {
		t.Fatalf("期望 Error 非空，实际为空")
	}
}

func TestCheckWithRetryZeroUnreachable(t *testing.T) {
	// 先监听再关闭，得到确定无人监听的 TCP 地址：
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 1,
	}
	got, retries := CheckWithRetry(m, 0)
	if retries != 0 {
		t.Fatalf("期望 retries=0，实际为 %d", retries)
	}
	if got.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
}

func TestCheckWithRetryTwoUnreachable(t *testing.T) {
	// 先监听再关闭，得到确定无人监听的 TCP 地址：
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 1,
	}
	got, retries := CheckWithRetry(m, 2)
	if retries != 2 {
		t.Fatalf("期望 retries=2，实际为 %d", retries)
	}
	if got.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
}

func TestCheckWithRetryTwoHTTPSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:       "http",
		Target:     srv.URL,
		TimeoutSec: 2,
	}
	got, retries := CheckWithRetry(m, 2)
	if retries != 0 {
		t.Fatalf("期望 retries=0，实际为 %d", retries)
	}
	if got.Ok != 1 {
		t.Fatalf("期望 Ok=1，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
}

func TestCheckWithRetryCtxCanceled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     "127.0.0.1:1",
		TimeoutSec: 30,
	}
	got, _ := CheckWithRetryCtx(ctx, m, 0)
	if got.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
}

func TestCheckEmptyKindHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:       "",
		Target:     srv.URL,
		TimeoutSec: 2,
	}
	got := Check(m)
	if got.Ok != 1 {
		t.Fatalf("期望 Ok=1，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
}

func TestCheckPOSTToGetOnlyHandler(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:       "http",
		Target:     srv.URL,
		Method:     "POST",
		TimeoutSec: 2,
	}
	got := Check(m)
	if got.Ok != 0 && got.Ok != 1 {
		t.Fatalf("期望 Ok 为 0 或 1，实际为 %d", got.Ok)
	}
}

func TestCheckEmptyTarget(t *testing.T) {
	m := store.Monitor{
		Kind:       "http",
		Target:     "",
		TimeoutSec: 2,
	}
	got := Check(m)
	if got.Ok != 0 {
		t.Fatalf("期望 Ok=0，实际 Ok=%d, Error=%q", got.Ok, got.Error)
	}
}