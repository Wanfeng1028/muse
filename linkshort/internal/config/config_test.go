package config

import (
	"testing"
	"time"
)

func TestFromEnv_Purge默认(t *testing.T) {
	t.Setenv(envPurgeInterval, "")
	t.Setenv(envPurgeRetentionDays, "")
	t.Setenv(envAdminKey, "k")

	cfg := FromEnv()
	if cfg.PurgeInterval != 24*time.Hour {
		t.Fatalf("PurgeInterval = %s, want 24h", cfg.PurgeInterval)
	}
	if cfg.PurgeRetentionDays != 7 {
		t.Fatalf("PurgeRetentionDays = %d, want 7", cfg.PurgeRetentionDays)
	}
}

func TestFromEnv_Purge自定义(t *testing.T) {
	t.Setenv(envPurgeInterval, "90m")
	t.Setenv(envPurgeRetentionDays, "3")
	t.Setenv(envAdminKey, "k")

	cfg := FromEnv()
	if cfg.PurgeInterval != 90*time.Minute {
		t.Fatalf("PurgeInterval = %s, want 90m", cfg.PurgeInterval)
	}
	if cfg.PurgeRetentionDays != 3 {
		t.Fatalf("PurgeRetentionDays = %d, want 3", cfg.PurgeRetentionDays)
	}
}

func TestFromEnv_Purge保留天数负值回落默认(t *testing.T) {
	t.Setenv(envPurgeInterval, "90m")
	t.Setenv(envPurgeRetentionDays, "-5")
	t.Setenv(envAdminKey, "k")

	cfg := FromEnv()
	if cfg.PurgeInterval != 90*time.Minute {
		t.Fatalf("PurgeInterval = %s, want 90m", cfg.PurgeInterval)
	}
	if cfg.PurgeRetentionDays != 7 {
		t.Fatalf("PurgeRetentionDays = %d, want 7", cfg.PurgeRetentionDays)
	}
}
