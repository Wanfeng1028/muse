package log

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// parseLines 把多行 JSON 日志拆成 map 列表，任一行不是合法 JSON 直接 Fatal。
func parseLines(t *testing.T, raw string) []map[string]any {
	t.Helper()
	trimmed := strings.TrimRight(raw, "\n")
	if trimmed == "" {
		return nil
	}
	lines := strings.Split(trimmed, "\n")
	out := make([]map[string]any, 0, len(lines))
	for i, ln := range lines {
		var m map[string]any
		if err := json.Unmarshal([]byte(ln), &m); err != nil {
			t.Fatalf("第 %d 行不是合法 JSON: %v, 原文=%q", i, err, ln)
		}
		out = append(out, m)
	}
	return out
}

// TestLoggerMultiSourceFieldConflictLastWriteWins 验证多源拼装时同 key 不同值的覆盖顺序。
// log() 先写基础字段 ts/level/msg，再遍历 fields 覆盖写入，所以 fields 里的同名 key 会顶掉基础字段。
func TestLoggerMultiSourceFieldConflictLastWriteWins(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "info")

	// 故意用 level、msg、ts 三个基础 key 去撞。
	l.Info("原始消息", map[string]any{
		"level": "error",
		"msg":   "被字段覆盖",
		"ts":    "1999-01-01T00:00:00Z",
		"user":  "晚风",
	})

	entries := parseLines(t, buf.String())
	if len(entries) != 1 {
		t.Fatalf("期望 1 条日志, 实际 %d", len(entries))
	}
	e := entries[0]
	if e["level"] != "error" {
		t.Fatalf("level 应被 fields 覆盖为 error, 实际 %v", e["level"])
	}
	if e["msg"] != "被字段覆盖" {
		t.Fatalf("msg 应被 fields 覆盖, 实际 %v", e["msg"])
	}
	if e["ts"] != "1999-01-01T00:00:00Z" {
		t.Fatalf("ts 应被 fields 覆盖, 实际 %v", e["ts"])
	}
	if e["user"] != "晚风" {
		t.Fatalf("user 字段应保留, 实际 %v", e["user"])
	}
}

// TestLoggerMultiSourceFieldConflictNonStringValues 验证同 key 覆盖到非字符串类型时也生效。
func TestLoggerMultiSourceFieldConflictNonStringValues(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "info")

	l.Info("a", map[string]any{"n": 1, "ok": true})
	l.Info("b", map[string]any{"n": 2, "ok": false})

	entries := parseLines(t, buf.String())
	if len(entries) != 2 {
		t.Fatalf("期望 2 条日志, 实际 %d", len(entries))
	}
	if entries[0]["n"].(float64) != 1 {
		t.Fatalf("第一条 n 应为 1, 实际 %v", entries[0]["n"])
	}
	if entries[1]["n"].(float64) != 2 {
		t.Fatalf("第二条 n 应为 2, 实际 %v", entries[1]["n"])
	}
	if entries[0]["ok"] != true {
		t.Fatalf("第一条 ok 应为 true, 实际 %v", entries[0]["ok"])
	}
	if entries[1]["ok"] != false {
		t.Fatalf("第二条 ok 应为 false, 实际 %v", entries[1]["ok"])
	}
}

// TestLoggerConcurrentWriteRaceSafe 并发写同一个 Logger，验证 -race 下不炸且每条都是合法 JSON。
func TestLoggerConcurrentWriteRaceSafe(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "info")

	const goroutines = 16
	const perG = 32
	var wg sync.WaitGroup
	wg.Add(goroutines)
	for g := 0; g < goroutines; g++ {
		go func(gid int) {
			defer wg.Done()
			for i := 0; i < perG; i++ {
				l.Info("并发", map[string]any{"g": gid, "i": i})
			}
		}(g)
	}
	wg.Wait()

	entries := parseLines(t, buf.String())
	if len(entries) != goroutines*perG {
		t.Fatalf("期望 %d 条日志, 实际 %d", goroutines*perG, len(entries))
	}
	for i, e := range entries {
		if e["msg"] != "并发" {
			t.Fatalf("第 %d 条 msg 不对: %v", i, e["msg"])
		}
		if _, ok := e["g"]; !ok {
			t.Fatalf("第 %d 条缺少 g 字段", i)
		}
	}
}

