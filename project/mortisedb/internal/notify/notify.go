package notify

import (
	"bytes"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

const (
	EventPending      = "conflict.pending"
	EventResolvedAuto = "conflict.resolved_auto"
	EventResolved     = "conflict.resolved"
)

var AllEvents = []string{EventPending, EventResolvedAuto, EventResolved}

var AppVersion = "dev"

const MetricDeliveries = "mortisedb_conflict_webhook_deliveries_total"

const (
	defaultTimeout    = 10 * time.Second
	defaultMaxRetries = 3
)

func init() {
	metrics.Default().RegisterCounter(MetricDeliveries, "冲突 webhook 投递次数（按事件/状态分类）", "event", "status")
}

// Sign 计算 HMAC-SHA256 签名，返回 hex 小写。
func Sign(secret string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// BuildPayload 构造投递 JSON。Marshal 失败返回 nil。
func BuildPayload(event string, c store.Conflict, deliveryID string) []byte {
	payload := map[string]any{
		"event":           event,
		"occurred_at":     time.Now().UTC().Format(time.RFC3339),
		"mortise_version": AppVersion,
		"delivery_id":     deliveryID,
		"conflict": map[string]any{
			"id":          c.ID,
			"table_name":  c.TableName,
			"pk":          c.PK,
			"source_a":    c.SourceA,
			"source_b":    c.SourceB,
			"row_json":    c.RowJSON,
			"status":      c.Status,
			"created_at":  c.CreatedAt,
			"resolved_at": c.ResolvedAt,
		},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil
	}
	return body
}

// Notifier 是 webhook 投递器。
type Notifier struct {
	url        string
	secret     string
	timeout    time.Duration
	maxRetries int
	events     map[string]bool
	logger     *log.Logger
}

// FromConfig 依据配置构造 Notifier。
func FromConfig(cfg *config.Config, logger *log.Logger) *Notifier {
	n := &Notifier{
		timeout:    defaultTimeout,
		maxRetries: defaultMaxRetries,
		logger:     logger,
		events:     make(map[string]bool),
	}
	if cfg == nil {
		return n
	}
	nc := cfg.Notify
	n.url = nc.ConflictWebhookURL
	n.secret = nc.ConflictWebhookSecret
	if nc.ConflictWebhookTimeout != "" {
		if d, err := time.ParseDuration(nc.ConflictWebhookTimeout); err == nil {
			n.timeout = d
		}
	}
	if nc.ConflictWebhookMaxRetries > 0 {
		n.maxRetries = nc.ConflictWebhookMaxRetries
	}
	if len(nc.ConflictEvents) == 0 {
		for _, e := range AllEvents {
			n.events[e] = true
		}
	} else {
		for _, e := range nc.ConflictEvents {
			n.events[e] = true
		}
	}
	return n
}

// Enabled 报告投递器是否启用。
func (n *Notifier) Enabled() bool {
	if n == nil {
		return false
	}
	return n.url != ""
}

// Subscribed 报告事件是否被订阅。
func (n *Notifier) Subscribed(event string) bool {
	if n == nil {
		return false
	}
	return n.events[event]
}

// NotifyAsync 异步投递通知，永不阻塞、永不抛错。
func (n *Notifier) NotifyAsync(event string, c store.Conflict) {
	if !n.Enabled() || !n.Subscribed(event) {
		metrics.Default().Inc(MetricDeliveries, event, "dropped")
		return
	}
	go n.deliver(event, c)
}

// PendingNotify 描述一项延迟投递请求。
type PendingNotify struct {
	Event    string
	Conflict store.Conflict
	Table    string
	PK       string
	Since    string
}

// FireAfterCommit 在事务提交成功后触发投递。
func (n *Notifier) FireAfterCommit(st *store.Store, items []PendingNotify) {
	if !n.Enabled() {
		for _, it := range items {
			metrics.Default().Inc(MetricDeliveries, it.Event, "dropped")
		}
		return
	}
	for _, it := range items {
		if it.Conflict.ID != 0 {
			n.NotifyAsync(it.Event, it.Conflict)
			continue
		}
		if st == nil {
			continue
		}
		conflicts, err := st.ListConflicts("resolved_auto")
		if err != nil {
			if n.logger != nil {
				n.logger.Error("conflict webhook 回查冲突失败", map[string]any{
					"event": it.Event,
					"table": it.Table,
					"pk":    it.PK,
					"error": err.Error(),
				})
			}
			continue
		}
		for _, c := range conflicts {
			if it.Table != "" && c.TableName != it.Table {
				continue
			}
			if it.PK != "" && c.PK != it.PK {
				continue
			}
			if it.Since != "" {
				if c.ResolvedAt == "" || c.ResolvedAt < it.Since {
					continue
				}
			}
			n.NotifyAsync(it.Event, c)
		}
	}
}

// FireTableConflicts 在某表事务提交成功后，扫描该表本次（since 起）新增的冲突并异步投递。
//
// pending：CreatedAt >= since；resolved_auto：ResolvedAt >= since（ResolvedAt 为空时回退用 CreatedAt，
// 覆盖"创建即自动解决"的记录）。未启用或 st 为 nil 时直接返回（不查库）。
// 时间为 RFC3339 秒级字符串比较；同秒边界可能多投，接收端应按 delivery_id 去重。
// 查库失败只记 Error 日志（不断言 logger 非空），永不抛错、永不阻塞调用方。
func (n *Notifier) FireTableConflicts(st *store.Store, table, since string) {
	if !n.Enabled() || st == nil {
		return
	}
	conflicts, err := st.ListConflicts("")
	if err != nil {
		if n.logger != nil {
			n.logger.Error("conflict webhook 回查冲突失败", map[string]any{
				"table": table,
				"error": err.Error(),
			})
		}
		return
	}
	for _, c := range conflicts {
		if c.TableName != table {
			continue
		}
		switch c.Status {
		case "pending":
			if since != "" && c.CreatedAt < since {
				continue
			}
			n.NotifyAsync(EventPending, c)
		case "resolved_auto":
			ts := c.ResolvedAt
			if ts == "" {
				ts = c.CreatedAt
			}
			if since != "" && ts < since {
				continue
			}
			n.NotifyAsync(EventResolvedAuto, c)
		}
	}
}

func newDeliveryID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return strconv.FormatInt(time.Now().UnixNano(), 16)
	}
	return hex.EncodeToString(b)
}

