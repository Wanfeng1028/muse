package checker

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"sentinel/internal/store"
)

func TestR2_CheckKindEmptyDefaultsHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
	}

	got := Check(m)
	if got.Ok != 1 {
		t.Fatalf("Ok = %d, want 1; Error = %q", got.Ok, got.Error)
	}
	if !got.StatusCode.Valid {
		t.Fatalf("StatusCode.Valid = false, want true")
	}
	if got.StatusCode.Int64 != 200 {
		t.Fatalf("StatusCode.Int64 = %d, want 200", got.StatusCode.Int64)
	}
}

func TestR2_CheckKindUnknownFallsToHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "websocket",
		Target:         srv.URL,
		TimeoutSec:     2,
		ExpectedStatus: 200,
	}

	got := Check(m)
	if got.Ok != 1 {
		t.Fatalf("Ok = %d, want 1; Error = %q", got.Ok, got.Error)
	}
	if !got.StatusCode.Valid {
		t.Fatalf("StatusCode.Valid = false, want true")
	}
	if got.StatusCode.Int64 != 200 {
		t.Fatalf("StatusCode.Int64 = %d, want 200", got.StatusCode.Int64)
	}
}

func TestR2_CheckTLSSelfSignedFails(t *testing.T) {
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	m := store.Monitor{
		Kind:           "https",
		Target:         srv.URL,
		TimeoutSec:     5,
		ExpectedStatus: 200,
	}

	got := Check(m)
	if got.Ok != 0 {
		t.Fatalf("Ok = %d, want 0; Error = %q", got.Ok, got.Error)
	}
	if got.Error == "" {
		t.Fatalf("Error is empty, want non-empty TLS verification failure")
	}
	// 这是有意验证的严格行为：Check 使用默认 http.Client，未设置 InsecureSkipVerify，因此自签名证书必须导致失败。
}

func TestR2_CheckInvalidTargetURL(t *testing.T) {
	m := store.Monitor{
		Kind:       "http",
		Target:     "http://[::1",
		TimeoutSec: 2,
	}

	got := Check(m)
	if got.Ok != 0 {
		t.Fatalf("Ok = %d, want 0; Error = %q", got.Ok, got.Error)
	}
	if !strings.Contains(got.Error, "构造请求失败") {
		t.Fatalf("Error = %q, want it to contain %q", got.Error, "构造请求失败")
	}
}
