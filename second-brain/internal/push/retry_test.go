// internal/push/retry_test.go
package push

import (
	"context"
	"errors"
	"fmt"
	"math/rand"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// stubSender 是一个可控的 notify.Sender 桩。
// errs 按调用次序返回：第 n 次调用返回 errs[n]（越界则返回 nil），calls 记录调用次数。
type stubSender struct {
	name  string
	errs  []error
	calls int
}

func (s *stubSender) Name() string { return s.name }

func (s *stubSender) Send(ctx context.Context, msg notify.Message) error {
	idx := s.calls
	s.calls++
	if idx < len(s.errs) {
		return s.errs[idx]
	}
	return nil
}

// recordingSleeper 记录每次休眠的时长并立刻返回 nil（绝不真睡）。
type recordingSleeper struct {
	durations []time.Duration
}

func (r *recordingSleeper) sleep(ctx context.Context, d time.Duration) error {
	r.durations = append(r.durations, d)
	return nil
}

func (r *recordingSleeper) count() int { return len(r.durations) }

// TestIsRetryable 表格驱动验证可重试判定。
func TestIsRetryable(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want bool
	}{
		{"nil 不算可重试", nil, false},
		{"连接错误可重试", fmt.Errorf("%w: 连接失败", notify.ErrConn), true},
		{"认证错误不可重试", fmt.Errorf("%w: 认证被拒绝", notify.ErrAuth), false},
		{"订阅失效不可重试", notify.ErrSubscriptionGone, false},
		{"503 可重试", errors.New("notify: webhook 返回非 2xx 状态 503: x"), true},
		{"429 可重试", errors.New("notify: webhook 返回非 2xx 状态 429: 限流"), true},
		{"400 不可重试", errors.New("notify: webhook 返回非 2xx 状态 400: bad"), false},
		{"webpush 404 不可重试", errors.New("webpush: 推送服务返回状态码 404"), false},
		{"webpush 500 可重试", errors.New("webpush: 推送服务返回状态码 500"), true},
		{"未知错误 fail-open 可重试", errors.New("some unknown boom"), true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := IsRetryable(c.err); got != c.want {
				t.Fatalf("IsRetryable(%v) = %v, want %v", c.err, got, c.want)
			}
		})
	}
}

// TestBackoffForAttempt 验证退避计算区间与上限钳制。
func TestBackoffForAttempt(t *testing.T) {
	policy := RetryPolicy{
		BaseBackoff: 1000 * time.Millisecond,
		MaxBackoff:  30 * time.Second,
		JitterRatio: 0.25,
	}
	rng := rand.New(rand.NewSource(1))

	inRange := func(d, lo, hi time.Duration) bool {
		return d >= lo && d <= hi
	}

	d0 := backoffForAttempt(policy, 0, rng)
	if !inRange(d0, 750*time.Millisecond, 1250*time.Millisecond) {
		t.Fatalf("attempt=0 期望落在 [750ms,1250ms]，实际 %v", d0)
	}

	d1 := backoffForAttempt(policy, 1, rng)
	if !inRange(d1, 1500*time.Millisecond, 2500*time.Millisecond) {
		t.Fatalf("attempt=1 期望落在 [1500ms,2500ms]，实际 %v", d1)
	}

	d2 := backoffForAttempt(policy, 2, rng)
	if !inRange(d2, 3000*time.Millisecond, 5000*time.Millisecond) {
		t.Fatalf("attempt=2 期望落在 [3000ms,5000ms]，实际 %v", d2)
	}

	// attempt=-1 按 0 处理，落在与 attempt=0 相同区间。
	dNeg := backoffForAttempt(policy, -1, rng)
	if !inRange(dNeg, 750*time.Millisecond, 1250*time.Millisecond) {
		t.Fatalf("attempt=-1 期望按 0 计，落在 [750ms,1250ms]，实际 %v", dNeg)
	}

	// attempt=10，base*2^10 远超 MaxBackoff，应被钳到 30s，抖动后下限 22.5s。
	dBig := backoffForAttempt(policy, 10, rng)
	if dBig > 30*time.Second {
		t.Fatalf("attempt=10 结果 %v 超过 MaxBackoff 30s", dBig)
	}
	if dBig < 22500*time.Millisecond {
		t.Fatalf("attempt=10 结果 %v 低于钳制抖动下限 22.5s", dBig)
	}
}