func backoffDelay(attempt int) time.Duration {
	base := time.Second * time.Duration(math.Pow(2, float64(attempt)))
	jitter := 0.75 + 0.5*randFloat64()
	return time.Duration(float64(base) * jitter)
}

func randFloat64() float64 {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		return 0.5
	}
	var v uint64
	for i := 0; i < 8; i++ {
		v = (v << 8) | uint64(b[i])
	}
	return float64(v>>11) / float64(uint64(1)<<53)
}

func (n *Notifier) client() *http.Client {
	return &http.Client{
		Timeout: n.timeout,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

// deliverResult 表示单次请求结果分类。
type deliverResult int

const (
	resultDelivered deliverResult = iota
	resultRetry
	resultDropped
)

func (n *Notifier) deliver(event string, c store.Conflict) {
	deliveryID := newDeliveryID()
	body := BuildPayload(event, c, deliveryID)
	if body == nil {
		metrics.Default().Inc(MetricDeliveries, event, "failed")
		if n.logger != nil {
			n.logger.Error("conflict webhook 投递失败", map[string]any{
				"event":       event,
				"delivery_id": deliveryID,
				"url":         n.url,
				"attempts":    0,
				"last_error":  "payload marshal failed",
			})
		}
		return
	}
	signature := "sha256=" + Sign(n.secret, body)

	client := n.client()
	total := 1 + n.maxRetries
	var lastErr string

	for attempt := 0; attempt < total; attempt++ {
		if attempt > 0 {
			time.Sleep(backoffDelay(attempt - 1))
		}
		res, errMsg := n.attempt(client, event, deliveryID, signature, body)
		switch res {
		case resultDelivered:
			metrics.Default().Inc(MetricDeliveries, event, "delivered")
			return
		case resultDropped:
			metrics.Default().Inc(MetricDeliveries, event, "dropped")
			return
		case resultRetry:
			if errMsg != "" {
				lastErr = errMsg
			}
		}
	}

	metrics.Default().Inc(MetricDeliveries, event, "failed")
	if n.logger != nil {
		n.logger.Error("conflict webhook 投递失败", map[string]any{
			"event":       event,
			"delivery_id": deliveryID,
			"url":         n.url,
			"attempts":    total,
			"last_error":  lastErr,
		})
	}
}

func (n *Notifier) attempt(client *http.Client, event, deliveryID, signature string, body []byte) (deliverResult, string) {
	req, err := http.NewRequest(http.MethodPost, n.url, bytes.NewReader(body))
	if err != nil {
		return resultRetry, err.Error()
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mortise-Signature", signature)
	req.Header.Set("X-Mortise-Event", event)
	req.Header.Set("X-Mortise-Delivery-Id", deliveryID)

	resp, err := client.Do(req)
	if err != nil {
		return resultRetry, err.Error()
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)

	code := resp.StatusCode
	switch {
	case code >= 200 && code < 300:
		return resultDelivered, ""
	case code == http.StatusTooManyRequests:
		return resultRetry, fmt.Sprintf("status %d", code)
	case code >= 500:
		return resultRetry, fmt.Sprintf("status %d", code)
	case code >= 300 && code < 400:
		return resultRetry, fmt.Sprintf("status %d", code)
	default:
		return resultDropped, fmt.Sprintf("status %d", code)
	}
}
