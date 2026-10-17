package config

import (
	"testing"
)

// TestBreakerConfigDefaults 验证熔断配置默认值
func TestBreakerConfigDefaults(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 默认配置失败: %v", err)
	}
	if cfg.BreakerFailureThreshold != 5 {
		t.Fatalf("默认 BreakerFailureThreshold 应为 5，实际 %d", cfg.BreakerFailureThreshold)
	}
	if cfg.BreakerOpenTimeoutSec != 300 {
		t.Fatalf("默认 BreakerOpenTimeoutSec 应为 300，实际 %d", cfg.BreakerOpenTimeoutSec)
	}
}

// TestBreakerConfigValid 验证合法配置解析
func TestBreakerConfigValid(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	t.Setenv("SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD", "10")
	t.Setenv("SENTINEL_WEBHOOK_BREAKER_OPEN_TIMEOUT_SEC", "60")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 合法配置失败: %v", err)
	}
	if cfg.BreakerFailureThreshold != 10 {
		t.Fatalf("BreakerFailureThreshold 应为 10，实际 %d", cfg.BreakerFailureThreshold)
	}
	if cfg.BreakerOpenTimeoutSec != 60 {
		t.Fatalf("BreakerOpenTimeoutSec 应为 60，实际 %d", cfg.BreakerOpenTimeoutSec)
	}
}

// TestBreakerConfigInvalid 验证非法配置返回错误
func TestBreakerConfigInvalid(t *testing.T) {
	cases := []struct {
		name      string
		threshold string
		timeout   string
	}{
		{"threshold=0", "0", ""},
		{"threshold=101", "101", ""},
		{"threshold=abc", "abc", ""},
		{"timeout=5", "", "5"},
		{"timeout=90000", "", "90000"},
		{"timeout=abc", "", "abc"},
	}
	for _, c := range cases {
		c := c
		t.Run(c.name, func(t *testing.T) {
			t.Setenv("SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD", c.threshold)
			t.Setenv("SENTINEL_WEBHOOK_BREAKER_OPEN_TIMEOUT_SEC", c.timeout)
			if _, err := Load(); err == nil {
				t.Fatalf("非法配置 %s 应返回错误", c.name)
			}
		})
	}
}
