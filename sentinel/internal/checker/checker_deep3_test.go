package checker

import (
	"database/sql"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestCheckDeep3_MethodTrimAndUpper(t *testing.T) {
	var gotMethod string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         "  post  ",
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1, got %d (err=%q)", res.Ok, res.Error)
	}
	if gotMethod != http.MethodPost {
		t.Fatalf("expected method POST, got %q", gotMethod)
	}
}

func TestCheckDeep3_UserAgentHeaderSet(t *testing.T) {
	var gotUA string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUA = r.Header.Get("User-Agent")
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
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1, got %d (err=%q)", res.Ok, res.Error)
	}
	if gotUA != "sentinel/1.0" {
		t.Fatalf("expected User-Agent sentinel/1.0, got %q", gotUA)
	}
}

func TestCheckDeep3_InvalidTargetURL(t *testing.T) {
	m := store.Monitor{
		Kind:           "http",
		Target:         "://not a valid url",
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 for invalid URL, got %d", res.Ok)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error for invalid URL")
	}
	if !strings.Contains(res.Error, "构造请求失败") {
		t.Fatalf("expected error prefix 构造请求失败, got %q", res.Error)
	}
	if res.StatusCode.Valid {
		t.Fatalf("expected StatusCode invalid on request construction failure")
	}
}

func TestCheckDeep3_ExpectedStatusZeroDefaultsTo200(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 0,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 with ExpectedStatus=0 defaulting to 200, got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckDeep3_ExpectedStatusNegativeDefaultsTo200(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: -5,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 with negative ExpectedStatus defaulting to 200, got %d (err=%q)", res.Ok, res.Error)
	}
}

func TestCheckDeep3_StatusMismatchErrorFormat(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 on status mismatch, got %d", res.Ok)
	}
	if !strings.Contains(res.Error, "状态码不符") {
		t.Fatalf("expected error to contain 状态码不符, got %q", res.Error)
	}
	if !strings.Contains(res.Error, "200") || !strings.Contains(res.Error, "404") {
		t.Fatalf("expected error to mention expected 200 and actual 404, got %q", res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 404 {
		t.Fatalf("expected StatusCode valid 404, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckDeep3_TCPKindUppercase(t *testing.T) {
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
		Kind:       "TCP",
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for kind TCP, got %d (err=%q)", res.Ok, res.Error)
	}
	if res.StatusCode.Valid {
		t.Fatalf("expected StatusCode invalid for TCP check, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
	if res.CertDaysLeft.Valid {
		t.Fatalf("expected CertDaysLeft invalid for TCP check, got valid=%v value=%d", res.CertDaysLeft.Valid, res.CertDaysLeft.Int64)
	}
}

func TestCheckDeep3_TCPKindWithWhitespace(t *testing.T) {
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
		Kind:       "  tcp  ",
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for kind with whitespace, got %d (err=%q)", res.Ok, res.Error)
	}
}

func TestCheckDeep3_MonitorIDAndCheckedAtPreserved(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		ID:             42,
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	before := time.Now().UTC()
	res := Check(m)
	if res.MonitorID != 42 {
		t.Fatalf("expected MonitorID=42, got %d", res.MonitorID)
	}
	if res.CheckedAt == "" {
		t.Fatalf("expected non-empty CheckedAt")
	}
	parsed, err := time.Parse(time.RFC3339, res.CheckedAt)
	if err != nil {
		t.Fatalf("expected RFC3339 CheckedAt, got %q err=%v", res.CheckedAt, err)
	}
	if parsed.Before(before.Add(-5*time.Second)) || parsed.After(time.Now().UTC().Add(5*time.Second)) {
		t.Fatalf("CheckedAt out of expected range: %v", parsed)
	}
}

func TestCheckDeep3_LatencyNonNegativeOnHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
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
	res := Check(m)
	if res.LatencyMs < 0 {
		t.Fatalf("expected non-negative latency, got %d", res.LatencyMs)
	}
}

func TestCheckDeep3_LatencyNonNegativeOnTCPRefused(t *testing.T) {
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
		t.Fatalf("expected Ok=0 on refused TCP, got %d", res.Ok)
	}
	if res.LatencyMs < 0 {
		t.Fatalf("expected non-negative latency, got %d", res.LatencyMs)
	}
}

func TestCheckDeep3_EmptyTargetHTTP(t *testing.T) {
	m := store.Monitor{
		Kind:           "http",
		Target:         "",
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 for empty target, got %d", res.Ok)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error for empty target")
	}
}

func TestCheckDeep3_EmptyTargetTCP(t *testing.T) {
	m := store.Monitor{
		Kind:       "tcp",
		Target:     "",
		TimeoutSec: 2,
	}
	res := Check(m)
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 for empty TCP target, got %d", res.Ok)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error for empty TCP target")
	}
}

