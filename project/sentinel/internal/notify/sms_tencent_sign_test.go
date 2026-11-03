package notify

import (
	"strings"
	"testing"
)

func TestTencentSign_FixedVector(t *testing.T) {
	secretId := "AKID" + "z8krbsJ5yKBZQpn74WFkmLPx3" + "EXAMPLE"
	secretKey := "Gu5t9xGARNpq86cd98joQYCN3" + "EXAMPLE"
	host := "sms.tencentcloudapi.com"
	timestamp := int64(1551113065)
	payload := []byte(`{"PhoneNumberSet":["+8613711112222"],"SmsSdkAppId":"1400006666","SignName":"test","TemplateId":"1110","TemplateParamSet":["1234"]}`)
	expectedSignature := "be8acb9d3ed0a2318cd7f83d178a155bdb2f5fac52a4c0c73ca0b15cb17a692b"

	got := tencentSign(secretId, secretKey, host, payload, timestamp)

	expectedPrefix := "TC3-HMAC-SHA256 Credential=" + secretId + "/2019-02-25/sms/tc3_request, SignedHeaders=content-type;host, Signature="
	if !strings.HasPrefix(got, expectedPrefix) {
		t.Fatalf("Authorization 前缀不对\n期望前缀: %s\n实际结果: %s", expectedPrefix, got)
	}
	if !strings.HasSuffix(got, expectedSignature) {
		t.Fatalf("Authorization 签名后缀不对\n期望后缀: %s\n实际结果: %s", expectedSignature, got)
	}
}

func TestTencentSign_Deterministic(t *testing.T) {
	secretId := "AKID" + "z8krbsJ5yKBZQpn74WFkmLPx3" + "EXAMPLE"
	secretKey := "Gu5t9xGARNpq86cd98joQYCN3" + "EXAMPLE"
	host := "sms.tencentcloudapi.com"
	timestamp := int64(1551113065)
	payload := []byte(`{"PhoneNumberSet":["+8613711112222"],"SmsSdkAppId":"1400006666","SignName":"test","TemplateId":"1110","TemplateParamSet":["1234"]}`)

	first := tencentSign(secretId, secretKey, host, payload, timestamp)
	second := tencentSign(secretId, secretKey, host, payload, timestamp)
	if first != second {
		t.Fatalf("同一输入两次调用结果不一致\n第一次: %s\n第二次: %s", first, second)
	}

	other := tencentSign(secretId, secretKey, host, payload, timestamp+1)
	if first == other {
		t.Fatalf("timestamp 加一后签名不应该相同，两次都是: %s", first)
	}
}