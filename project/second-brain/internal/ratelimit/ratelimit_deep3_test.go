package ratelimit

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func newTestLimiter(t *testing.T, cfg Config) (*Limiter, *time.Time) {
	t.Helper()
	l := New(cfg)
	now := time.Unix(1000, 0)
	nowRef := &now
	l.SetNowFunc(func() time.Time { return *nowRef })
	return l, nowRef
}

func TestAllow_BurstExactBoundary(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 3, WriteRPS: 1, WriteBurst: 2}
	l, _ := newTestLimiter(t, cfg)

	// 读桶：前 3 次 true，第 4 次 false
	for i := 0; i < 3; i++ {
		ok, _ := l.allow("k", false)
		if !ok {
			t.Fatalf("read #%d want true", i+1)
		}
	}
	if ok, _ := l.allow("k", false); ok {
		t.Fatalf("read #4 want false")
	}

	// 写桶独立：前 2 次 true，第 3 次 false
	for i := 0; i < 2; i++ {
		ok, _ := l.allow("k", true)
		if !ok {
			t.Fatalf("write #%d want true", i+1)
		}
	}
	if ok, _ := l.allow("k", true); ok {
		t.Fatalf("write #3 want false")
	}
}

func TestAllow_RefillOverTime(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 3, WriteRPS: 1, WriteBurst: 2}
	l, now := newTestLimiter(t, cfg)

	for i := 0; i < 3; i++ {
		if ok, _ := l.allow("k", false); !ok {
			t.Fatalf("drain #%d want true", i+1)
		}
	}
	if ok, _ := l.allow("k", false); ok {
		t.Fatalf("drained want false")
	}

	*now = now.Add(2500 * time.Millisecond) // +2.5 tokens -> 2.5
	if ok, _ := l.allow("k", false); !ok {
		t.Fatalf("refill #1 want true")
	}
	if ok, _ := l.allow("k", false); !ok {
		t.Fatalf("refill #2 want true")
	}
	// 剩 0.5 < 1
	if ok, _ := l.allow("k", false); ok {
		t.Fatalf("refill #3 want false (0.5 left)")
	}
}

func TestAllow_RefillCappedAtBurst(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 3, WriteRPS: 1, WriteBurst: 2}
	l, now := newTestLimiter(t, cfg)

	for i := 0; i < 3; i++ {
		if ok, _ := l.allow("k", false); !ok {
			t.Fatalf("drain #%d want true", i+1)
		}
	}
	if ok, _ := l.allow("k", false); ok {
		t.Fatalf("drained want false")
	}

	*now = now.Add(time.Hour) // 3600 tokens 补充但被钳制到 Burst=3
	for i := 0; i < 3; i++ {
		if ok, _ := l.allow("k", false); !ok {
			t.Fatalf("capped #%d want true", i+1)
		}
	}
	if ok, _ := l.allow("k", false); ok {
		t.Fatalf("capped #4 want false (must be exactly 3)")
	}
}

func TestAllow_RetryAfterExact(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	l, _ := newTestLimiter(t, cfg)

	if ok, _ := l.allow("k", false); !ok {
		t.Fatalf("first want true")
	}
	ok, retry := l.allow("k", false)
	if ok {
		t.Fatalf("second want false")
	}
	// need=1, rate=1, ceil(1/1)=1
	if retry != 1 {
		t.Fatalf("retryAfter want 1, got %d", retry)
	}
}

func TestAllow_RetryAfterMinOne(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1000, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	l, _ := newTestLimiter(t, cfg)

	if ok, _ := l.allow("k", false); !ok {
		t.Fatalf("first want true")
	}
	ok, retry := l.allow("k", false)
	if ok {
		t.Fatalf("second want false")
	}
	// need=1, rate=1000, ceil(1/1000)=1；此处 ceil 已得 1，同样断言 ==1（secs<1→1 分支）
	if retry != 1 {
		t.Fatalf("retryAfter want 1, got %d", retry)
	}
}

func TestMiddleware_ReadWriteBucketsIndependent(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 100, Burst: 100, WriteRPS: 1, WriteBurst: 1}
	l, _ := newTestLimiter(t, cfg)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := l.Middleware(nil, next)

	do := func(method string) int {
		req := httptest.NewRequest(method, "/x", nil)
		req.RemoteAddr = "10.0.0.1:1234"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec.Code
	}

	if c := do(http.MethodPost); c != http.StatusOK {
		t.Fatalf("POST #1 want 200, got %d", c)
	}
	if c := do(http.MethodPost); c != http.StatusTooManyRequests {
		t.Fatalf("POST #2 want 429, got %d", c)
	}
	// 写桶已空，读桶应不受影响
	if c := do(http.MethodGet); c != http.StatusOK {
		t.Fatalf("GET want 200, got %d", c)
	}
}

