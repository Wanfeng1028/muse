// internal/push/scheduler.go
package push

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// PushResult 表示一次推送尝试的结果。
type PushResult struct {
	Channel string
	User    string
	Status  string
	Detail  string
}

// SenderSet 保存各通道的发送器，nil 表示该通道未配置。
type SenderSet struct {
	SMTP    notify.Sender
	Webhook notify.Sender
	// WebPush 为 Web Push 发送器，nil 表示未配置 VAPID。
	WebPush *notify.WebPushSender
}

// BuildSenders 根据配置构建各通道发送器。
func BuildSenders(pc config.PushConfig) SenderSet {
	var set SenderSet
	if pc.SMTPHost != "" {
		set.SMTP = notify.NewSMTPSender(pc.SMTPHost, pc.SMTPPort, pc.SMTPUser, pc.SMTPPass, pc.SMTPFrom, pc.SMTPTLS)
	}
	if pc.WebhookURL != "" {
		set.Webhook = notify.NewWebhookSender(pc.WebhookURL, pc.WebhookSecret, 15*time.Second)
	}
	if pc.VAPIDConfigured() {
		if wp, err := notify.NewWebPushSender(pc.VAPIDPublicKey, pc.VAPIDPrivateKey, pc.VAPIDSubject, 15*time.Second); err != nil {
			slog.Warn("push.webpush_build_failed", "error", err)
		} else {
			set.WebPush = wp
		}
	}
	// v0.11 发送重试：SMTP/Webhook 统一走指数退避包装器。Name() 原样透出，
	// push_log 的 channel 名保持 "smtp"/"webhook" 不变。
	policy := DefaultRetryPolicy()
	if set.SMTP != nil {
		set.SMTP = WrapWithRetry(set.SMTP, policy)
	}
	if set.Webhook != nil {
		set.Webhook = WrapWithRetry(set.Webhook, policy)
	}
	return set
}

// NextPushTime 计算下一次推送时刻。clockTime 形如 "08:30"。
// 若当天该时刻尚未到达则返回当天，否则返回次日。
func NextPushTime(now time.Time, clockTime string, loc *time.Location) (time.Time, error) {
	if loc == nil {
		loc = time.Local
	}
	parts := strings.Split(clockTime, ":")
	if len(parts) != 2 {
		return time.Time{}, fmt.Errorf("非法时间格式: %q", clockTime)
	}
	hour, err := strconv.Atoi(strings.TrimSpace(parts[0]))
	if err != nil {
		return time.Time{}, fmt.Errorf("非法小时: %q", clockTime)
	}
	minute, err := strconv.Atoi(strings.TrimSpace(parts[1]))
	if err != nil {
		return time.Time{}, fmt.Errorf("非法分钟: %q", clockTime)
	}
	if hour < 0 || hour > 23 || minute < 0 || minute > 59 {
		return time.Time{}, fmt.Errorf("时间越界: %q", clockTime)
	}

	local := now.In(loc)
	candidate := time.Date(local.Year(), local.Month(), local.Day(), hour, minute, 0, 0, loc)
	if !candidate.After(local) {
		candidate = candidate.AddDate(0, 0, 1)
	}
	return candidate, nil
}

