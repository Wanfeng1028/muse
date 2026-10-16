package ratelimit

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
)

// 统一的测试用 userOf：从 X-User 头取用户标识。
func testUserOf(r *http.Request) string {
	return r.Header.Get("X-User")
}

// TestValidate 覆盖 Config.Validate 的边界行为。

// allowOnce 包装双返回值的 allow，只取是否放行（测试便利函数）。
func allowOnce(l *Limiter, key string, write bool) bool {
	ok, _ := l.allow(key, write)
	return ok
}

func TestValidate(t *testing.T) {
	// Enabled=false 时，零值 Config 应通过（即使各速率字段为 0/负数）。
	var zero Config
	if err := zero.Validate(); err != nil {
		t.Fatalf("Enabled=false 的零值 Config 应通过校验，实际返回错误: %v", err)
	}

	// Enabled=false 且字段为负也不应报错。
	if err := (Config{Enabled: false, RPS: -1, Burst: -1}).Validate(); err != nil {
		t.Fatalf("Enabled=false 时负数字段应通过校验，实际返回错误: %v", err)
	}

	cases := []struct {
		name string
		cfg  Config
	}{
		{"RPS=0", Config{Enabled: true, RPS: 0, Burst: 1, WriteRPS: 1, WriteBurst: 1}},
		{"Burst=-1", Config{Enabled: true, RPS: 1, Burst: -1, WriteRPS: 1, WriteBurst: 1}},
		{"WriteRPS=0", Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 0, WriteBurst: 1}},
		{"WriteBurst=-1", Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: -1}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := tc.cfg.Validate(); err == nil {
				t.Fatalf("Enabled=true 且 %s 时应返回错误，实际为 nil", tc.name)
			}
		})
	}

	// 合法配置应通过。
	valid := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	if err := valid.Validate(); err != nil {
		t.Fatalf("合法配置应通过校验，实际返回错误: %v", err)
	}
}

// TestBucketRefill 验证令牌桶补充逻辑与 burst 上限（使用假时钟，不 sleep）。
func TestBucketRefill(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 2, WriteRPS: 1, WriteBurst: 2}
	l := New(cfg)

	// 注入假时钟：now 变量由测试手动推进。
	now := time.Unix(1000, 0)
	l.SetNowFunc(func() time.Time { return now })

	// 同一 key 连续读：前 2 次 true，第 3 次 false（桶被耗尽）。
	for i := 0; i < 2; i++ {
		if !allowOnce(l, "k", false) {
			t.Fatalf("第 %d 次 allow 应为 true（burst=2）", i+1)
		}
	}
	if allowOnce(l, "k", false) {
		t.Fatalf("第 3 次 allow 应为 false（桶已耗尽）")
	}

	// 快进 1.5 秒：RPS=1，应补充 1 个令牌。
	now = now.Add(1500 * time.Millisecond)
	if !allowOnce(l, "k", false) {
		t.Fatalf("快进 1.5 秒后 allow 应为 true（补充了令牌）")
	}
	// 再立即取一次：此时桶应为空（1.5s 只补 1 个，被上面消耗掉）。
	if allowOnce(l, "k", false) {
		t.Fatalf("补充的令牌被消耗后，再次 allow 应为 false")
	}

	// 再快进 10 秒：即使时间足够补满，也不能超过 burst=2。
	now = now.Add(10 * time.Second)
	if !allowOnce(l, "k", false) {
		t.Fatalf("快进 10 秒后第 1 次 allow 应为 true")
	}
	if !allowOnce(l, "k", false) {
		t.Fatalf("快进 10 秒后第 2 次 allow 应为 true")
	}
	if allowOnce(l, "k", false) {
		t.Fatalf("快进 10 秒后第 3 次 allow 应为 false（burst 上限为 2）")
	}
}

// TestWriteBucketIndependent 验证读/写两套桶相互独立。
func TestWriteBucketIndependent(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 100, Burst: 100, WriteRPS: 1, WriteBurst: 1}
	l := New(cfg)
	now := time.Unix(2000, 0)
	l.SetNowFunc(func() time.Time { return now })

	// 写桶 burst=1：第一次写通过，第二次写被拒。
	if !allowOnce(l, "k", true) {
		t.Fatalf("第一次写 allow 应为 true")
	}
	if allowOnce(l, "k", true) {
		t.Fatalf("第二次写 allow 应为 false（写桶已空）")
	}
	// 读桶独立且额度充足：仍应通过。
	if !allowOnce(l, "k", false) {
		t.Fatalf("读 allow 应为 true（读桶独立于写桶）")
	}
}

// TestDisabledPassthrough 验证 Enabled=false 时中间件完全放行。
func TestDisabledPassthrough(t *testing.T) {
	// 极端配置：Burst=0 也不限流。
	cfg := Config{Enabled: false, RPS: 0, Burst: 0, WriteRPS: 0, WriteBurst: 0}
	l := New(cfg)

	okHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	h := l.Middleware(testUserOf, okHandler)

	// 连续多次请求都应 200。
	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.Header.Set("X-User", "u1")
		req.RemoteAddr = "9.9.9.9:1234"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("Enabled=false 时第 %d 次请求应为 200，实际为 %d", i+1, rec.Code)
		}
	}
}

