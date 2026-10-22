package config

import (
	"reflect"
	"testing"
)

func TestSplitWebhookURLs_Basic(t *testing.T) {
	got := SplitWebhookURLs("https://a.example/hook, https://b.example/hook")
	want := []string{"https://a.example/hook", "https://b.example/hook"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SplitWebhookURLs() = %v, want %v", got, want)
	}
}

func TestSplitWebhookURLs_EmptyItems(t *testing.T) {
	got := SplitWebhookURLs("a,, ,b")
	want := []string{"a", "b"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SplitWebhookURLs() = %v, want %v", got, want)
	}
}

func TestSplitWebhookURLs_Dedup(t *testing.T) {
	got := SplitWebhookURLs("a,b,a")
	want := []string{"a", "b"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SplitWebhookURLs() = %v, want %v", got, want)
	}
}

func TestSplitWebhookURLs_Empty(t *testing.T) {
	if got := SplitWebhookURLs(""); len(got) != 0 {
		t.Fatalf("SplitWebhookURLs() = %v, want no items", got)
	}
}

func TestFromEnv_IPAlertThreshold(t *testing.T) {
	t.Setenv("LINKSHORT_PASSWORD_FAIL_ALERT_IP_THRESHOLD", "7")

	cfg := FromEnv()
	if cfg.PasswordFailAlertIPThreshold != 7 {
		t.Fatalf("PasswordFailAlertIPThreshold = %d, want 7", cfg.PasswordFailAlertIPThreshold)
	}
}

func TestFromEnv_WebhookURLs(t *testing.T) {
	const raw = "https://x/1, https://x/2"
	t.Setenv("LINKSHORT_ALERT_WEBHOOK_URL", raw)

	cfg := FromEnv()
	if len(cfg.AlertWebhookURLs) != 2 {
		t.Fatalf("len(AlertWebhookURLs) = %d, want 2", len(cfg.AlertWebhookURLs))
	}
	if cfg.AlertWebhookURL != raw {
		t.Fatalf("AlertWebhookURL = %q, want %q", cfg.AlertWebhookURL, raw)
	}
}
