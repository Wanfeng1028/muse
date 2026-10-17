package notify

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTencentSend_Success(t *testing.T) {
	var gotAction string
	var gotVersion string
	var gotAuth string
	var gotBody []byte

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAction = r.Header.Get("X-TC-Action")
		gotVersion = r.Header.Get("X-TC-Version")
		gotAuth = r.Header.Get("Authorization")
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Errorf("read request body failed: %v", err)
		}
		gotBody = body

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"Response":{"SendStatusSet":[{"Code":"Ok","Message":"send success","PhoneNumber":"+8613800138000"}],"RequestId":"test-req-id"}}`))
	}))
	defer server.Close()

	sender, err := NewTencentSMSSender(TencentConfig{
		SecretId:    "id",
		SecretKey:   "key",
		SmsSdkAppId: "1400006666",
		SignName:    "sig",
		TemplateId:  "1110",
		Endpoint:    server.URL,
	})

	err = sender.Send("13800138000", "hello")
	if err != nil {
		t.Fatalf("Send returned error: %v", err)
	}

	if gotAction != "SendSms" {
		t.Errorf("X-TC-Action = %q, want %q", gotAction, "SendSms")
	}
	if gotVersion != "2021-01-11" {
		t.Errorf("X-TC-Version = %q, want %q", gotVersion, "2021-01-11")
	}
	if !strings.HasPrefix(gotAuth, "TC3-HMAC-SHA256 Credential=") {
		t.Errorf("Authorization = %q, want prefix %q", gotAuth, "TC3-HMAC-SHA256 Credential=")
	}

	var req struct {
		PhoneNumberSet   []string `json:"PhoneNumberSet"`
		SmsSdkAppId      string   `json:"SmsSdkAppId"`
		SignName         string   `json:"SignName"`
		TemplateId       string   `json:"TemplateId"`
		TemplateParamSet []string `json:"TemplateParamSet"`
	}
	if err := json.Unmarshal(gotBody, &req); err != nil {
		t.Fatalf("unmarshal request body failed: %v, body=%s", err, string(gotBody))
	}
	if len(req.PhoneNumberSet) != 1 || req.PhoneNumberSet[0] != "+8613800138000" {
		t.Errorf("PhoneNumberSet = %v, want [\"+8613800138000\"]", req.PhoneNumberSet)
	}
	if req.SmsSdkAppId != "1400006666" {
		t.Errorf("SmsSdkAppId = %q, want %q", req.SmsSdkAppId, "1400006666")
	}
	if req.SignName != "sig" {
		t.Errorf("SignName = %q, want %q", req.SignName, "sig")
	}
	if req.TemplateId != "1110" {
		t.Errorf("TemplateId = %q, want %q", req.TemplateId, "1110")
	}
	if len(req.TemplateParamSet) != 1 || req.TemplateParamSet[0] != "hello" {
		t.Errorf("TemplateParamSet = %v, want [\"hello\"]", req.TemplateParamSet)
	}
}

func TestTencentSend_FailedCode(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"Response":{"SendStatusSet":[{"Code":"FailedOperation.PhoneNumberInBlacklist","Message":"phone in blacklist"}],"RequestId":"x"}}`))
	}))
	defer server.Close()

	sender, err := NewTencentSMSSender(TencentConfig{
		SecretId:    "id",
		SecretKey:   "key",
		SmsSdkAppId: "1400006666",
		SignName:    "sig",
		TemplateId:  "1110",
		Endpoint:    server.URL,
	})

	err = sender.Send("13800138000", "hello")
	if err == nil {
		t.Fatalf("Send returned nil error, want error containing %q", "FailedOperation.PhoneNumberInBlacklist")
	}
	if !strings.Contains(err.Error(), "FailedOperation.PhoneNumberInBlacklist") {
		t.Errorf("error = %q, want it to contain %q", err.Error(), "FailedOperation.PhoneNumberInBlacklist")
	}
}

func TestTencentSend_InvalidPhone(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"Response":{"SendStatusSet":[{"Code":"Ok","Message":"send success","PhoneNumber":"+8613800138000"}],"RequestId":"test-req-id"}}`))
	}))
	defer server.Close()

	sender, err := NewTencentSMSSender(TencentConfig{
		SecretId:    "id",
		SecretKey:   "key",
		SmsSdkAppId: "1400006666",
		SignName:    "sig",
		TemplateId:  "1110",
		Endpoint:    server.URL,
	})

	err = sender.Send("12345", "hi")
	if err == nil {
		t.Fatalf("Send returned nil error for invalid phone")
	}
	if requestCount != 0 {
		t.Errorf("requestCount = %d, want 0 (no request should be sent for invalid phone)", requestCount)
	}
}

func TestTencentSend_MissingAK(t *testing.T) {
	sender, err := NewTencentSMSSender(TencentConfig{})
	if err == nil {
		t.Fatalf("NewTencentSMSSender returned nil error for empty config")
	}
	if sender != nil {
		t.Errorf("sender = %v, want nil", sender)
	}
}