// TestLoggerLevelCaseInsensitiveStoredVerbatim 验证 level 大小写敏感存储：源码没做归一化。
// New 仅在 level=="" 时回填 "info"，传入的大写字符串原样保留。
func TestLoggerLevelCaseInsensitiveStoredVerbatim(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "INFO")
	l.Warn("w", nil)
	l.Error("e", nil)

	entries := parseLines(t, buf.String())
	if len(entries) != 2 {
		t.Fatalf("期望 2 条日志, 实际 %d", len(entries))
	}
	if entries[0]["level"] != "warn" {
		t.Fatalf("Warn 应写 warn, 实际 %v", entries[0]["level"])
	}
	if entries[1]["level"] != "error" {
		t.Fatalf("Error 应写 error, 实际 %v", entries[1]["level"])
	}
}

// TestRequestIDRoundTripAndEmpty 验证 context 里请求 ID 的存取与缺省。
func TestRequestIDRoundTripAndEmpty(t *testing.T) {
	if got := RequestIDFrom(context.Background()); got != "" {
		t.Fatalf("空 context 应返回空串, 实际 %q", got)
	}
	ctx := WithRequestID(context.Background(), "rid-123")
	if got := RequestIDFrom(ctx); got != "rid-123" {
		t.Fatalf("期望 rid-123, 实际 %q", got)
	}
	// 覆盖写：同 key 再次 WithRequestID 应替换
	ctx2 := WithRequestID(ctx, "rid-456")
	if got := RequestIDFrom(ctx2); got != "rid-456" {
		t.Fatalf("覆盖后期望 rid-456, 实际 %q", got)
	}
}

// TestNewRequestIDUniqueAndTimestamped 验证请求 ID 唯一且带纳秒时间戳前缀。
func TestNewRequestIDUniqueAndTimestamped(t *testing.T) {
	const n = 200
	seen := make(map[string]struct{}, n)
	for i := 0; i < n; i++ {
		id := NewRequestID()
		if id == "" {
			t.Fatal("请求 ID 不应为空")
		}
		parts := strings.SplitN(id, "-", 2)
		if len(parts) != 2 {
			t.Fatalf("请求 ID 格式应为 纳秒-随机hex, 实际 %q", id)
		}
		if len(parts[1]) != 16 {
			t.Fatalf("随机部分应为 16 位 hex, 实际 %q", parts[1])
		}
		if _, err := time.ParseDuration(parts[0] + "ns"); err != nil {
			t.Fatalf("前缀应为纳秒时间戳, 实际 %q, err=%v", parts[0], err)
		}
		if _, dup := seen[id]; dup {
			t.Fatalf("请求 ID 重复: %q", id)
		}
		seen[id] = struct{}{}
	}
}

// TestRequestIDMiddlewareLogsAccessAndInjectsID 验证中间件注入请求 ID、记录访问日志。
func TestRequestIDMiddlewareLogsAccessAndInjectsID(t *testing.T) {
	var buf bytes.Buffer
	logger := New(&buf, "info")

	var seenID string
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenID = RequestIDFrom(r.Context())
		w.WriteHeader(http.StatusTeapot)
		_, _ = w.Write([]byte("hi"))
	})

	h := RequestIDMiddleware(inner, logger)
	req := httptest.NewRequest(http.MethodGet, "/orders/42", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if seenID == "" {
		t.Fatal("handler 内应能从 context 取到请求 ID")
	}
	if rec.Code != http.StatusTeapot {
		t.Fatalf("响应码应为 418, 实际 %d", rec.Code)
	}

	entries := parseLines(t, buf.String())
	if len(entries) != 1 {
		t.Fatalf("期望 1 条访问日志, 实际 %d", len(entries))
	}
	e := entries[0]
	if e["request_id"] != seenID {
		t.Fatalf("日志 request_id 应等于 handler 内取到的 ID, 日志=%v handler=%v", e["request_id"], seenID)
	}
	if e["method"] != http.MethodGet {
		t.Fatalf("method 应为 GET, 实际 %v", e["method"])
	}
	if e["path"] != "/orders/42" {
		t.Fatalf("path 应为 /orders/42, 实际 %v", e["path"])
	}
	if e["status"].(float64) != float64(http.StatusTeapot) {
		t.Fatalf("status 应为 418, 实际 %v", e["status"])
	}
	if _, ok := e["duration_ms"]; !ok {
		t.Fatal("访问日志应包含 duration_ms")
	}
}

