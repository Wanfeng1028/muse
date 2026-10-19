package notify

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"sentinel/internal/log"
)

// TencentConfig 腾讯云短信发送器配置。
type TencentConfig struct {
	SecretId   string
	SecretKey  string
	SmsSdkAppId string
	SignName   string
	TemplateId string
	Region     string
	Endpoint   string
	HTTPClient *http.Client
}

// TencentSMSSender 腾讯云短信发送器。
type TencentSMSSender struct {
	secretId    string
	secretKey   string
	smsSdkAppId string
	signName    string
	templateId  string
	region      string
	endpoint    string
	httpClient  *http.Client
}

// Provider 返回发送器标识，供短信发送记录使用。
func (s *TencentSMSSender) Provider() string { return "tencent" }

// NewTencentSMSSender 创建腾讯云短信发送器。
func NewTencentSMSSender(cfg TencentConfig) (*TencentSMSSender, error) {
	if cfg.SecretId == "" {
		return nil, fmt.Errorf("腾讯云短信 SecretId 为空，请配置 SENTINEL_SMS_TENCENT_SECRET_ID")
	}
	if cfg.SecretKey == "" {
		return nil, fmt.Errorf("腾讯云短信 SecretKey 为空，请配置 SENTINEL_SMS_TENCENT_SECRET_KEY")
	}
	endpoint := cfg.Endpoint
	if endpoint == "" {
		endpoint = "sms.tencentcloudapi.com"
	}
	region := cfg.Region
	if region == "" {
		region = "ap-guangzhou"
	}
	client := cfg.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	return &TencentSMSSender{
		secretId:    cfg.SecretId,
		secretKey:   cfg.SecretKey,
		smsSdkAppId: cfg.SmsSdkAppId,
		signName:    cfg.SignName,
		templateId:  cfg.TemplateId,
		region:      region,
		endpoint:    endpoint,
		httpClient:  client,
	}, nil
}

// tencentSign 按腾讯云 TC3-HMAC-SHA256 规范计算 Authorization 头值。
// payload 必须是紧凑 JSON（无空格），由调用方保证。
func tencentSign(secretId, secretKey, host string, payload []byte, timestamp int64) string {
	// 第一步：拼 CanonicalRequest
	canonicalHeaders := "content-type:application/json\nhost:" + host + "\n"
	signedHeaders := "content-type;host"
	hashedPayload := sha256Hex(payload)
	canonicalRequest := "POST\n/\n\n" + canonicalHeaders + "\n" + signedHeaders + "\n" + hashedPayload

	// 第二步：拼 StringToSign
	date := time.Unix(timestamp, 0).UTC().Format("2006-01-02")
	credentialScope := date + "/sms/tc3_request"
	hashedCanonical := sha256Hex([]byte(canonicalRequest))
	stringToSign := "TC3-HMAC-SHA256\n" + fmt.Sprintf("%d", timestamp) + "\n" + credentialScope + "\n" + hashedCanonical

	// 第三步：逐层派生签名密钥并签名
	secretDate := hmacSHA256([]byte("TC3"+secretKey), []byte(date))
	secretService := hmacSHA256(secretDate, []byte("sms"))
	secretSigning := hmacSHA256(secretService, []byte("tc3_request"))
	signature := hex.EncodeToString(hmacSHA256(secretSigning, []byte(stringToSign)))

	return "TC3-HMAC-SHA256 Credential=" + secretId + "/" + credentialScope +
		", SignedHeaders=" + signedHeaders + ", Signature=" + signature
}

// sha256Hex 返回字节切片的 SHA256 十六进制小写字符串。
func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// hmacSHA256 返回 HMAC-SHA256 原始字节。
func hmacSHA256(key, data []byte) []byte {
	mac := hmac.New(sha256.New, key)
	mac.Write(data)
	return mac.Sum(nil)
}

// toE164 把大陆 11 位号码补 "+86" 前缀，已带 "+" 的号码保持不变。
func toE164(phone string) string {
	if strings.HasPrefix(phone, "+") {
		return phone
	}
	return "+86" + phone
}

// Send 发送短信，失败重试 1 次（共 2 次，间隔 2 秒）。
// 模板必须定义 1 个变量，对应阿里云渠道的 ${msg} 约定。
func (s *TencentSMSSender) Send(phone, message string) error {
	if err := ValidatePhone(phone); err != nil {
		return err
	}
	e164 := toE164(phone)
	payload, err := json.Marshal(map[string]interface{}{
		"PhoneNumberSet":   []string{e164},
		"SmsSdkAppId":      s.smsSdkAppId,
		"SignName":         s.signName,
		"TemplateId":       s.templateId,
		"TemplateParamSet": []string{message},
	})
	if err != nil {
		return fmt.Errorf("序列化腾讯云短信请求失败: %w", err)
	}

	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			time.Sleep(2 * time.Second)
		}
		lastErr = s.doSend(e164, payload)
		if lastErr == nil {
			return nil
		}
		log.Logger().Warn("腾讯云短信发送失败", "phone", e164, "attempt", attempt+1, "err", lastErr)
	}
	return lastErr
}

// doSend 发起一次腾讯云短信请求。
func (s *TencentSMSSender) doSend(e164 string, payload []byte) error {
	timestamp := time.Now().Unix()
	host := s.endpoint
	authorization := tencentSign(s.secretId, s.secretKey, host, payload, timestamp)

	url := "https://" + s.endpoint + "/"
	if strings.HasPrefix(s.endpoint, "http://") {
		url = s.endpoint + "/"
		host = strings.TrimPrefix(s.endpoint, "http://")
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("构造腾讯云短信请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-TC-Action", "SendSms")
	req.Header.Set("X-TC-Timestamp", fmt.Sprintf("%d", timestamp))
	req.Header.Set("X-TC-Version", "2021-01-11")
	req.Header.Set("X-TC-Region", s.region)
	req.Header.Set("Authorization", authorization)

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("请求腾讯云短信接口失败: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("读取腾讯云短信响应失败: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("腾讯云短信接口返回状态码 %d: %s", resp.StatusCode, string(body))
	}

	var result struct {
		Response struct {
			SendStatusSet []struct {
				Code        string `json:"Code"`
				Message     string `json:"Message"`
				PhoneNumber string `json:"PhoneNumber"`
			} `json:"SendStatusSet"`
			RequestId string `json:"RequestId"`
		} `json:"Response"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return fmt.Errorf("解析腾讯云短信响应失败: %w", err)
	}
	if len(result.Response.SendStatusSet) == 0 {
		return fmt.Errorf("腾讯云短信响应缺少 SendStatusSet: %s", string(body))
	}
	status := result.Response.SendStatusSet[0]
	if status.Code != "Ok" {
		return fmt.Errorf("腾讯云短信发送失败: Code=%s Message=%s PhoneNumber=%s", status.Code, status.Message, status.PhoneNumber)
	}
	return nil
}