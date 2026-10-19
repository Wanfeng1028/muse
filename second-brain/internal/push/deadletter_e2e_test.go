package push

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// 建库 + 一篇今日到期的笔记，供 RunPushForUser 产生推送内容。
func setupDueNote(t *testing.T) (*store.Store, time.Time) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("打开内存库失败: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })

	ctx := context.Background()
	id, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("建笔记失败: %v", err)
	}
	today := time.Now()
	yesterday := today.AddDate(0, 0, -1)
	if _, err := st.RecordReview(ctx, id.ID, 4, yesterday, "local"); err != nil {
		t.Fatalf("记录复习失败: %v", err)
	}
	return st, today
}

// 按通道名建立结果索引，断言时不依赖 channelEntries 的顺序。
func indexResults(results []PushResult) map[string]PushResult {
	m := make(map[string]PushResult, len(results))
	for _, r := range results {
		m[r.Channel] = r
	}
	return m
}

// 全通道重试耗尽 → 每个通道都转死信，当日不再重推，跨天重新尝试。
func TestRunPushForUser_AllChannelsExhaustToDeadLetter(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "2")

	st, now := setupDueNote(t)
	ctx := context.Background()
	dateKey := now.Format("2006-01-02")

	sleeper := &recordingSleeper{}
	policy := RetryPolicy{
		MaxRetries:  2,
		BaseBackoff: time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0,
	}

	// 3 轮运行 × 每轮 3 次尝试，共 9 个可重试错误
	connErrs := func() []error {
		return []error{notify.ErrConn, notify.ErrConn, notify.ErrConn,
			notify.ErrConn, notify.ErrConn, notify.ErrConn,
			notify.ErrConn, notify.ErrConn, notify.ErrConn}
	}
	smtpStub := &stubSender{name: "smtp", errs: connErrs()}
	webhookStub := &stubSender{name: "webhook", errs: connErrs()}
	senders := SenderSet{
		SMTP:    WrapWithRetrySleeper(smtpStub, policy, sleeper.sleep),
		Webhook: WrapWithRetrySleeper(webhookStub, policy, sleeper.sleep),
	}

	results := RunPushForUser(ctx, st, senders, config.PushConfig{}, now, "local")
	byChannel := indexResults(results)

	smtpRes, ok := byChannel["smtp"]
	if !ok {
		t.Fatalf("结果中缺少 smtp 通道: %+v", results)
	}
	if smtpRes.Status != "failed_permanent" {
		t.Fatalf("smtp 期望 failed_permanent, 实得 %q", smtpRes.Status)
	}
	if !strings.Contains(smtpRes.Detail, "重试耗尽") {
		t.Fatalf("smtp Detail 应含 %q, 实得 %q", "重试耗尽", smtpRes.Detail)
	}

	hookRes, ok := byChannel["webhook"]
	if !ok {
		t.Fatalf("结果中缺少 webhook 通道: %+v", results)
	}
	if hookRes.Status != "failed_permanent" {
		t.Fatalf("webhook 期望 failed_permanent, 实得 %q", hookRes.Status)
	}
	if !strings.Contains(hookRes.Detail, "重试耗尽") {
		t.Fatalf("webhook Detail 应含 %q, 实得 %q", "重试耗尽", hookRes.Detail)
	}

	if got, ok := st.PushLogStatus(dateKey, "smtp", "local"); !ok || got != "failed_permanent" {
		t.Fatalf("PushLogStatus(smtp) 期望 failed_permanent/true, 实得 %q/%v", got, ok)
	}
	if got, ok := st.PushLogStatus(dateKey, "webhook", "local"); !ok || got != "failed_permanent" {
		t.Fatalf("PushLogStatus(webhook) 期望 failed_permanent/true, 实得 %q/%v", got, ok)
	}

	if smtpStub.calls != 3 {
		t.Fatalf("smtp 期望调用 3 次(1+2 重试), 实得 %d", smtpStub.calls)
	}
	if webhookStub.calls != 3 {
		t.Fatalf("webhook 期望调用 3 次(1+2 重试), 实得 %d", webhookStub.calls)
	}

	// 同一天再次运行：HasPushedFor 只统计 sent，失败通道同日会重尝试 →
	// 再次 failed_permanent；RecordDeadLetter 幂等，不产生重复行。
	results2 := RunPushForUser(ctx, st, senders, config.PushConfig{}, now, "local")
	byChannel2 := indexResults(results2)
	if got := byChannel2["smtp"].Status; got != "failed_permanent" {
		t.Fatalf("同日重跑 smtp 期望 failed_permanent, 实得 %q", got)
	}
	if got := byChannel2["webhook"].Status; got != "failed_permanent" {
		t.Fatalf("同日重跑 webhook 期望 failed_permanent, 实得 %q", got)
	}
	if smtpStub.calls != 6 {
		t.Fatalf("同日重跑后 smtp 调用数应为 6, 实得 %d", smtpStub.calls)
	}
	if webhookStub.calls != 6 {
		t.Fatalf("同日重跑后 webhook 调用数应为 6, 实得 %d", webhookStub.calls)
	}
	// RecordDeadLetter 幂等：同日重跑后状态仍为 failed_permanent（行被 upsert 而非新增，
	// 细粒度行数断言见 retry 包内 RecordDeadLetter 单元测试）。

	// 新的一天：新 dateKey，重新尝试 → 再次 failed_permanent（死信按天隔离）。
	tomorrow := now.AddDate(0, 0, 1)
	results3 := RunPushForUser(ctx, st, senders, config.PushConfig{}, tomorrow, "local")
	byChannel3 := indexResults(results3)
	if got := byChannel3["smtp"].Status; got != "failed_permanent" {
		t.Fatalf("次日 smtp 期望 failed_permanent, 实得 %q", got)
	}
	if got := byChannel3["webhook"].Status; got != "failed_permanent" {
		t.Fatalf("次日 webhook 期望 failed_permanent, 实得 %q", got)
	}
	if smtpStub.calls != 9 {
		t.Fatalf("次日重试后 smtp 调用数应为 9, 实得 %d", smtpStub.calls)
	}
	if webhookStub.calls != 9 {
		t.Fatalf("次日重试后 webhook 调用数应为 9, 实得 %d", webhookStub.calls)
	}
}