// TestWrapWithRetry_FailTwiceThenSucceed 前两次失败、第三次成功。
func TestWrapWithRetry_FailTwiceThenSucceed(t *testing.T) {
	inner := &stubSender{
		name: "smtp",
		errs: []error{
			fmt.Errorf("%w: dial fail", notify.ErrConn),
			fmt.Errorf("%w: dial fail", notify.ErrConn),
			nil,
		},
	}
	sleeper := &recordingSleeper{}
	wrapped := WrapWithRetrySleeper(inner, RetryPolicy{
		MaxRetries:  3,
		BaseBackoff: 10 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0.25,
	}, sleeper.sleep)

	if got := wrapped.Name(); got != "smtp" {
		t.Fatalf("Name() = %q, want %q", got, "smtp")
	}

	err := wrapped.Send(context.Background(), notify.Message{})
	if err != nil {
		t.Fatalf("Send 期望成功，实际 err = %v", err)
	}
	if inner.calls != 3 {
		t.Fatalf("calls = %d, want 3", inner.calls)
	}
	if sleeper.count() != 2 {
		t.Fatalf("睡眠次数 = %d, want 2", sleeper.count())
	}
}

// TestWrapWithRetry_NonRetryableNoSleep 不可重试错误应立即返回，不睡眠。
func TestWrapWithRetry_NonRetryableNoSleep(t *testing.T) {
	inner := &stubSender{
		name: "smtp",
		errs: []error{fmt.Errorf("%w: 认证被拒绝", notify.ErrAuth)},
	}
	sleeper := &recordingSleeper{}
	wrapped := WrapWithRetrySleeper(inner, RetryPolicy{
		MaxRetries:  5,
		BaseBackoff: 10 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0.25,
	}, sleeper.sleep)

	err := wrapped.Send(context.Background(), notify.Message{})
	if err == nil {
		t.Fatalf("Send 期望返回错误，实际 nil")
	}

	var ree *RetryExhaustedError
	if !errors.As(err, &ree) {
		t.Fatalf("错误类型期望 *RetryExhaustedError，实际 %T: %v", err, err)
	}
	if ree.Attempts != 1 {
		t.Fatalf("Attempts = %d, want 1", ree.Attempts)
	}
	if inner.calls != 1 {
		t.Fatalf("calls = %d, want 1", inner.calls)
	}
	if sleeper.count() != 0 {
		t.Fatalf("睡眠次数 = %d, want 0", sleeper.count())
	}
}

// TestWrapWithRetry_AlwaysFailExhausts 始终失败耗尽重试次数。
func TestWrapWithRetry_AlwaysFailExhausts(t *testing.T) {
	inner := &stubSender{
		name: "webhook",
		errs: []error{
			errors.New("notify: webhook 返回非 2xx 状态 503: x"),
			errors.New("notify: webhook 返回非 2xx 状态 503: x"),
			errors.New("notify: webhook 返回非 2xx 状态 503: x"),
			errors.New("notify: webhook 返回非 2xx 状态 503: x"),
		},
	}
	sleeper := &recordingSleeper{}
	wrapped := WrapWithRetrySleeper(inner, RetryPolicy{
		MaxRetries:  2,
		BaseBackoff: 10 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0.25,
	}, sleeper.sleep)

	err := wrapped.Send(context.Background(), notify.Message{})
	if err == nil {
		t.Fatalf("Send 期望返回错误，实际 nil")
	}

	var ree *RetryExhaustedError
	if !errors.As(err, &ree) {
		t.Fatalf("错误类型期望 *RetryExhaustedError，实际 %T: %v", err, err)
	}
	if ree.Attempts != 3 {
		t.Fatalf("Attempts = %d, want 3", ree.Attempts)
	}
	if inner.calls != 3 {
		t.Fatalf("calls = %d, want 3", inner.calls)
	}
	if sleeper.count() != 2 {
		t.Fatalf("睡眠次数 = %d, want 2", sleeper.count())
	}
}

// TestWrapWithRetry_ContextCancel 上下文已取消时应立刻返回 ctx.Err()。
func TestWrapWithRetry_ContextCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	inner := &stubSender{
		name: "webhook",
		errs: []error{fmt.Errorf("%w: dial fail", notify.ErrConn)},
	}

	// sleeper 收到已取消的 ctx 时返回 ctx.Err()。
	sleep := func(sctx context.Context, d time.Duration) error {
		return sctx.Err()
	}

	wrapped := WrapWithRetrySleeper(inner, RetryPolicy{
		MaxRetries:  3,
		BaseBackoff: 10 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0.25,
	}, sleep)

	err := wrapped.Send(ctx, notify.Message{})
	if err == nil {
		t.Fatalf("Send 期望返回错误，实际 nil")
	}
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("错误期望 errors.Is(context.Canceled)，实际 %v", err)
	}
}

