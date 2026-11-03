package notify

import (
	"strings"
	"testing"

	"sentinel/internal/store"
)

// fakeSource 内存 SubscriberSource 实现。
type fakeSource struct {
	pages map[int64][]int64
	subs  map[int64][]store.Subscriber
}

func (f fakeSource) ListPageIDsForMonitor(monitorID int64) ([]int64, error) {
	return f.pages[monitorID], nil
}

func (f fakeSource) ListConfirmedSubscribers(pageID int64) ([]store.Subscriber, error) {
	return f.subs[pageID], nil
}

// TestNotifySubscribers_Fanout 扇出与去重。
func TestNotifySubscribers_Fanout(t *testing.T) {
	src := fakeSource{
		pages: map[int64][]int64{1: {10, 11}},
		subs: map[int64][]store.Subscriber{
			10: {
				{Email: "a@x.com", Token: "tk1", PageTitle: "页面十", PageSlug: "ten"},
			},
			11: {
				{Email: "a@x.com", Token: "tk2", PageTitle: "页面十一", PageSlug: "eleven"},
				{Email: "c@x.com", Token: "tk3", PageTitle: "页面十一", PageSlug: "eleven"},
			},
		},
	}
	mm := &MemoryMailer{}
	err := NotifySubscribers(src, mm, "https://status.example.com", 1, "down", "站点A", "https://a.example", "2026-10-16T00:00:00Z", "连接超时")
	if err != nil {
		t.Fatalf("NotifySubscribers 失败: %v", err)
	}

	msgs := mm.Messages()
	if len(msgs) != 2 {
		t.Fatalf("应发送 2 封，实际 %d", len(msgs))
	}

	var aMsg, cMsg *SentMail
	for i := range msgs {
		if len(msgs[i].Recipients) == 1 && msgs[i].Recipients[0] == "a@x.com" {
			aMsg = &msgs[i]
		}
		if len(msgs[i].Recipients) == 1 && msgs[i].Recipients[0] == "c@x.com" {
			cMsg = &msgs[i]
		}
	}
	if aMsg == nil {
		t.Fatalf("未找到 a@x.com 的邮件")
	}
	if cMsg == nil {
		t.Fatalf("未找到 c@x.com 的邮件")
	}
	if !strings.Contains(aMsg.Subject, "宕机") {
		t.Errorf("a 的 subject 应含宕机: %q", aMsg.Subject)
	}
	if !strings.Contains(aMsg.Body, "tk1") {
		t.Errorf("a 的 body 应含首个页面 token tk1: %q", aMsg.Body)
	}
	if !strings.Contains(aMsg.Body, "https://status.example.com/api/status/") {
		t.Errorf("a 的 body 应含退订链接前缀: %q", aMsg.Body)
	}
}

// TestNotifySubscribers_Recovered 恢复事件主题。
func TestNotifySubscribers_Recovered(t *testing.T) {
	src := fakeSource{
		pages: map[int64][]int64{1: {10}},
		subs: map[int64][]store.Subscriber{
			10: {{Email: "a@x.com", Token: "tk1", PageTitle: "页面十", PageSlug: "ten"}},
		},
	}
	mm := &MemoryMailer{}
	if err := NotifySubscribers(src, mm, "https://status.example.com", 1, "recovered", "站点A", "https://a.example", "2026-10-16T00:00:00Z", ""); err != nil {
		t.Fatalf("NotifySubscribers 失败: %v", err)
	}
	msgs := mm.Messages()
	if len(msgs) != 1 {
		t.Fatalf("应发送 1 封，实际 %d", len(msgs))
	}
	if !strings.Contains(msgs[0].Subject, "已恢复") {
		t.Errorf("subject 应含已恢复: %q", msgs[0].Subject)
	}
}

// TestNotifySubscribers_NoSubscribers 无订阅者返回 nil、零发送。
func TestNotifySubscribers_NoSubscribers(t *testing.T) {
	src := fakeSource{
		pages: map[int64][]int64{},
		subs:  map[int64][]store.Subscriber{},
	}
	mm := &MemoryMailer{}
	if err := NotifySubscribers(src, mm, "", 99, "down", "站点A", "https://a.example", "2026-10-16T00:00:00Z", ""); err != nil {
		t.Fatalf("NotifySubscribers 失败: %v", err)
	}
	if len(mm.Messages()) != 0 {
		t.Fatalf("应发送 0 封，实际 %d", len(mm.Messages()))
	}
}
