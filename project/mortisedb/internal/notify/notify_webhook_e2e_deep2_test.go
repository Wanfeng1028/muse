package notify

import (
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	mlog "github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

type deep2Capture struct {
	mu       sync.Mutex
	requests []deep2Request
}

type deep2Request struct {
	Body   []byte
	Header http.Header
}

func (c *deep2Capture) append(r deep2Request) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.requests = append(c.requests, r)
}

func (c *deep2Capture) snapshot() []deep2Request {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]deep2Request, len(c.requests))
	copy(out, c.requests)
	return out
}

func (c *deep2Capture) count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.requests)
}

func deep2WaitFor(t *testing.T, cond func() bool, msg string) {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("timeout waiting for %s", msg)
}

func deep2E2EMetricValue(t *testing.T, rendered, event, status string) float64 {
	t.Helper()
	prefix := fmt.Sprintf("%s{event=%q,status=%q}", MetricDeliveries, event, status)
	var total float64
	for _, line := range strings.Split(rendered, "\n") {
		if !strings.HasPrefix(line, prefix) {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		var v float64
		if _, err := fmt.Sscanf(fields[len(fields)-1], "%g", &v); err != nil {
			continue
		}
		total += v
	}
	return total
}

func deep2VerifySignature(t *testing.T, secret string, body []byte, sigHeader string) {
	t.Helper()
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	want := "sha256=" + hex.EncodeToString(mac.Sum(nil))
	if sigHeader != want {
		t.Fatalf("signature mismatch: got %q want %q", sigHeader, want)
	}
}

func deep2E2EOpenStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(t.TempDir() + "/deep2.db")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	if st == nil || st.DB == nil {
		t.Fatalf("store.Open returned nil DB")
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("store.Migrate: %v", err)
	}
	return st
}

func deep2Config(url, secret string, events []string) *config.Config {
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = url
	cfg.Notify.ConflictWebhookSecret = secret
	cfg.Notify.ConflictWebhookTimeout = "5s"
	cfg.Notify.ConflictWebhookMaxRetries = 3
	cfg.Notify.ConflictEvents = events
	return cfg
}

func deep2Now() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func deep2Before(ts string) string {
	parsed, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return time.Now().UTC().Add(-time.Minute).Format(time.RFC3339)
	}
	return parsed.Add(-time.Minute).UTC().Format(time.RFC3339)
}

func TestDeep2E2E_PendingPayloadAndSignature(t *testing.T) {
	const secret = "deep2-secret-pending"
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, secret, []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	st := deep2E2EOpenStore(t)

	created := deep2Now()
	c := store.Conflict{
		TableName: "users",
		PK:        "42",
		SourceA:   "primary",
		SourceB:   "replica",
		RowJSON:   `{"id":42,"name":"alice"}`,
		Status:    "pending",
		CreatedAt: created,
	}
	if _, err := st.RecordConflict(st.DB, c); err != nil {
		t.Fatalf("RecordConflict: %v", err)
	}

	n.FireTableConflicts(st, "users", deep2Before(created))

	deep2WaitFor(t, func() bool { return cap.count() >= 1 }, "pending webhook delivery")
	reqs := cap.snapshot()
	req := reqs[0]

	var payload struct {
		Event      string `json:"event"`
		OccurredAt string `json:"occurred_at"`
		MortiseVer string `json:"mortise_version"`
		DeliveryID string `json:"delivery_id"`
		Conflict   struct {
			ID         int64  `json:"id"`
			TableName  string `json:"table_name"`
			PK         string `json:"pk"`
			SourceA    string `json:"source_a"`
			SourceB    string `json:"source_b"`
			RowJSON    string `json:"row_json"`
			Status     string `json:"status"`
			CreatedAt  string `json:"created_at"`
			ResolvedAt string `json:"resolved_at"`
		} `json:"conflict"`
	}
	if err := json.Unmarshal(req.Body, &payload); err != nil {
		t.Fatalf("unmarshal payload: %v body=%s", err, string(req.Body))
	}

	if payload.Event != EventPending {
		t.Fatalf("event = %q want %q", payload.Event, EventPending)
	}
	if payload.Conflict.TableName != "users" {
		t.Fatalf("table_name = %q", payload.Conflict.TableName)
	}
	if payload.Conflict.PK != "42" {
		t.Fatalf("pk = %q", payload.Conflict.PK)
	}
	if payload.Conflict.SourceA != "primary" {
		t.Fatalf("source_a = %q", payload.Conflict.SourceA)
	}
	if payload.Conflict.SourceB != "replica" {
		t.Fatalf("source_b = %q", payload.Conflict.SourceB)
	}
	if payload.Conflict.RowJSON != `{"id":42,"name":"alice"}` {
		t.Fatalf("row_json = %q", payload.Conflict.RowJSON)
	}
	if payload.Conflict.Status != "pending" {
		t.Fatalf("status = %q want pending", payload.Conflict.Status)
	}
	if payload.DeliveryID == "" {
		t.Fatalf("delivery_id empty")
	}
	if payload.MortiseVer == "" {
		t.Fatalf("mortise_version empty")
	}
	if _, err := time.Parse(time.RFC3339, payload.OccurredAt); err != nil {
		t.Fatalf("occurred_at not RFC3339: %q err=%v", payload.OccurredAt, err)
	}

	deep2VerifySignature(t, secret, req.Body, req.Header.Get("X-Mortise-Signature"))
	if got := req.Header.Get("X-Mortise-Event"); got != EventPending {
		t.Fatalf("X-Mortise-Event = %q want %q", got, EventPending)
	}
	if got := req.Header.Get("X-Mortise-Delivery-Id"); got != payload.DeliveryID {
		t.Fatalf("X-Mortise-Delivery-Id = %q want %q", got, payload.DeliveryID)
	}
}

