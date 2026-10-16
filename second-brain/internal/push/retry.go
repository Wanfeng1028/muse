package push

import (
	"context"
	"errors"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"regexp"
	"strconv"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// RetryPolicy 描述指数退避重试的策略参数。
// 之所以把退避参数集中到结构体，是为了让调用方（或测试）能注入自定义策略，
// 避免退避时长散落在各调用点导致行为不一致。
type RetryPolicy struct {
	// MaxRetries 是首次尝试之外的最大重试次数，因此总尝试次数 = MaxRetries+1。
	MaxRetries int
	// BaseBackoff 是第 0 次重试（attempt=0）的基础退避时长。
	BaseBackoff time.Duration
	// MaxBackoff 是单次退避的上限，避免指数增长导致睡眠过久。
	MaxBackoff time.Duration
	// JitterRatio 是抖动比例，实际退避在 [d*(1-r), d*(1+r)] 区间内随机。
	JitterRatio float64
}

// DefaultRetryPolicy 从环境变量读取重试策略，缺省值与非法值都回落到安全默认。
// 之所以做上限/下限钳制，是因为外部环境可能被误配置成极端值（例如 100 次重试），
// 会拖垮整个推送批次，因此这里强制收敛到合理范围。
func DefaultRetryPolicy() RetryPolicy {
	maxRetries := 3
	if v := os.Getenv("SB_PUSH_MAX_RETRIES"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			maxRetries = n
		}
	}
	if maxRetries > 10 {
		maxRetries = 10
	}

	baseMS := 1000
	if v := os.Getenv("SB_PUSH_RETRY_BASE_MS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			baseMS = n
		}
	}
	if baseMS > 60000 {
		baseMS = 60000
	}

	return RetryPolicy{
		MaxRetries:  maxRetries,
		BaseBackoff: time.Duration(baseMS) * time.Millisecond,
		MaxBackoff:  30 * time.Second,
		JitterRatio: 0.25,
	}
}

// httpStatusPattern 用于从错误文本中提取 HTTP 状态码。RE2 不支持前瞻，
// 用 (?:\D|$) 挡掉 2000/4290 这类更长数字串，避免取前三位误判。
var httpStatusPattern = regexp.MustCompile(`状态(?:码)?\s*(\d{3})(?:\D|$)`)

// httpStatusPatternEn 用于从英文错误文本中提取 HTTP 状态码。
var httpStatusPatternEn = regexp.MustCompile(`(?i)(?:\bhttp\b|\bstatus\b)\s*[:：]?\s*(\d{3})(?:\D|$)`)

// IsRetryable 判定一个错误是否值得重试。
//
// 分类策略（顺序敏感，先匹配更具体的哨兵错误）：
//   - nil：没有错误，无需重试。
//   - ctx 取消/超时：不可重试，直接透出。
//   - ErrAuth：鉴权失败是配置/凭据问题，重试只会浪费配额并可能触发风控，永不重试。
//   - ErrSubscriptionGone：订阅已失效（410/404），应交给调用方走清理流程，重试无意义。
//   - ErrConn：网络/连接错误属于典型的瞬时故障，可重试。
//   - HTTP 状态码：429（限流）与 5xx（服务端错误）可重试；2xx/3xx 明确不可重试；其余 4xx 是请求本身有问题，重试无用。
//   - 兜底：无法识别的错误返回 true。这是有意为之的 fail-open 策略：
//     我们宁可多试一次，也不愿因为分类器覆盖不全而漏掉本可恢复的瞬时故障；
//     即便重试全部失败，最终仍有死信（failed_permanent）兜底记录，不会静默丢失。
func IsRetryable(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return false
	}
	if errors.Is(err, notify.ErrAuth) {
		return false
	}
	if errors.Is(err, notify.ErrSubscriptionGone) {
		return false
	}
	if errors.Is(err, notify.ErrConn) {
		return true
	}

	if m := httpStatusPattern.FindStringSubmatch(err.Error()); m != nil {
		if code, convErr := strconv.Atoi(m[1]); convErr == nil {
			if code == 429 || (code >= 500 && code <= 599) {
				return true
			}
			if code >= 200 && code <= 399 {
				return false
			}
			if code >= 400 && code <= 499 {
				return false
			}
		}
	}
	if m := httpStatusPatternEn.FindStringSubmatch(err.Error()); m != nil {
		if code, convErr := strconv.Atoi(m[1]); convErr == nil {
			if code == 429 || (code >= 500 && code <= 599) {
				return true
			}
			if code >= 200 && code <= 399 {
				return false
			}
			if code >= 400 && code <= 499 {
				return false
			}
		}
	}

	// fail-open：未知错误倾向于可重试，最终由死信兜底。
	return true
}

