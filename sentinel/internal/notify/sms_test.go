package notify

import (
	"crypto/hmac"
	"crypto/sha1"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sort"
	"strings"
	"testing"
)

func TestValidatePhone(t *testing.T) {
	valid := []string{"13800138000", "+85212345678"}
	for _, p := range valid {
		if err := ValidatePhone(p); err != nil {
			t.Fatalf("ValidatePhone(%q) 期望无错，实际 %v", p, err)
		}
	}
	invalid := []string{"123", "1380013800a", "", "+86"}
	for _, p := range invalid {
		if err := ValidatePhone(p); err == nil {
			t.Fatalf("ValidatePhone(%q) 期望有错，实际 nil", p)
		}
	}
}

func TestParsePhones(t *testing.T) {
	got, err := ParsePhones("13800138000, 13900139000,13800138000")
	if err != nil {
		t.Fatalf("ParsePhones 期望无错，实际 %v", err)
	}
	want := []string{"13800138000", "13900139000"}
	if len(got) != len(want) {
		t.Fatalf("ParsePhones 长度 = %d，期望 %d（%v）", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("ParsePhones[%d] = %q，期望 %q", i, got[i], want[i])
		}
	}

	_, err = ParsePhones("13800138000,123")
	if err == nil {
		t.Fatalf("ParsePhones 非法号码期望有错，实际 nil")
	}
	if !strings.Contains(err.Error(), "第 2 个") {
		t.Fatalf("ParsePhones 错误应含“第 2 个”，实际 %q", err.Error())
	}

	empty, err := ParsePhones("")
	if err != nil {
		t.Fatalf("ParsePhones(\"\") 期望 err 为 nil，实际 %v", err)
	}
	if len(empty) != 0 {
		t.Fatalf("ParsePhones(\"\") 期望空切片，实际 %v", empty)
	}
}

func TestMockSmsSender_CapturesContent(t *testing.T) {
	m := &MockSmsSender{}
	if err := m.Send("13800138000", "hello"); err != nil {
		t.Fatalf("Send 期望无错，实际 %v", err)
	}
	msgs := m.Messages()
	if len(msgs) != 1 {
		t.Fatalf("Messages 长度 = %d，期望 1", len(msgs))
	}
	if msgs[0].Phone != "13800138000" {
		t.Fatalf("Phone = %q，期望 %q", msgs[0].Phone, "13800138000")
	}
	if msgs[0].Message != "hello" {
		t.Fatalf("Message = %q，期望 %q", msgs[0].Message, "hello")
	}
	if msgs[0].At == "" {
		t.Fatalf("At 不应为空")
	}
}

func TestMockSmsSender_RetryOnce(t *testing.T) {
	boom := errors.New("boom")
	m := &MockSmsSender{FailCount: 1, FailErr: boom}
	if err := m.Send("13800138000", "hello"); err == nil || err.Error() != "boom" {
		t.Fatalf("第一次 Send 期望 boom，实际 %v", err)
	}
	if err := m.Send("13800138000", "hello"); err != nil {
		t.Fatalf("第二次 Send 期望 nil，实际 %v", err)
	}
	msgs := m.Messages()
	if len(msgs) != 1 {
		t.Fatalf("Messages 长度 = %d，期望 1（失败不记录）", len(msgs))
	}
}

func TestNewAliyunSMSSender_MissingAK(t *testing.T) {
	if _, err := NewAliyunSMSSender(AliyunConfig{}); err == nil {
		t.Fatalf("空 cfg 期望有错，实际 nil")
	} else if !strings.Contains(err.Error(), "未配置") {
		t.Fatalf("错误应含“未配置”，实际 %q", err.Error())
	}

	if _, err := NewAliyunSMSSender(AliyunConfig{AccessKeyID: "test-id"}); err == nil {
		t.Fatalf("只缺 Secret 期望有错，实际 nil")
	} else if !strings.Contains(err.Error(), "未配置") {
		t.Fatalf("错误应含“未配置”，实际 %q", err.Error())
	}
}

func TestBuildSMSMessage(t *testing.T) {
	down := BuildSMSMessage("down", "web", "https://x", "2026-10-16T00:00:00Z", "")
	if !strings.Contains(down, "【sentinel 告警】") {
		t.Fatalf("down 消息应含“【sentinel 告警】”，实际 %q", down)
	}
	if !strings.Contains(down, "web") {
		t.Fatalf("down 消息应含 name，实际 %q", down)
	}

	recovered := BuildSMSMessage("recovered", "web", "https://x", "2026-10-16T00:00:00Z", "")
	if !strings.Contains(recovered, "【sentinel 恢复】") {
		t.Fatalf("recovered 消息应含“【sentinel 恢复】”，实际 %q", recovered)
	}
}