func TestDeep2E2E_ResolvedAutoPayload(t *testing.T) {
	const secret = "deep2-secret-resolved-auto"
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, secret, []string{EventResolvedAuto})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	st := deep2E2EOpenStore(t)

	created := deep2Now()
	resolved := deep2Now()
	c := store.Conflict{
		TableName:  "orders",
		PK:         "7",
		SourceA:    "a",
		SourceB:    "b",
		RowJSON:    `{"id":7}`,
		Status:     "resolved_auto",
		CreatedAt:  created,
		ResolvedAt: resolved,
	}
	if _, err := st.RecordConflict(st.DB, c); err != nil {
		t.Fatalf("RecordConflict: %v", err)
	}

	n.FireTableConflicts(st, "orders", deep2Before(resolved))

	deep2WaitFor(t, func() bool { return cap.count() >= 1 }, "resolved_auto webhook delivery")
	req := cap.snapshot()[0]

	var payload struct {
		Event    string `json:"event"`
		Conflict struct {
			Status     string `json:"status"`
			ResolvedAt string `json:"resolved_at"`
		} `json:"conflict"`
	}
	if err := json.Unmarshal(req.Body, &payload); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}
	if payload.Event != EventResolvedAuto {
		t.Fatalf("event = %q want %q", payload.Event, EventResolvedAuto)
	}
	if payload.Conflict.Status != "resolved_auto" {
		t.Fatalf("status = %q", payload.Conflict.Status)
	}
	if payload.Conflict.ResolvedAt == "" {
		t.Fatalf("resolved_at empty")
	}
	deep2VerifySignature(t, secret, req.Body, req.Header.Get("X-Mortise-Signature"))
}

func TestDeep2E2E_ResolvedEventDirect(t *testing.T) {
	const secret = "deep2-secret-direct"
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, secret, []string{EventResolved})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	c := store.Conflict{
		TableName:  "items",
		PK:         "99",
		SourceA:    "x",
		SourceB:    "y",
		RowJSON:    `{"id":99}`,
		Status:     "resolved",
		CreatedAt:  deep2Now(),
		ResolvedAt: deep2Now(),
	}
	n.NotifyAsync(EventResolved, c)

	deep2WaitFor(t, func() bool { return cap.count() >= 1 }, "resolved webhook delivery")
	req := cap.snapshot()[0]

	var payload struct {
		Event    string `json:"event"`
		Conflict struct {
			Status string `json:"status"`
		} `json:"conflict"`
	}
	if err := json.Unmarshal(req.Body, &payload); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}
	if payload.Event != EventResolved {
		t.Fatalf("event = %q want %q", payload.Event, EventResolved)
	}
	deep2VerifySignature(t, secret, req.Body, req.Header.Get("X-Mortise-Signature"))
	if got := req.Header.Get("X-Mortise-Event"); got != EventResolved {
		t.Fatalf("X-Mortise-Event = %q want %q", got, EventResolved)
	}
}

