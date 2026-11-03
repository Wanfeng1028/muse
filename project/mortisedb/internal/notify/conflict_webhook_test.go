package notify

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func sampleConflict() store.Conflict {
	return store.Conflict{
		ID:         42,
		TableName:  "users",
		PK:         "id=7",
		SourceA:    "mysql",
		SourceB:    "postgres",
		RowJSON:    `{"id":7,"name":"late"}`,
		Status:     "open",
		CreatedAt:  "2024-01-02T03:04:05Z",
		ResolvedAt: "",
	}
}

// 用例 1：正常 2xx，服务端收到完整 JSON，字段齐全且值一致。
func TestConflictWebhookSendSuccess(t *testing.T) {
	var mu sync.Mutex
	var gotBody []byte
	var gotMethod string
	var gotContentType string

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		mu.Lock()
		gotBody = body
		gotMethod = r.Method
		gotContentType = r.Header.Get("Content-Type")
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()

	w := NewConflictWebhook(srv.URL, 5*time.Second)
	c := sampleConflict()
	if err := w.Send(c); err != nil {
		t.Fatalf("Send returned error: %v", err)
	}

	mu.Lock()
	method := gotMethod
	contentType := gotContentType
	body := append([]byte(nil), gotBody...)
	mu.Unlock()

	if method != http.MethodPost {
		t.Fatalf("method = %q, want POST", method)
	}
	if contentType != "application/json" {
		t.Fatalf("content-type = %q, want application/json", contentType)
	}

	var decoded map[string]any
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("decode body: %v; raw=%s", err, string(body))
	}

	wantKeys := []string{"id", "table_name", "pk", "source_a", "source_b", "row_json", "status", "created_at", "resolved_at"}
	for _, k := range wantKeys {
		if _, ok := decoded[k]; !ok {
			t.Fatalf("missing field %q in body: %s", k, string(body))
		}
	}

	if decoded["table_name"] != "users" {
		t.Fatalf("table_name = %v, want users", decoded["table_name"])
	}
	if decoded["pk"] != "id=7" {
		t.Fatalf("pk = %v, want id=7", decoded["pk"])
	}
	if decoded["source_a"] != "mysql" {
		t.Fatalf("source_a = %v, want mysql", decoded["source_a"])
	}
	if decoded["source_b"] != "postgres" {
		t.Fatalf("source_b = %v, want postgres", decoded["source_b"])
	}
	if decoded["row_json"] != `{"id":7,"name":"late"}` {
		t.Fatalf("row_json = %v, want {\"id\":7,\"name\":\"late\"}", decoded["row_json"])
	}
	if decoded["status"] != "open" {
		t.Fatalf("status = %v, want open", decoded["status"])
	}
	if decoded["created_at"] != "2024-01-02T03:04:05Z" {
		t.Fatalf("created_at = %v, want 2024-01-02T03:04:05Z", decoded["created_at"])
	}
	if decoded["resolved_at"] != "" {
		t.Fatalf("resolved_at = %v, want empty", decoded["resolved_at"])
	}
	id, ok := decoded["id"].(float64)
	if !ok || int64(id) != 42 {
		t.Fatalf("id = %v, want 42", decoded["id"])
	}
}

// 用例 2：非 2xx 返回错误，错误信息包含状态码和前 200 字节 body。
func TestConflictWebhookSendNon2xx(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("boom server exploded"))
	}))
	defer srv.Close()

	w := NewConflictWebhook(srv.URL, 5*time.Second)
	err := w.Send(sampleConflict())
	if err == nil {
		t.Fatal("Send returned nil, want error")
	}
	msg := err.Error()
	if !strings.Contains(msg, "500") {
		t.Fatalf("error %q does not contain status code 500", msg)
	}
	if !strings.Contains(msg, "boom server exploded") {
		t.Fatalf("error %q does not contain body text", msg)
	}
}

// 用例 3：非 2xx 时只截取 body 前 200 字节。
func TestConflictWebhookSendTruncatesBody(t *testing.T) {
	longBody := strings.Repeat("x", 500)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(longBody))
	}))
	defer srv.Close()

	w := NewConflictWebhook(srv.URL, 5*time.Second)
	err := w.Send(sampleConflict())
	if err == nil {
		t.Fatal("Send returned nil, want error")
	}
	msg := err.Error()
	if !strings.Contains(msg, "400") {
		t.Fatalf("error %q does not contain status code 400", msg)
	}
	// body 部分应为 200 个 x
	if !strings.Contains(msg, strings.Repeat("x", 200)) {
		t.Fatalf("error %q does not contain 200 x bytes", msg)
	}
	if strings.Contains(msg, strings.Repeat("x", 201)) {
		t.Fatalf("error %q contains more than 200 body bytes", msg)
	}
}

// 用例 4：空 URL 直接跳过，不发请求，返回 nil。
func TestConflictWebhookEmptyURLSkips(t *testing.T) {
	var hits int
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		hits++
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	// URL 为空字符串，即使有可用 server 也不应发请求
	w := NewConflictWebhook("", 5*time.Second)
	if err := w.Send(sampleConflict()); err != nil {
		t.Fatalf("Send returned error on empty URL: %v", err)
	}

	mu.Lock()
	n := hits
	mu.Unlock()
	if n != 0 {
		t.Fatalf("server hits = %d, want 0", n)
	}
}

