package notify

import (
	"strings"
	"testing"
)

func TestR2_BuildSubscriberSubject(t *testing.T) {
	if got := BuildSubscriberSubject("down", "api"); got != "[sentinel] 服务状态通知：api 宕机" {
		t.Fatalf("down subject = %q", got)
	}
	if got := BuildSubscriberSubject("recovered", "api"); got != "[sentinel] 服务状态通知：api 已恢复" {
		t.Fatalf("recovered subject = %q", got)
	}
	if got := BuildSubscriberSubject("paused", "api"); got != "[sentinel] 服务状态通知：api paused" {
		t.Fatalf("unknown event subject = %q", got)
	}
}

func TestR2_BuildSubscriberBodyDown(t *testing.T) {
	body := BuildSubscriberBody("我的状态页", "down", "api", "http://t/", "2026-01-01T00:00:00Z", "boom", "https://u/unsub")

	for _, want := range []string{
		"我的状态页",
		"监控名称: api",
		"事件: 宕机",
		"错误信息: boom",
		"https://u/unsub",
	} {
		if !strings.Contains(body, want) {
			t.Fatalf("body %q does not contain %q", body, want)
		}
	}
}

func TestR2_BuildSubscriberBodyDownNoErr(t *testing.T) {
	body := BuildSubscriberBody("我的状态页", "down", "api", "http://t/", "2026-01-01T00:00:00Z", "", "https://u/unsub")

	if strings.Contains(body, "错误信息") {
		t.Fatalf("body unexpectedly contains error info: %q", body)
	}
	if !strings.Contains(body, "事件: 宕机") {
		t.Fatalf("body %q does not contain down event", body)
	}
}

func TestR2_BuildSubscriberBodyRecovered(t *testing.T) {
	body := BuildSubscriberBody("我的状态页", "recovered", "api", "http://t/", "2026-01-01T00:00:00Z", "", "https://u/unsub")

	if !strings.Contains(body, "事件: 已恢复") {
		t.Fatalf("body %q does not contain recovered event", body)
	}
	if strings.Contains(body, "错误信息") {
		t.Fatalf("body unexpectedly contains error info: %q", body)
	}
}