// backoffForAttempt 计算第 attempt 次重试应睡眠的时长（attempt 从 0 起）。
//
// 计算方式：base * 2^attempt，随后先钳制到 MaxBackoff，再叠加 ±JitterRatio 的抖动，
// 最后再钳制到 MaxBackoff。抖动的作用是避免多个通道在同一时刻集中重试（惊群），
// 这里必须使用调用方传入的 rng，避免污染全局随机源导致并发下行为不可预测。
func backoffForAttempt(policy RetryPolicy, attempt int, rng *rand.Rand) time.Duration {
	if attempt < 0 {
		attempt = 0
	}

	base := policy.BaseBackoff
	if base <= 0 {
		return 0
	}

	// attempt 过大时 2^attempt 必然溢出，直接取 MaxBackoff。
	if policy.MaxBackoff > 0 && attempt > 30 {
		return policy.MaxBackoff
	}

	d := time.Duration(float64(base) * math.Pow(2, float64(attempt)))

	// 先钳制上限，避免指数增长溢出后再做抖动计算。
	if policy.MaxBackoff > 0 && d > policy.MaxBackoff {
		d = policy.MaxBackoff
	}

	// 再应用抖动，最后再次钳制上限，保证结果不超过 MaxBackoff。
	if policy.JitterRatio > 0 && rng != nil {
		// rand.Float64 返回 [0,1)，映射到 [-JitterRatio, +JitterRatio]。
		delta := (rng.Float64()*2 - 1) * policy.JitterRatio
		d = time.Duration(float64(d) * (1 + delta))
	}

	if d < 0 {
		d = 0
	}
	if policy.MaxBackoff > 0 && d > policy.MaxBackoff {
		d = policy.MaxBackoff
	}
	return d
}

// Sleeper 抽象"等待一段时间"，便于测试注入假实现。
type Sleeper func(ctx context.Context, d time.Duration) error

// DefaultSleeper 使用 time.Timer 实现可被 ctx 取消的睡眠。
// 用 Timer 而非 time.Sleep，是为了在 ctx 取消时能立刻返回，避免批次退出被拖住。
func DefaultSleeper(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// RetryExhaustedError 表示重试已耗尽（含不可重试的立即失败）。
type RetryExhaustedError struct {
	Attempts  int
	LastErr   error
	Immediate bool
}

// Error 实现 error 接口。
func (e *RetryExhaustedError) Error() string {
	if e == nil {
		return "push: 重试耗尽"
	}
	if e.Immediate {
		return fmt.Sprintf("push: 发送失败（不可重试，共尝试 %d 次）: %v", e.Attempts, e.LastErr)
	}
	return fmt.Sprintf("push: 发送失败（重试耗尽，共尝试 %d 次）: %v", e.Attempts, e.LastErr)
}

// Unwrap 暴露底层错误，便于调用方用 errors.Is/As 做进一步判断。
func (e *RetryExhaustedError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.LastErr
}

// retrySender 是包裹了重试逻辑的 Sender 装饰器。
type retrySender struct {
	inner  notify.Sender
	policy RetryPolicy
	sleep  Sleeper
}

// Name 原样透传内层 sender 的通道名。
// 红线要求：push_log 的 channel 列必须保持 smtp/webhook/webpush 原样，
// 因此这里绝不允许添加任何后缀或改写。
func (r *retrySender) Name() string {
	return r.inner.Name()
}

// Send 按策略执行发送与重试。
//
// 语义约定：
//   - 总尝试次数 = MaxRetries+1。
//   - 首次失败且不可重试：立刻返回 RetryExhaustedError，不睡眠。
//   - 可重试失败且仍有剩余次数：按 backoffForAttempt 睡眠后继续。
//   - ctx 取消：立刻返回 ctx.Err()（不包装成耗尽，便于上层区分"取消"与"失败"）。
func (r *retrySender) Send(ctx context.Context, msg notify.Message) error {
	sleep := r.sleep
	if sleep == nil {
		sleep = DefaultSleeper
	}

	// 每次 Send 新建独立 rng，种子混入全局安全随机数避免同纳秒并发种子相同。
	rng := rand.New(rand.NewSource(time.Now().UnixNano() ^ int64(rand.Uint64())))

	totalAttempts := r.policy.MaxRetries + 1
	if totalAttempts < 1 {
		totalAttempts = 1
	}

	name := r.inner.Name()

	var lastErr error
	for attempt := 0; attempt < totalAttempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}

		lastErr = r.inner.Send(ctx, msg)
		if lastErr == nil {
			return nil
		}

		if ctx.Err() != nil {
			return ctx.Err()
		}

		if !IsRetryable(lastErr) {
			// 不可重试：立即返回，不睡眠，避免无谓等待。
			return &RetryExhaustedError{Attempts: attempt + 1, LastErr: lastErr, Immediate: true}
		}

		// 已是最后一次尝试，不再睡眠。
		if attempt == totalAttempts-1 {
			break
		}

		d := backoffForAttempt(r.policy, attempt, rng)
		log.Printf("push: %s 发送失败（第 %d/%d 次），%v 后重试：%v", name, attempt+1, totalAttempts, d, lastErr)
		if err := sleep(ctx, d); err != nil {
			// ctx 取消（或 sleeper 自定义错误）：立刻返回，不包装成耗尽。
			return err
		}
	}

	log.Printf("push: %s 发送失败，已尝试 %d 次不再重试：%v", name, totalAttempts, lastErr)
	return &RetryExhaustedError{Attempts: totalAttempts, LastErr: lastErr}
}

