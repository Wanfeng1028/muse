package notify

import (
	"strings"
	"testing"
)

func TestParseChannels_SMS(t *testing.T) {
	got := ParseChannels("sms,wecom")
	if len(got) != 2 || got[0] != "sms" || got[1] != "wecom" {
		t.Fatalf("ParseChannels(\"sms,wecom\") = %v，期望 [sms wecom]", got)
	}
}

func TestNotify_SMS_MockFanout(t *testing.T) {
	mock := &MockSmsSender{}
	n := Notifier{
		SMSSender: mock,
		Channels:  []string{"sms"},
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
	}
	errs := n.Notify(Target{NotifyChannels: "sms"}, "down", "web", "https://x", "2026-10-16T00:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("errs 期望为空，实际 %v", errs)
	}
	msgs := mock.Messages()
	if len(msgs) != 1 {
		t.Fatalf("Messages 长度 = %d，期望 1", len(msgs))
	}
	if !strings.Contains(msgs[0].Message, "【sentinel 告警】") {
		t.Fatalf("消息应含“【sentinel 告警】”，实际 %q", msgs[0].Message)
	}
}

func TestNotify_SMS_TargetPhonesOverride(t *testing.T) {
	mock := &MockSmsSender{}
	n := Notifier{
		SMSSender: mock,
		Channels:  []string{"sms"},
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
	}
	errs := n.Notify(Target{NotifyChannels: "sms", SMSPhones: "13900139000"}, "down", "web", "https://x", "2026-10-16T00:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("errs 期望为空，实际 %v", errs)
	}
	msgs := mock.Messages()
	if len(msgs) != 1 {
		t.Fatalf("Messages 长度 = %d，期望 1", len(msgs))
	}
	if msgs[0].Phone != "13900139000" {
		t.Fatalf("Phone = %q，期望 13900139000（目标级覆盖全局）", msgs[0].Phone)
	}
}

func TestNotify_SMS_NoPhones(t *testing.T) {
	mock := &MockSmsSender{}
	n := Notifier{
		SMSSender: mock,
		Channels:  []string{"sms"},
	}
	errs := n.Notify(Target{NotifyChannels: "sms"}, "down", "web", "https://x", "2026-10-16T00:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("errs 期望为空（跳过不算错），实际 %v", errs)
	}
	if len(mock.Messages()) != 0 {
		t.Fatalf("Messages 长度 = %d，期望 0", len(mock.Messages()))
	}
}

func TestNotify_SMS_SenderNil(t *testing.T) {
	n := Notifier{
		Channels: []string{"sms"},
		SMS:      SMSConfig{Phones: []string{"13800138000"}},
	}
	errs := n.Notify(Target{NotifyChannels: "sms"}, "down", "web", "https://x", "2026-10-16T00:00:00Z", "boom")
	if len(errs) == 0 {
		t.Fatalf("errs 期望非空，实际 nil")
	}
}

func TestNotify_SMS_InvalidPhone(t *testing.T) {
	mock := &MockSmsSender{}
	n := Notifier{
		SMSSender: mock,
		Channels:  []string{"sms"},
	}
	errs := n.Notify(Target{NotifyChannels: "sms", SMSPhones: "123"}, "down", "web", "https://x", "2026-10-16T00:00:00Z", "boom")
	if len(errs) == 0 {
		t.Fatalf("errs 期望非空，实际 nil")
	}
	found := false
	for _, e := range errs {
		if e != nil && strings.Contains(e.Error(), "号码非法") {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("errs 应含“号码非法”，实际 %v", errs)
	}
}

func TestNotify_SMS_Recovered(t *testing.T) {
	mock := &MockSmsSender{}
	n := Notifier{
		SMSSender: mock,
		Channels:  []string{"sms"},
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
	}
	errs := n.Notify(Target{NotifyChannels: "sms"}, "recovered", "web", "https://x", "2026-10-16T00:00:00Z", "")
	if len(errs) != 0 {
		t.Fatalf("errs 期望为空，实际 %v", errs)
	}
	msgs := mock.Messages()
	if len(msgs) != 1 {
		t.Fatalf("Messages 长度 = %d，期望 1", len(msgs))
	}
	if !strings.Contains(msgs[0].Message, "【sentinel 恢复】") {
		t.Fatalf("消息应含“【sentinel 恢复】”，实际 %q", msgs[0].Message)
	}
}
