package notify

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"math/rand/v2"
	"net/http"
	"strings"
	"time"

	"sentinel/internal/log"
	"sentinel/internal/metrics"
	"sentinel/internal/store"
)

// QueueSender 把 webhook 投递任务持久化到 SQLite 队列并由 worker 按指数退避重投。
type QueueSender struct {
	Store          *store.Store
	MaxAttempts    int              // <=0 则用 8
	BaseBackoffSec int64            // <=0 则用 60
	TickSec        int              // <=0 则用 15
	Limiter        *RateLimiter     // 入队限流器；nil 表示不限流
	Breakers       *BreakerRegistry // 投递熔断注册表；nil 表示不熔断

}

const (
	defaultQueueMaxAttempts    = 8
	defaultQueueBaseBackoffSec = int64(60)
	defaultQueueTickSec        = 15
	maxBackoff                 = 24 * time.Hour
)

// BackoffFor 计算第 attempt 次投递失败后的退避时长。
// attempt < 1 按 1 处理；d = base * 2^(attempt-1)，超过 24h 则钳制到 24h；
// jitter 为 [0, base) 均匀随机整数秒（使用 math/rand/v2）。
func (q *QueueSender) BackoffFor(attempt int) time.Duration {
	base := q.BaseBackoffSec
	if base <= 0 {
		base = defaultQueueBaseBackoffSec
	}
	if attempt < 1 {
		attempt = 1
	}

	shift := attempt - 1
	var mult int64
	if shift >= 62 {
		mult = math.MaxInt64
	} else {
		mult = int64(1) << uint(shift)
	}

	var d int64
	if mult > int64(maxBackoff/time.Second)/base {
		d = int64(maxBackoff / time.Second)
	} else {
		d = base * mult
		if d > int64(maxBackoff/time.Second) {
			d = int64(maxBackoff / time.Second)
		}
	}

	jitter := int64(0)
	if base > 1 {
		jitter = rand.Int64N(base)
	}

	total := time.Duration(d)*time.Second + time.Duration(jitter)*time.Second
	if total > maxBackoff {
		total = maxBackoff
	}
	return total
}

// EnqueueWebhook 把一次 webhook 事件入队。url 为空（去空格后）直接返回 nil。
// payload 结构与同步发送保持一致。
func (q *QueueSender) EnqueueWebhook(monitorID int64, url, event, name, target, at, errMsg string) error {
	u := strings.TrimSpace(url)
	if u == "" {
		return nil
	}

	if q.Limiter != nil && !q.Limiter.Allow() {
		log.Logger().Warn("webhook 入队被限流拒绝", "monitor_id", monitorID, "url", u, "event", event)
		metrics.Default.RecordEnqueueRejected()
		return ErrEnqueueRateLimited
	}

	body, err := json.Marshal(payload{
		Event:   event,
		Name:    name,
		Target:  target,
		At:      at,
		ErrMsg:  errMsg,
		Service: "sentinel",
	})
	if err != nil {
		return fmt.Errorf("序列化通知失败: %w", err)
	}

	maxAttempts := q.MaxAttempts
	if maxAttempts <= 0 {
		maxAttempts = defaultQueueMaxAttempts
	}

	if _, err := q.Store.EnqueueDelivery(monitorID, u, event, string(body), maxAttempts); err != nil {
		return fmt.Errorf("入队 webhook 投递失败: %w", err)
	}
	return nil
}

// postWebhookOnce 执行一次 webhook POST 请求。非 2xx 返回中文错误。
// webhookStatusError 表示下游返回了非 2xx 状态码。
// Permanent 为 true 表示该失败不可通过重试解决（4xx 且非 408/429）。
type webhookStatusError struct {
	StatusCode int
	Permanent  bool
}

func (e *webhookStatusError) Error() string {
	if e.Permanent {
		return fmt.Sprintf("永久失败: 非 2xx 状态码: %d", e.StatusCode)
	}
	return fmt.Sprintf("非 2xx 状态码: %d", e.StatusCode)
}

func postWebhookOnce(url string, body []byte) error {
	client := &http.Client{Timeout: 10 * time.Second}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("构造通知请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<20))
	_ = resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &webhookStatusError{
			StatusCode: resp.StatusCode,
			Permanent:  resp.StatusCode >= 400 && resp.StatusCode < 500 && resp.StatusCode != 408 && resp.StatusCode != 429,
		}
	}
	return nil
}

