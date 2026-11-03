package notify

import (
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"

	"sentinel/internal/store"
)

type stubSource struct {
	pageIDs     []int64
	pageIDsErr  error
	subsByPage  map[int64][]store.Subscriber
	subsErrByPg map[int64]error
}

func (s *stubSource) ListPageIDsForMonitor(monitorID int64) ([]int64, error) {
	if s.pageIDsErr != nil {
		return nil, s.pageIDsErr
	}
	out := make([]int64, len(s.pageIDs))
	copy(out, s.pageIDs)
	return out, nil
}

func (s *stubSource) ListConfirmedSubscribers(pageID int64) ([]store.Subscriber, error) {
	if s.subsErrByPg != nil {
		if err, ok := s.subsErrByPg[pageID]; ok && err != nil {
			return nil, err
		}
	}
	subs := s.subsByPage[pageID]
	out := make([]store.Subscriber, len(subs))
	copy(out, subs)
	return out, nil
}

type failingMailer struct {
	mu      sync.Mutex
	failOn  map[string]error
	attempt []string
}

func (m *failingMailer) SendMail(recipients []string, subject, body string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, r := range recipients {
		m.attempt = append(m.attempt, r)
		if m.failOn != nil {
			if err, ok := m.failOn[r]; ok && err != nil {
				return err
			}
		}
	}
	return nil
}

func (m *failingMailer) attempts() []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]string, len(m.attempt))
	copy(out, m.attempt)
	return out
}

func makeSub(_ int64, email, slug, title, token string) store.Subscriber {
	return store.Subscriber{
		Email:     email,
		PageSlug:  slug,
		PageTitle: title,
		Token:     token,
	}
}

func TestBuildSubscriberSubject_TableDriven(t *testing.T) {
	cases := []struct {
		name  string
		event string
		mName string
		want  string
	}{
		{"down事件", "down", "api-gateway", "[sentinel] 服务状态通知：api-gateway 宕机"},
		{"recovered事件", "recovered", "订单服务", "[sentinel] 服务状态通知：订单服务 已恢复"},
		{"未知事件透传", "degraded", "cache", "[sentinel] 服务状态通知：cache degraded"},
		{"空名称", "down", "", "[sentinel] 服务状态通知： 宕机"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := BuildSubscriberSubject(tc.event, tc.mName)
			if got != tc.want {
				t.Fatalf("主题不匹配: got=%q want=%q", got, tc.want)
			}
			if !strings.HasPrefix(got, "[sentinel]") {
				t.Fatalf("主题缺少前缀: %q", got)
			}
		})
	}
}

