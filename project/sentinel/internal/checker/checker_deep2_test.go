package checker

import (
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestCheck_KindEmptyDefaultsToHTTP_Deep2(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for empty kind defaulting to http, got %d (err=%q)", res.Ok, res.Error)
	}
	if res.Error != "" {
		t.Fatalf("expected no error, got %q", res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheck_KindUppercaseHTTP_Deep2(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "HTTP",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for kind HTTP (trim+lower), got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheck_KindMixedCaseTCP_Deep2(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer ln.Close()

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
		Kind:       "Tcp",
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for kind Tcp (trim+lower), got %d (err=%q)", res.Ok, res.Error)
	}
	if res.Error != "" {
		t.Fatalf("expected no error, got %q", res.Error)
	}
}

func TestCheck_TimeoutSecZeroDefaults_Deep2(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     0,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 with TimeoutSec=0 (default applied), got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckWithRetry_MaxRetriesNegative_Deep2(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         "http://" + addr,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res, retries := CheckWithRetry(m, -1)
	if retries != 0 {
		t.Fatalf("expected retries=0 when maxRetries=-1 (clamped to 0), got %d", retries)
	}
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 on connection refused, got %d", res.Ok)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error on connection refused")
	}
	if res.StatusCode.Valid {
		t.Fatalf("expected StatusCode invalid on network error, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckWithRetry_FirstSuccess_Deep2(t *testing.T) {
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res, retries := CheckWithRetry(m, 3)
	if retries != 0 {
		t.Fatalf("expected retries=0 on first success, got %d", retries)
	}
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1, got %d (err=%q)", res.Ok, res.Error)
	}
	if hits != 1 {
		t.Fatalf("expected exactly 1 HTTP hit, got %d", hits)
	}
}

func TestCheckWithRetry_ConnectionRefused_Deep2(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         "http://" + addr,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	const maxRetries = 2
	res, retries := CheckWithRetry(m, maxRetries)
	if retries != maxRetries {
		t.Fatalf("expected retries=%d on persistent connection refused, got %d", maxRetries, retries)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error after retries exhausted")
	}
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d", res.Ok)
	}
	if res.StatusCode.Valid {
		t.Fatalf("expected StatusCode invalid on network error")
	}
}

func TestCheckWithRetry_StatusMismatchNoRetry_Deep2(t *testing.T) {
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 201,
		TimeoutSec:     2,
	}
	res, retries := CheckWithRetry(m, 3)
	if retries != 0 {
		t.Fatalf("expected retries=0 on status mismatch, got %d", retries)
	}
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 on status mismatch, got %d", res.Ok)
	}
	if !res.StatusCode.Valid {
		t.Fatalf("expected StatusCode valid on status mismatch, got valid=%v", res.StatusCode.Valid)
	}
	if res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode=200 (server response), got %d", res.StatusCode.Int64)
	}
	if hits != 1 {
		t.Fatalf("expected exactly 1 HTTP hit on mismatch (no retry), got %d", hits)
	}
}

func TestCheck_TCPTargetSuccess_Deep2(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer ln.Close()

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
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for reachable TCP target, got %d (err=%q)", res.Ok, res.Error)
	}
	if res.Error != "" {
		t.Fatalf("expected no error, got %q", res.Error)
	}
}

func TestCheck_TCPTargetRefused_Deep2(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	m := store.Monitor{
		Kind:       "tcp",
		Target:     addr,
		TimeoutSec: 2,
	}
	res := Check(m)
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 for refused TCP target, got %d", res.Ok)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error for refused TCP target")
	}
	if !strings.Contains(strings.ToLower(res.Error), "refused") &&
		!strings.Contains(strings.ToLower(res.Error), "connect") {
		t.Fatalf("expected connection-related error, got %q", res.Error)
	}
}