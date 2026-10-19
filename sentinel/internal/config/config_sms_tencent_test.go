package config

import (
	"strings"
	"testing"
)

func TestLoad_SMSModeTencentRejected(t *testing.T) {
	t.Setenv("SENTINEL_SMS_MODE", "tencent")
	_, err := Load()
	if err == nil {
		t.Fatalf("Load returned nil error for SENTINEL_SMS_MODE=tencent")
	}
	if !strings.Contains(err.Error(), "仅支持") {
		t.Errorf("error = %q, want it to contain %q", err.Error(), "仅支持")
	}
}
