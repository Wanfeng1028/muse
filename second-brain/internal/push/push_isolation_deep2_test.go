package push

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

type captureSender struct {
	name string
	msgs []notify.Message
	err  error
}

func (c *captureSender) Name() string { return c.name }
func (c *captureSender) Send(ctx context.Context, msg notify.Message) error {
	c.msgs = append(c.msgs, msg)
	return c.err
}

func TestWithRetry_MaxRetriesZero_OneAttempt(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 0, BaseBackoff: time.Millisecond, MaxBackoff: time.Second}
	attempts := 0
	sleeps := 0
	attemptFn := func() error {
		attempts++
		return notify.ErrConn
	}
	sleep := func(ctx context.Context, d time.Duration) error {
		sleeps++
		return nil
	}
	err := withRetry(context.Background(), policy, sleep, "smtp", attemptFn)
	var rex *RetryExhaustedError
	if !errors.As(err, &rex) {
		t.Fatalf("期望 *RetryExhaustedError，实际 %v", err)
	}
	if rex.Attempts != 1 {
		t.Fatalf("Attempts 期望 1，实际 %d", rex.Attempts)
	}
	if rex.Immediate {
		t.Fatalf("Immediate 期望 false，实际 true")
	}
	if attempts != 1 {
		t.Fatalf("attemptFn 调用次数期望 1，实际 %d", attempts)
	}
	if sleeps != 0 {
		t.Fatalf("sleep 调用次数期望 0，实际 %d", sleeps)
	}
}

func TestWithRetry_MaxRetriesTwo_ThreeAttempts(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 2, BaseBackoff: time.Millisecond, MaxBackoff: time.Second}
	attempts := 0
	sleeps := 0
	attemptFn := func() error {
		attempts++
		return notify.ErrConn
	}
	sleep := func(ctx context.Context, d time.Duration) error {
		sleeps++
		return nil
	}
	err := withRetry(context.Background(), policy, sleep, "smtp", attemptFn)
	var rex *RetryExhaustedError
	if !errors.As(err, &rex) {
		t.Fatalf("期望 *RetryExhaustedError，实际 %v", err)
	}
	if rex.Attempts != 3 {
		t.Fatalf("Attempts 期望 3，实际 %d", rex.Attempts)
	}
	if rex.Immediate {
		t.Fatalf("Immediate 期望 false，实际 true")
	}
	if attempts != 3 {
		t.Fatalf("attemptFn 调用次数期望 3，实际 %d", attempts)
	}
	if sleeps != 2 {
		t.Fatalf("sleep 调用次数期望 2，实际 %d", sleeps)
	}
}

func TestWithRetry_NonRetryable_Immediate(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 3, BaseBackoff: time.Millisecond, MaxBackoff: time.Second}
	attempts := 0
	sleeps := 0
	attemptFn := func() error {
		attempts++
		return notify.ErrAuth
	}
	sleep := func(ctx context.Context, d time.Duration) error {
		sleeps++
		return nil
	}
	err := withRetry(context.Background(), policy, sleep, "smtp", attemptFn)
	var rex *RetryExhaustedError
	if !errors.As(err, &rex) {
		t.Fatalf("期望 *RetryExhaustedError，实际 %v", err)
	}
	if !rex.Immediate {
		t.Fatalf("Immediate 期望 true，实际 false")
	}
	if rex.Attempts != 1 {
		t.Fatalf("Attempts 期望 1，实际 %d", rex.Attempts)
	}
	if attempts != 1 {
		t.Fatalf("attemptFn 调用次数期望 1，实际 %d", attempts)
	}
	if sleeps != 0 {
		t.Fatalf("sleep 调用次数期望 0，实际 %d", sleeps)
	}
}

