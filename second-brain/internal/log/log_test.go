package log

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMiddlewareGeneratesRequestID(t *testing.T) {
	orig := slog.Default()
	defer slog.SetDefault(orig)

	var buf bytes.Buffer
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, nil)))

	var gotID string
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotID = FromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	Middleware(handler).ServeHTTP(rec, req)

	headerID := rec.Header().Get("X-Request-ID")
	if headerID == "" {
		t.Fatalf("expected X-Request-ID header to be non-empty")
	}
	if gotID != headerID {
		t.Fatalf("context id %q != header id %q", gotID, headerID)
	}
}

func TestMiddlewarePassthrough(t *testing.T) {
	orig := slog.Default()
	defer slog.SetDefault(orig)

	var buf bytes.Buffer
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, nil)))

	const want = "test-abc-123"
	var gotID string
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotID = FromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Request-ID", want)
	Middleware(handler).ServeHTTP(rec, req)

	if gotID != want {
		t.Fatalf("context id = %q, want %q", gotID, want)
	}
	if h := rec.Header().Get("X-Request-ID"); h != want {
		t.Fatalf("header id = %q, want %q", h, want)
	}
}

func TestMiddlewareLogsFields(t *testing.T) {
	orig := slog.Default()
	defer slog.SetDefault(orig)

	var buf bytes.Buffer
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, nil)))

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/health", nil)
	Middleware(handler).ServeHTTP(rec, req)

	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) == 0 || lines[len(lines)-1] == "" {
		t.Fatalf("expected log output, got %q", buf.String())
	}
	last := lines[len(lines)-1]

	var entry map[string]any
	if err := json.Unmarshal([]byte(last), &entry); err != nil {
		t.Fatalf("failed to parse log JSON: %v, raw=%q", err, last)
	}

	if entry["msg"] != "http.request" {
		t.Fatalf("msg = %v, want http.request", entry["msg"])
	}
	if _, ok := entry["request_id"]; !ok {
		t.Fatalf("missing request_id field")
	}
	if entry["method"] != "GET" {
		t.Fatalf("method = %v, want GET", entry["method"])
	}
	if entry["path"] != "/api/health" {
		t.Fatalf("path = %v, want /api/health", entry["path"])
	}
	status, ok := entry["status"].(float64)
	if !ok || int(status) != 200 {
		t.Fatalf("status = %v, want 200", entry["status"])
	}
	latency, ok := entry["latency_ms"].(float64)
	if !ok {
		t.Fatalf("latency_ms missing or not numeric: %v", entry["latency_ms"])
	}
	if latency < 0 {
		t.Fatalf("latency_ms = %v, want >= 0", latency)
	}
}

func TestMiddlewareLogsErrorLevel(t *testing.T) {
	orig := slog.Default()
	defer slog.SetDefault(orig)

	var buf bytes.Buffer
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, nil)))

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/boom", nil)
	Middleware(handler).ServeHTTP(rec, req)

	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) == 0 {
		t.Fatalf("expected log output")
	}
	last := lines[len(lines)-1]

	var entry map[string]any
	if err := json.Unmarshal([]byte(last), &entry); err != nil {
		t.Fatalf("failed to parse log JSON: %v, raw=%q", err, last)
	}

	if entry["level"] != "ERROR" {
		t.Fatalf("level = %v, want ERROR", entry["level"])
	}
	if _, ok := entry["request_id"]; !ok {
		t.Fatalf("missing request_id field")
	}
}

func TestNewRequestIDUnique(t *testing.T) {
	const n = 1000
	seen := make(map[string]struct{}, n)
	for i := 0; i < n; i++ {
		id := NewRequestID()
		if len(id) != 32 {
			t.Fatalf("id length = %d, want 32, id=%q", len(id), id)
		}
		for _, c := range id {
			if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
				t.Fatalf("id contains non-hex char %q in %q", c, id)
			}
		}
		if _, dup := seen[id]; dup {
			t.Fatalf("duplicate id generated: %q", id)
		}
		seen[id] = struct{}{}
	}
}

func TestFromContextEmpty(t *testing.T) {
	if got := FromContext(context.Background()); got != "" {
		t.Fatalf("FromContext(background) = %q, want empty", got)
	}
}

func TestInitLevel(t *testing.T) {
	orig := slog.Default()
	defer slog.SetDefault(orig)

	t.Setenv("SB_LOG_LEVEL", "debug")
	Init()
	if !slog.Default().Enabled(context.Background(), slog.LevelDebug) {
		t.Fatalf("expected Debug enabled after SB_LOG_LEVEL=debug")
	}

	t.Setenv("SB_LOG_LEVEL", "bogus")
	Init()
	if slog.Default().Enabled(context.Background(), slog.LevelDebug) {
		t.Fatalf("expected Debug disabled for bogus level")
	}
	if !slog.Default().Enabled(context.Background(), slog.LevelInfo) {
		t.Fatalf("expected Info enabled for bogus level")
	}
}

func TestRequestLogger(t *testing.T) {
	orig := slog.Default()
	defer slog.SetDefault(orig)

	var buf bytes.Buffer
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, nil)))

	ctx := WithRequestID(context.Background(), "abc-123")
	logger := RequestLogger(ctx)
	logger.Info("hello")
	logger2 := RequestLogger(context.Background())
	logger2.Info("world")

	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) != 2 {
		t.Fatalf("expected 2 log lines, got %d: %q", len(lines), buf.String())
	}

	var withID map[string]any
	if err := json.Unmarshal([]byte(lines[0]), &withID); err != nil {
		t.Fatalf("parse line0: %v, raw=%q", err, lines[0])
	}
	if withID["request_id"] != "abc-123" {
		t.Fatalf("request_id = %v, want abc-123", withID["request_id"])
	}

	var withoutID map[string]any
	if err := json.Unmarshal([]byte(lines[1]), &withoutID); err != nil {
		t.Fatalf("parse line1: %v, raw=%q", err, lines[1])
	}
	if _, ok := withoutID["request_id"]; ok {
		t.Fatalf("expected no request_id field, got %v", withoutID["request_id"])
	}
}
