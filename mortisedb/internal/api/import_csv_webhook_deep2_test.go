package api

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
	syncpkg "github.com/Wanfeng1028/muse/mortisedb/internal/sync"
)

type deep2ImportCapture struct {
	mu       sync.Mutex
	requests []deep2Req
}

type deep2Req struct {
	body      []byte
	signature string
}

func (c *deep2ImportCapture) handler(secret string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		c.mu.Lock()
		c.requests = append(c.requests, deep2Req{body: body, signature: r.Header.Get("X-Mortise-Signature")})
		c.mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}
}

func (c *deep2ImportCapture) snapshot() []deep2Req {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]deep2Req, len(c.requests))
	copy(out, c.requests)
	return out
}

func deep2Wait(t *testing.T, cond func() bool) bool {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(50 * time.Millisecond)
	}
	return cond()
}

func deep2VerifySig(secret string, body []byte, sig string) bool {
	if !strings.HasPrefix(sig, "sha256=") {
		return false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(expected), []byte(sig))
}

func deep2BuildMultipart(t *testing.T, fileContent string, fields map[string]string, includeFile bool) (*bytes.Buffer, string) {
	t.Helper()
	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)
	if includeFile {
		fw, err := w.CreateFormFile("file", "t.csv")
		if err != nil {
			t.Fatalf("CreateFormFile: %v", err)
		}
		if _, err := fw.Write([]byte(fileContent)); err != nil {
			t.Fatalf("write file: %v", err)
		}
	}
	for k, v := range fields {
		if err := w.WriteField(k, v); err != nil {
			t.Fatalf("WriteField: %v", err)
		}
	}
	if err := w.Close(); err != nil {
		t.Fatalf("close writer: %v", err)
	}
	return &buf, w.FormDataContentType()
}

func deep2Setup(t *testing.T) (*store.Store, *config.Config, *log.Logger) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	if err := st.EnsureTable("users", "id", []infer.Column{{Name: "id", Type: "TEXT"}, {Name: "name", Type: "TEXT"}}); err != nil {
		t.Fatalf("EnsureTable: %v", err)
	}
	seedHash := syncpkg.HashRow("1", []string{"id", "name"}, []any{"1", "alice"})
	if err := st.UpsertRow(st.DB, "users", "id", "1", []string{"id", "name"}, []any{"1", "alice"}, seedHash, "srcA"); err != nil {
		t.Fatalf("UpsertRow: %v", err)
	}
	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{{Name: "csvsrc", Type: "csv"}}
	return st, cfg, log.New(io.Discard, "info")
}

func deep2GetName(t *testing.T, st *store.Store, table, pk string) string {
	t.Helper()
	cols, rows, err := st.Query(fmt.Sprintf(`SELECT "name" FROM "%s" WHERE "id"='%s'`, table, pk))
	if err != nil {
		t.Fatalf("query name: %v", err)
	}
	if len(rows) == 0 {
		return ""
	}
	nameIdx := -1
	for i, c := range cols {
		if c == "name" {
			nameIdx = i
		}
	}
	if nameIdx < 0 || nameIdx >= len(rows[0]) {
		return ""
	}
	s, _ := rows[0][nameIdx].(string)
	return s
}

func TestDeep2ImportCSV_PendingFiresWebhook(t *testing.T) {
	st, cfg, logger := deep2Setup(t)
	cfg.Sync.Conflict = "manual"

	cap := &deep2ImportCapture{}
	secret := "deep2secret"
	ts := httptest.NewServer(cap.handler(secret))
	defer ts.Close()
	cfg.Notify.ConflictWebhookURL = ts.URL
	cfg.Notify.ConflictWebhookSecret = secret

	srv := NewServer(st, cfg, logger)

	body, ct := deep2BuildMultipart(t, "id,name\n1,bob\n", map[string]string{
		"source":      "csvsrc",
		"table":       "users",
		"primary_key": "id",
	}, true)

	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d body=%s", rec.Code, rec.Body.String())
	}

	ok := deep2Wait(t, func() bool {
		for _, r := range cap.snapshot() {
			var payload map[string]any
			if err := json.Unmarshal(r.body, &payload); err != nil {
				continue
			}
			if payload["event"] == "conflict.pending" {
				return true
			}
		}
		return false
	})
	if !ok {
		t.Fatalf("no conflict.pending webhook delivered")
	}

	var found *deep2Req
	for i := range cap.snapshot() {
		r := cap.snapshot()[i]
		var payload map[string]any
		if err := json.Unmarshal(r.body, &payload); err != nil {
			continue
		}
		if payload["event"] == "conflict.pending" {
			found = &r
			break
		}
	}
	if found == nil {
		t.Fatalf("pending webhook missing")
	}

	var payload map[string]any
	if err := json.Unmarshal(found.body, &payload); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}
	conflict, _ := payload["conflict"].(map[string]any)
	if conflict == nil {
		t.Fatalf("payload.payload missing: %s", string(found.body))
	}
	if got, _ := conflict["source_a"].(string); got != "srcA" {
		t.Fatalf("source_a = %q, want srcA", got)
	}
	if got, _ := conflict["source_b"].(string); got != "csvsrc" {
		t.Fatalf("source_b = %q, want csvsrc", got)
	}
	if got, _ := conflict["pk"].(string); got != "1" {
		t.Fatalf("pk = %q, want 1", got)
	}
	if got, _ := conflict["status"].(string); got != "pending" {
		t.Fatalf("status = %q, want pending", got)
	}
	if !deep2VerifySig(secret, found.body, found.signature) {
		t.Fatalf("signature invalid: %q", found.signature)
	}

	conflicts, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(conflicts) != 1 {
		t.Fatalf("expected 1 pending conflict, got %d", len(conflicts))
	}
}