// TestRequestIDMiddlewareDefaultStatusWhenHandlerSilent 验证 handler 不显式 WriteHeader 时默认 200。
func TestRequestIDMiddlewareDefaultStatusWhenHandlerSilent(t *testing.T) {
	var buf bytes.Buffer
	logger := New(&buf, "info")

	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("ok"))
	})

	h := RequestIDMiddleware(inner, logger)
	req := httptest.NewRequest(http.MethodPost, "/ping", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("响应码应为 200, 实际 %d", rec.Code)
	}
	entries := parseLines(t, buf.String())
	if len(entries) != 1 {
		t.Fatalf("期望 1 条日志, 实际 %d", len(entries))
	}
	if entries[0]["status"].(float64) != float64(http.StatusOK) {
		t.Fatalf("日志 status 应为 200, 实际 %v", entries[0]["status"])
	}
	if entries[0]["method"] != http.MethodPost {
		t.Fatalf("method 应为 POST, 实际 %v", entries[0]["method"])
	}
}

// TestRequestIDMiddlewareDistinctIDsAcrossRequests 验证多次请求 ID 不重复且日志条数正确。
func TestRequestIDMiddlewareDistinctIDsAcrossRequests(t *testing.T) {
	var buf bytes.Buffer
	logger := New(&buf, "info")
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
	h := RequestIDMiddleware(inner, logger)

	const n = 50
	for i := 0; i < n; i++ {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
	}

	entries := parseLines(t, buf.String())
	if len(entries) != n {
		t.Fatalf("期望 %d 条日志, 实际 %d", n, len(entries))
	}
	seen := make(map[string]struct{}, n)
	for i, e := range entries {
		id, _ := e["request_id"].(string)
		if id == "" {
			t.Fatalf("第 %d 条日志缺少 request_id", i)
		}
		if _, dup := seen[id]; dup {
			t.Fatalf("request_id 重复: %q", id)
		}
		seen[id] = struct{}{}
	}
}

// errWriter 永远返回错误，用来触发 log 的序列化兜底路径。
type errWriter struct{}

func (errWriter) Write(p []byte) (int, error) { return 0, errors.New("write failed") }

// TestLoggerMarshalFallbackOnBadValue 用无法 JSON 序列化的字段触发兜底输出。
// func 类型无法被 encoding/json 序列化，会走 fmt.Sprintf 兜底分支。
func TestLoggerMarshalFallbackOnBadValue(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "info")
	l.Error("坏值", map[string]any{"fn": func() {}})

	entries := parseLines(t, buf.String())
	if len(entries) != 1 {
		t.Fatalf("期望 1 条兜底日志, 实际 %d", len(entries))
	}
	e := entries[0]
	if e["level"] != "error" {
		t.Fatalf("兜底日志 level 应为 error, 实际 %v", e["level"])
	}
	if e["msg"] != "坏值" {
		t.Fatalf("兜底日志 msg 应为 坏值, 实际 %v", e["msg"])
	}
	if _, ok := e["ts"]; !ok {
		t.Fatal("兜底日志应包含 ts")
	}
}

// TestLoggerWritesToFailingWriterNoPanic 写失败不应 panic，接口返回错误被吞掉。
func TestLoggerWritesToFailingWriterNoPanic(t *testing.T) {
	l := New(errWriter{}, "info")
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("写失败不应 panic, 收到 %v", r)
		}
	}()
	l.Info("会失败", map[string]any{"k": "v"})
	l.Warn("还是失败", nil)
	l.Error("依旧失败", map[string]any{"n": 1})
}

// TestLoggerEmptyFieldsOmitsExtraKeys 空 fields 时只写基础三个 key。
func TestLoggerEmptyFieldsOmitsExtraKeys(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "info")
	l.Info("只有基础字段", nil)

	entries := parseLines(t, buf.String())
	if len(entries) != 1 {
		t.Fatalf("期望 1 条日志, 实际 %d", len(entries))
	}
	e := entries[0]
	if len(e) != 3 {
		t.Fatalf("空 fields 应只有 3 个 key, 实际 %d 个: %v", len(e), e)
	}
	if e["msg"] != "只有基础字段" {
		t.Fatalf("msg 不对: %v", e["msg"])
	}
	if e["level"] != "info" {
		t.Fatalf("level 不对: %v", e["level"])
	}
}

// TestLoggerDefaultLevelWhenEmpty 验证 New 在 level 为空串时回填 info。
func TestLoggerDefaultLevelWhenEmpty(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, "")
	l.Info("默认级别", nil)

	entries := parseLines(t, buf.String())
	if len(entries) != 1 {
		t.Fatalf("期望 1 条日志, 实际 %d", len(entries))
	}
	if entries[0]["level"] != "info" {
		t.Fatalf("默认级别日志应为 info, 实际 %v", entries[0]["level"])
	}
	if entries[0]["msg"] != "默认级别" {
		t.Fatalf("msg 不对: %v", entries[0]["msg"])
	}
}