// RunPushForUser 对单个用户执行一次推送。now 可注入以便测试。单个通道失败不影响其他通道。
func RunPushForUser(ctx context.Context, st *store.Store, senders SenderSet, pc config.PushConfig, now time.Time, user string) []PushResult {
	user = store.NormalizeUser(user)
	loc, err := time.LoadLocation(pc.Timezone)
	if err != nil || pc.Timezone == "" {
		loc = time.Local
	}
	dateKey := now.In(loc).Format("2006-01-02")

	due, err := st.ListDueReviews(now, 50, user)
	if err != nil {
		slog.Error("push.list_due_failed", "user", user, "error", err)
	}
	stats, err := st.ReviewStats(now, user)
	if err != nil {
		slog.Error("push.review_stats_failed", "user", user, "error", err)
	}

	items := make([]notify.DigestItem, 0, len(due))
	overdueCount := 0
	for _, d := range due {
		if d.OverdueDays > 0 {
			overdueCount++
		}
		items = append(items, notify.DigestItem{
			Title:       d.Note.Title,
			Snippet:     snippetOf(d.Note.Body, 120),
			Tags:        d.Note.Tags,
			DueDate:     d.DueDate,
			OverdueDays: d.OverdueDays,
		})
	}
	digestStats := notify.DigestStats{
		DueCount:    len(items),
		OverdueDays: overdueCount,
		Streak:      stats.StreakDays,
	}

	var results []PushResult
	for _, ch := range channelEntries(senders) {
		if ch.sender == nil {
			continue
		}
		name := ch.sender.Name()
		if st.HasPushedFor(dateKey, name, user) {
			results = append(results, PushResult{Channel: name, User: user, Status: "skipped", Detail: "今日已推送"})
			continue
		}

		msg := notify.BuildDigestMessage(now, items, digestStats, pc.MailTo)
		sendCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
		sendErr := ch.sender.Send(sendCtx, msg)
		cancel()

		if sendErr != nil {
			// v0.11 发送重试：重试耗尽转死信（push_log status='failed_permanent'），
			// RecordDeadLetter 幂等：同一 due 批次重复触发不会重复入死信。
			var rex *RetryExhaustedError
			if errors.As(sendErr, &rex) {
				detail := truncateRunes("重试耗尽: "+rex.LastErr.Error(), 200)
				if err := RecordDeadLetter(st, dateKey, name, user, rex.LastErr); err != nil {
					slog.Error("push.dead_letter_write_failed", "channel", name, "error", err)
				}
				results = append(results, PushResult{Channel: name, User: user, Status: "failed_permanent", Detail: detail})
				continue
			}
			detail := sendErr.Error()
			if len(detail) > 200 {
				detail = detail[:200]
			}
			if err := st.RecordPushFor(dateKey, name, user, "failed", detail); err != nil {
				slog.Error("push.record_write_failed", "channel", name, "user", user, "error", err)
			}
			results = append(results, PushResult{Channel: name, User: user, Status: "failed", Detail: detail})
			continue
		}
		if err := st.RecordPushFor(dateKey, name, user, "sent", ""); err != nil {
			slog.Error("push.record_write_failed", "channel", name, "user", user, "error", err)
		}
		results = append(results, PushResult{Channel: name, User: user, Status: "sent", Detail: ""})
	}
	if senders.WebPush != nil && len(items) > 0 {
		const wpName = "webpush"
		if st.HasPushedFor(dateKey, wpName, user) {
			results = append(results, PushResult{Channel: wpName, User: user, Status: "skipped", Detail: "今日已推送"})
		} else {
			results = append(results, sendWebPushDigest(ctx, st, senders.WebPush, dateKey, user, len(items)))
		}
	}
	return results
}

// sendWebPushDigest 向指定用户的全部浏览器订阅推送复习摘要，410/404 失效订阅顺手清理。
func sendWebPushDigest(ctx context.Context, st *store.Store, wp *notify.WebPushSender, dateKey, user string, dueCount int) PushResult {
	const wpName = "webpush"
	subs, err := st.ListSubscriptionsForUser(user)
	if err != nil {
		return PushResult{Channel: wpName, User: user, Status: "failed", Detail: truncateRunes("读取订阅失败: "+err.Error(), 200)}
	}
	if len(subs) == 0 {
		return PushResult{Channel: wpName, User: user, Status: "skipped", Detail: "该用户无浏览器订阅"}
	}
	title := "第二大脑 · 复习提醒"
	var body string
	if dueCount == 1 {
		body = "有 1 篇笔记到期了，点开看看"
	} else {
		body = fmt.Sprintf("今天有 %d 篇笔记到期了，点开看看", dueCount)
	}
	const targetURL = "/#review"
	sentN, goneN := 0, 0
	var failMsg string
	var exhausted *RetryExhaustedError
	policy := DefaultRetryPolicy()
	for _, s := range subs {
		target := notify.WebPushTarget{Endpoint: s.Endpoint, P256DH: s.P256DH, Auth: s.Auth}
		err := SendWebPushWithRetry(ctx, wp, target, title, body, targetURL, policy, nil)
		if err == nil {
			sentN++
			continue
		}
		if errors.Is(err, notify.ErrSubscriptionGone) {
			goneN++
			if _, delErr := st.DeleteSubscriptionForUser(user, s.Endpoint); delErr != nil {
				slog.Error("push.subscription_cleanup_failed", "user", user, "error", delErr)
			}
			continue
		}
		var rex *RetryExhaustedError
		if errors.As(err, &rex) {
			if exhausted == nil {
				exhausted = rex
			}
			if failMsg == "" {
				failMsg = rex.LastErr.Error()
			}
			continue
		}
		if failMsg == "" {
			failMsg = err.Error()
		}
	}
	var status, detail string
	if sentN > 0 {
		status = "sent"
		if goneN > 0 {
			detail = fmt.Sprintf("成功 %d 条，清理失效订阅 %d 条", sentN, goneN)
		}
	} else if goneN > 0 && failMsg == "" {
		status = "failed"
		detail = fmt.Sprintf("全部订阅已失效，清理 %d 条", goneN)
	} else {
		status = "failed"
		detail = truncateRunes("推送失败: "+failMsg, 200)
	}
	// v0.11 发送重试：全部订阅都重试耗尽且无成功时转死信（幂等）。
	if status == "failed" && exhausted != nil {
		if err := RecordDeadLetter(st, dateKey, wpName, user, exhausted.LastErr); err != nil {
			slog.Error("push.dead_letter_write_failed", "channel", wpName, "error", err)
		}
		status = "failed_permanent"
		detail = truncateRunes("重试耗尽: "+exhausted.LastErr.Error(), 200)
	} else if err := st.RecordPushFor(dateKey, wpName, user, status, detail); err != nil {
		slog.Error("push.record_write_failed", "channel", wpName, "user", user, "error", err)
	}
	return PushResult{Channel: wpName, User: user, Status: status, Detail: detail}
}