func TestBuildSubscriberBody_TableDriven(t *testing.T) {
	cases := []struct {
		name       string
		pageTitle  string
		event      string
		mName      string
		target     string
		at         string
		errMsg     string
		unsubURL   string
		wantSubs   []string
		wantAbsent []string
	}{
		{
			name:      "down带错误信息",
			pageTitle: "主站状态",
			event:     "down",
			mName:     "支付服务",
			target:    "https://pay.example.com/health",
			at:        "2024-05-01 10:00:00",
			errMsg:    "connection refused",
			unsubURL:  "https://status.example.com/api/status/main/unsubscribe?token=abc",
			wantSubs: []string{
				"您订阅的状态页「主站状态」有服务状态变化：",
				"监控名称: 支付服务",
				"目标: https://pay.example.com/health",
				"时间: 2024-05-01 10:00:00",
				"事件: 宕机",
				"错误信息: connection refused",
				"退订本状态页通知：https://status.example.com/api/status/main/unsubscribe?token=abc",
			},
			wantAbsent: []string{"事件: 已恢复"},
		},
		{
			name:      "recovered无错误信息",
			pageTitle: "主站状态",
			event:     "recovered",
			mName:     "支付服务",
			target:    "https://pay.example.com/health",
			at:        "2024-05-01 11:00:00",
			errMsg:    "",
			unsubURL:  "/api/status/main/unsubscribe?token=abc",
			wantSubs: []string{
				"事件: 已恢复",
				"退订本状态页通知：/api/status/main/unsubscribe?token=abc",
			},
			wantAbsent: []string{"事件: 宕机", "错误信息:"},
		},
		{
			name:      "未知事件原样输出",
			pageTitle: "主站状态",
			event:     "degraded",
			mName:     "支付服务",
			target:    "https://pay.example.com/health",
			at:        "2024-05-01 12:00:00",
			errMsg:    "should-not-appear",
			unsubURL:  "/unsub",
			wantSubs: []string{
				"事件: degraded",
				"退订本状态页通知：/unsub",
			},
			wantAbsent: []string{"事件: 宕机", "事件: 已恢复", "错误信息:"},
		},
		{
			name:      "空标题空目标",
			pageTitle: "",
			event:     "down",
			mName:     "",
			target:    "",
			at:        "",
			errMsg:    "",
			unsubURL:  "",
			wantSubs: []string{
				"您订阅的状态页「」有服务状态变化：",
				"监控名称: \r\n",
				"目标: \r\n",
				"事件: 宕机",
				"退订本状态页通知：\r\n",
			},
			wantAbsent: []string{"错误信息:"},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := BuildSubscriberBody(tc.pageTitle, tc.event, tc.mName, tc.target, tc.at, tc.errMsg, tc.unsubURL)
			for _, w := range tc.wantSubs {
				if !strings.Contains(got, w) {
					t.Fatalf("正文缺少片段 %q，实际正文:\n%s", w, got)
				}
			}
			for _, a := range tc.wantAbsent {
				if strings.Contains(got, a) {
					t.Fatalf("正文不应包含片段 %q，实际正文:\n%s", a, got)
				}
			}
			if !strings.Contains(got, "\r\n") {
				t.Fatalf("正文应使用 CRLF 换行，实际:\n%s", got)
			}
		})
	}
}

func TestNotifySubscribers_ListPageIDsError(t *testing.T) {
	src := &stubSource{pageIDsErr: errors.New("db connection lost")}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "")
	if err == nil {
		t.Fatal("期望返回错误，实际为 nil")
	}
	if !strings.Contains(err.Error(), "查询状态页失败") {
		t.Fatalf("错误信息应包含包装前缀，实际: %v", err)
	}
	if !strings.Contains(err.Error(), "db connection lost") {
		t.Fatalf("错误信息应包含底层原因，实际: %v", err)
	}
	if got := len(mailer.Messages()); got != 0 {
		t.Fatalf("查询失败时不应发送邮件，实际发送 %d 封", got)
	}
}

func TestNotifySubscribers_EmptyPageIDs(t *testing.T) {
	src := &stubSource{pageIDs: []int64{}}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "")
	if err != nil {
		t.Fatalf("空页面列表不应返回错误，实际: %v", err)
	}
	if got := len(mailer.Messages()); got != 0 {
		t.Fatalf("空页面列表不应发送邮件，实际发送 %d 封", got)
	}
}

func TestNotifySubscribers_SubscriberQueryErrorContinues(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10, 20},
		subsByPage: map[int64][]store.Subscriber{
			10: {makeSub(1, "a@example.com", "page-a", "页面A", "tok-a")},
			20: {makeSub(2, "b@example.com", "page-b", "页面B", "tok-b")},
		},
		subsErrByPg: map[int64]error{
			10: errors.New("query timeout"),
		},
	}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "boom")
	if err != nil {
		t.Fatalf("单个页面查询失败应继续，不应返回错误，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 1 {
		t.Fatalf("应只发送 1 封邮件（页面20），实际 %d 封", len(msgs))
	}
	if msgs[0].Recipients[0] != "b@example.com" {
		t.Fatalf("应发给页面20的订阅者，实际收件人: %v", msgs[0].Recipients)
	}
	if !strings.Contains(msgs[0].Body, "页面B") {
		t.Fatalf("正文应使用页面20的标题，实际: %s", msgs[0].Body)
	}
}