func TestMiddleware_429BodyAndRetryAfterHeader(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	l, _ := newTestLimiter(t, cfg)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := l.Middleware(nil, next)

	req1 := httptest.NewRequest(http.MethodGet, "/x", nil)
	req1.RemoteAddr = "10.0.0.2:1111"
	rec1 := httptest.NewRecorder()
	h.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("GET #1 want 200, got %d", rec1.Code)
	}

	req2 := httptest.NewRequest(http.MethodGet, "/x", nil)
	req2.RemoteAddr = "10.0.0.2:1111"
	rec2 := httptest.NewRecorder()
	h.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("GET #2 want 429, got %d", rec2.Code)
	}
	if ra := rec2.Header().Get("Retry-After"); ra != "1" {
		t.Fatalf("Retry-After want \"1\", got %q", ra)
	}
	if ct := rec2.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("Content-Type want application/json, got %q", ct)
	}

	var body map[string]any
	if err := json.Unmarshal(rec2.Body.Bytes(), &body); err != nil {
		t.Fatalf("body unmarshal: %v, raw=%q", err, rec2.Body.String())
	}
	if got, _ := body["error"].(string); got != "rate limit exceeded" {
		t.Fatalf("body.error want %q, got %v", "rate limit exceeded", body["error"])
	}
	if _, ok := body["request_id"]; !ok {
		t.Fatalf("body must contain request_id key, got %v", body)
	}
}

func TestMiddleware_Disabled_Passthrough(t *testing.T) {
	cfg := Config{Enabled: false} // 其余字段全 0，非法但 Enabled=false 不校验
	l, _ := newTestLimiter(t, cfg)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := l.Middleware(nil, next)

	for i := 0; i < 20; i++ {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.RemoteAddr = "10.0.0.3:2222"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("iter %d want 200, got %d", i, rec.Code)
		}
	}
}

func TestValidate_EachFieldInvalid(t *testing.T) {
	cases := []struct {
		name string
		cfg  Config
	}{
		{"RPS_zero", Config{Enabled: true, RPS: 0, Burst: 1, WriteRPS: 1, WriteBurst: 1}},
		{"Burst_zero", Config{Enabled: true, RPS: 1, Burst: 0, WriteRPS: 1, WriteBurst: 1}},
		{"WriteRPS_zero", Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 0, WriteBurst: 1}},
		{"WriteBurst_zero", Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 0}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := tc.cfg.Validate(); err == nil {
				t.Fatalf("want non-nil error for %+v", tc.cfg)
			}
		})
	}

	// Enabled=false 全 0 → nil
	if err := (Config{Enabled: false}).Validate(); err != nil {
		t.Fatalf("disabled zero cfg want nil, got %v", err)
	}
}

func TestClientIP_XFFOnlyCommas_FallsThrough(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("X-Forwarded-For", ", ,")
	req.Header.Set("X-Real-IP", "9.9.9.9")
	if got := clientIP(req); got != "9.9.9.9" {
		t.Fatalf("clientIP want %q, got %q", "9.9.9.9", got)
	}
}

func TestIsWriteMethod_Table(t *testing.T) {
	cases := []struct {
		method string
		want   bool
	}{
		{"GET", false},
		{"HEAD", false},
		{"OPTIONS", false},
		{"POST", true},
		{"PUT", true},
		{"DELETE", true},
		{"PATCH", true},
		{"BREW", true},
		{"", true},
	}
	for _, tc := range cases {
		if got := isWriteMethod(tc.method); got != tc.want {
			t.Fatalf("isWriteMethod(%q) want %v, got %v", tc.method, tc.want, got)
		}
	}
}

func TestMiddleware_IPIsolation_NoUser(t *testing.T) {
	cfg := Config{Enabled: true, RPS: 1, Burst: 1, WriteRPS: 1, WriteBurst: 1}
	l, _ := newTestLimiter(t, cfg)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	h := l.Middleware(nil, next)

	do := func(addr string) int {
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.RemoteAddr = addr
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec.Code
	}

	if c := do("1.1.1.1:1000"); c != http.StatusOK {
		t.Fatalf("1.1.1.1 #1 want 200, got %d", c)
	}
	if c := do("1.1.1.1:1000"); c != http.StatusTooManyRequests {
		t.Fatalf("1.1.1.1 #2 want 429, got %d", c)
	}
	if c := do("2.2.2.2:2000"); c != http.StatusOK {
		t.Fatalf("2.2.2.2 want 200, got %d", c)
	}
}