// TestIntegration429 通过 logpkg.Middleware + limiter.Middleware 组成完整链路，
// 用 httptest 真实发请求，断言 429、Retry-After 与 JSON 体。
func TestIntegration429(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 2, Burst: 2, WriteRPS: 2, WriteBurst: 2}
	l := New(cfg)
	now := time.Unix(3000, 0)
	l.SetNowFunc(func() time.Time { return now })

	okHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	// 链路：logpkg（注入 request_id 到 context）在外层，limiter 在内层。
	h := logpkg.Middleware(l.Middleware(testUserOf, okHandler))

	// 同一 IP、同一用户，快速发 10 个 GET。
	var got429 int
	var firstCodes []int
	for i := 0; i < 10; i++ {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.Header.Set("X-User", "u1")
		req.Header.Set("X-Forwarded-For", "5.5.5.5")
		req.RemoteAddr = "5.5.5.5:1234"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)

		if i < 2 {
			firstCodes = append(firstCodes, rec.Code)
		}

		if rec.Code == http.StatusTooManyRequests {
			got429++

			// 断言 Retry-After 头存在且为 >=1 的整数秒。
			ra := rec.Header().Get("Retry-After")
			if ra == "" {
				t.Fatalf("429 响应缺少 Retry-After 头")
			}
			secs, err := parseIntSeconds(ra)
			if err != nil {
				t.Fatalf("Retry-After 不是合法整数秒: %q, err=%v", ra, err)
			}
			if secs < 1 {
				t.Fatalf("Retry-After 应 >= 1，实际为 %d", secs)
			}

			// 断言 JSON 体。
			var body struct {
				Error     string `json:"error"`
				RequestID string `json:"request_id"`
			}
			if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
				t.Fatalf("429 响应体不是合法 JSON: %v, body=%q", err, rec.Body.String())
			}
			if body.Error != "rate limit exceeded" {
				t.Fatalf("429 JSON error 字段应为 %q，实际为 %q", "rate limit exceeded", body.Error)
			}
			if body.RequestID == "" {
				t.Fatalf("429 JSON request_id 不应为空（应来自外层 logpkg 中间件）")
			}
		}
	}

	if got429 == 0 {
		t.Fatalf("10 个快速请求中应至少出现 1 个 429，实际为 0")
	}
	// 前 2 个请求应为 200（burst=2）。
	for i, code := range firstCodes {
		if code != http.StatusOK {
			t.Fatalf("前 2 个请求中第 %d 个应为 200，实际为 %d", i+1, code)
		}
	}
}

// TestIntegrationWriteStricter 验证写请求限流更严，且读请求不受影响。
func TestIntegrationWriteStricter(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 100, Burst: 100, WriteRPS: 1, WriteBurst: 1}
	l := New(cfg)
	now := time.Unix(4000, 0)
	l.SetNowFunc(func() time.Time { return now })

	okHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	h := logpkg.Middleware(l.Middleware(testUserOf, okHandler))

	// 快速发 3 个 POST：写桶 burst=1，至少 1 个 429。
	var got429 int
	for i := 0; i < 3; i++ {
		req := httptest.NewRequest(http.MethodPost, "/", nil)
		req.Header.Set("X-User", "u1")
		req.Header.Set("X-Forwarded-For", "6.6.6.6")
		req.RemoteAddr = "6.6.6.6:1234"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code == http.StatusTooManyRequests {
			got429++
		}
	}
	if got429 == 0 {
		t.Fatalf("3 个快速 POST 中应至少出现 1 个 429，实际为 0")
	}

	// 读桶独立且额度充足，GET 应继续 200。
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-User", "u1")
	req.Header.Set("X-Forwarded-For", "6.6.6.6")
	req.RemoteAddr = "6.6.6.6:1234"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("写限流后 GET 应仍为 200，实际为 %d", rec.Code)
	}
}

// TestClientIPDimension 验证按 client IP 隔离限流维度。
func TestClientIPDimension(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	l := New(cfg)
	now := time.Unix(5000, 0)
	l.SetNowFunc(func() time.Time { return now })

	okHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	h := l.Middleware(testUserOf, okHandler)

	// 用户 u1 从 1.1.1.1 打爆读桶：第 1 个 200，第 2 个 429。
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.Header.Set("X-User", "u1")
		req.Header.Set("X-Forwarded-For", "1.1.1.1")
		req.RemoteAddr = "1.1.1.1:1234"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if i == 0 && rec.Code != http.StatusOK {
			t.Fatalf("1.1.1.1 第 1 个请求应为 200，实际为 %d", rec.Code)
		}
		if i == 1 && rec.Code != http.StatusTooManyRequests {
			t.Fatalf("1.1.1.1 第 2 个请求应为 429，实际为 %d", rec.Code)
		}
	}

	// 同一用户换 IP 2.2.2.2：桶独立，应仍为 200。
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-User", "u1")
	req.Header.Set("X-Forwarded-For", "2.2.2.2")
	req.RemoteAddr = "2.2.2.2:1234"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("换 IP 后请求应为 200（IP 维度隔离），实际为 %d", rec.Code)
	}
}

// parseIntSeconds 解析 Retry-After 的整数秒值（仅接受纯十进制整数）。
func parseIntSeconds(s string) (int, error) {
	n := 0
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c < '0' || c > '9' {
			return 0, errNotInteger
		}
		n = n*10 + int(c-'0')
	}
	if len(s) == 0 {
		return 0, errNotInteger
	}
	return n, nil
}

var errNotInteger = &parseError{"not an integer"}

type parseError struct{ msg string }

func (e *parseError) Error() string { return e.msg }