func TestNotifySubscribers_DedupAcrossPages(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10, 20, 30},
		subsByPage: map[int64][]store.Subscriber{
			10: {makeSub(1, "  DUP@Example.COM  ", "page-a", "页面A", "tok-a")},
			20: {makeSub(2, "dup@example.com", "page-b", "页面B", "tok-b")},
			30: {
				makeSub(3, "dup@example.com", "page-c", "页面C", "tok-c"),
				makeSub(4, "other@example.com", "page-c", "页面C", "tok-d"),
			},
		},
	}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "recovered", "api", "http://api/health", "2024-05-01 10:00:00", "")
	if err != nil {
		t.Fatalf("正常流程不应返回错误，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 2 {
		t.Fatalf("同一邮箱应只收一封，共 2 个唯一邮箱，实际 %d 封", len(msgs))
	}
	firstBody := msgs[0].Body
	if !strings.Contains(firstBody, "页面A") {
		t.Fatalf("去重后应取首个页面标题（页面A），实际正文: %s", firstBody)
	}
	if msgs[0].Recipients[0] != "  DUP@Example.COM  " {
		t.Fatalf("发送应使用原始邮箱（保留大小写与空白），实际: %q", msgs[0].Recipients[0])
	}
	if msgs[1].Recipients[0] != "other@example.com" {
		t.Fatalf("第二个唯一邮箱应为 other@example.com，实际: %q", msgs[1].Recipients[0])
	}
}

func TestNotifySubscribers_EmptyEmailSkipped(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {
				makeSub(1, "", "page-a", "页面A", "tok-a"),
				makeSub(2, "   ", "page-a", "页面A", "tok-b"),
				makeSub(3, "real@example.com", "page-a", "页面A", "tok-c"),
			},
		},
	}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "")
	if err != nil {
		t.Fatalf("空邮箱应被跳过而非报错，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 1 {
		t.Fatalf("空邮箱应被跳过，只应发送 1 封，实际 %d 封", len(msgs))
	}
	if msgs[0].Recipients[0] != "real@example.com" {
		t.Fatalf("应只发给真实邮箱，实际: %q", msgs[0].Recipients[0])
	}
	if !strings.Contains(msgs[0].Body, "退订本状态页通知：/api/status/page-a/unsubscribe?token=tok-c") {
		t.Fatalf("空 baseURL 应使用相对路径退订链接，实际正文: %s", msgs[0].Body)
	}
}

func TestNotifySubscribers_PublicBaseURLJoin(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {makeSub(1, "user@example.com", "slug-x", "页面X", "tok-x")},
		},
	}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "")
	if err != nil {
		t.Fatalf("正常流程不应返回错误，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 1 {
		t.Fatalf("应发送 1 封邮件，实际 %d 封", len(msgs))
	}
	want := "退订本状态页通知：https://status.example.com/api/status/slug-x/unsubscribe?token=tok-x"
	if !strings.Contains(msgs[0].Body, want) {
		t.Fatalf("退订链接拼接不正确，want 包含 %q，实际正文:\n%s", want, msgs[0].Body)
	}
	if msgs[0].Subject != "[sentinel] 服务状态通知：api 宕机" {
		t.Fatalf("主题不正确，实际: %q", msgs[0].Subject)
	}
}

