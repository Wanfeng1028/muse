// Package log 提供基于标准库 log/slog 的全局日志设施。
// 默认输出 JSON 格式到 os.Stdout，支持通过环境变量控制日志级别。
// 同时提供基于 context 的 request_id 传递与提取能力。
package log

import (
	"context"
	"log/slog"
	"os"
	"strings"
	"sync"
)

// ctxKey 用于在 context 中存储 request_id 的私有键类型。
type ctxKey struct{}

var (
	globalMu sync.RWMutex
	global   *slog.Logger
)

// Init 根据传入的级别字符串初始化全局 logger。
// 合法取值（大小写不敏感）：debug、info、warn、error。非法值回退到 info。
func Init(level string) {
	lvl := parseLevel(level)
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: lvl,
	})
	l := slog.New(handler)
	globalMu.Lock()
	global = l
	globalMu.Unlock()
	slog.SetDefault(l)
}

// parseLevel 将字符串转换为 slog.Level，非法值回退到 info。
func parseLevel(level string) slog.Level {
	switch strings.ToLower(strings.TrimSpace(level)) {
	case "debug":
		return slog.LevelDebug
	case "info", "":
		return slog.LevelInfo
	case "warn", "warning":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}

// Logger 返回全局 logger。若未调用过 Init，则返回一个默认 JSON handler logger。
func Logger() *slog.Logger {
	globalMu.RLock()
	l := global
	globalMu.RUnlock()
	if l != nil {
		return l
	}
	// 兜底：未初始化时创建一个 info 级别的 JSON logger。
	l = slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	globalMu.Lock()
	global = l
	globalMu.Unlock()
	return l
}

// WithRequestID 将 request_id 写入 context 并返回新的 context。
func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, ctxKey{}, id)
}

// RequestIDFrom 从 context 中提取 request_id，不存在时返回空字符串。
func RequestIDFrom(ctx context.Context) string {
	if ctx == nil {
		return ""
	}
	if v, ok := ctx.Value(ctxKey{}).(string); ok {
		return v
	}
	return ""
}