// truncateRunes 按 rune 截断到 n 个字符。
func truncateRunes(s string, n int) string {
	if n <= 0 {
		return ""
	}
	rs := []rune(s)
	if len(rs) <= n {
		return s
	}
	return string(rs[:n])
}

// RunPush 执行一次推送：按有到期回顾的用户循环分发，每个用户独立 digest。无用户到期时回退为默认用户单次推送（保持空库行为与旧测试兼容）。
func RunPush(ctx context.Context, st *store.Store, senders SenderSet, pc config.PushConfig, now time.Time) []PushResult {
	users, err := st.ListUsersWithDueReviews(now)
	if err != nil {
		slog.Error("push.list_users_failed", "error", err)
		users = nil
	}
	if len(users) == 0 {
		users = []string{store.DefaultUser}
	}
	var results []PushResult
	for _, u := range users {
		results = append(results, RunPushForUser(ctx, st, senders, pc, now, u)...)
	}
	return results
}

type channelEntry struct {
	name   string
	sender notify.Sender
}

func channelEntries(senders SenderSet) []channelEntry {
	return []channelEntry{
		{name: "smtp", sender: senders.SMTP},
		{name: "webhook", sender: senders.Webhook},
	}
}

func snippetOf(body string, max int) string {
	body = strings.TrimSpace(body)
	if len(body) <= max {
		return body
	}
	runes := []rune(body)
	if len(runes) <= max {
		return body
	}
	return string(runes[:max])
}

// Scheduler 定时触发推送。
type Scheduler struct {
	st       *store.Store
	senders  SenderSet
	pc       config.PushConfig
	nowFunc  func() time.Time
	interval time.Duration

	stopCh chan struct{}
	doneCh chan struct{}
	once   sync.Once
}

// NewScheduler 创建调度器。
func NewScheduler(st *store.Store, senders SenderSet, pc config.PushConfig) *Scheduler {
	return &Scheduler{
		st:       st,
		senders:  senders,
		pc:       pc,
		nowFunc:  time.Now,
		interval: 30 * time.Second,
		stopCh:   make(chan struct{}),
		doneCh:   make(chan struct{}),
	}
}

// SetNowFunc 注入时间源，仅用于测试。
func (s *Scheduler) SetNowFunc(fn func() time.Time) {
	if fn != nil {
		s.nowFunc = fn
	}
}

// SetInterval 注入检查间隔，仅用于测试。
func (s *Scheduler) SetInterval(d time.Duration) {
	if d > 0 {
		s.interval = d
	}
}

// Start 启动调度循环。
func (s *Scheduler) Start() {
	go s.loop()
}

// Stop 停止调度循环并等待退出。
func (s *Scheduler) Stop() {
	s.once.Do(func() {
		close(s.stopCh)
	})
	<-s.doneCh
}

func (s *Scheduler) loop() {
	defer close(s.doneCh)

	loc, err := time.LoadLocation(s.pc.Timezone)
	if err != nil || s.pc.Timezone == "" {
		loc = time.Local
	}

	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()

	// 启动时先检查一次
	s.tick(loc)

	for {
		select {
		case <-s.stopCh:
			return
		case <-ticker.C:
			s.tick(loc)
		}
	}
}

func (s *Scheduler) tick(loc *time.Location) {
	now := s.nowFunc()
	next, err := NextPushTime(now, s.pc.Time, loc)
	if err != nil {
		slog.Error("push.next_time_parse_failed", "error", err)
		return
	}
	// 当 now 已过今日推送时刻（next 落在次日）时，视为到点需推送。
	// 通过比较 now 所在日期与 next 所在日期判断。
	local := now.In(loc)
	if next.Year() == local.Year() && next.YearDay() == local.YearDay() {
		// 当天推送时刻尚未到达
		return
	}
	dateKey := local.Format("2006-01-02")
	users, err := s.st.ListUsersWithDueReviews(now)
	if err != nil {
		slog.Error("push.list_users_failed", "error", err)
		return
	}
	if len(users) == 0 {
		users = []string{store.DefaultUser}
	}
	for _, u := range users {
		if s.st.HasPushedFor(dateKey, "smtp", u) || s.st.HasPushedFor(dateKey, "webhook", u) || s.st.HasPushedFor(dateKey, "webpush", u) {
			continue
		}
		results := RunPushForUser(context.Background(), s.st, s.senders, s.pc, now, u)
		for _, r := range results {
			slog.Info("push.tick_result", "channel", r.Channel, "user", r.User, "status", r.Status, "detail", r.Detail)
		}
	}
}