// TestRecordDeadLetter_Idempotent 验证死信写入幂等。
func TestRecordDeadLetter_Idempotent(t *testing.T) {
	st, err := store.Open(filepath.Join(t.TempDir(), "t.db"))
	if err != nil {
		t.Fatalf("store.Open 失败: %v", err)
	}
	defer st.Close()

	date := "2026-10-16"
	channel := "webhook"
	user := "local"

	firstErr := errors.New("notify: webhook 返回非 2xx 状态 503: x")
	if err := RecordDeadLetter(st, date, channel, user, firstErr); err != nil {
		t.Fatalf("首次 RecordDeadLetter 失败: %v", err)
	}

	status, found := st.PushLogStatus(date, channel, user)
	if !found {
		t.Fatalf("PushLogStatus 未找到记录")
	}
	if status != "failed_permanent" {
		t.Fatalf("PushLogStatus = %q, want %q", status, "failed_permanent")
	}

	rows, err := st.ListPushLogFor(10, user)
	if err != nil {
		t.Fatalf("ListPushLogFor 失败: %v", err)
	}

	var detail string
	matched := 0
	for _, r := range rows {
		if r.Date == date && r.Channel == channel && r.User == user {
			matched++
			detail = r.Detail
		}
	}
	if matched != 1 {
		t.Fatalf("期望匹配 1 行，实际 %d 行", matched)
	}
	if !strings.Contains(detail, "503") {
		t.Fatalf("detail 期望含 \"503\"，实际 %q", detail)
	}

	// 二次写入不同错误文本，应幂等：不新增行、不改写 detail。
	secondErr := errors.New("notify: webhook 返回非 2xx 状态 500: 另一个错误")
	if err := RecordDeadLetter(st, date, channel, user, secondErr); err != nil {
		t.Fatalf("二次 RecordDeadLetter 失败: %v", err)
	}

	rows2, err := st.ListPushLogFor(10, user)
	if err != nil {
		t.Fatalf("二次 ListPushLogFor 失败: %v", err)
	}

	var detail2 string
	matched2 := 0
	for _, r := range rows2 {
		if r.Date == date && r.Channel == channel && r.User == user {
			matched2++
			detail2 = r.Detail
		}
	}
	if matched2 != 1 {
		t.Fatalf("二次调用后期望仍匹配 1 行，实际 %d 行", matched2)
	}
	if detail2 != detail {
		t.Fatalf("detail 被改写：first=%q second=%q", detail, detail2)
	}
	if strings.Contains(detail2, "500") {
		t.Fatalf("detail 不应被第二次错误文本覆盖，实际 %q", detail2)
	}
}

// TestDefaultRetryPolicy_Env 验证环境变量解析与默认值。
func TestDefaultRetryPolicy_Env(t *testing.T) {
	t.Run("MaxRetries=5", func(t *testing.T) {
		t.Setenv("SB_PUSH_MAX_RETRIES", "5")
		if got := DefaultRetryPolicy().MaxRetries; got != 5 {
			t.Fatalf("MaxRetries = %d, want 5", got)
		}
	})
	t.Run("MaxRetries=abc 回退 3", func(t *testing.T) {
		t.Setenv("SB_PUSH_MAX_RETRIES", "abc")
		if got := DefaultRetryPolicy().MaxRetries; got != 3 {
			t.Fatalf("MaxRetries = %d, want 3", got)
		}
	})
	t.Run("MaxRetries=-2 回退 3", func(t *testing.T) {
		t.Setenv("SB_PUSH_MAX_RETRIES", "-2")
		if got := DefaultRetryPolicy().MaxRetries; got != 3 {
			t.Fatalf("MaxRetries = %d, want 3", got)
		}
	})
	t.Run("MaxRetries=99 上限 10", func(t *testing.T) {
		t.Setenv("SB_PUSH_MAX_RETRIES", "99")
		if got := DefaultRetryPolicy().MaxRetries; got != 10 {
			t.Fatalf("MaxRetries = %d, want 10", got)
		}
	})
	t.Run("BaseBackoff=250ms", func(t *testing.T) {
		t.Setenv("SB_PUSH_RETRY_BASE_MS", "250")
		if got := DefaultRetryPolicy().BaseBackoff; got != 250*time.Millisecond {
			t.Fatalf("BaseBackoff = %v, want 250ms", got)
		}
	})
	t.Run("BaseBackoff=oops 回退 1000ms", func(t *testing.T) {
		t.Setenv("SB_PUSH_RETRY_BASE_MS", "oops")
		if got := DefaultRetryPolicy().BaseBackoff; got != 1000*time.Millisecond {
			t.Fatalf("BaseBackoff = %v, want 1000ms", got)
		}
	})
}