// 用例 5：超时触发，Send 返回错误且不长时间阻塞。
func TestConflictWebhookTimeout(t *testing.T) {
	release := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-release
		w.WriteHeader(http.StatusOK)
	}))
	defer func() {
		close(release)
		srv.Close()
	}()

	w := NewConflictWebhook(srv.URL, 100*time.Millisecond)
	start := time.Now()
	err := w.Send(sampleConflict())
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("Send returned nil, want timeout error")
	}
	if elapsed > 3*time.Second {
		t.Fatalf("Send took %v, want around 100ms timeout", elapsed)
	}
	if !strings.Contains(err.Error(), "post conflict webhook") {
		t.Fatalf("error %q does not mention post conflict webhook", err.Error())
	}
}

// 用例 6：非法 timeout 环境变量（非整数）启动失败。
func TestLoadConflictWebhookConfigInvalidTimeoutNotInt(t *testing.T) {
	t.Setenv("MORTISE_CONFLICT_WEBHOOK_URL", "http://example.com/hook")
	t.Setenv("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC", "abc")

	cfg, err := LoadConflictWebhookConfig()
	if err == nil {
		t.Fatal("LoadConflictWebhookConfig returned nil error, want error")
	}
	if cfg.URL != "" || cfg.Timeout != 0 || cfg.Enabled {
		t.Fatalf("cfg = %+v, want zero value on error", cfg)
	}
	if !strings.Contains(err.Error(), "MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC") {
		t.Fatalf("error %q does not mention env var name", err.Error())
	}
}

// 用例 7：非法 timeout（<=0）启动失败。
func TestLoadConflictWebhookConfigNonPositiveTimeout(t *testing.T) {
	t.Setenv("MORTISE_CONFLICT_WEBHOOK_URL", "http://example.com/hook")
	t.Setenv("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC", "0")

	cfg, err := LoadConflictWebhookConfig()
	if err == nil {
		t.Fatal("LoadConflictWebhookConfig returned nil error, want error")
	}
	if cfg.Enabled {
		t.Fatalf("cfg.Enabled = true, want false on error")
	}
	if !strings.Contains(err.Error(), "must be > 0") {
		t.Fatalf("error %q does not mention must be > 0", err.Error())
	}
}

// 用例 8：未设置 timeout 时默认 10 秒。
func TestLoadConflictWebhookConfigDefaultTimeout(t *testing.T) {
	t.Setenv("MORTISE_CONFLICT_WEBHOOK_URL", "http://example.com/hook")
	os.Unsetenv("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC")

	cfg, err := LoadConflictWebhookConfig()
	if err != nil {
		t.Fatalf("LoadConflictWebhookConfig error: %v", err)
	}
	if !cfg.Enabled {
		t.Fatal("cfg.Enabled = false, want true")
	}
	if cfg.Timeout != 10*time.Second {
		t.Fatalf("cfg.Timeout = %v, want 10s", cfg.Timeout)
	}
	if cfg.URL != "http://example.com/hook" {
		t.Fatalf("cfg.URL = %q, want http://example.com/hook", cfg.URL)
	}
}

// 用例 9：URL 为空时 Enabled=false，Timeout 仍按默认 10 秒。
func TestLoadConflictWebhookConfigEmptyURLDisabled(t *testing.T) {
	os.Unsetenv("MORTISE_CONFLICT_WEBHOOK_URL")
	os.Unsetenv("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC")

	cfg, err := LoadConflictWebhookConfig()
	if err != nil {
		t.Fatalf("LoadConflictWebhookConfig error: %v", err)
	}
	if cfg.Enabled {
		t.Fatal("cfg.Enabled = true, want false when URL empty")
	}
	if cfg.URL != "" {
		t.Fatalf("cfg.URL = %q, want empty", cfg.URL)
	}
	if cfg.Timeout != 10*time.Second {
		t.Fatalf("cfg.Timeout = %v, want 10s", cfg.Timeout)
	}
}

// 用例 10：NewConflictWebhook 对非法 timeout 回落到 10 秒，且 URL 为空时 Send 返回 nil。
func TestNewConflictWebhookFallbackAndNilClient(t *testing.T) {
	w := NewConflictWebhook("", 0)
	if w.Timeout != 10*time.Second {
		t.Fatalf("w.Timeout = %v, want 10s", w.Timeout)
	}
	if w.client == nil {
		t.Fatal("w.client = nil, want non-nil")
	}
	if w.client.Timeout != 10*time.Second {
		t.Fatalf("w.client.Timeout = %v, want 10s", w.client.Timeout)
	}

	if err := w.Send(sampleConflict()); err != nil {
		t.Fatalf("Send on empty URL returned error: %v", err)
	}
}

// 用例 11：并发 Send 到同一 server，每个请求都收到合法 JSON。
func TestConflictWebhookConcurrentSends(t *testing.T) {
	var mu sync.Mutex
	received := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var decoded map[string]any
		if err := json.Unmarshal(body, &decoded); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		mu.Lock()
		received++
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	w := NewConflictWebhook(srv.URL, 5*time.Second)
	const n = 8
	var wg sync.WaitGroup
	errs := make([]error, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			errs[idx] = w.Send(sampleConflict())
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("Send[%d] error: %v", i, err)
		}
	}
	mu.Lock()
	got := received
	mu.Unlock()
	if got != n {
		t.Fatalf("server received %d requests, want %d", got, n)
	}
}

// 用例 12：2xx 边界（201）视为成功。
func TestConflictWebhook2xxBoundary(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte(`created`))
	}))
	defer srv.Close()

	w := NewConflictWebhook(srv.URL, 5*time.Second)
	if err := w.Send(sampleConflict()); err != nil {
		t.Fatalf("Send returned error for 201: %v", err)
	}
}
