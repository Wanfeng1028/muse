package api

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

type deep2Captured struct {
	method string
	header http.Header
	body   []byte
}

type deep2Capture struct {
	mu       sync.Mutex
	requests []deep2Captured
	sleep    time.Duration
}

func (c *deep2Capture) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		c.mu.Lock()
		c.requests = append(c.requests, deep2Captured{
			method: r.Method,
			header: r.Header.Clone(),
			body:   body,
		})
		sleep := c.sleep
		c.mu.Unlock()
		if sleep > 0 {
			time.Sleep(sleep)
		}
		w.WriteHeader(http.StatusOK)
	}
}

func (c *deep2Capture) snapshot() []deep2Captured {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]deep2Captured, len(c.requests))
	copy(out, c.requests)
	return out
}

func (c *deep2Capture) count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.requests)
}

func deep2SetupServer(t *testing.T, captureURL, secret string) (*store.Store, http.Handler) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	cols := []infer.Column{{Name: "id", Type: "INTEGER"}, {Name: "name", Type: "TEXT"}}
	if err := st.EnsureTable("users", "id", cols); err != nil {
		t.Fatalf("ensure table: %v", err)
	}
	if err := st.UpsertRow(st.DB, "users", "id", "1", []string{"id", "name"}, []any{"1", "alice"}, "h1", "srcA"); err != nil {
		t.Fatalf("upsert row: %v", err)
	}

	cfg := config.DefaultConfig()
	cfg.Notify.ConflictWebhookURL = captureURL
	cfg.Notify.ConflictWebhookSecret = secret
	cfg.Notify.ConflictWebhookTimeout = "5s"
	cfg.Notify.ConflictWebhookMaxRetries = 0
	cfg.Notify.ConflictEvents = []string{"conflict.resolved"}

	logger := log.New(io.Discard, "info")
	handler := NewServer(st, cfg, logger)
	return st, handler
}

func deep2RecordConflict(t *testing.T, st *store.Store) int64 {
	t.Helper()
	if _, err := st.RecordConflict(st.DB, store.Conflict{
		TableName: "users",
		PK:        "1",
		SourceA:   "srcA",
		SourceB:   "srcB",
		RowJSON:   `{"id":"1","name":"bob"}`,
		Status:    "pending",
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}); err != nil {
		t.Fatalf("record conflict: %v", err)
	}
	conflicts, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("list conflicts: %v", err)
	}
	if len(conflicts) == 0 {
		t.Fatalf("expected at least one pending conflict")
	}
	return conflicts[len(conflicts)-1].ID
}

func deep2ResolveBody(rowJSON, table, pkCol, pk string) []byte {
	payload := map[string]string{
		"row_json": rowJSON,
		"table":    table,
		"pk_col":   pkCol,
		"pk":       pk,
	}
	b, _ := json.Marshal(payload)
	return b
}

func deep2PostResolve(t *testing.T, handler http.Handler, path string, body []byte) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	return rr
}

func deep2PollFor(t *testing.T, timeout, interval time.Duration, cond func() bool) bool {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(interval)
	}
	return cond()
}

func deep2PollResolved(c *deep2Capture, timeout, interval time.Duration, want int) []deep2Captured {
	var matched []deep2Captured
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		matched = matched[:0]
		for _, req := range c.snapshot() {
			var payload map[string]any
			if err := json.Unmarshal(req.body, &payload); err != nil {
				continue
			}
			if ev, _ := payload["event"].(string); ev == "conflict.resolved" {
				matched = append(matched, req)
			}
		}
		if len(matched) >= want {
			return matched
		}
		time.Sleep(interval)
	}
	return matched
}

func deep2HMAC(secret string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

func TestDeep2ResolveFiresWebhookE2E(t *testing.T) {
	capture := &deep2Capture{}
	srv := httptest.NewServer(capture.handler())
	defer srv.Close()

	const secret = "deep2-secret"
	st, handler := deep2SetupServer(t, srv.URL, secret)
	id := deep2RecordConflict(t, st)

	body := deep2ResolveBody(`{"id":"1","name":"carol"}`, "users", "id", "1")
	path := "/api/conflicts/" + deep2IntToString(id) + "/resolve"
	rr := deep2PostResolve(t, handler, path, body)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !bytes.Contains(rr.Body.Bytes(), []byte("resolved")) {
		t.Fatalf("expected body to contain resolved, got %s", rr.Body.String())
	}

	matched := deep2PollResolved(capture, 10*time.Second, 50*time.Millisecond, 1)
	if len(matched) < 1 {
		t.Fatalf("expected conflict.resolved webhook delivery within 10s, got %d", len(matched))
	}
	req := matched[0]

	var payload map[string]any
	if err := json.Unmarshal(req.body, &payload); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}
	conflict, ok := payload["conflict"].(map[string]any)
	if !ok {
		t.Fatalf("payload missing conflict object: %v", payload)
	}
	if gotID, _ := conflict["id"].(float64); int64(gotID) != id {
		t.Fatalf("expected conflict.id %d, got %v", id, conflict["id"])
	}
	if status, _ := conflict["status"].(string); status != "resolved" {
		t.Fatalf("expected status resolved, got %v", conflict["status"])
	}

	sig := req.header.Get("X-Mortise-Signature")
	expected := "sha256=" + deep2HMAC(secret, req.body)
	if sig != expected {
		t.Fatalf("signature mismatch: got %q want %q", sig, expected)
	}
	if ev := req.header.Get("X-Mortise-Event"); ev != "conflict.resolved" {
		t.Fatalf("expected X-Mortise-Event conflict.resolved, got %q", ev)
	}
}

