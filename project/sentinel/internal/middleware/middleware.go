// Package middleware 提供 HTTP 中间件：请求 ID 注入、鉴权与访问日志。
package middleware

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	applog "sentinel/internal/log"
	"sentinel/internal/metrics"
	"sentinel/internal/store"
)

// ctxKey 用于在 context 中存储用户与租户信息的私有键类型。
type ctxKey string

var (
	userKey     = ctxKey("user")
	tenantIDKey = ctxKey("tenant-id")
)

// UserFrom 从 context 中提取当前用户，未鉴权时返回 nil。
func UserFrom(ctx context.Context) *store.User {
	if ctx == nil {
		return nil
	}
	if v, ok := ctx.Value(userKey).(*store.User); ok {
		return v
	}
	return nil
}

// TenantIDFrom 从 context 中提取当前租户 ID，未鉴权时返回 0。
func TenantIDFrom(ctx context.Context) int64 {
	if ctx == nil {
		return 0
	}
	if v, ok := ctx.Value(tenantIDKey).(int64); ok {
		return v
	}
	return 0
}

// newRequestID 生成 16 字节随机 hex 字符串。
func newRequestID() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err != nil {
		// 极端情况下回退到时间戳，保证仍能返回非空 ID。
		return hex.EncodeToString([]byte(time.Now().UTC().Format(time.RFC3339Nano)))
	}
	return hex.EncodeToString(buf[:])
}

// RequestID 中间件：读取或生成 X-Request-ID，写入 context 与响应头。
func RequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimSpace(r.Header.Get("X-Request-ID"))
		if id == "" {
			id = newRequestID()
		}
		w.Header().Set("X-Request-ID", id)
		ctx := applog.WithRequestID(r.Context(), id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// Logging 中间件：记录访问日志并上报指标。
func Logging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		latency := time.Since(start)
		latencyMs := latency.Milliseconds()

		reqID := applog.RequestIDFrom(r.Context())
		applog.Logger().Info("http_request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rec.status,
			"latency_ms", latencyMs,
			"request_id", reqID,
		)
		metrics.Default.RecordHTTP(r.Method, r.URL.Path, rec.status, latencyMs)
	})
}

// statusRecorder 捕获响应状态码。
type statusRecorder struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

func (s *statusRecorder) WriteHeader(code int) {
	if s.wroteHeader {
		return
	}
	s.status = code
	s.wroteHeader = true
	s.ResponseWriter.WriteHeader(code)
}

func (s *statusRecorder) Write(b []byte) (int, error) {
	if !s.wroteHeader {
		s.wroteHeader = true
	}
	return s.ResponseWriter.Write(b)
}

// Auth 提供基于 Bearer Token 的鉴权中间件。
type Auth struct {
	store *store.Store
}

// NewAuth 构造 Auth。
func NewAuth(st *store.Store) *Auth {
	return &Auth{store: st}
}

// Middleware 返回鉴权中间件。
// exactWhitelist 中的条目对请求路径做精确匹配；prefixWhitelist 中的条目做前缀匹配。
// 命中任一白名单则跳过鉴权，其余请求必须携带 Authorization: Bearer <token>。
func (a *Auth) Middleware(exactWhitelist []string, prefixWhitelist []string) func(http.Handler) http.Handler {
	exact := make([]string, 0, len(exactWhitelist))
	prefixes := make([]string, 0, len(prefixWhitelist))
	exact = append(exact, exactWhitelist...)
	prefixes = append(prefixes, prefixWhitelist...)

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			path := r.URL.Path

			for _, p := range exact {
				if path == p {
					next.ServeHTTP(w, r)
					return
				}
			}
			for _, p := range prefixes {
				if strings.HasPrefix(path, p) {
					next.ServeHTTP(w, r)
					return
				}
			}

			token := extractBearer(r.Header.Get("Authorization"))
			if token == "" {
				writeUnauthorized(w, r)
				return
			}
			hash := sha256.Sum256([]byte(token))
			hashHex := hex.EncodeToString(hash[:])

			users, err := a.store.ListUsers()
			if err != nil {
				applog.Logger().Error("鉴权失败：查询用户出错",
					"error", err.Error(),
					"request_id", applog.RequestIDFrom(r.Context()),
				)
				writeUnauthorized(w, r)
				return
			}

			var matched *store.User
			for i := range users {
				if subtle.ConstantTimeCompare([]byte(users[i].TokenHash), []byte(hashHex)) == 1 {
					u := users[i]
					matched = &u
					break
				}
			}
			if matched == nil {
				writeUnauthorized(w, r)
				return
			}

			ctx := context.WithValue(r.Context(), userKey, matched)
			ctx = context.WithValue(ctx, tenantIDKey, matched.TenantID)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// extractBearer 从 Authorization 头解析 Bearer token。
func extractBearer(h string) string {
	h = strings.TrimSpace(h)
	if h == "" {
		return ""
	}
	const prefix = "Bearer "
	if len(h) < len(prefix) || !strings.EqualFold(h[:len(prefix)], prefix) {
		return ""
	}
	return strings.TrimSpace(h[len(prefix):])
}

// writeUnauthorized 输出 401 JSON 响应。
func writeUnauthorized(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusUnauthorized)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": "未授权"})
}
