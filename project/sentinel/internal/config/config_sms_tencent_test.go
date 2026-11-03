package config

import (
	"strings"
	"testing"
)

func setTencentEnvs(t *testing.T, secretID, secretKey, sdkAppID, signName, templateID string) {
	t.Helper()
	t.Setenv("SENTINEL_API_TOKEN", "test-api-token")
	t.Setenv("SENTINEL_SMS_MODE", "tencent")
	t.Setenv("SENTINEL_SMS_TENCENT_SECRET_ID", secretID)
	t.Setenv("SENTINEL_SMS_TENCENT_SECRET_KEY", secretKey)
	t.Setenv("SENTINEL_SMS_TENCENT_SDK_APP_ID", sdkAppID)
	t.Setenv("SENTINEL_SMS_TENCENT_SIGN_NAME", signName)
	t.Setenv("SENTINEL_SMS_TENCENT_TEMPLATE_ID", templateID)
}

func TestLoad_SMSModeTencentAccepted(t *testing.T) {
	setTencentEnvs(t, "test-secret-id", "test-secret-key", "test-sdk-app-id", "test-sign", "test-template")
	t.Setenv("SENTINEL_SMS_TENCENT_REGION", "ap-nanjing")
	t.Setenv("SENTINEL_SMS_TENCENT_ENDPOINT", "sms.example.com")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load returned error for complete tencent config: %v", err)
	}
	if cfg.SMSMode != "tencent" {
		t.Fatalf("SMSMode = %q, want tencent", cfg.SMSMode)
	}
	if cfg.SMSTencentSecretID != "test-secret-id" || cfg.SMSTencentSecretKey != "test-secret-key" {
		t.Fatalf("secret id/key not passed through: %+v", cfg)
	}
	if cfg.SMSTencentSdkAppID != "test-sdk-app-id" || cfg.SMSTencentSignName != "test-sign" || cfg.SMSTencentTemplateID != "test-template" {
		t.Fatalf("sdk app id / sign / template not passed through: %+v", cfg)
	}
	if cfg.SMSTencentRegion != "ap-nanjing" {
		t.Fatalf("SMSTencentRegion = %q, want ap-nanjing", cfg.SMSTencentRegion)
	}
	if cfg.SMSTencentEndpoint != "sms.example.com" {
		t.Fatalf("SMSTencentEndpoint = %q, want sms.example.com", cfg.SMSTencentEndpoint)
	}
}

func TestLoad_SMSModeTencentMissingField(t *testing.T) {
	full := []string{"test-secret-id", "test-secret-key", "test-sdk-app-id", "test-sign", "test-template"}
	envNames := []string{
		"SENTINEL_SMS_TENCENT_SECRET_ID",
		"SENTINEL_SMS_TENCENT_SECRET_KEY",
		"SENTINEL_SMS_TENCENT_SDK_APP_ID",
		"SENTINEL_SMS_TENCENT_SIGN_NAME",
		"SENTINEL_SMS_TENCENT_TEMPLATE_ID",
	}
	for i, envName := range envNames {
		vals := append([]string{}, full...)
		vals[i] = ""
		setTencentEnvs(t, vals[0], vals[1], vals[2], vals[3], vals[4])
		_, err := Load()
		if err == nil {
			t.Fatalf("Load returned nil error with %s empty", envName)
		}
		if !strings.Contains(err.Error(), envName) {
			t.Fatalf("error %q does not mention %q", err.Error(), envName)
		}
	}
}

func TestLoad_SMSModeIllegalStillRejected(t *testing.T) {
	t.Setenv("SENTINEL_SMS_MODE", "carrierpigeon")
	_, err := Load()
	if err == nil {
		t.Fatalf("Load returned nil error for illegal SMS mode")
	}
	if !strings.Contains(err.Error(), "仅支持 mock/aliyun/tencent") {
		t.Fatalf("error = %q, want it to contain %q", err.Error(), "仅支持 mock/aliyun/tencent")
	}
}
