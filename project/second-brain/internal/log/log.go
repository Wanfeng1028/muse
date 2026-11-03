// Package log 提供 second-brain 的结构化日志基础设施。
//
// 该包基于标准库 log/slog，统一输出 JSON 日志，并提供 request_id
// 的生成、context 注入与 HTTP 中间件支持。使用方通常以 logpkg
// 别名导入本包，以避免与标准库 log 冲突。
package log

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"sync/atomic"
	"time"
)

// serviceName 是写入所有日志的固定 service 属性值。
const serviceName = "second-brain"

// requestIDHeader 是透传 request_id 的 HTTP 头名称。
const requestIDHeader = "X-Request-ID"

// requestIDKey 是 context 中存放 request_id 的键类型。
// 使用未导出结构体类型可避免与其他包的键发生冲突。
type requestIDKey struct{}

// fallbackCounter 用于在 crypto/rand 失败时生成唯一后缀。
var fallbackCounter uint64

// Init 从 SB_LOG_LEVEL 环境变量初始化 slog 默认 logger。
//
// 取值 debug/info/warn/error（大小写不敏感），缺省或非法时为 info。
// 输出 JSON 到 os.Stdout，并附加 service="second-brain" 属性。
func Init() {
	level := parseLevel(os.Getenv("SB_LOG_LEVEL"))
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: level,
	})
	logger := slog.New(handler).With(slog.String("service", serviceName))
	slog.SetDefault(logger)
}

// parseLevel 将环境变量字符串解析为 slog.Level，非法或缺省返回 info。
func parseLevel(raw string) slog.Level {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "debug":
		return slog.LevelDebug
	case "info":
		return slog.LevelInfo
	case "warn":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}

// NewRequestID 生成 32 位十六进制随机 request_id（crypto/rand 16 字节）。
//
// 当 rand 读取失败时，回退为纳秒时间戳加原子计数器拼接，保证不返回空串。
func NewRequestID() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err == nil {
		return hex.EncodeToString(buf[:])
	}

	// 回退路径：纳秒时间戳 + 原子计数器。
	counter := atomic.AddUint64(&fallbackCounter, 1)
	ts := time.Now().UnixNano()
	// 使用 %x 拼接时间戳与计数器，保证非空且随调用递增。
	fallback := strings.Join([]string{
		formatUint64Hex(uint64(ts)),
		formatUint64Hex(counter),
	}, "")
	if fallback == "" {
		// 理论上不会发生，作为最终保险。
		return "00000000000000000000000000000000"
	}
	return fallback
}

// formatUint64Hex 将 uint64 格式化为十六进制字符串。
func formatUint64Hex(v uint64) string {
	const digits = "0123456789abcdef"
	if v == 0 {
		return "0"
	}
	var tmp [16]byte
	i := len(tmp)
	for v > 0 {
		i--
		tmp[i] = digits[v&0xF]
		v >>= 4
	}
	return string(tmp[i:])
}

// WithRequestID 把 request_id 注入 context。
//
// 使用包内未导出结构体类型作为 key，防止与其他包的键冲突。
func WithRequestID(ctx context.Context, id string) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, requestIDKey{}, id)
}

// FromContext 从 context 取出 request_id，缺失返回 ""。
func FromContext(ctx context.Context) string {
	if ctx == nil {
		return ""
	}
	id, ok := ctx.Value(requestIDKey{}).(string)
	if !ok {
		return ""
	}
	return id
}

// RequestLogger 返回携带 request_id 属性的 *slog.Logger。
//
// 若 ctx 中无 request_id，则返回 slog.Default()。
func RequestLogger(ctx context.Context) *slog.Logger {
	id := FromContext(ctx)
	if id == "" {
		return slog.Default()
	}
	return slog.Default().With(slog.String("request_id", id))
}

// Middleware 是 HTTP 中间件，用于透传或生成 request_id 并记录请求日志。
//
//  1. 读取 X-Request-ID 请求头透传；缺失则调用 NewRequestID() 生成。
//  2. 将 request_id 注入 request 的 context。
//  3. 向响应头回写 X-Request-ID。
//  4. 请求结束后记录一条 JSON 日志，msg 固定为 "http.request"，
//     字段包含 request_id / method / path / status / latency_ms。
//     status >= 500 使用 Error 级别，其余使用 Info 级别。
//  5. 通过 ResponseWriter 包装器捕获真实状态码，默认 200。
func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestID := r.Header.Get(requestIDHeader)
		if requestID == "" {
			requestID = NewRequestID()
		}

		ctx := WithRequestID(r.Context(), requestID)
		r = r.WithContext(ctx)

		w.Header().Set(requestIDHeader, requestID)

		recorder := &statusRecorder{
			ResponseWriter: w,
			status:         http.StatusOK,
		}

		start := time.Now()
		next.ServeHTTP(recorder, r)
		latency := time.Since(start)

		logger := slog.Default()
		attrs := []slog.Attr{
			slog.String("request_id", requestID),
			slog.String("method", r.Method),
			slog.String("path", r.URL.Path),
			slog.Int("status", recorder.status),
			slog.Int64("latency_ms", latency.Milliseconds()),
		}

		if recorder.status >= http.StatusInternalServerError {
			logger.LogAttrs(ctx, slog.LevelError, "http.request", attrs...)
			return
		}
		logger.LogAttrs(ctx, slog.LevelInfo, "http.request", attrs...)
	})
}

// statusRecorder 包装 http.ResponseWriter 以捕获真实写入的状态码。
type statusRecorder struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

// WriteHeader 记录状态码并转发给底层 ResponseWriter。
func (r *statusRecorder) WriteHeader(code int) {
	if r.wroteHeader {
		return
	}
	r.status = code
	r.wroteHeader = true
	r.ResponseWriter.WriteHeader(code)
}

// Write 在未显式写入状态码时，默认按 200 记录。
func (r *statusRecorder) Write(b []byte) (int, error) {
	if !r.wroteHeader {
		r.WriteHeader(http.StatusOK)
	}
	return r.ResponseWriter.Write(b)
}
