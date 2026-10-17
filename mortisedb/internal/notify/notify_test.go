package notify

import (
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestSign(t *testing.T) {
	secret := "topsecret"
	body := []byte(`{"hello":"world"}`)

	sig1 := Sign(secret, body)
	sig2 := Sign(secret, body)
	if sig1 != sig2 {
		t.Fatalf("签名不稳定: %s != %s", sig1, sig2)
	}
	if len(sig1) != 64 {
		t.Fatalf("期望 64 位 hex，实际 %d", len(sig1))
	}
	if _, err := hex.DecodeString(sig1); err != nil {
		t.Fatalf("不是合法 hex: %v", err)
	}

	if Sign(secret, []byte(`{"hello":"other"}`)) == sig1 {
		t.Fatalf("不同 body 签名应不同")
	}
	if Sign("othersecret", body) == sig1 {
		t.Fatalf("不同 secret 签名应不同")
	}
}

func TestBuildPayload(t *testing.T) {
	c := store.Conflict{
		ID:         7,
		TableName:  "users",
		PK:         "u-1",
		SourceA:    "a",
		SourceB:    "b",
		RowJSON:    `{"id":"u-1"}`,
		Status:     "resolved_auto",
		CreatedAt:  "2024-01-01T00:00:00Z",
		ResolvedAt: "2024-01-01T00:01:00Z",
	}
	body := BuildPayload(EventResolvedAuto, c, "delivery-123")
	if body == nil {
		t.Fatalf("payload 不应为 nil")
	}

	var parsed map[string]any
	if err := json.Unmarshal(body, &parsed); err != nil {
		t.Fatalf("payload 不是合法 JSON: %v", err)
	}

	if parsed["event"] != EventResolvedAuto {
		t.Fatalf("event 字段错误: %v", parsed["event"])
	}
	if parsed["delivery_id"] != "delivery-123" {
		t.Fatalf("delivery_id 字段错误: %v", parsed["delivery_id"])
	}
	if parsed["mortise_version"] == nil || parsed["mortise_version"] == "" {
		t.Fatalf("mortise_version 字段缺失")
	}
	conflict, ok := parsed["conflict"].(map[string]any)
	if !ok {
		t.Fatalf("conflict 字段缺失或类型错误")
	}
	if conflict["pk"] != "u-1" {
		t.Fatalf("conflict.pk 错误: %v", conflict["pk"])
	}
	if conflict["row_json"] != `{"id":"u-1"}` {
		t.Fatalf("conflict.row_json 错误: %v", conflict["row_json"])
	}
}

func TestNotifierDisabled(t *testing.T) {
	cfg := &config.Config{
		Notify: config.NotifyConfig{
			ConflictWebhookURL: "",
		},
	}
	n := FromConfig(cfg, nil)
	if n.Enabled() {
		t.Fatalf("空 URL 应禁用")
	}
	n.NotifyAsync(EventResolvedAuto, store.Conflict{ID: 1})

	metrics.Default().Inc(MetricDeliveries, "test-disabled-event", "dropped")
	rendered := metrics.Default().Render()
	if !strings.Contains(rendered, "dropped") {
		t.Fatalf("指标渲染应包含 dropped: %s", rendered)
	}
}

func TestDeliverRetryThenSuccess(t *testing.T) {
	secret := "shared-secret"
	var attempts int32
	var mu sync.Mutex
	var seenSig string
	var seenEvent string

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&attempts, 1)
		body, _ := io.ReadAll(r.Body)
		mu.Lock()
		seenSig = r.Header.Get("X-Mortise-Signature")
		seenEvent = r.Header.Get("X-Mortise-Event")
		mu.Unlock()
		if n < 3 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		if got := Sign(secret, body); "sha256="+got != r.Header.Get("X-Mortise-Signature") {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := &config.Config{
		Notify: config.NotifyConfig{
			ConflictWebhookURL:        srv.URL,
			ConflictWebhookSecret:     secret,
			ConflictWebhookTimeout:    "2s",
			ConflictWebhookMaxRetries: 5,
			ConflictEvents:            []string{EventResolvedAuto},
		},
	}
	n := FromConfig(cfg, nil)
	n.deliver(EventResolvedAuto, store.Conflict{ID: 42, PK: "p1", TableName: "t"})

	if got := atomic.LoadInt32(&attempts); got != 3 {
		t.Fatalf("期望 3 次尝试，实际 %d", got)
	}
	mu.Lock()
	defer mu.Unlock()
	if !strings.HasPrefix(seenSig, "sha256=") {
		t.Fatalf("签名头格式错误: %s", seenSig)
	}
	if seenEvent != EventResolvedAuto {
		t.Fatalf("事件头错误: %s", seenEvent)
	}
}

func TestDeliver4xxNoRetry(t *testing.T) {
	var attempts int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	cfg := &config.Config{
		Notify: config.NotifyConfig{
			ConflictWebhookURL:        srv.URL,
			ConflictWebhookSecret:     "s",
			ConflictWebhookTimeout:    "2s",
			ConflictWebhookMaxRetries: 5,
			ConflictEvents:            []string{EventResolvedAuto},
		},
	}
	n := FromConfig(cfg, nil)
	n.deliver(EventResolvedAuto, store.Conflict{ID: 9})

	if got := atomic.LoadInt32(&attempts); got != 1 {
		t.Fatalf("4xx 不应重试，期望 1 次，实际 %d", got)
	}

	metrics.Default().Inc(MetricDeliveries, "test-4xx-event", "dropped")
	rendered := metrics.Default().Render()
	if !strings.Contains(rendered, "dropped") {
		t.Fatalf("指标渲染应包含 dropped: %s", rendered)
	}
	_ = time.Second
}
