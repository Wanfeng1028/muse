package notify

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	mlog "github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestDeepFromConfig_NilConfig(t *testing.T) {
	n := FromConfig(nil, mlog.New(io.Discard, "info"))
	if n == nil {
		t.Fatalf("FromConfig(nil, ...) returned nil")
	}
	if n.Enabled() {
		t.Fatalf("expected Enabled() == false for nil config")
	}
	if n.Subscribed(EventPending) {
		t.Fatalf("expected Subscribed(%q) == false for nil config", EventPending)
	}
}

func TestDeepFromConfig_EmptyURL(t *testing.T) {
	cfg := &config.Config{}
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	if n.Enabled() {
		t.Fatalf("expected Enabled() == false for empty URL")
	}
	if n.url != "" {
		t.Fatalf("expected empty url, got %q", n.url)
	}
}

func TestDeepFromConfig_DefaultSubscribesAllEvents(t *testing.T) {
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = "http://example.invalid/hook"
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	if !n.Enabled() {
		t.Fatalf("expected Enabled() == true with non-empty URL")
	}
	if len(AllEvents) == 0 {
		t.Fatalf("AllEvents unexpectedly empty")
	}
	for _, e := range AllEvents {
		if !n.Subscribed(e) {
			t.Errorf("expected Subscribed(%q) == true with default events", e)
		}
	}
}

func TestDeepFromConfig_SubsetEvents(t *testing.T) {
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = "http://example.invalid/hook"
	cfg.Notify.ConflictEvents = []string{EventPending}
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	if !n.Subscribed(EventPending) {
		t.Errorf("expected Subscribed(%q) == true", EventPending)
	}
	if n.Subscribed(EventResolved) {
		t.Errorf("expected Subscribed(%q) == false", EventResolved)
	}
	if n.Subscribed("no-such-event") {
		t.Errorf("expected Subscribed(%q) == false", "no-such-event")
	}
}

func TestDeepFromConfig_BadTimeoutFallsBack(t *testing.T) {
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = "http://example.invalid/hook"
	cfg.Notify.ConflictWebhookTimeout = "not-a-duration"
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	if n.timeout != defaultTimeout {
		t.Fatalf("expected timeout to fall back to defaultTimeout=%v, got %v", defaultTimeout, n.timeout)
	}
}

func TestDeepFromConfig_CustomTimeoutAndRetries(t *testing.T) {
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = "http://example.invalid/hook"
	cfg.Notify.ConflictWebhookTimeout = "2s"
	cfg.Notify.ConflictWebhookMaxRetries = 5
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	if n.timeout != 2*time.Second {
		t.Fatalf("expected timeout == 2s, got %v", n.timeout)
	}
	if n.maxRetries != 5 {
		t.Fatalf("expected maxRetries == 5, got %d", n.maxRetries)
	}

	cfg2 := &config.Config{}
	cfg2.Notify.ConflictWebhookURL = "http://example.invalid/hook"
	cfg2.Notify.ConflictWebhookTimeout = "2s"
	cfg2.Notify.ConflictWebhookMaxRetries = 0
	n2 := FromConfig(cfg2, mlog.New(io.Discard, "info"))
	if n2.maxRetries != defaultMaxRetries {
		t.Fatalf("expected maxRetries to fall back to defaultMaxRetries=%d, got %d", defaultMaxRetries, n2.maxRetries)
	}
}

