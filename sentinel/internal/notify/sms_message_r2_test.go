package notify

import "testing"

func TestR2_BuildSMSMessageDown(t *testing.T) {
	msg := BuildSMSMessage("down", "api", "http://t/", "2026-01-01T00:00:00Z", "boom")
	expected := "【sentinel 告警】api 宕机，目标 http://t/，时间 2026-01-01T00:00:00Z，错误：boom"
	if msg != expected {
		t.Fatalf("BuildSMSMessage(down) = %q, want %q", msg, expected)
	}
}

func TestR2_BuildSMSMessageDownNoErr(t *testing.T) {
	msg := BuildSMSMessage("down", "api", "http://t/", "2026-01-01T00:00:00Z", "")
	expected := "【sentinel 告警】api 宕机，目标 http://t/，时间 2026-01-01T00:00:00Z"
	if msg != expected {
		t.Fatalf("BuildSMSMessage(down, no error) = %q, want %q", msg, expected)
	}
}

func TestR2_BuildSMSMessageRecovered(t *testing.T) {
	msg := BuildSMSMessage("recovered", "api", "http://t/", "2026-01-01T00:00:00Z", "")
	expected := "【sentinel 恢复】api 已恢复，目标 http://t/，时间 2026-01-01T00:00:00Z"
	if msg != expected {
		t.Fatalf("BuildSMSMessage(recovered) = %q, want %q", msg, expected)
	}
}

func TestR2_BuildSMSMessageOther(t *testing.T) {
	msg := BuildSMSMessage("paused", "api", "http://t/", "2026-01-01T00:00:00Z", "")
	expected := "【sentinel】api paused，目标 http://t/，时间 2026-01-01T00:00:00Z"
	if msg != expected {
		t.Fatalf("BuildSMSMessage(other) = %q, want %q", msg, expected)
	}
}