// 不可重试错误 → 一次调用即转死信，不进入重试休眠。
func TestRunPushForUser_NonRetryableGoesDeadLetterImmediately(t *testing.T) {
	t.Setenv("SB_PUSH_MAX_RETRIES", "2")

	st, now := setupDueNote(t)
	ctx := context.Background()
	dateKey := now.Format("2006-01-02")

	sleeper := &recordingSleeper{}
	policy := RetryPolicy{
		MaxRetries:  2,
		BaseBackoff: time.Millisecond,
		MaxBackoff:  time.Second,
		JitterRatio: 0,
	}

	smtpStub := &stubSender{
		name: "smtp",
		errs: []error{notify.ErrAuth},
	}
	senders := SenderSet{
		SMTP: WrapWithRetrySleeper(smtpStub, policy, sleeper.sleep),
	}

	results := RunPushForUser(ctx, st, senders, config.PushConfig{}, now, "local")
	byChannel := indexResults(results)

	smtpRes, ok := byChannel["smtp"]
	if !ok {
		t.Fatalf("结果中缺少 smtp 通道: %+v", results)
	}
	if smtpRes.Status != "failed_permanent" {
		t.Fatalf("smtp 期望 failed_permanent, 实得 %q", smtpRes.Status)
	}
	if smtpStub.calls != 1 {
		t.Fatalf("不可重试错误应只调用 1 次, 实得 %d", smtpStub.calls)
	}
	if len(sleeper.durations) != 0 {
		t.Fatalf("不可重试错误不应触发休眠, 实得 %v", sleeper.durations)
	}
	if got, ok := st.PushLogStatus(dateKey, "smtp", "local"); !ok || got != "failed_permanent" {
		t.Fatalf("PushLogStatus(smtp) 期望 failed_permanent/true, 实得 %q/%v", got, ok)
	}
}