func TestDeep2ImportCSV_ResolvedAutoFiresWebhook(t *testing.T) {
	st, cfg, logger := deep2Setup(t)
	cfg.Sync.Conflict = "priority"
	cfg.Sync.Priority = []string{"csvsrc", "srcA"}

	cap := &deep2ImportCapture{}
	secret := "deep2secret"
	ts := httptest.NewServer(cap.handler(secret))
	defer ts.Close()
	cfg.Notify.ConflictWebhookURL = ts.URL
	cfg.Notify.ConflictWebhookSecret = secret

	srv := NewServer(st, cfg, logger)

	body, ct := deep2BuildMultipart(t, "id,name\n1,bob\n", map[string]string{
		"source":      "csvsrc",
		"table":       "users",
		"primary_key": "id",
	}, true)

	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	ok := deep2Wait(t, func() bool {
		for _, r := range cap.snapshot() {
			var payload map[string]any
			if err := json.Unmarshal(r.body, &payload); err != nil {
				continue
			}
			if payload["event"] == "conflict.resolved_auto" {
				return true
			}
		}
		return false
	})
	if !ok {
		t.Fatalf("no conflict.resolved_auto webhook delivered")
	}

	if got := deep2GetName(t, st, "users", "1"); got != "bob" {
		t.Fatalf("name = %q, want bob", got)
	}
}

func TestDeep2ImportCSV_NoConflictNoWebhook(t *testing.T) {
	st, cfg, logger := deep2Setup(t)
	cfg.Sync.Conflict = "manual"

	cap := &deep2ImportCapture{}
	secret := "deep2secret"
	ts := httptest.NewServer(cap.handler(secret))
	defer ts.Close()
	cfg.Notify.ConflictWebhookURL = ts.URL
	cfg.Notify.ConflictWebhookSecret = secret

	srv := NewServer(st, cfg, logger)

	body, ct := deep2BuildMultipart(t, "id,name\n2,bob\n", map[string]string{
		"source":      "csvsrc",
		"table":       "users",
		"primary_key": "id",
	}, true)

	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	time.Sleep(2 * time.Second)
	if len(cap.snapshot()) != 0 {
		t.Fatalf("expected no webhooks, got %d", len(cap.snapshot()))
	}

	conflicts, err := st.ListConflicts("")
	if err != nil {
		t.Fatalf("ListConflicts: %v", err)
	}
	if len(conflicts) != 0 {
		t.Fatalf("expected 0 conflicts, got %d", len(conflicts))
	}
}

func TestDeep2ImportCSV_SameContentNoWebhook(t *testing.T) {
	st, cfg, logger := deep2Setup(t)
	cfg.Sync.Conflict = "manual"

	cap := &deep2ImportCapture{}
	secret := "deep2secret"
	ts := httptest.NewServer(cap.handler(secret))
	defer ts.Close()
	cfg.Notify.ConflictWebhookURL = ts.URL
	cfg.Notify.ConflictWebhookSecret = secret

	srv := NewServer(st, cfg, logger)

	body, ct := deep2BuildMultipart(t, "id,name\n1,alice\n", map[string]string{
		"source":      "csvsrc",
		"table":       "users",
		"primary_key": "id",
	}, true)

	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	time.Sleep(2 * time.Second)
	if len(cap.snapshot()) != 0 {
		t.Fatalf("expected no webhooks, got %d", len(cap.snapshot()))
	}
}

func TestDeep2ImportCSV_UnknownSourceNoWebhook(t *testing.T) {
	st, cfg, logger := deep2Setup(t)
	cfg.Sync.Conflict = "manual"

	cap := &deep2ImportCapture{}
	secret := "deep2secret"
	ts := httptest.NewServer(cap.handler(secret))
	defer ts.Close()
	cfg.Notify.ConflictWebhookURL = ts.URL
	cfg.Notify.ConflictWebhookSecret = secret

	srv := NewServer(st, cfg, logger)

	body, ct := deep2BuildMultipart(t, "id,name\n1,bob\n", map[string]string{
		"source":      "nosuch",
		"table":       "users",
		"primary_key": "id",
	}, true)

	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rec.Code, rec.Body.String())
	}

	time.Sleep(2 * time.Second)
	if len(cap.snapshot()) != 0 {
		t.Fatalf("expected no webhooks, got %d", len(cap.snapshot()))
	}
}

func TestDeep2ImportCSV_MissingFileNoWebhook(t *testing.T) {
	st, cfg, logger := deep2Setup(t)
	cfg.Sync.Conflict = "manual"

	cap := &deep2ImportCapture{}
	secret := "deep2secret"
	ts := httptest.NewServer(cap.handler(secret))
	defer ts.Close()
	cfg.Notify.ConflictWebhookURL = ts.URL
	cfg.Notify.ConflictWebhookSecret = secret

	srv := NewServer(st, cfg, logger)

	body, ct := deep2BuildMultipart(t, "", map[string]string{
		"source":      "csvsrc",
		"table":       "users",
		"primary_key": "id",
	}, false)

	req := httptest.NewRequest(http.MethodPost, "/api/import/csv", body)
	req.Header.Set("Content-Type", ct)
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rec.Code, rec.Body.String())
	}

	time.Sleep(2 * time.Second)
	if len(cap.snapshot()) != 0 {
		t.Fatalf("expected no webhooks, got %d", len(cap.snapshot()))
	}
}
