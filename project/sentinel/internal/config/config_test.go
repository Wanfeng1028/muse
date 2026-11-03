package config

import (
	"strings"
	"testing"
)

func TestLoad_SMTPWeComChannels(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	t.Setenv("SENTINEL_SMTP_HOST", "smtp.example.com")
	t.Setenv("SENTINEL_SMTP_PORT", "587")
	t.Setenv("SENTINEL_SMTP_USERNAME", "u")
	t.Setenv("SENTINEL_SMTP_PASSWORD", "p")
	t.Setenv("SENTINEL_SMTP_FROM", "a@x.com")
	t.Setenv("SENTINEL_SMTP_TO", "b@x.com")
	t.Setenv("SENTINEL_WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/x")
	t.Setenv("SENTINEL_WECOM_MENTION_ALL", "true")
	t.Setenv("SENTINEL_NOTIFY_CHANNELS", "smtp,wecom")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 期望成功，实际返回错误: %v", err)
	}

	if cfg.SMTPHost != "smtp.example.com" {
		t.Errorf("SMTPHost 期望 %q，实际 %q", "smtp.example.com", cfg.SMTPHost)
	}
	if cfg.SMTPPort != 587 {
		t.Errorf("SMTPPort 期望 587，实际 %d", cfg.SMTPPort)
	}
	if cfg.SMTPUsername != "u" {
		t.Errorf("SMTPUsername 期望 %q，实际 %q", "u", cfg.SMTPUsername)
	}
	if cfg.SMTPPassword != "p" {
		t.Errorf("SMTPPassword 期望 %q，实际 %q", "p", cfg.SMTPPassword)
	}
	if cfg.SMTPFrom != "a@x.com" {
		t.Errorf("SMTPFrom 期望 %q，实际 %q", "a@x.com", cfg.SMTPFrom)
	}
	if cfg.SMTPTo != "b@x.com" {
		t.Errorf("SMTPTo 期望 %q，实际 %q", "b@x.com", cfg.SMTPTo)
	}
	if cfg.WeComWebhookURL != "https://qyapi.weixin.qq.com/x" {
		t.Errorf("WeComWebhookURL 期望 %q，实际 %q", "https://qyapi.weixin.qq.com/x", cfg.WeComWebhookURL)
	}
	if !cfg.WeComMentionAll {
		t.Error("WeComMentionAll 期望 true，实际 false")
	}
	if len(cfg.NotifyChannels) != 2 || cfg.NotifyChannels[0] != "smtp" || cfg.NotifyChannels[1] != "wecom" {
		t.Errorf("NotifyChannels 期望 [\"smtp\",\"wecom\"]，实际 %v", cfg.NotifyChannels)
	}
}

func TestLoad_Defaults(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 期望成功，实际返回错误: %v", err)
	}

	if cfg.SMTPPort != 25 {
		t.Errorf("SMTPPort 默认期望 25，实际 %d", cfg.SMTPPort)
	}
	if cfg.WeComMentionAll {
		t.Error("WeComMentionAll 默认期望 false，实际 true")
	}
	if len(cfg.NotifyChannels) != 1 || cfg.NotifyChannels[0] != "webhook" {
		t.Errorf("NotifyChannels 默认期望 [\"webhook\"]，实际 %v", cfg.NotifyChannels)
	}
	if cfg.SMTPHost != "" {
		t.Errorf("SMTPHost 默认期望空字符串，实际 %q", cfg.SMTPHost)
	}
}

func TestLoad_InvalidChannel(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	t.Setenv("SENTINEL_NOTIFY_CHANNELS", "carrier_pigeon")

	_, err := Load()
	if err == nil {
		t.Fatal("非法渠道值期望 Load 返回错误，实际返回 nil")
	}
	if !strings.Contains(err.Error(), "SENTINEL_NOTIFY_CHANNELS") {
		t.Errorf("错误信息应包含 \"SENTINEL_NOTIFY_CHANNELS\"，实际: %v", err)
	}
}

func TestLoad_InvalidBool(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	t.Setenv("SENTINEL_WECOM_MENTION_ALL", "maybe")

	_, err := Load()
	if err == nil {
		t.Fatal("非法布尔值期望 Load 返回错误，实际返回 nil")
	}
	if !strings.Contains(err.Error(), "SENTINEL_WECOM_MENTION_ALL") {
		t.Errorf("错误信息应包含 \"SENTINEL_WECOM_MENTION_ALL\"，实际: %v", err)
	}
}