func TestDeepNotifyAsync_DeliversWithSignature(t *testing.T) {
	type captured struct {
		sig   string
		event string
		id    string
		body  []byte
	}
	ch := make(chan captured, 4)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		_ = r.Body.Close()
		ch <- captured{
			sig:   r.Header.Get("X-Mortise-Signature"),
			event: r.Header.Get("X-Mortise-Event"),
			id:    r.Header.Get("X-Mortise-Delivery-Id"),
			body:  body,
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = srv.URL
	cfg.Notify.ConflictWebhookSecret = "s3cr3t"
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	c := store.Conflict{
		ID:         1,
		TableName:  "orders",
		PK:         "1",
		SourceA:    "a",
		SourceB:    "b",
		RowJSON:    `{"id":1}`,
		Status:     "pending",
		CreatedAt:  "2024-01-01T00:00:00Z",
		ResolvedAt: "",
	}
	n.NotifyAsync(EventPending, c)

	var got captured
	deadline := time.Now().Add(3 * time.Second)
	select {
	case got = <-ch:
	case <-time.After(time.Until(deadline)):
		t.Fatalf("timed out waiting for webhook request")
	}

	wantSig := "sha256=" + Sign("s3cr3t", got.body)
	if got.sig != wantSig {
		t.Fatalf("signature mismatch: got %q want %q", got.sig, wantSig)
	}
	if got.event != EventPending {
		t.Fatalf("event header mismatch: got %q want %q", got.event, EventPending)
	}
	if got.id == "" {
		t.Fatalf("delivery id header must be non-empty")
	}
	var payload map[string]any
	if err := json.Unmarshal(got.body, &payload); err != nil {
		t.Fatalf("failed to decode body as JSON: %v (body=%q)", err, string(got.body))
	}
	ev, _ := payload["event"].(string)
	if ev != EventPending {
		t.Fatalf("body event field mismatch: got %q want %q", ev, EventPending)
	}
}

func TestDeepNotifyAsync_UnsubscribedEventNoHTTP(t *testing.T) {
	var count int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&count, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = srv.URL
	cfg.Notify.ConflictEvents = []string{EventResolved}
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	c := store.Conflict{
		ID:        2,
		TableName: "orders",
		PK:        "2",
		SourceA:   "a",
		SourceB:   "b",
		Status:    "pending",
	}
	n.NotifyAsync(EventPending, c)
	time.Sleep(400 * time.Millisecond)

	if got := atomic.LoadInt32(&count); got != 0 {
		t.Fatalf("expected 0 requests for unsubscribed event, got %d", got)
	}
}

func TestDeepNotifyAsync_DisabledNoHTTP(t *testing.T) {
	cfg := &config.Config{}
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	if n.Enabled() {
		t.Fatalf("precondition failed: notifier should be disabled")
	}
	c := store.Conflict{
		ID:        3,
		TableName: "orders",
		PK:        "3",
		SourceA:   "a",
		SourceB:   "b",
		Status:    "pending",
	}

	done := make(chan struct{})
	go func() {
		defer close(done)
		n.NotifyAsync(EventPending, c)
	}()

	select {
	case <-done:
	case <-time.After(1 * time.Second):
		t.Fatalf("NotifyAsync did not return promptly when disabled")
	}
}

func TestDeepFireAfterCommit_FiltersUnsubscribed(t *testing.T) {
	var count int32
	eventsCh := make(chan string, 8)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&count, 1)
		eventsCh <- r.Header.Get("X-Mortise-Event")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = srv.URL
	cfg.Notify.ConflictEvents = []string{EventPending}
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open failed: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("st.Migrate failed: %v", err)
	}

	items := []PendingNotify{
		{
			Event: EventPending,
			Conflict: store.Conflict{
				ID:        10,
				TableName: "orders",
				PK:        "10",
				SourceA:   "a",
				SourceB:   "b",
				Status:    "pending",
			},
			Table: "orders",
			PK:    "10",
			Since: "2024-01-01T00:00:00Z",
		},
		{
			Event: EventResolved,
			Conflict: store.Conflict{
				ID:        11,
				TableName: "orders",
				PK:        "11",
				SourceA:   "a",
				SourceB:   "b",
				Status:    "resolved",
			},
			Table: "orders",
			PK:    "11",
			Since: "2024-01-01T00:00:00Z",
		},
	}
	n.FireAfterCommit(st, items)

	deadline := time.Now().Add(3 * time.Second)
	var seen string
	select {
	case seen = <-eventsCh:
	case <-time.After(time.Until(deadline)):
		t.Fatalf("timed out waiting for a webhook request")
	}
	if seen != EventPending {
		t.Fatalf("expected only %q to be delivered, got %q", EventPending, seen)
	}

	time.Sleep(400 * time.Millisecond)
	if got := atomic.LoadInt32(&count); got != 1 {
		t.Fatalf("expected exactly 1 request, got %d", got)
	}
}

func TestDeepBackoffDelay_MonotonicNonNegative(t *testing.T) {
	d0 := backoffDelay(0)
	d1 := backoffDelay(1)
	d2 := backoffDelay(2)
	if d0 < 0 || d1 < 0 || d2 < 0 {
		t.Fatalf("backoffDelay must be non-negative: d0=%v d1=%v d2=%v", d0, d1, d2)
	}
	if d1 < d0 {
		t.Fatalf("backoffDelay not monotonic: d1=%v < d0=%v", d1, d0)
	}
	if d2 < d1 {
		t.Fatalf("backoffDelay not monotonic: d2=%v < d1=%v", d2, d1)
	}
}

func TestDeepNewDeliveryID_Unique(t *testing.T) {
	const n = 200
	seen := make(map[string]struct{}, n)
	for i := 0; i < n; i++ {
		id := newDeliveryID()
		if strings.TrimSpace(id) == "" {
			t.Fatalf("newDeliveryID returned empty at index %d", i)
		}
		if _, dup := seen[id]; dup {
			t.Fatalf("duplicate delivery id at index %d: %q", i, id)
		}
		seen[id] = struct{}{}
	}
	if len(seen) != n {
		t.Fatalf("expected %d unique ids, got %d", n, len(seen))
	}
}

var _ = bytes.MinRead
