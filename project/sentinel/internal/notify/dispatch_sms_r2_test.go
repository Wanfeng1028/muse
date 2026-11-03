package notify

import (
	"strings"
	"testing"
)

func hasErrContaining(errs []error, substr string) bool {
	for _, err := range errs {
		if err != nil && strings.Contains(err.Error(), substr) {
			return true
		}
	}
	return false
}

func TestR2_NotifySMSInvalidPhones(t *testing.T) {
	n := Notifier{Channels: []string{"sms"}, SMSSender: &MockSmsSender{}}
	tgt := Target{SMSPhones: "13800138000,abc"}

	errs := n.Notify(tgt, "down", "api", "http://t/", "now", "boom")
	if len(errs) == 0 {
		t.Fatal("expected errors for invalid sms phones, got nil")
	}
	if !hasErrContaining(errs, "sms 渠道号码非法") {
		t.Fatalf("expected error containing %q, got %v", "sms 渠道号码非法", errs)
	}
}

func TestR2_NotifySMSNoSender(t *testing.T) {
	n := Notifier{Channels: []string{"sms"}}
	tgt := Target{SMSPhones: "13800138000"}

	errs := n.Notify(tgt, "down", "api", "http://t/", "now", "boom")
	if len(errs) == 0 {
		t.Fatal("expected errors when sms sender is nil, got nil")
	}
	if !hasErrContaining(errs, "短信发送器未初始化") {
		t.Fatalf("expected error containing %q, got %v", "短信发送器未初始化", errs)
	}
}

func TestR2_NotifySMSSuccess(t *testing.T) {
	sender := &MockSmsSender{}
	n := Notifier{Channels: []string{"sms"}, SMSSender: sender}
	tgt := Target{SMSPhones: "13800138000,+14155552671"}

	errs := n.Notify(tgt, "down", "api", "http://t/", "now", "boom")
	if errs != nil {
		t.Fatalf("expected no errors, got %v", errs)
	}

	msgs := sender.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 sent messages, got %d", len(msgs))
	}
	for i, msg := range msgs {
		if !strings.Contains(msg.Message, "api") {
			t.Fatalf("message %d does not contain monitor name: %q", i, msg.Message)
		}
	}
}

func TestR2_NotifySMSEmptyPhonesSkipped(t *testing.T) {
	n := Notifier{Channels: []string{"sms"}}
	tgt := Target{SMSPhones: ""}

	if len(n.SMS.Phones) != 0 {
		t.Fatalf("precondition failed: expected empty global sms phones, got %v", n.SMS.Phones)
	}

	errs := n.Notify(tgt, "down", "api", "http://t/", "now", "boom")
	if errs != nil {
		t.Fatalf("expected no errors when sms phones are empty, got %v", errs)
	}
}