func TestNotifySubscribers_SendFailureContinues(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {
				makeSub(1, "bad@example.com", "page-a", "页面A", "tok-a"),
				makeSub(2, "good@example.com", "page-a", "页面A", "tok-b"),
			},
		},
	}
	mailer := &failingMailer{
		failOn: map[string]error{
			"bad@example.com": errors.New("smtp: 550 mailbox unavailable"),
		},
	}

	err := NotifySubscribers(src, mailer, "", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "")
	if err != nil {
		t.Fatalf("单个发送失败应记日志并继续，不应返回错误，实际: %v", err)
	}
	attempts := mailer.attempts()
	if len(attempts) != 2 {
		t.Fatalf("两个订阅者都应尝试发送，实际尝试 %d 次: %v", len(attempts), attempts)
	}
	if attempts[0] != "bad@example.com" || attempts[1] != "good@example.com" {
		t.Fatalf("发送顺序应与订阅者顺序一致，实际: %v", attempts)
	}
}

func TestNotifySubscribers_MultiplePagesAllDelivered(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10, 20},
		subsByPage: map[int64][]store.Subscriber{
			10: {
				makeSub(1, "a@example.com", "page-a", "页面A", "tok-a"),
				makeSub(2, "b@example.com", "page-a", "页面A", "tok-b"),
			},
			20: {
				makeSub(3, "c@example.com", "page-b", "页面B", "tok-c"),
			},
		},
	}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "timeout")
	if err != nil {
		t.Fatalf("正常流程不应返回错误，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 3 {
		t.Fatalf("三个不同邮箱都应收到邮件，实际 %d 封", len(msgs))
	}
	byRecipient := map[string]SentMail{}
	for _, m := range msgs {
		byRecipient[m.Recipients[0]] = m
	}
	for _, email := range []string{"a@example.com", "b@example.com", "c@example.com"} {
		if _, ok := byRecipient[email]; !ok {
			t.Fatalf("收件人 %s 未收到邮件，实际收件人集合: %v", email, byRecipient)
		}
	}
	if !strings.Contains(byRecipient["a@example.com"].Body, "页面A") {
		t.Fatalf("a@example.com 应使用页面A标题，实际: %s", byRecipient["a@example.com"].Body)
	}
	if !strings.Contains(byRecipient["c@example.com"].Body, "页面B") {
		t.Fatalf("c@example.com 应使用页面B标题，实际: %s", byRecipient["c@example.com"].Body)
	}
}

func TestNotifySubscribers_LongFields(t *testing.T) {
	longName := strings.Repeat("名", 500)
	longTarget := "https://example.com/" + strings.Repeat("p", 2000)
	longErr := strings.Repeat("e", 3000)
	longToken := strings.Repeat("t", 400)
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {makeSub(1, "long@example.com", "page-long", "长页面", longToken)},
		},
	}
	mailer := &MemoryMailer{}

	err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", longName, longTarget, "2024-05-01 10:00:00", longErr)
	if err != nil {
		t.Fatalf("超长字段不应导致错误，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 1 {
		t.Fatalf("应发送 1 封邮件，实际 %d 封", len(msgs))
	}
	body := msgs[0].Body
	if !strings.Contains(body, "监控名称: "+longName) {
		t.Fatalf("正文应包含完整超长名称，实际长度 %d", len(body))
	}
	if !strings.Contains(body, "目标: "+longTarget) {
		t.Fatalf("正文应包含完整超长目标")
	}
	if !strings.Contains(body, "错误信息: "+longErr) {
		t.Fatalf("正文应包含完整超长错误信息")
	}
	wantUnsub := "退订本状态页通知：https://status.example.com/api/status/page-long/unsubscribe?token=" + longToken
	if !strings.Contains(body, wantUnsub) {
		t.Fatalf("正文应包含完整超长退订链接")
	}
}