func TestDeep2E2E_AsyncNeverBlocks(t *testing.T) {
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, "deep2-secret-nonblock", []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	c := store.Conflict{
		TableName: "t",
		PK:        "1",
		Status:    "pending",
		CreatedAt: deep2Now(),
	}

	start := time.Now()
	n.NotifyAsync(EventPending, c)
	elapsed := time.Since(start)
	if elapsed > 500*time.Millisecond {
		t.Fatalf("NotifyAsync blocked for %v (want <= 500ms)", elapsed)
	}

	deep2WaitFor(t, func() bool { return cap.count() >= 1 }, "delivery after slow handler")
}

func TestDeep2E2E_RetryOn500ThenSuccess(t *testing.T) {
	const secret = "deep2-secret-retry"
	cap := &deep2Capture{}
	var attempts int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		n := atomic.AddInt32(&attempts, 1)
		if n <= 2 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, secret, []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	before := metrics.Default().Render()
	beforeDelivered := deep2E2EMetricValue(t, before, EventPending, "delivered")

	c := store.Conflict{TableName: "t", PK: "2", Status: "pending", CreatedAt: deep2Now()}
	n.NotifyAsync(EventPending, c)

	deep2WaitFor(t, func() bool {
		return atomic.LoadInt32(&attempts) >= 3 && cap.count() >= 3
	}, "retry attempts")

	deep2WaitFor(t, func() bool {
		after := metrics.Default().Render()
		return deep2E2EMetricValue(t, after, EventPending, "delivered")-beforeDelivered >= 1
	}, "delivered metric increment")

	if got := atomic.LoadInt32(&attempts); got != 3 {
		t.Fatalf("total attempts = %d want 3", got)
	}
}

func TestDeep2E2E_NoRetryOn400(t *testing.T) {
	const secret = "deep2-secret-400"
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, secret, []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	before := metrics.Default().Render()
	beforeDropped := deep2E2EMetricValue(t, before, EventPending, "dropped")

	c := store.Conflict{TableName: "t", PK: "3", Status: "pending", CreatedAt: deep2Now()}
	n.NotifyAsync(EventPending, c)

	deep2WaitFor(t, func() bool { return cap.count() >= 1 }, "400 delivery attempt")
	deep2WaitFor(t, func() bool {
		after := metrics.Default().Render()
		return deep2E2EMetricValue(t, after, EventPending, "dropped")-beforeDropped >= 1
	}, "dropped metric increment")

	time.Sleep(500 * time.Millisecond)
	if got := cap.count(); got != 1 {
		t.Fatalf("request count = %d want exactly 1 (no retry on 400)", got)
	}
}

func TestDeep2E2E_UnsubscribedDropped(t *testing.T) {
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, "deep2-secret-unsub", []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	before := metrics.Default().Render()
	beforeDropped := deep2E2EMetricValue(t, before, EventResolved, "dropped")

	c := store.Conflict{TableName: "t", PK: "4", Status: "resolved", CreatedAt: deep2Now()}
	n.NotifyAsync(EventResolved, c)

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if cap.count() > 0 {
			t.Fatalf("unexpected delivery for unsubscribed event")
		}
		time.Sleep(50 * time.Millisecond)
	}
	if got := cap.count(); got != 0 {
		t.Fatalf("request count = %d want 0", got)
	}

	deep2WaitFor(t, func() bool {
		after := metrics.Default().Render()
		return deep2E2EMetricValue(t, after, EventResolved, "dropped")-beforeDropped >= 1
	}, "dropped metric increment for unsubscribed event")
}