// WrapWithRetry 用默认 sleeper 包裹 sender。
func WrapWithRetry(sender notify.Sender, policy RetryPolicy) notify.Sender {
	return WrapWithRetrySleeper(sender, policy, nil)
}

// WrapWithRetrySleeper 用指定 sleeper 包裹 sender（nil 时使用 DefaultSleeper）。
func WrapWithRetrySleeper(sender notify.Sender, policy RetryPolicy, sleep Sleeper) notify.Sender {
	if sleep == nil {
		sleep = DefaultSleeper
	}
	return &retrySender{
		inner:  sender,
		policy: policy,
		sleep:  sleep,
	}
}

// SendWebPushWithRetry 把 WebPush 的 SendToSubscription 适配进统一的重试循环。
//
// 之所以单独提供一个函数而不是复用 Sender 装饰器，是因为 WebPushSender 的
// 发送入口签名（目标 + 标题 + 正文 + URL）与 notify.Sender.Send(ctx, Message) 不同，
// 直接套装饰器需要额外构造 Message 适配层，反而增加耦合。
//
// 注意：ErrSubscriptionGone 被 IsRetryable 判定为不可重试，会原样透出（经 RetryExhaustedError 包装后
// 仍可用 errors.Is 命中），调用方据此执行订阅清理。
func SendWebPushWithRetry(
	ctx context.Context,
	wp *notify.WebPushSender,
	target notify.WebPushTarget,
	title, body, url string,
	policy RetryPolicy,
	sleep Sleeper,
) error {
	if sleep == nil {
		sleep = DefaultSleeper
	}

	rng := rand.New(rand.NewSource(time.Now().UnixNano() ^ int64(rand.Uint64())))

	totalAttempts := policy.MaxRetries + 1
	if totalAttempts < 1 {
		totalAttempts = 1
	}

	name := "webpush"

	var lastErr error
	for attempt := 0; attempt < totalAttempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}

		lastErr = wp.SendToSubscription(ctx, target, title, body, url)
		if lastErr == nil {
			return nil
		}

		if ctx.Err() != nil {
			return ctx.Err()
		}

		if !IsRetryable(lastErr) {
			return &RetryExhaustedError{Attempts: attempt + 1, LastErr: lastErr, Immediate: true}
		}

		if attempt == totalAttempts-1 {
			break
		}

		d := backoffForAttempt(policy, attempt, rng)
		log.Printf("push: %s 发送失败（第 %d/%d 次），%v 后重试：%v", name, attempt+1, totalAttempts, d, lastErr)
		if err := sleep(ctx, d); err != nil {
			return err
		}
	}

	log.Printf("push: %s 发送失败，已尝试 %d 次不再重试：%v", name, totalAttempts, lastErr)
	return &RetryExhaustedError{Attempts: totalAttempts, LastErr: lastErr}
}

// truncateRetryDetail 按 rune 截断字符串到 max 个字符，避免把多字节字符切坏。
// 这里不引用 scheduler.go 的私有函数，是为了让 retry.go 自洽、不依赖其他文件的内部实现。
func truncateRetryDetail(s string, max int) string {
	if max <= 0 {
		return ""
	}
	runes := []rune(s)
	if len(runes) <= max {
		return s
	}
	return string(runes[:max])
}

// RecordDeadLetter 记录一条死信（failed_permanent）。
//
// 幂等依据：push_log 上存在唯一索引 idx_push_log_date_channel_user(date, channel, user_id)，
// 且 RecordPushFor 内部使用 ON CONFLICT DO UPDATE 做 upsert。若同一 due 批次内
// 该 (date, channel, user) 已被标记为 failed_permanent，则直接返回 nil，避免重复写入、
// 也避免把后续批次的 detail 覆盖成不同的错误信息（保持首次失败原因可追溯）。
func RecordDeadLetter(st *store.Store, dateKey, channel, user string, lastErr error) error {
	if st == nil {
		return errors.New("push: nil store")
	}

	status, found := st.PushLogStatus(dateKey, channel, user)
	if found && status == "failed_permanent" {
		return nil
	}

	detail := "重试耗尽: "
	if lastErr != nil {
		detail += lastErr.Error()
	}
	detail = truncateRetryDetail(detail, 200)

	return st.RecordPushFor(dateKey, channel, user, "failed_permanent", detail)
}

// 保证 retrySender 满足 notify.Sender 接口（编译期检查）。
var _ notify.Sender = (*retrySender)(nil)
