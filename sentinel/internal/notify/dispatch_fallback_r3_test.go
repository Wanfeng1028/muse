package notify

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestR2_WebhookTargetURLPreferredOverGlobal(t *testing.T) {
	var targetHits, globalHits int
	targetServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		targetHits++
	}))
	defer targetServer.Close()
	globalServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		globalHits++
	}))
	defer globalServer.Close()

	n := &Notifier{
		WebhookURL: globalServer.URL,
		Channels:   []string{"webhook"},
	}
	target := Target{WebhookURL: targetServer.URL}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if errs != nil {
		t.Fatalf("expected nil errs, got %v", errs)
	}
	if targetHits != 1 {
		t.Errorf("expected target server hit 1 time, got %d", targetHits)
	}
	if globalHits != 0 {
		t.Errorf("expected global server hit 0 times, got %d", globalHits)
	}
}

func TestR2_WebhookFallsBackToGlobal(t *testing.T) {
	var globalHits int
	globalServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		globalHits++
	}))
	defer globalServer.Close()

	n := &Notifier{
		WebhookURL: globalServer.URL,
		Channels:   []string{"webhook"},
	}
	target := Target{}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if errs != nil {
		t.Fatalf("expected nil errs, got %v", errs)
	}
	if globalHits != 1 {
		t.Errorf("expected global server hit 1 time, got %d", globalHits)
	}
}

type failOneSmsSender struct {
	sent []string
}

func (f *failOneSmsSender) Send(phone, message string) error {
	if phone == "13800000001" {
		return errors.New("boom")
	}
	f.sent = append(f.sent, phone)
	return nil
}

func (f *failOneSmsSender) Provider() string {
	return "fail-one"
}

func TestR2_SMSOneNumberFailureDoesNotBlockOthers(t *testing.T) {
	fake := &failOneSmsSender{}
	n := &Notifier{
		Channels:  []string{"sms"},
		SMSSender: fake,
	}
	target := Target{SMSPhones: "13800000001,13800000002"}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if len(errs) != 1 {
		t.Fatalf("expected 1 error, got %d: %v", len(errs), errs)
	}
	if !containsSubstr(errs[0].Error(), "13800000001") {
		t.Errorf("expected error to contain 13800000001, got %v", errs[0])
	}
	found := false
	for _, p := range fake.sent {
		if p == "13800000002" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected fake.sent to contain 13800000002, got %v", fake.sent)
	}
}

func TestR2_SMSNilSenderRecordedAsError(t *testing.T) {
	n := &Notifier{
		Channels: []string{"sms"},
	}
	target := Target{SMSPhones: "13800000001"}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if len(errs) != 1 {
		t.Fatalf("expected 1 error, got %d: %v", len(errs), errs)
	}
	if !containsSubstr(errs[0].Error(), "短信发送器未初始化") {
		t.Errorf("expected error to contain 短信发送器未初始化, got %v", errs[0])
	}
}

func TestR2_SMSInvalidPhonesRecordedAsError(t *testing.T) {
	n := &Notifier{
		Channels:  []string{"sms"},
		SMSSender: &MockSmsSender{},
	}
	target := Target{SMSPhones: "not-a-phone"}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if len(errs) != 1 {
		t.Fatalf("expected 1 error, got %d: %v", len(errs), errs)
	}
	if !containsSubstr(errs[0].Error(), "号码非法") {
		t.Errorf("expected error to contain 号码非法, got %v", errs[0])
	}
}

func TestR2_QueueEnqueuePathSkipsDirectSend(t *testing.T) {
	var hits int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
	}))
	defer server.Close()

	n := &Notifier{
		WebhookURL: server.URL,
		Channels:   []string{"webhook"},
		Queue:      &QueueSender{},
	}
	// MonitorID>0 的入队路径由 queue 包的测试覆盖
	target := Target{MonitorID: 0}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if errs != nil {
		t.Fatalf("expected nil errs, got %v", errs)
	}
	if hits != 1 {
		t.Errorf("expected server hit 1 time, got %d", hits)
	}
}

func TestR2_MultiChannelPartialFailure(t *testing.T) {
	closedServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	closedServer.Close()
	badURL := closedServer.URL

	mock := &MockSmsSender{}
	n := &Notifier{
		Channels:   []string{"webhook", "sms"},
		WebhookURL: badURL,
		SMSSender:  mock,
	}
	target := Target{SMSPhones: "13800000001"}

	errs := n.Notify(target, "ALERT", "test-monitor", "https://example.com", "2026-10-21T00:00:00Z", "")
	if len(errs) != 1 {
		t.Fatalf("expected 1 error, got %d: %v", len(errs), errs)
	}
	if !containsSubstr(errs[0].Error(), "webhook") {
		t.Errorf("expected error to contain webhook, got %v", errs[0])
	}
	if len(mock.Sent) != 1 {
		t.Errorf("expected mock.Sent length 1, got %d", len(mock.Sent))
	}
}

func containsSubstr(s, substr string) bool {
	return strings.Contains(s, substr)
}