func TestDeep2E2E_DisabledDropped(t *testing.T) {
	cfg := deep2Config("", "deep2-secret-disabled", []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	st := deep2E2EOpenStore(t)

	before := metrics.Default().Render()
	beforeDropped := deep2E2EMetricValue(t, before, EventPending, "dropped")

	created := deep2Now()
	c := store.Conflict{TableName: "t", PK: "5", Status: "pending", CreatedAt: created}
	if _, err := st.RecordConflict(st.DB, c); err != nil {
		t.Fatalf("RecordConflict: %v", err)
	}

	n.FireTableConflicts(st, "t", deep2Before(created))

	// 未启用时 FireTableConflicts 直接返回、不查库、不记 dropped 指标；
	// 这里只断言没有发起任何投递尝试。
	after := metrics.Default().Render()
	if got := deep2E2EMetricValue(t, after, EventPending, "dropped") - beforeDropped; got != 0 {
		t.Fatalf("expected no dropped increment when disabled, got %v", got)
	}
}

func TestDeep2E2E_DeliveryIDUnique(t *testing.T) {
	const secret = "deep2-secret-unique"
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, secret, []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))

	c := store.Conflict{TableName: "t", PK: "6", Status: "pending", CreatedAt: deep2Now()}
	n.NotifyAsync(EventPending, c)
	n.NotifyAsync(EventPending, c)

	deep2WaitFor(t, func() bool { return cap.count() >= 2 }, "two deliveries")
	reqs := cap.snapshot()

	var idA, idB string
	for _, r := range reqs {
		var p struct {
			DeliveryID string `json:"delivery_id"`
		}
		if err := json.Unmarshal(r.Body, &p); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if idA == "" {
			idA = p.DeliveryID
		} else {
			idB = p.DeliveryID
		}
	}
	if idA == "" || idB == "" {
		t.Fatalf("delivery_id empty: a=%q b=%q", idA, idB)
	}
	if idA == idB {
		t.Fatalf("delivery_id not unique: %q == %q", idA, idB)
	}
}

func TestDeep2E2E_OnlyCommittedDelivered(t *testing.T) {
	cap := &deep2Capture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		cap.append(deep2Request{Body: body, Header: r.Header.Clone()})
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := deep2Config(srv.URL, "deep2-secret-commit", []string{EventPending})
	n := FromConfig(cfg, mlog.New(io.Discard, "info"))
	st := deep2E2EOpenStore(t)

	created1 := deep2Now()
	tx, err := st.DB.Begin()
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	if _, err := st.RecordConflict(tx, store.Conflict{
		TableName: "tx",
		PK:        "100",
		Status:    "pending",
		CreatedAt: created1,
	}); err != nil {
		tx.Rollback()
		t.Fatalf("RecordConflict in tx: %v", err)
	}
	if err := tx.Rollback(); err != nil {
		t.Fatalf("Rollback: %v", err)
	}

	n.FireTableConflicts(st, "tx", deep2Before(created1))

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if cap.count() > 0 {
			t.Fatalf("unexpected delivery for rolled-back conflict")
		}
		time.Sleep(50 * time.Millisecond)
	}
	if got := cap.count(); got != 0 {
		t.Fatalf("deliveries after rollback = %d want 0", got)
	}

	created2 := deep2Now()
	if _, err := st.RecordConflict(st.DB, store.Conflict{
		TableName: "tx",
		PK:        "200",
		Status:    "pending",
		CreatedAt: created2,
	}); err != nil {
		t.Fatalf("RecordConflict committed: %v", err)
	}

	n.FireTableConflicts(st, "tx", deep2Before(created2))

	deep2WaitFor(t, func() bool { return cap.count() >= 1 }, "committed conflict delivery")

	var lastBody []byte
	for _, r := range cap.snapshot() {
		lastBody = r.Body
	}
	var payload struct {
		Conflict struct {
			PK string `json:"pk"`
		} `json:"conflict"`
	}
	if err := json.Unmarshal(lastBody, &payload); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if payload.Conflict.PK != "200" {
		t.Fatalf("delivered pk = %q want 200", payload.Conflict.PK)
	}
	_ = sql.ErrNoRows
}
