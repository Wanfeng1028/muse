package log

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

type safeBuf struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (s *safeBuf) Write(p []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.b.Write(p)
}

func (s *safeBuf) String() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.b.String()
}

func isLowerHex(s string) bool {
	for _, c := range s {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			return false
		}
	}
	return true
}

func TestNewRequestID_Format_Deep2(t *testing.T) {
	id := NewRequestID()
	if len(id) != 32 {
		t.Fatalf("NewRequestID() length = %d, want 32", len(id))
	}
	if !isLowerHex(id) {
		t.Fatalf("NewRequestID() = %q, want lowercase hex only", id)
	}
	_, err := hex.DecodeString(id)
	if err != nil {
		t.Fatalf("NewRequestID() = %q not valid hex: %v", id, err)
	}
}

func TestNewRequestID_ConcurrentUnique_Deep2(t *testing.T) {
	const n = 50
	var wg sync.WaitGroup
	ids := make([]string, n)
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			ids[idx] = NewRequestID()
		}(i)
	}
	wg.Wait()

	seen := make(map[string]int, n)
	for _, id := range ids {
		seen[id]++
	}
	if len(seen) != n {
		t.Fatalf("unique ids = %d, want %d", len(seen), n)
	}
}

func TestWithRequestID_NilCtx_Deep2(t *testing.T) {
	ctx := WithRequestID(nil, "x")
	if ctx == nil {
		t.Fatal("WithRequestID(nil, ...) returned nil context")
	}
	if got := FromContext(ctx); got != "x" {
		t.Fatalf("FromContext = %q, want %q", got, "x")
	}
}

func TestWithRequestID_Overwrite_Deep2(t *testing.T) {
	ctx := context.Background()
	ctx = WithRequestID(ctx, "a")
	if got := FromContext(ctx); got != "a" {
		t.Fatalf("FromContext = %q, want %q", got, "a")
	}
	ctx = WithRequestID(ctx, "b")
	if got := FromContext(ctx); got != "b" {
		t.Fatalf("FromContext = %q, want %q", got, "b")
	}
}

func TestParseLevel_Deep2(t *testing.T) {
	cases := []struct {
		in   string
		want slog.Level
	}{
		{"debug", slog.LevelDebug},
		{"DEBUG", slog.LevelDebug},
		{" warn ", slog.LevelWarn},
		{"Error", slog.LevelError},
		{"", slog.LevelInfo},
		{"bogus", slog.LevelInfo},
		{"info", slog.LevelInfo},
	}
	for _, c := range cases {
		if got := parseLevel(c.in); got != c.want {
			t.Errorf("parseLevel(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestFormatUint64Hex_Deep2(t *testing.T) {
	cases := []struct {
		in   uint64
		want string
	}{
		{0, "0"},
		{16, "10"},
		{255, "ff"},
		{0xABCDEF, "abcdef"},
	}
	for _, c := range cases {
		if got := formatUint64Hex(c.in); got != c.want {
			t.Errorf("formatUint64Hex(%d) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestStatusRecorder_Deep2(t *testing.T) {
	r1 := &statusRecorder{ResponseWriter: httptest.NewRecorder()}
	r1.WriteHeader(http.StatusNotFound)
	r1.WriteHeader(http.StatusOK)
	if r1.status != http.StatusNotFound {
		t.Fatalf("r1.status = %d, want %d", r1.status, http.StatusNotFound)
	}

	r2 := &statusRecorder{ResponseWriter: httptest.NewRecorder()}
	if _, err := r2.Write([]byte("x")); err != nil {
		t.Fatalf("r2.Write error: %v", err)
	}
	if r2.status != http.StatusOK {
		t.Fatalf("r2.status = %d, want %d", r2.status, http.StatusOK)
	}
}

func TestMiddleware_GeneratedIDFormat_Deep2(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := Middleware(next)

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	id := rec.Header().Get(requestIDHeader)
	if id == "" {
		t.Fatal("X-Request-ID header is empty, want generated id")
	}
	if len(id) != 32 {
		t.Fatalf("X-Request-ID length = %d, want 32", len(id))
	}
	if !isLowerHex(id) {
		t.Fatalf("X-Request-ID = %q, want lowercase hex only", id)
	}
}

func TestMiddleware_ConcurrentUniqueIDs_Deep2(t *testing.T) {
	const n = 30
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := Middleware(next)

	var wg sync.WaitGroup
	ids := make([]string, n)
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			req := httptest.NewRequest(http.MethodGet, "/", nil)
			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, req)
			ids[idx] = rec.Header().Get(requestIDHeader)
		}(i)
	}
	wg.Wait()

	seen := make(map[string]int, n)
	for _, id := range ids {
		if id == "" {
			t.Fatal("got empty X-Request-ID from middleware")
		}
		seen[id]++
	}
	if len(seen) != n {
		t.Fatalf("unique ids = %d, want %d", len(seen), n)
	}
}

func TestMiddleware_ConcurrentLogsNotInterleaved_Deep2(t *testing.T) {
	const n = 30

	orig := slog.Default()
	buf := &safeBuf{}
	handler := slog.NewJSONHandler(buf, &slog.HandlerOptions{Level: slog.LevelDebug})
	slog.SetDefault(slog.New(handler))
	defer slog.SetDefault(orig)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get(requestIDHeader)
		if id != "" && id[len(id)-1]%2 == 0 {
			w.WriteHeader(http.StatusOK)
		} else {
			w.WriteHeader(http.StatusInternalServerError)
		}
	})
	h := Middleware(next)

	ids := make([]string, n)
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			id := NewRequestID()
			ids[idx] = id
			req := httptest.NewRequest(http.MethodGet, "/", nil)
			req.Header.Set(requestIDHeader, id)
			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, req)
		}(i)
	}
	wg.Wait()

	valid := make(map[string]struct{}, n)
	for _, id := range ids {
		valid[id] = struct{}{}
	}

	content := strings.TrimSpace(buf.String())
	if content == "" {
		t.Fatal("no logs captured")
	}
	lines := strings.Split(content, "\n")
	if len(lines) != n {
		t.Fatalf("log lines = %d, want %d", len(lines), n)
	}
	for i, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			t.Fatalf("line %d is empty", i)
		}
		var m map[string]any
		if err := json.Unmarshal([]byte(line), &m); err != nil {
			t.Fatalf("line %d not valid JSON: %v (line=%q)", i, err, line)
		}
		msg, ok := m["msg"].(string)
		if !ok || msg != "http.request" {
			t.Fatalf("line %d msg = %v, want http.request", i, m["msg"])
		}
		rid, ok := m["request_id"].(string)
		if !ok {
			t.Fatalf("line %d missing request_id", i)
		}
		if _, ok := valid[rid]; !ok {
			t.Fatalf("line %d request_id = %q not among issued ids", i, rid)
		}
		if _, ok := m["status"]; !ok {
			t.Fatalf("line %d missing status field", i)
		}
	}
}
