package notify

import (
	"strings"
	"testing"
)

type record struct {
	phone     string
	message   string
	provider  string
	status    string
	errMsg    string
	monitorID int64
}

type fakeRecorder struct {
	records []record
}

func (r *fakeRecorder) RecordSMSLog(phone, message, provider, status, errMsg string) error {
	return r.RecordSMSLogForMonitor(phone, message, provider, status, errMsg, 0)
}

func (r *fakeRecorder) RecordSMSLogForMonitor(phone, message, provider, status, errMsg string, monitorID int64) error {
	r.records = append(r.records, record{
		phone:     phone,
		message:   message,
		provider:  provider,
		status:    status,
		errMsg:    errMsg,
		monitorID: monitorID,
	})
	return nil
}

func TestNotifySMS_LogsSent(t *testing.T) {
	rec := &fakeRecorder{}
	n := &Notifier{
		Channels:  []string{"sms"},
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
		SMSSender: &MockSmsSender{},
		SMSLogger: rec,
	}

	errs := n.Notify(Target{}, "down", "web", "https://a", "2026-10-17T00:00:00Z", "")

	if errs != nil {
		t.Fatalf("expected errs to be nil, got %v", errs)
	}
	if len(rec.records) != 1 {
		t.Fatalf("expected 1 recorded sms log, got %d", len(rec.records))
	}
	got := rec.records[0]
	if got.phone != "13800138000" {
		t.Errorf("expected phone %q, got %q", "13800138000", got.phone)
	}
	if got.provider != "mock" {
		t.Errorf("expected provider %q, got %q", "mock", got.provider)
	}
	if got.status != "sent" {
		t.Errorf("expected status %q, got %q", "sent", got.status)
	}
	if !strings.Contains(got.message, "宕机") {
		t.Errorf("expected message to contain %q, got %q", "宕机", got.message)
	}
}

func TestNotifySMS_LogsFailed(t *testing.T) {
	rec := &fakeRecorder{}
	n := &Notifier{
		Channels:  []string{"sms"},
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
		SMSSender: &MockSmsSender{FailCount: 1},
		SMSLogger: rec,
	}

	errs := n.Notify(Target{}, "down", "web", "https://a", "2026-10-17T00:00:00Z", "")

	if len(errs) == 0 {
		t.Fatalf("expected errs to be non-empty, got %v", errs)
	}
	if len(rec.records) != 1 {
		t.Fatalf("expected 1 recorded sms log, got %d", len(rec.records))
	}
	got := rec.records[0]
	if got.status != "failed" {
		t.Errorf("expected status %q, got %q", "failed", got.status)
	}
	if got.errMsg == "" {
		t.Errorf("expected errMsg to be non-empty, got %q", got.errMsg)
	}
}

func TestNotifySMS_NoLogger(t *testing.T) {
	n := &Notifier{
		SMS:       SMSConfig{Phones: []string{"13800138000"}},
		SMSSender: &MockSmsSender{},
		SMSLogger: nil,
	}

	errs := n.Notify(Target{}, "down", "web", "https://a", "2026-10-17T00:00:00Z", "")

	if errs != nil {
		t.Fatalf("expected errs to be nil, got %v", errs)
	}
	if n.SMSLogger != nil {
		t.Errorf("expected SMSLogger to be nil, got %v", n.SMSLogger)
	}
}