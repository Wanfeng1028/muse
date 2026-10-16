// internal/push/scheduler.go
package push

import (
	"context"
	"fmt"
	"log"
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
	Status  string
	Detail  string
}

// SenderSet 保存各通道的发送器，nil 表示该通道未配置。
type SenderSet struct {
	SMTP    notify.Sender
	Webhook notify.Sender
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

// RunPush 执行一次推送。now 可注入以便测试。
// 单个通道失败不影响其他通道。
func RunPush(ctx context.Context, st *store.Store, senders SenderSet, pc config.PushConfig, now time.Time) []PushResult {
	loc, err := time.LoadLocation(pc.Timezone)
	if err != nil || pc.Timezone == "" {
		loc = time.Local
	}
	dateKey := now.In(loc).Format("2006-01-02")

	// 推送暂按默认用户聚合，多用户推送见后续计划
	due, err := st.ListDueReviews(now, 50, store.DefaultUser)
	if err != nil {
		log.Printf("推送获取待复习列表失败: %v", err)
	}
	// 推送暂按默认用户聚合，多用户推送见后续计划
	stats, err := st.ReviewStats(now, store.DefaultUser)
	if err != nil {
		log.Printf("推送获取复习统计失败: %v", err)
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
		if st.HasPushed(dateKey, name) {
			results = append(results, PushResult{Channel: name, Status: "skipped", Detail: "今日已推送"})
			continue
		}

		msg := notify.BuildDigestMessage(now, items, digestStats, pc.MailTo)
		sendCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
		sendErr := ch.sender.Send(sendCtx, msg)
		cancel()

		if sendErr != nil {
			detail := sendErr.Error()
			if len(detail) > 200 {
				detail = detail[:200]
			}
			if err := st.RecordPush(dateKey, name, "failed", detail); err != nil {
				log.Printf("推送记录写入失败 (%s): %v", name, err)
			}
			results = append(results, PushResult{Channel: name, Status: "failed", Detail: detail})
			continue
		}
		if err := st.RecordPush(dateKey, name, "sent", ""); err != nil {
			log.Printf("推送记录写入失败 (%s): %v", name, err)
		}
		results = append(results, PushResult{Channel: name, Status: "sent", Detail: ""})
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
		log.Printf("推送调度时间解析失败: %v", err)
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
	if s.st.HasPushed(dateKey, "smtp") || s.st.HasPushed(dateKey, "webhook") {
		return
	}
	results := RunPush(context.Background(), s.st, s.senders, s.pc, now)
	for _, r := range results {
		log.Printf("推送 %s: %s %s", r.Channel, r.Status, r.Detail)
	}
}