func TestDeep2ResolveBadRequestNoWebhook(t *testing.T) {
	capture := &deep2Capture{}
	srv := httptest.NewServer(capture.handler())
	defer srv.Close()

	st, handler := deep2SetupServer(t, srv.URL, "deep2-secret")
	id := deep2RecordConflict(t, st)

	rr := deep2PostResolve(t, handler, "/api/conflicts/abc/resolve", deep2ResolveBody(`{"id":"1","name":"carol"}`, "users", "id", "1"))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid id, got %d body=%s", rr.Code, rr.Body.String())
	}

	path := "/api/conflicts/" + deep2IntToString(id) + "/resolve"
	rr2 := deep2PostResolve(t, handler, path, []byte("not-json"))
	if rr2.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid JSON, got %d body=%s", rr2.Code, rr2.Body.String())
	}

	time.Sleep(2 * time.Second)
	if n := capture.count(); n != 0 {
		t.Fatalf("expected no webhook deliveries, got %d", n)
	}
}

func TestDeep2ResolveNonexistentIDNoWebhook(t *testing.T) {
	capture := &deep2Capture{}
	srv := httptest.NewServer(capture.handler())
	defer srv.Close()

	_, handler := deep2SetupServer(t, srv.URL, "deep2-secret")

	rr := deep2PostResolve(t, handler, "/api/conflicts/99999/resolve", deep2ResolveBody(`{"id":"1","name":"carol"}`, "users", "id", "1"))
	_ = rr

	time.Sleep(2 * time.Second)
	if n := capture.count(); n != 0 {
		t.Fatalf("expected no webhook deliveries for nonexistent id, got %d", n)
	}
}

func TestDeep2ResolveResponseNotBlockedByWebhook(t *testing.T) {
	capture := &deep2Capture{sleep: 3 * time.Second}
	srv := httptest.NewServer(capture.handler())
	defer srv.Close()

	st, handler := deep2SetupServer(t, srv.URL, "deep2-secret")
	id := deep2RecordConflict(t, st)

	body := deep2ResolveBody(`{"id":"1","name":"carol"}`, "users", "id", "1")
	path := "/api/conflicts/" + deep2IntToString(id) + "/resolve"

	start := time.Now()
	rr := deep2PostResolve(t, handler, path, body)
	elapsed := time.Since(start)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rr.Code, rr.Body.String())
	}
	if elapsed > 1500*time.Millisecond {
		t.Fatalf("expected HTTP response within 1.5s, took %v", elapsed)
	}

	matched := deep2PollResolved(capture, 10*time.Second, 50*time.Millisecond, 1)
	if len(matched) < 1 {
		t.Fatalf("expected conflict.resolved webhook delivery eventually, got %d", len(matched))
	}
}

func TestDeep2ResolveRowActuallyWritten(t *testing.T) {
	capture := &deep2Capture{}
	srv := httptest.NewServer(capture.handler())
	defer srv.Close()

	st, handler := deep2SetupServer(t, srv.URL, "deep2-secret")
	id := deep2RecordConflict(t, st)

	body := deep2ResolveBody(`{"id":"1","name":"carol"}`, "users", "id", "1")
	path := "/api/conflicts/" + deep2IntToString(id) + "/resolve"
	rr := deep2PostResolve(t, handler, path, body)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rr.Code, rr.Body.String())
	}

	cols, rows, err := st.Query("SELECT id, name FROM users WHERE id = '1'")
	if err != nil {
		t.Fatalf("query users: %v", err)
	}
	if len(rows) == 0 {
		t.Fatalf("expected row with id=1 to exist")
	}
	nameIdx := -1
	for i, c := range cols {
		if c == "name" {
			nameIdx = i
		}
	}
	if nameIdx < 0 {
		t.Fatalf("name column not found in %v", cols)
	}
	name, _ := rows[0][nameIdx].(string)
	if name != "carol" {
		t.Fatalf("expected name carol after resolve, got %q (row=%v)", name, rows[0])
	}
}

func TestDeep2ResolveIdempotentWebhook(t *testing.T) {
	capture := &deep2Capture{}
	srv := httptest.NewServer(capture.handler())
	defer srv.Close()

	st, handler := deep2SetupServer(t, srv.URL, "deep2-secret")
	id := deep2RecordConflict(t, st)

	body := deep2ResolveBody(`{"id":"1","name":"carol"}`, "users", "id", "1")
	path := "/api/conflicts/" + deep2IntToString(id) + "/resolve"

	rr1 := deep2PostResolve(t, handler, path, body)
	if rr1.Code != http.StatusOK {
		t.Fatalf("expected first resolve 200, got %d body=%s", rr1.Code, rr1.Body.String())
	}
	rr2 := deep2PostResolve(t, handler, path, body)
	if rr2.Code != http.StatusOK {
		t.Fatalf("expected second resolve 200, got %d body=%s", rr2.Code, rr2.Body.String())
	}

	matched := deep2PollResolved(capture, 10*time.Second, 50*time.Millisecond, 2)
	if len(matched) < 2 {
		t.Fatalf("expected 2 conflict.resolved deliveries, got %d", len(matched))
	}
}

func deep2IntToString(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var buf [20]byte
	i := len(buf)
	for v > 0 {
		i--
		buf[i] = byte('0' + v%10)
		v /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
