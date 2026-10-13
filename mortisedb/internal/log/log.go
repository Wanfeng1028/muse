// Package log 提供结构化 JSON 日志与请求 ID 中间件。
package log

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

// Logger 是并发安全的结构化日志器。
type Logger struct {
	mu    sync.Mutex
	w     io.Writer
	level string
}

// New 创建 Logger，level 取值 debug/info/warn/error（大小写不敏感）。
func New(w io.Writer, level string) *Logger {
	if level == "" {
		level = "info"
	}
	return &Logger{w: w, level: level}
}

type ctxKey struct{}

// WithRequestID 将请求 ID 写入 context。
func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, ctxKey{}, id)
}

// RequestIDFrom 从 context 取出请求 ID，不存在返回空串。
func RequestIDFrom(ctx context.Context) string {
	if v, ok := ctx.Value(ctxKey{}).(string); ok {
		return v
	}
	return ""
}

// NewRequestID 生成时间戳纳秒 + 随机 hex 的请求 ID。
func NewRequestID() string {
	var b [8]byte
	_, _ = rand.Read(b[:])
	return fmt.Sprintf("%d-%s", time.Now().UnixNano(), hex.EncodeToString(b[:]))
}

// log 输出单行 JSON 日志：ts/level/msg/request_id+fields。
func (l *Logger) log(level, msg string, fields map[string]any) {
	entry := map[string]any{
		"ts":    time.Now().UTC().Format(time.RFC3339),
		"level": level,
		"msg":   msg,
	}
	for k, v := range fields {
		entry[k] = v
	}
	buf, err := json.Marshal(entry)
	if err != nil {
		// 兜底：序列化失败也输出一条可读信息
		buf = []byte(fmt.Sprintf(`{"ts":%q,"level":%q,"msg":%q}`, entry["ts"], level, msg))
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	_, _ = l.w.Write(append(buf, '\n'))
}

// Info 记录 info 级别日志。
func (l *Logger) Info(msg string, fields map[string]any) { l.log("info", msg, fields) }

// Warn 记录 warn 级别日志。
func (l *Logger) Warn(msg string, fields map[string]any) { l.log("warn", msg, fields) }

// Error 记录 error 级别日志。
func (l *Logger) Error(msg string, fields map[string]any) { l.log("error", msg, fields) }

// statusRecorder 记录响应状态码。
type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

// RequestIDMiddleware 生成请求 ID、放入 context，并记录访问日志。
func RequestIDMiddleware(next http.Handler, logger *Logger) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		id := NewRequestID()
		ctx := WithRequestID(r.Context(), id)
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r.WithContext(ctx))
		dur := time.Since(start).Milliseconds()
		logger.Info("访问", map[string]any{
			"request_id":  id,
			"method":      r.Method,
			"path":        r.URL.Path,
			"status":      rec.status,
			"duration_ms": dur,
		})
	})
}
