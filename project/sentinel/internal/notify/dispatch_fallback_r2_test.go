package notify

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func TestR2_NotifyNoChannelsNoURL(t *testing.T) {
	n := Notifier{}
	errs := n.Notify(Target{MonitorID: 1}, "down", "api", "http://t/", "now", "boom")
	if errs != nil {
		t.Fatalf("expected nil errors when default webhook has no URL, got %v", errs)
	}
}

func TestR2_NotifyInvalidChannelDropped(t *testing.T) {
	n := Notifier{Channels: []string{"carrier-pigeon"}}
	target := Target{NotifyChannels: "webhook,carrier-pigeon", WebhookURL: ""}
	errs := n.Notify(target, "down", "n", "t", "now", "")
	if errs != nil {
		t.Fatalf("expected nil errors when invalid channel is dropped and webhook URL is empty, got %v", errs)
	}
}

func TestR2_NotifyTargetChannelOverridesGlobal(t *testing.T) {
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{WebhookURL: "http://global/", Channels: []string{"webhook"}}
	t1 := Target{
		MonitorID:      0,
		NotifyChannels: "sms",
		WebhookURL:     srv.URL,
		SMSPhones:      "13800138000",
	}

	errs := n.Notify(t1, "down", "n", "t", "now", "")
	if len(errs) == 0 {
		t.Fatalf("expected sms channel error when SMSSender is nil")
	}

	foundSMS := false
	for _, err := range errs {
		if strings.Contains(err.Error(), "sms") {
			foundSMS = true
		}
	}
	if !foundSMS {
		t.Fatalf("expected an error mentioning sms, got %v", errs)
	}

	if got := hits.Load(); got != 0 {
		t.Fatalf("expected no webhook request when target channels override global webhook, got %d", got)
	}
}
