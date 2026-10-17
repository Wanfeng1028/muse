package config

import "testing"

// TestEnqueueRateLimitDefaults 校验默认值。
func TestEnqueueRateLimitDefaults(t *testing.T) {
	t.Setenv("SENTINEL_API_TOKEN", "test-token")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load 失败: %v", err)
	}
	if cfg.QueueEnqueueRPS != 20 {
		t.Fatalf("QueueEnqueueRPS = %v, 期望 20", cfg.QueueEnqueueRPS)
	}
	if cfg.QueueEnqueueBurst != 40 {
		t.Fatalf("QueueEnqueueBurst = %d, 期望 40", cfg.QueueEnqueueBurst)
	}
}

// TestEnqueueRateLimitValid 校验合法取值解析。
func TestEnqueueRateLimitValid(t *testing.T) {
	t.Run("RPS=5.5 BURST=100", func(t *testing.T) {
		t.Setenv("SENTINEL_API_TOKEN", "test-token")
		t.Setenv("SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", "5.5")
		t.Setenv("SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST", "100")
		cfg, err := Load()
		if err != nil {
			t.Fatalf("Load 失败: %v", err)
		}
		if cfg.QueueEnqueueRPS != 5.5 {
			t.Fatalf("QueueEnqueueRPS = %v, 期望 5.5", cfg.QueueEnqueueRPS)
		}
		if cfg.QueueEnqueueBurst != 100 {
			t.Fatalf("QueueEnqueueBurst = %d, 期望 100", cfg.QueueEnqueueBurst)
		}
	})
	t.Run("RPS=0 禁用合法", func(t *testing.T) {
		t.Setenv("SENTINEL_API_TOKEN", "test-token")
		t.Setenv("SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", "0")
		cfg, err := Load()
		if err != nil {
			t.Fatalf("Load 失败: %v", err)
		}
		if cfg.QueueEnqueueRPS != 0 {
			t.Fatalf("QueueEnqueueRPS = %v, 期望 0", cfg.QueueEnqueueRPS)
		}
	})
}

// TestEnqueueRateLimitInvalid 校验非法取值一律报错。
func TestEnqueueRateLimitInvalid(t *testing.T) {
	cases := []struct {
		name  string
		key   string
		value string
	}{
		{"RPS 非数字", "SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", "abc"},
		{"RPS 为负", "SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", "-5"},
		{"RPS 超上限", "SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", "20000"},
		{"RPS 低于下限", "SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", "0.05"},
		{"BURST 为 0", "SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST", "0"},
		{"BURST 超上限", "SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST", "200000"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Setenv("SENTINEL_API_TOKEN", "test-token")
			t.Setenv(c.key, c.value)
			if _, err := Load(); err == nil {
				t.Fatalf("Load 期望返回 err，实际 nil（%s=%s）", c.key, c.value)
			}
		})
	}
}