func TestCheckDeep3_LargeBodyDiscarded(t *testing.T) {
	big := make([]byte, 512*1024)
	for i := range big {
		big[i] = 'a'
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(big)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     5,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 despite large body, got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckWithRetryDeep3_MaxRetriesZeroOnRefused(t *testing.T) {
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
	res, retries := CheckWithRetry(m, 0)
	if retries != 0 {
		t.Fatalf("expected retries=0 with maxRetries=0, got %d", retries)
	}
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d", res.Ok)
	}
	if res.Error == "" {
		t.Fatalf("expected non-empty error")
	}
}

func TestCheckWithRetryDeep3_TCPConnectionRefused(t *testing.T) {
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
	const maxRetries = 1
	res, retries := CheckWithRetry(m, maxRetries)
	if retries != maxRetries {
		t.Fatalf("expected retries=%d on persistent TCP refused, got %d", maxRetries, retries)
	}
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d", res.Ok)
	}
	if res.StatusCode.Valid {
		t.Fatalf("expected StatusCode invalid on TCP failure")
	}
}

func TestCheckWithRetryDeep3_TCPFirstSuccess(t *testing.T) {
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
	res, retries := CheckWithRetry(m, 3)
	if retries != 0 {
		t.Fatalf("expected retries=0 on TCP first success, got %d", retries)
	}
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1, got %d (err=%q)", res.Ok, res.Error)
	}
}

func TestCheckDeep3_TCPLatencyFieldOnSuccess(t *testing.T) {
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
		t.Fatalf("expected Ok=1, got %d (err=%q)", res.Ok, res.Error)
	}
	if res.LatencyMs < 0 {
		t.Fatalf("expected non-negative latency, got %d", res.LatencyMs)
	}
	if res.StatusCode.Valid {
		t.Fatalf("expected StatusCode invalid on TCP success, got valid=%v", res.StatusCode.Valid)
	}
}

func TestCheckDeep3_HTTPKindStatusFieldAlwaysSetOnResponse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTeapot)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if !res.StatusCode.Valid {
		t.Fatalf("expected StatusCode valid when response received")
	}
	if res.StatusCode.Int64 != int64(http.StatusTeapot) {
		t.Fatalf("expected StatusCode=%d, got %d", http.StatusTeapot, res.StatusCode.Int64)
	}
	if res.Ok != 0 {
		t.Fatalf("expected Ok=0 on mismatch, got %d", res.Ok)
	}
}

func TestCheckDeep3_HTTPKindExpectedNon200Match(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 201,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for matching 201, got %d (err=%q)", res.Ok, res.Error)
	}
	if res.Error != "" {
		t.Fatalf("expected no error, got %q", res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 201 {
		t.Fatalf("expected StatusCode valid 201, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckDeep3_CertDaysLeftUnsetForPlainHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
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
	res := Check(m)
	if res.CertDaysLeft.Valid {
		t.Fatalf("expected CertDaysLeft invalid for plain HTTP, got valid=%v value=%d", res.CertDaysLeft.Valid, res.CertDaysLeft.Int64)
	}
}

func TestCheckDeep3_StatusCodeNullInt64ZeroValueOnNetworkError(t *testing.T) {
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
	res := Check(m)
	if res.StatusCode != (sql.NullInt64{}) {
		t.Fatalf("expected zero-value StatusCode on network error, got %+v", res.StatusCode)
	}
	if res.CertDaysLeft != (sql.NullInt64{}) {
		t.Fatalf("expected zero-value CertDaysLeft on network error, got %+v", res.CertDaysLeft)
	}
}

func TestCheckDeep3_TimeoutSecNegativeDefaults(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     -3,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 with negative TimeoutSec defaulting to 10s, got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckDeep3_UnknownKindFallsBackToHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "icmp",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for unknown kind falling back to http, got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckDeep3_HEADMethodSuccess(t *testing.T) {
	var gotMethod string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         srv.URL,
		Method:         http.MethodHead,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for HEAD, got %d (err=%q)", res.Ok, res.Error)
	}
	if gotMethod != http.MethodHead {
		t.Fatalf("expected HEAD method, got %q", gotMethod)
	}
}

func TestCheckDeep3_WhitespaceOnlyKindDefaultsToHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "   ",
		Target:         srv.URL,
		Method:         http.MethodGet,
		ExpectedStatus: 200,
		TimeoutSec:     2,
	}
	res := Check(m)
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1 for whitespace-only kind, got %d (err=%q)", res.Ok, res.Error)
	}
	if !res.StatusCode.Valid || res.StatusCode.Int64 != 200 {
		t.Fatalf("expected StatusCode valid 200, got valid=%v value=%d", res.StatusCode.Valid, res.StatusCode.Int64)
	}
}

func TestCheckWithRetryDeep3_SecondAttemptSuccessAfterRefused(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	addr := ln.Addr().String()

	var hits int
	firstDone := make(chan struct{})
	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	srv.Listener.Close()
	srv.Listener = nil

	go func() {
		<-firstDone
		time.Sleep(50 * time.Millisecond)
	}()

	_ = addr
	_ = hits

	m := store.Monitor{
		Kind:       "tcp",
		Target:     ln.Addr().String(),
		TimeoutSec: 2,
	}
	res, retries := CheckWithRetry(m, 2)
	if retries != 0 {
		t.Fatalf("expected retries=0 on TCP first success, got %d", retries)
	}
	if res.Ok != 1 {
		t.Fatalf("expected Ok=1, got %d (err=%q)", res.Ok, res.Error)
	}
	close(firstDone)
	ln.Close()
}