// aliyunPercentEncode 按 RFC3986 编码：A-Za-z0-9 与 -_.~ 不编码，空格→%20，*→%2A。
func aliyunPercentEncode(s string) string {
	var b strings.Builder
	for _, r := range []byte(s) {
		switch {
		case (r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') ||
			r == '-' || r == '_' || r == '.' || r == '~':
			b.WriteByte(r)
		case r == ' ':
			b.WriteString("%20")
		case r == '*':
			b.WriteString("%2A")
		default:
			b.WriteString(fmt.Sprintf("%%%02X", r))
		}
	}
	return b.String()
}

// aliyunSign 独立实现签名，用于交叉验证实现与规范一致。
func aliyunSign(params map[string]string, accessKeySecret string) string {
	keys := make([]string, 0, len(params))
	for k := range params {
		if k == "Signature" {
			continue
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, k := range keys {
		parts = append(parts, aliyunPercentEncode(k)+"="+aliyunPercentEncode(params[k]))
	}
	canonical := strings.Join(parts, "&")
	stringToSign := "POST&%2F&" + aliyunPercentEncode(canonical)
	mac := hmac.New(sha1.New, []byte(accessKeySecret+"&"))
	mac.Write([]byte(stringToSign))
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

func TestAliyunSMSSender_Success(t *testing.T) {
	const (
		akID     = "test-id"     // 示例假值
		akSecret = "test-secret" // 示例假值
		signName = "测试签名"
		tplCode  = "SMS_0001"
	)

	var gotParams url.Values
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Errorf("ParseForm 失败：%v", err)
		}
		gotParams = r.PostForm
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"Code":"OK","Message":"OK"}`))
	}))
	defer srv.Close()

	sender, err := NewAliyunSMSSender(AliyunConfig{
		AccessKeyID:     akID,
		AccessKeySecret: akSecret,
		SignName:        signName,
		TemplateCode:    tplCode,
	})
	if err != nil {
		t.Fatalf("NewAliyunSMSSender 期望无错，实际 %v", err)
	}
	// 包内测试可直接替换未导出字段指向 TLS 测试服务器
	sender.cfg.HTTPClient = srv.Client()
	sender.cfg.Endpoint = srv.Listener.Addr().String()

	if err := sender.Send("13800138000", "hello"); err != nil {
		t.Fatalf("Send 期望无错，实际 %v", err)
	}

	if gotParams == nil {
		t.Fatalf("服务端未收到请求")
	}
	if gotParams.Get("Action") != "SendSms" {
		t.Fatalf("Action = %q，期望 SendSms", gotParams.Get("Action"))
	}
	if gotParams.Get("PhoneNumbers") != "13800138000" {
		t.Fatalf("PhoneNumbers = %q，期望 13800138000", gotParams.Get("PhoneNumbers"))
	}
	if gotParams.Get("SignName") != signName {
		t.Fatalf("SignName = %q，期望 %q", gotParams.Get("SignName"), signName)
	}
	if gotParams.Get("TemplateCode") != tplCode {
		t.Fatalf("TemplateCode = %q，期望 %q", gotParams.Get("TemplateCode"), tplCode)
	}
	if !strings.Contains(gotParams.Get("TemplateParam"), "msg") {
		t.Fatalf("TemplateParam 应含 msg，实际 %q", gotParams.Get("TemplateParam"))
	}
	if gotParams.Get("Signature") == "" {
		t.Fatalf("Signature 不应为空")
	}

	// 交叉验证签名
	params := map[string]string{}
	for k := range gotParams {
		params[k] = gotParams.Get(k)
	}
	wantSig := aliyunSign(params, akSecret)
	if gotParams.Get("Signature") != wantSig {
		t.Fatalf("Signature = %q，期望 %q", gotParams.Get("Signature"), wantSig)
	}
}

func TestAliyunSMSSender_RetryOnce(t *testing.T) {
	const (
		akID     = "test-id"     // 示例假值
		akSecret = "test-secret" // 示例假值
	)

	hits := 0
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.Header().Set("Content-Type", "application/json")
		if hits == 1 {
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte(`{"Code":"InternalError"}`))
			return
		}
		_, _ = w.Write([]byte(`{"Code":"OK","Message":"OK"}`))
	}))
	defer srv.Close()

	sender, err := NewAliyunSMSSender(AliyunConfig{
		AccessKeyID:     akID,
		AccessKeySecret: akSecret,
		SignName:        "测试签名",
		TemplateCode:    "SMS_0001",
	})
	if err != nil {
		t.Fatalf("NewAliyunSMSSender 期望无错，实际 %v", err)
	}
	sender.cfg.HTTPClient = srv.Client()
	sender.cfg.Endpoint = srv.Listener.Addr().String()

	if err := sender.Send("13800138000", "hello"); err != nil {
		t.Fatalf("Send 期望无错（重试后成功），实际 %v", err)
	}
	if hits != 2 {
		t.Fatalf("服务端命中次数 = %d，期望 2", hits)
	}
}

func TestAliyunSMSSender_PersistentFailure(t *testing.T) {
	const (
		akID     = "test-id"     // 示例假值
		akSecret = "test-secret" // 示例假值
	)

	hits := 0
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"Code":"isv.SMS_SIGNATURE_ERROR","Message":"签名错"}`))
	}))
	defer srv.Close()

	sender, err := NewAliyunSMSSender(AliyunConfig{
		AccessKeyID:     akID,
		AccessKeySecret: akSecret,
		SignName:        "测试签名",
		TemplateCode:    "SMS_0001",
	})
	if err != nil {
		t.Fatalf("NewAliyunSMSSender 期望无错，实际 %v", err)
	}
	sender.cfg.HTTPClient = srv.Client()
	sender.cfg.Endpoint = srv.Listener.Addr().String()

	if err := sender.Send("13800138000", "hello"); err == nil {
		t.Fatalf("Send 期望非空错误，实际 nil")
	}
	if hits != 2 {
		t.Fatalf("服务端命中次数 = %d，期望 2（重试一次）", hits)
	}
}