// TestSendWebPushWithRetry_EndpointValidationError 验证 endpoint 校验失败时走满重试。
//
// 注意：SendToSubscription 会先校验 endpoint 前缀，再触碰 receiver 字段。
// 传 "http://127.0.0.1/" 会在 nil 解引用之前返回参数错误，因此 wp=nil 是安全的。
func TestSendWebPushWithRetry_EndpointValidationError(t *testing.T) {
	var wp *notify.WebPushSender // nil receiver，安全见上方注释

	target := notify.WebPushTarget{
		Endpoint: "http://127.0.0.1/",
		P256DH:   "fake-p256dh",
		Auth:     "fake-auth",
	}

	sleeper := &recordingSleeper{}
	policy := RetryPolicy{
		MaxRetries:  2,
		BaseBackoff: 10 * time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0.25,
	}

	err := SendWebPushWithRetry(context.Background(), wp, target, "标题", "正文", "https://example.com", policy, sleeper.sleep)
	if err == nil {
		t.Fatalf("期望返回错误，实际 nil")
	}
	if sleeper.count() != 2 {
		t.Fatalf("睡眠次数 = %d, want 2（fail-open 走满重试）", sleeper.count())
	}
	if !strings.Contains(err.Error(), "https://") {
		t.Fatalf("错误文本期望含 \"https://\"，实际 %q", err.Error())
	}
}

func TestWithRetry_SucceedsAfterFailures(t *testing.T) {
	calls := 0
	sleeper := &recordingSleeper{}
	err := withRetry(context.Background(), DefaultRetryPolicy(), sleeper.sleep, "test", func() error {
		calls++
		if calls <= 2 {
			return errors.New("状态码 500")
		}
		return nil
	})
	if err != nil {
		t.Fatalf("期望 err == nil，实际 %v", err)
	}
	if calls != 3 {
		t.Fatalf("调用次数 = %d, want 3", calls)
	}
	if sleeper.count() != 2 {
		t.Fatalf("睡眠次数 = %d, want 2", sleeper.count())
	}
}

func TestWithRetry_ExhaustsAndWraps(t *testing.T) {
	calls := 0
	sleeper := &recordingSleeper{}
	policy := RetryPolicy{MaxRetries: 2}
	err := withRetry(context.Background(), policy, sleeper.sleep, "test", func() error {
		calls++
		return errors.New("状态码 500")
	})
	if err == nil {
		t.Fatalf("期望返回错误，实际 nil")
	}
	var exhausted *RetryExhaustedError
	if !errors.As(err, &exhausted) {
		t.Fatalf("期望 *RetryExhaustedError，实际 %T", err)
	}
	if exhausted.Attempts != 3 {
		t.Fatalf("Attempts = %d, want 3", exhausted.Attempts)
	}
	if sleeper.count() != 2 {
		t.Fatalf("睡眠次数 = %d, want 2", sleeper.count())
	}
}

func TestWithRetry_NonRetryableNoSleep(t *testing.T) {
	sleeper := &recordingSleeper{}
	err := withRetry(context.Background(), DefaultRetryPolicy(), sleeper.sleep, "test", func() error {
		return notify.ErrAuth
	})
	if err == nil {
		t.Fatalf("期望返回错误，实际 nil")
	}
	var exhausted *RetryExhaustedError
	if !errors.As(err, &exhausted) {
		t.Fatalf("期望 *RetryExhaustedError，实际 %T", err)
	}
	if !exhausted.Immediate {
		t.Fatalf("Immediate = false, want true")
	}
	if sleeper.count() != 0 {
		t.Fatalf("睡眠次数 = %d, want 0", sleeper.count())
	}
}

func TestWithRetry_ContextCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	sleeper := &recordingSleeper{}
	err := withRetry(ctx, DefaultRetryPolicy(), sleeper.sleep, "test", func() error {
		return nil
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("期望 context.Canceled，实际 %v", err)
	}
	var exhausted *RetryExhaustedError
	if errors.As(err, &exhausted) {
		t.Fatalf("期望非 *RetryExhaustedError，实际 %T", err)
	}
}