func TestNotifySubscribers_ConcurrentSafe(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {
				makeSub(1, "u1@example.com", "page-a", "页面A", "tok-1"),
				makeSub(2, "u2@example.com", "page-a", "页面A", "tok-2"),
				makeSub(3, "u3@example.com", "page-a", "页面A", "tok-3"),
			},
		},
	}
	mailer := &MemoryMailer{}

	const goroutines = 20
	var wg sync.WaitGroup
	errs := make([]error, goroutines)
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			errs[idx] = NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", "")
		}(i)
	}
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("goroutine %d 返回错误: %v", i, err)
		}
	}
	msgs := mailer.Messages()
	if len(msgs) != goroutines*3 {
		t.Fatalf("并发发送总数应为 %d，实际 %d", goroutines*3, len(msgs))
	}
	countByRecipient := map[string]int{}
	for _, m := range msgs {
		countByRecipient[m.Recipients[0]]++
	}
	for _, email := range []string{"u1@example.com", "u2@example.com", "u3@example.com"} {
		if countByRecipient[email] != goroutines {
			t.Fatalf("收件人 %s 应收到 %d 封，实际 %d 封", email, goroutines, countByRecipient[email])
		}
	}
}

func TestNotifySubscribers_IdempotentSingleRun(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {makeSub(1, "idem@example.com", "page-a", "页面A", "tok-a")},
		},
	}
	mailer := &MemoryMailer{}

	if err := NotifySubscribers(src, mailer, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", ""); err != nil {
		t.Fatalf("第一次调用失败: %v", err)
	}
	first := mailer.Messages()
	if len(first) != 1 {
		t.Fatalf("第一次调用应发送 1 封，实际 %d 封", len(first))
	}

	mailer2 := &MemoryMailer{}
	if err := NotifySubscribers(src, mailer2, "https://status.example.com", 1, "down", "api", "http://api/health", "2024-05-01 10:00:00", ""); err != nil {
		t.Fatalf("第二次调用失败: %v", err)
	}
	second := mailer2.Messages()
	if len(second) != 1 {
		t.Fatalf("第二次调用应发送 1 封，实际 %d 封", len(second))
	}

	if first[0].Subject != second[0].Subject {
		t.Fatalf("两次调用主题应一致: %q vs %q", first[0].Subject, second[0].Subject)
	}
	if first[0].Body != second[0].Body {
		t.Fatalf("两次调用正文应一致:\n第一次:\n%s\n第二次:\n%s", first[0].Body, second[0].Body)
	}
	if first[0].Recipients[0] != second[0].Recipients[0] {
		t.Fatalf("两次调用收件人应一致: %v vs %v", first[0].Recipients, second[0].Recipients)
	}
}

func TestNotifySubscribers_InvalidURLFieldsPassThrough(t *testing.T) {
	src := &stubSource{
		pageIDs: []int64{10},
		subsByPage: map[int64][]store.Subscriber{
			10: {makeSub(1, "url@example.com", "page-a", "页面A", "tok-a")},
		},
	}
	mailer := &MemoryMailer{}

	invalidTarget := "http://[::1]:namedport/health"
	err := NotifySubscribers(src, mailer, "not-a-valid-base-url", 1, "down", "api", invalidTarget, "2024-05-01 10:00:00", "")
	if err != nil {
		t.Fatalf("非法 URL 字段应原样透传不报错，实际: %v", err)
	}
	msgs := mailer.Messages()
	if len(msgs) != 1 {
		t.Fatalf("应发送 1 封邮件，实际 %d 封", len(msgs))
	}
	if !strings.Contains(msgs[0].Body, "目标: "+invalidTarget) {
		t.Fatalf("非法目标 URL 应原样写入正文，实际正文:\n%s", msgs[0].Body)
	}
	wantUnsub := "退订本状态页通知：not-a-valid-base-url/api/status/page-a/unsubscribe?token=tok-a"
	if !strings.Contains(msgs[0].Body, wantUnsub) {
		t.Fatalf("非空 baseURL 应直接拼接，want 包含 %q，实际正文:\n%s", wantUnsub, msgs[0].Body)
	}
	if !strings.Contains(msgs[0].Subject, fmt.Sprintf("%s 宕机", "api")) {
		t.Fatalf("主题应包含监控名与事件，实际: %q", msgs[0].Subject)
	}
}