func TestWithRetry_CtxAlreadyCanceled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	policy := RetryPolicy{MaxRetries: 3, BaseBackoff: time.Millisecond, MaxBackoff: time.Second}
	attempts := 0
	attemptFn := func() error {
		attempts++
		return notify.ErrConn
	}
	sleep := func(ctx context.Context, d time.Duration) error { return nil }
	err := withRetry(ctx, policy, sleep, "smtp", attemptFn)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("期望 context.Canceled，实际 %v", err)
	}
	if attempts != 0 {
		t.Fatalf("attemptFn 调用次数期望 0，实际 %d", attempts)
	}
}

var errSleepBoom = errors.New("sleep boom")

func TestWithRetry_SleepError_StopsImmediately(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 3, BaseBackoff: time.Millisecond, MaxBackoff: time.Second}
	attempts := 0
	attemptFn := func() error {
		attempts++
		return notify.ErrConn
	}
	sleep := func(ctx context.Context, d time.Duration) error {
		return errSleepBoom
	}
	err := withRetry(context.Background(), policy, sleep, "smtp", attemptFn)
	if !errors.Is(err, errSleepBoom) {
		t.Fatalf("期望 errSleepBoom，实际 %v", err)
	}
	if attempts != 1 {
		t.Fatalf("attemptFn 调用次数期望 1，实际 %d", attempts)
	}
}

