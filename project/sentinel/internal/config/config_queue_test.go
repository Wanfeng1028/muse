package config

import (
	"testing"
)

func TestQueueConfigDefaults(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.QueueMaxAttempts != 8 {
		t.Errorf("QueueMaxAttempts = %d, 期望 8", cfg.QueueMaxAttempts)
	}
	if cfg.QueueBaseBackoffSec != 60 {
		t.Errorf("QueueBaseBackoffSec = %d, 期望 60", cfg.QueueBaseBackoffSec)
	}
	if cfg.QueueTickSec != 15 {
		t.Errorf("QueueTickSec = %d, 期望 15", cfg.QueueTickSec)
	}
}

func TestQueueConfigValid(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	t.Setenv("SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS", "20")
	t.Setenv("SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC", "3600")
	t.Setenv("SENTINEL_WEBHOOK_QUEUE_TICK_SEC", "300")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.QueueMaxAttempts != 20 {
		t.Errorf("QueueMaxAttempts = %d, 期望 20", cfg.QueueMaxAttempts)
	}
	if cfg.QueueBaseBackoffSec != 3600 {
		t.Errorf("QueueBaseBackoffSec = %d, 期望 3600", cfg.QueueBaseBackoffSec)
	}
	if cfg.QueueTickSec != 300 {
		t.Errorf("QueueTickSec = %d, 期望 300", cfg.QueueTickSec)
	}
}

func TestQueueConfigOutOfRange(t *testing.T) {
	cases := []struct {
		name     string
		envKey   string
		envValue string
	}{
		{"max_attempts_zero", "SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS", "0"},
		{"max_attempts_over", "SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS", "21"},
		{"base_backoff_over", "SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC", "3601"},
		{"base_backoff_under", "SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC", "4"},
		{"tick_over", "SENTINEL_WEBHOOK_QUEUE_TICK_SEC", "301"},
		{"tick_under", "SENTINEL_WEBHOOK_QUEUE_TICK_SEC", "4"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("SENTINEL_API_TOKEN", "test-token")
			t.Setenv(tc.envKey, tc.envValue)

			_, err := Load()
			if err == nil {
				t.Fatalf("期望错误，得到 nil")
			}
			if !contains(err.Error(), tc.envKey) {
				t.Errorf("错误信息 %q 未点名变量 %q", err.Error(), tc.envKey)
			}
		})
	}
}

func contains(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