// ProcessDue 扫描到期的投递记录并逐条尝试投递。
// 成功标记 done；失败分类处理：永久失败（4xx 且非 408/429）立即标记 failed，
// 不消耗重试；可重试失败（网络错/超时/5xx/408/429）在耗尽 attempt 后标记 dead，
// 否则标记 retrying 并安排下次重试。
// BreakerStates 返回各下游 host 的熔断状态（0=闭合，1=断开，2=半开）；
// 未配置熔断注册表时返回 nil。供 /api/metrics 导出。
func (q *QueueSender) BreakerStates() map[string]int {
	if q.Breakers == nil {
		return nil
	}
	snap := q.Breakers.Snapshot()
	out := make(map[string]int, len(snap))
	for host, st := range snap {
		out[host] = int(st)
	}
	return out
}

func (q *QueueSender) ProcessDue(ctx context.Context) error {

	if err := q.Store.RecoverStaleDeliveries(time.Now().UTC()); err != nil {
		return fmt.Errorf("捞取到期投递失败: %w", err)
	}
	now := time.Now().UTC().Format(time.RFC3339)
	items, err := q.Store.ClaimDueDeliveries(now, 100)
	if err != nil {
		return fmt.Errorf("捞取到期投递失败: %w", err)
	}

	for _, d := range items {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		var br *CircuitBreaker
		if q.Breakers != nil {
			br = q.Breakers.Get(d.URL)
			if !br.BeforeRequest() {
				log.Logger().Warn("webhook 投递被熔断跳过", "delivery_id", d.ID, "url", d.URL, "state", br.State().String())
				if err := q.Store.ReleaseClaim(d.ID); err != nil {
					log.Logger().Error("释放认领失败", "delivery_id", d.ID, "err", err)
				}
				continue
			}
		}

		if err := postWebhookOnce(d.URL, []byte(d.Payload)); err == nil {
			if br != nil {
				br.AfterRequest(true)
			}

			if err := q.Store.MarkDeliveryDone(d.ID); err != nil {
				log.Logger().Error("标记投递成功失败", "delivery_id", d.ID, "error", err)
			}
			continue
		} else {
			errMsg := err.Error()
			attempts := d.Attempt + 1

			maxAttempts := d.MaxAttempts
			if maxAttempts <= 0 {
				maxAttempts = q.MaxAttempts
				if maxAttempts <= 0 {
					maxAttempts = defaultQueueMaxAttempts
				}
			}

			if attempts >= maxAttempts {
				var statusErr *webhookStatusError
				permanent := errors.As(err, &statusErr) && statusErr.Permanent
				var markErr error
				if permanent {
					markErr = q.Store.MarkDeliveryFailed(d.ID, errMsg)
				} else {
					markErr = q.Store.MarkDeliveryDead(d.ID, errMsg)
				}
				if markErr != nil {
					log.Logger().Error("标记投递最终失败失败", "delivery_id", d.ID, "error", err)
				}
				if markErr == nil && !permanent {
					metrics.Default.RecordWebhookDeadLetter()
				}
				log.Logger().Warn("Webhook 投递最终失败",
					"delivery_id", d.ID,
					"url", d.URL,
					"attempt", attempts,
					"error", err,
				)
				if br != nil {
					br.AfterRequest(false)
				}
				continue

			}

			next := time.Now().UTC().Add(q.BackoffFor(attempts)).Format(time.RFC3339)
			var statusErr *webhookStatusError
			permanent := errors.As(err, &statusErr) && statusErr.Permanent
			if permanent {
				if markErr := q.Store.MarkDeliveryFailed(d.ID, errMsg); markErr != nil {
					log.Logger().Error("标记投递永久失败失败", "delivery_id", d.ID, "error", markErr)
				}
				log.Logger().Warn("Webhook 投递永久失败",
					"delivery_id", d.ID,
					"url", d.URL,
					"attempt", attempts,
					"error", err,
				)
				if br != nil {
					br.AfterRequest(false)
				}
				continue
			}
			if err := q.Store.MarkDeliveryAttempt(d.ID, next, errMsg); err != nil {
				log.Logger().Error("记录投递重试失败", "delivery_id", d.ID, "error", err)
			}
			log.Logger().Warn("Webhook 投递失败，将重试",
				"delivery_id", d.ID,
				"url", d.URL,
				"attempt", attempts,
				"error", err,
			)
			if br != nil {
				br.AfterRequest(false)
			}

		}
	}
	return nil
}

// Run 启动后台循环，周期性调用 ProcessDue。ctx 取消后停止 ticker 并返回。
func (q *QueueSender) Run(ctx context.Context) {
	tick := q.TickSec
	if tick <= 0 {
		tick = defaultQueueTickSec
	}

	ticker := time.NewTicker(time.Duration(tick) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := q.ProcessDue(ctx); err != nil {
				log.Logger().Error("webhook 投递队列扫描失败", "error", err)
			}
		}
	}
}