func TestRecordDeadLetter_Idempotent_KeepsFirstDetail(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	_ = ctx
	if err := RecordDeadLetter(st, "2025-01-02", "smtp", "alice", errors.New("第一次boom")); err != nil {
		t.Fatalf("第一次 RecordDeadLetter 期望 nil，实际 %v", err)
	}
	if err := RecordDeadLetter(st, "2025-01-02", "smtp", "alice", errors.New("第二次不同错误")); err != nil {
		t.Fatalf("第二次 RecordDeadLetter 期望 nil，实际 %v", err)
	}
	status, ok := st.PushLogStatus("2025-01-02", "smtp", "alice")
	if !ok {
		t.Fatalf("PushLogStatus 期望存在")
	}
	if status != "failed_permanent" {
		t.Fatalf("status 期望 failed_permanent，实际 %q", status)
	}
	logs, err := st.ListPushLogFor(10, "alice")
	if err != nil {
		t.Fatalf("ListPushLogFor 错误: %v", err)
	}
	var detail string
	found := false
	for _, l := range logs {
		if l.Channel == "smtp" && l.Date == "2025-01-02" {
			detail = l.Detail
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("未找到 smtp 2025-01-02 记录")
	}
	if !strings.Contains(detail, "第一次boom") {
		t.Fatalf("detail 期望含 第一次boom，实际 %q", detail)
	}
	if strings.Contains(detail, "第二次") {
		t.Fatalf("detail 不应含 第二次，实际 %q", detail)
	}
}

func TestRecordDeadLetter_NilStore(t *testing.T) {
	err := RecordDeadLetter(nil, "2025-01-02", "smtp", "alice", errors.New("boom"))
	if err == nil {
		t.Fatalf("nil store 期望返回非 nil error")
	}
}

func TestRecordDeadLetter_DetailTruncated200Runes(t *testing.T) {
	st := newTestStore(t)
	big := strings.Repeat("中", 300)
	err := RecordDeadLetter(st, "2025-01-02", "smtp", "alice", errors.New(big))
	if err != nil {
		t.Fatalf("RecordDeadLetter 期望 nil，实际 %v", err)
	}
	logs, lerr := st.ListPushLogFor(10, "alice")
	if lerr != nil {
		t.Fatalf("ListPushLogFor 错误: %v", lerr)
	}
	var detail string
	found := false
	for _, l := range logs {
		if l.Channel == "smtp" && l.Date == "2025-01-02" {
			detail = l.Detail
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("未找到记录")
	}
	if !strings.HasPrefix(detail, "重试耗尽: ") {
		t.Fatalf("detail 期望以 重试耗尽: 开头，实际 %q", detail)
	}
	if utf8.RuneCountInString(detail) > 200 {
		t.Fatalf("detail rune 数期望 ≤200，实际 %d", utf8.RuneCountInString(detail))
	}
}

func TestRunPushForUser_MultiUserIsolation(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	now := time.Date(2025, 1, 2, 9, 0, 0, 0, time.UTC)
	past := now.AddDate(0, 0, -2)

	an, err := st.CreateNoteFor(ctx, store.Note{Title: "alice-笔记A", Body: "body"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor alice 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, an.ID, 0, past, "alice"); err != nil {
		t.Fatalf("RecordReview alice 错误: %v", err)
	}
	bn, err := st.CreateNoteFor(ctx, store.Note{Title: "bob-笔记B", Body: "body"}, "bob")
	if err != nil {
		t.Fatalf("CreateNoteFor bob 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, bn.ID, 0, past, "bob"); err != nil {
		t.Fatalf("RecordReview bob 错误: %v", err)
	}

	senders := SenderSet{
		SMTP:    &fakeSender{name: "smtp"},
		Webhook: &fakeSender{name: "webhook"},
	}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}

	results := RunPushForUser(ctx, st, senders, pc, now, "alice")
	if len(results) != 2 {
		t.Fatalf("结果数期望 2，实际 %d", len(results))
	}
	for _, r := range results {
		if r.User != "alice" {
			t.Fatalf("User 期望 alice，实际 %q", r.User)
		}
		if r.Status != "sent" {
			t.Fatalf("Status 期望 sent，实际 %q", r.Status)
		}
	}
	dateKey := now.Format("2006-01-02")
	if !st.HasPushedFor(dateKey, "smtp", "alice") {
		t.Fatalf("alice smtp 应已推送")
	}
	if st.HasPushedFor(dateKey, "smtp", "bob") {
		t.Fatalf("bob smtp 不应被推送")
	}
}

func TestRunPushForUser_DigestItemsOnlyOwnNotes(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	now := time.Date(2025, 1, 2, 9, 0, 0, 0, time.UTC)
	past := now.AddDate(0, 0, -2)

	an, err := st.CreateNoteFor(ctx, store.Note{Title: "alice-笔记A", Body: "body"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor alice 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, an.ID, 0, past, "alice"); err != nil {
		t.Fatalf("RecordReview alice 错误: %v", err)
	}
	bn, err := st.CreateNoteFor(ctx, store.Note{Title: "bob-笔记B", Body: "body"}, "bob")
	if err != nil {
		t.Fatalf("CreateNoteFor bob 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, bn.ID, 0, past, "bob"); err != nil {
		t.Fatalf("RecordReview bob 错误: %v", err)
	}

	cap := &captureSender{name: "smtp"}
	senders := SenderSet{SMTP: cap}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}

	RunPushForUser(ctx, st, senders, pc, now, "alice")
	if len(cap.msgs) != 1 {
		t.Fatalf("捕获消息数期望 1，实际 %d", len(cap.msgs))
	}
	msg := cap.msgs[0]
	if len(msg.Items) == 0 {
		t.Fatalf("msg.Items 不应为空")
	}
	for _, it := range msg.Items {
		if !strings.Contains(it.Title, "alice-") {
			t.Fatalf("Item.Title 期望含 alice-，实际 %q", it.Title)
		}
		if strings.Contains(it.Title, "bob-") {
			t.Fatalf("Item.Title 不应含 bob-，实际 %q", it.Title)
		}
	}
	if msg.DueCount != len(msg.Items) {
		t.Fatalf("DueCount 期望 %d，实际 %d", len(msg.Items), msg.DueCount)
	}
}

func TestRunPushForUser_ExhaustedGoesDeadLetter_Idempotent(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	now := time.Date(2025, 1, 2, 9, 0, 0, 0, time.UTC)
	past := now.AddDate(0, 0, -2)

	an, err := st.CreateNoteFor(ctx, store.Note{Title: "alice-笔记A", Body: "body"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor alice 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, an.ID, 0, past, "alice"); err != nil {
		t.Fatalf("RecordReview alice 错误: %v", err)
	}

	inner := &fakeSender{name: "smtp", err: errors.New("状态码 503")}
	sender := WrapWithRetrySleeper(inner, RetryPolicy{MaxRetries: 1, BaseBackoff: time.Millisecond, MaxBackoff: time.Millisecond, JitterRatio: 0}, func(ctx context.Context, d time.Duration) error {
		return nil
	})
	senders := SenderSet{SMTP: sender}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}

	results := RunPushForUser(ctx, st, senders, pc, now, "alice")
	if len(results) != 1 {
		t.Fatalf("结果数期望 1，实际 %d", len(results))
	}
	if results[0].Status != "failed_permanent" {
		t.Fatalf("Status 期望 failed_permanent，实际 %q", results[0].Status)
	}
	if !strings.Contains(results[0].Detail, "重试耗尽") {
		t.Fatalf("Detail 期望含 重试耗尽，实际 %q", results[0].Detail)
	}
	dateKey := now.Format("2006-01-02")
	status, ok := st.PushLogStatus(dateKey, "smtp", "alice")
	if !ok {
		t.Fatalf("PushLogStatus 期望存在")
	}
	if status != "failed_permanent" {
		t.Fatalf("status 期望 failed_permanent，实际 %q", status)
	}

	RunPushForUser(ctx, st, senders, pc, now, "alice")
	status2, ok2 := st.PushLogStatus(dateKey, "smtp", "alice")
	if !ok2 {
		t.Fatalf("第二次 PushLogStatus 期望存在")
	}
	if status2 != "failed_permanent" {
		t.Fatalf("第二次 status 期望 failed_permanent，实际 %q", status2)
	}
	logs, lerr := st.ListPushLogFor(10, "alice")
	if lerr != nil {
		t.Fatalf("ListPushLogFor 错误: %v", lerr)
	}
	count := 0
	for _, l := range logs {
		if l.Date == dateKey && l.Channel == "smtp" {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("smtp 记录数期望 1，实际 %d", count)
	}
}

func TestRunPush_MultiUserDispatch(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	now := time.Date(2025, 1, 2, 9, 0, 0, 0, time.UTC)
	past := now.AddDate(0, 0, -2)

	an, err := st.CreateNoteFor(ctx, store.Note{Title: "alice-笔记A", Body: "body"}, "alice")
	if err != nil {
		t.Fatalf("CreateNoteFor alice 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, an.ID, 0, past, "alice"); err != nil {
		t.Fatalf("RecordReview alice 错误: %v", err)
	}
	bn, err := st.CreateNoteFor(ctx, store.Note{Title: "bob-笔记B", Body: "body"}, "bob")
	if err != nil {
		t.Fatalf("CreateNoteFor bob 错误: %v", err)
	}
	if _, err := st.RecordReview(ctx, bn.ID, 0, past, "bob"); err != nil {
		t.Fatalf("RecordReview bob 错误: %v", err)
	}

	senders := SenderSet{SMTP: &fakeSender{name: "smtp"}}
	pc := config.PushConfig{Timezone: "UTC", Time: "08:30"}

	results := RunPush(ctx, st, senders, pc, now)
	aliceSent := 0
	bobSent := 0
	for _, r := range results {
		if r.User == "alice" && r.Status == "sent" {
			aliceSent++
		}
		if r.User == "bob" && r.Status == "sent" {
			bobSent++
		}
	}
	if aliceSent != 1 {
		t.Fatalf("alice sent 数期望 1，实际 %d", aliceSent)
	}
	if bobSent != 1 {
		t.Fatalf("bob sent 数期望 1，实际 %d", bobSent)
	}

	users, err := st.ListUsersWithDueReviews(now)
	if err != nil {
		t.Fatalf("ListUsersWithDueReviews 错误: %v", err)
	}
	hasAlice := false
	hasBob := false
	for _, u := range users {
		if u == "alice" {
			hasAlice = true
		}
		if u == "bob" {
			hasBob = true
		}
	}
	if !hasAlice || !hasBob {
		t.Fatalf("ListUsersWithDueReviews 期望含 alice 和 bob，实际 %v", users)
	}
}
