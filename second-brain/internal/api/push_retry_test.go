package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func doPushTest(t *testing.T, srv *httptest.Server, channel string) (int, map[string]any) {
	t.Helper()
	payload, err := json.Marshal(map[string]any{"channel": channel})
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	resp, err := http.Post(srv.URL+"/api/push/test", "application/json", bytes.NewReader(payload))
	if err != nil {
		t.Fatalf("POST /api/push/test: %v", err)
	}
	defer resp.Body.Close()
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode response body: %v", err)
	}
	return resp.StatusCode, body
}

func assertOKBool(t *testing.T, body map[string]any, want bool) {
	t.Helper()
	raw, exists := body["ok"]
	if !exists {
		t.Fatalf("response body missing %q field: %#v", "ok", body)
	}
	got, isBool := raw.(bool)
	if !isBool {
		t.Fatalf("response field %q is %T, want bool: %#v", "ok", raw, body)
	}
	if got != want {
		t.Fatalf("response field %q = %v, want %v (body: %#v)", "ok", got, want, body)
	}
}

func TestPushTestWebhookRetryThenSuccess(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "3")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")

	var attempts int32
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&attempts, 1)
		if n < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte("temporarily unavailable"))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	defer receiver.Close()

	t.Setenv("SB_WEBHOOK_URL", receiver.URL)

	srv, _ := newPushTestServer(t)
	defer srv.Close()

	status, body := doPushTest(t, srv, "webhook")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want %d (body: %#v)", status, http.StatusOK, body)
	}
	assertOKBool(t, body, true)

	if got := atomic.LoadInt32(&attempts); got != 3 {
		t.Fatalf("webhook attempts = %d, want 3", got)
	}
}

func TestPushTestWebhookRetryExhausted(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "2")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")

	var attempts int32
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte("still unavailable"))
	}))
	defer receiver.Close()

	t.Setenv("SB_WEBHOOK_URL", receiver.URL)

	srv, _ := newPushTestServer(t)
	defer srv.Close()

	status, body := doPushTest(t, srv, "webhook")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want %d (body: %#v)", status, http.StatusOK, body)
	}
	assertOKBool(t, body, false)

	if got := atomic.LoadInt32(&attempts); got != 3 {
		t.Fatalf("webhook attempts = %d, want 3 (1 initial + 2 retries)", got)
	}
}

func TestPushTestWebhookNoRetryOn4xx(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "3")
	t.Setenv("SB_PUSH_RETRY_BASE_MS", "5")

	var attempts int32
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("bad request"))
	}))
	defer receiver.Close()

	t.Setenv("SB_WEBHOOK_URL", receiver.URL)

	srv, _ := newPushTestServer(t)
	defer srv.Close()

	status, body := doPushTest(t, srv, "webhook")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want %d (body: %#v)", status, http.StatusOK, body)
	}
	assertOKBool(t, body, false)

	if got := atomic.LoadInt32(&attempts); got != 1 {
		t.Fatalf("webhook attempts = %d, want 1 (4xx must not retry)", got)
	}
	if !strings.Contains(receiver.URL, "http://") {
		t.Fatalf("unexpected receiver URL: %q", receiver.URL)
	}
}
