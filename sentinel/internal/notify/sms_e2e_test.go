package notify

import (
	"strings"
	"testing"
)

// 本测试覆盖 main.go 中调度器回调 notifyFn 的真实调用路径：
// 即 Notifier.Notify 的全链路分发（渠道解析 -> 目标级/全局号码选择 -> SMS 发送）。
// 使用 MockSmsSender 捕获真实发出的短信内容与收件号码，验证告警与恢复两条生命周期。

func TestSMSAlertLifecycle_E2E(t *testing.T) {
	mock := &MockSmsSender{}
	// 全局默认渠道含 sms，走真实分发路径。
	n := Notifier{SMSSender: mock, Channels: []string{"sms"}}

	// 1. 模拟站点宕机。
	errs := n.Notify(
		Target{
			MonitorID:      7,
			NotifyChannels: "sms",
			SMSPhones:      "13800138000,13900139000",
		},
		"down",
		"官网首页",
		"https://web.example.com",
		"2026-10-16T23:00:00Z",
		"连接超时",
	)
	if len(errs) != 0 {
		t.Fatalf("宕机通知返回错误: %v", errs)
	}

	msgs := mock.Messages()
	if len(msgs) != 2 {
		t.Fatalf("宕机通知短信条数 = %d, 期望 2", len(msgs))
	}
	if msgs[0].Phone != "13800138000" {
		t.Errorf("第 1 条短信号码 = %q, 期望 %q", msgs[0].Phone, "13800138000")
	}
	if msgs[1].Phone != "13900139000" {
		t.Errorf("第 2 条短信号码 = %q, 期望 %q", msgs[1].Phone, "13900139000")
	}
	for i, m := range msgs {
		if !strings.Contains(m.Message, "【sentinel 告警】官网首页 宕机") {
			t.Errorf("第 %d 条短信内容缺少告警前缀: %q", i+1, m.Message)
		}
		if !strings.Contains(m.Message, "连接超时") {
			t.Errorf("第 %d 条短信内容缺少错误信息: %q", i+1, m.Message)
		}
		if m.At == "" {
			t.Errorf("第 %d 条短信 At 为空", i+1)
		}
	}

	// 2. 模拟站点恢复。
	errs = n.Notify(
		Target{
			MonitorID:      7,
			NotifyChannels: "sms",
			SMSPhones:      "13800138000,13900139000",
		},
		"recovered",
		"官网首页",
		"https://web.example.com",
		"2026-10-16T23:05:00Z",
		"",
	)
	if len(errs) != 0 {
		t.Fatalf("恢复通知返回错误: %v", errs)
	}

	msgs = mock.Messages()
	if len(msgs) != 4 {
		t.Fatalf("恢复后短信总条数 = %d, 期望 4", len(msgs))
	}
	for i := 2; i < 4; i++ {
		if !strings.Contains(msgs[i].Message, "【sentinel 恢复】官网首页 已恢复") {
			t.Errorf("第 %d 条短信内容缺少恢复前缀: %q", i+1, msgs[i].Message)
		}
		if msgs[i].At == "" {
			t.Errorf("第 %d 条短信 At 为空", i+1)
		}
	}
}

func TestSMSAlertLifecycle_GlobalPhonesFallback_E2E(t *testing.T) {
	mock := &MockSmsSender{}
	// 目标级 SMSPhones 为空时，回退到全局 SMS.Phones。
	n := Notifier{
		SMSSender: mock,
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
	}

	errs := n.Notify(
		Target{
			MonitorID:      7,
			NotifyChannels: "sms",
			SMSPhones:      "",
		},
		"down",
		"官网首页",
		"https://web.example.com",
		"2026-10-16T23:00:00Z",
		"连接超时",
	)
	if len(errs) != 0 {
		t.Fatalf("全局号码回退通知返回错误: %v", errs)
	}

	msgs := mock.Messages()
	if len(msgs) != 1 {
		t.Fatalf("全局号码回退短信条数 = %d, 期望 1", len(msgs))
	}
	if msgs[0].Phone != "13800138000" {
		t.Errorf("全局号码回退短信号码 = %q, 期望 %q", msgs[0].Phone, "13800138000")
	}
}
