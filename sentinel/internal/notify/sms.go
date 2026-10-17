package notify

import (
	"bytes"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha1"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"sentinel/internal/log"
)

// 中国大陆手机号正则：1 开头，第二位 3-9，共 11 位数字。
var cnPhoneRe = regexp.MustCompile(`^1[3-9]\d{9}$`)

// 国际手机号正则：+ 开头，后接 7~15 位数字。
var intlPhoneRe = regexp.MustCompile(`^\+\d{7,15}$`)

// ErrSMSNotConfigured 表示短信通道未配置。
var ErrSMSNotConfigured = errors.New("短信通道未配置")

// smsNow 返回当前 UTC 时间的 RFC3339 字符串。
func smsNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// ValidatePhone 校验手机号：去首尾空白后匹配中国大陆或国际号码格式。
func ValidatePhone(phone string) error {
	p := strings.TrimSpace(phone)
	if cnPhoneRe.MatchString(p) || intlPhoneRe.MatchString(p) {
		return nil
	}
	return fmt.Errorf("手机号 %q 非法：需为中国大陆号码（1[3-9]xxxxxxxxx）或国际号码（+ 后 7~15 位数字）", phone)
}

// ParsePhones 解析逗号分隔的手机号列表，去空白、去重、保序。
func ParsePhones(s string) ([]string, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil, nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	seen := make(map[string]struct{}, len(parts))
	idx := 0
	for _, raw := range parts {
		p := strings.TrimSpace(raw)
		if p == "" {
			continue
		}
		idx++
		if err := ValidatePhone(p); err != nil {
			return nil, fmt.Errorf("第 %d 个手机号 %s 非法：%v", idx, p, err)
		}
		if _, ok := seen[p]; ok {
			continue
		}
		seen[p] = struct{}{}
		out = append(out, p)
	}
	if len(out) == 0 {
		return nil, nil
	}
	return out, nil
}

// SentSMS 记录一条已发送短信。
type SentSMS struct {
	Phone   string
	Message string
	At      string
}

// SmsSender 短信发送接口。
type SmsSender interface {
	Send(phone, message string) error
}

// MockSmsSender 用于测试与演示的模拟发送器。
type MockSmsSender struct {
	sync.Mutex
	Sent      []SentSMS
	FailCount int
	FailErr   error
}

// Send 模拟发送：先校验手机号；FailCount>0 时前 N 次返回 FailErr（不记录）。
func (m *MockSmsSender) Send(phone, message string) error {
	if err := ValidatePhone(phone); err != nil {
		return err
	}
	m.Lock()
	defer m.Unlock()
	if m.FailCount > 0 {
		m.FailCount--
		if m.FailErr != nil {
			return m.FailErr
		}
		return errors.New("模拟发送失败")
	}
	m.Sent = append(m.Sent, SentSMS{Phone: phone, Message: message, At: smsNow()})
	log.Logger().Info("Mock 短信发送", "phone", phone, "len", len(message))
	return nil
}

// Messages 返回已发送记录的副本。
func (m *MockSmsSender) Messages() []SentSMS {
	m.Lock()
	defer m.Unlock()
	out := make([]SentSMS, len(m.Sent))
	copy(out, m.Sent)
	return out
}

// Reset 清空已发送记录与失败计数。
func (m *MockSmsSender) Reset() {
	m.Lock()
	defer m.Unlock()
	m.Sent = nil
	m.FailCount = 0
	m.FailErr = nil
}

// AliyunConfig 阿里云短信通道配置。
type AliyunConfig struct {
	AccessKeyID     string
	AccessKeySecret string
	SignName        string
	TemplateCode    string
	Endpoint        string
	RegionID        string
	HTTPClient      *http.Client
}

// AliyunSMSSender 阿里云短信 HTTP 实现。
type AliyunSMSSender struct {
	cfg AliyunConfig
}

// NewAliyunSMSSender 构造阿里云短信发送器。
func NewAliyunSMSSender(cfg AliyunConfig) (*AliyunSMSSender, error) {
	if strings.TrimSpace(cfg.AccessKeyID) == "" || strings.TrimSpace(cfg.AccessKeySecret) == "" {
		return nil, errors.New("短信通道未配置：缺少阿里云 AccessKeyID/AccessKeySecret，请设置 SENTINEL_SMS_ACCESS_KEY_ID 与 SENTINEL_SMS_ACCESS_KEY_SECRET")
	}
	if strings.TrimSpace(cfg.Endpoint) == "" {
		cfg.Endpoint = "dysmsapi.aliyuncs.com"
	}
	if strings.TrimSpace(cfg.RegionID) == "" {
		cfg.RegionID = "cn-hangzhou"
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 10 * time.Second}
	}
	return &AliyunSMSSender{cfg: cfg}, nil
}

// percentEncode 按 RFC 3986 对字符串进行百分号编码。
func percentEncode(s string) string {
	var buf bytes.Buffer
	for i := 0; i < len(s); i++ {
		c := s[i]
		if (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
			c == '-' || c == '_' || c == '.' || c == '~' {
			buf.WriteByte(c)
			continue
		}
		buf.WriteString(fmt.Sprintf("%%%02X", c))
	}
	return buf.String()
}

// uuid4 用 crypto/rand 生成 16 随机字节，拼成 8-4-4-4-12 格式的 hex 字符串。
func uuid4() (string, error) {
	var b [16]byte
	if _, err := io.ReadFull(rand.Reader, b[:]); err != nil {
		return "", err
	}
	h := hex.EncodeToString(b[:])
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:32], nil
}

// sign 计算阿里云 HMAC-SHA1 签名。
func (s *AliyunSMSSender) sign(params map[string]string) string {
	keys := make([]string, 0, len(params))
	for k := range params {
		if k == "Signature" {
			continue
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var parts []string
	for _, k := range keys {
		parts = append(parts, percentEncode(k)+"="+percentEncode(params[k]))
	}
	canonical := strings.Join(parts, "&")
	stringToSign := "POST" + "&" + percentEncode("/") + "&" + percentEncode(canonical)
	mac := hmac.New(sha1.New, []byte(s.cfg.AccessKeySecret+"&"))
	mac.Write([]byte(stringToSign))
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

// Send 发送单条短信；失败时重试一次（共 2 次尝试，间隔 2 秒）。
// 说明：模板变量固定为 ${msg}，阿里云短信模板需定义该变量；
// 短信正文建议由调用方控制在 70 字内以节省费用。
func (s *AliyunSMSSender) Send(phone, message string) error {
	if err := ValidatePhone(phone); err != nil {
		return err
	}
	templateParam, err := json.Marshal(map[string]string{"msg": message})
	if err != nil {
		return fmt.Errorf("序列化短信模板参数失败：%w", err)
	}

	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			time.Sleep(2 * time.Second)
		}
		lastErr = s.doSend(phone, string(templateParam))
		if lastErr == nil {
			return nil
		}
		log.Logger().Warn("发送阿里云短信失败", "phone", phone, "attempt", attempt+1, "error", lastErr)
	}
	return fmt.Errorf("发送短信失败（共尝试 2 次）：%w", lastErr)
}

// doSend 执行一次阿里云短信请求。
func (s *AliyunSMSSender) doSend(phone, templateParam string) error {
	nonce, err := uuid4()
	if err != nil {
		return fmt.Errorf("生成签名随机数失败：%w", err)
	}
	params := map[string]string{
		"Action":           "SendSms",
		"Version":          "2017-05-25",
		"RegionId":         s.cfg.RegionID,
		"Format":           "JSON",
		"SignatureMethod":  "HMAC-SHA1",
		"SignatureVersion": "1.0",
		"SignatureNonce":   nonce,
		"Timestamp":        time.Now().UTC().Format("2006-01-02T15:04:05Z"),
		"AccessKeyId":      s.cfg.AccessKeyID,
		"PhoneNumbers":     phone,
		"SignName":         s.cfg.SignName,
		"TemplateCode":     s.cfg.TemplateCode,
		"TemplateParam":    templateParam,
	}
	params["Signature"] = s.sign(params)

	form := url.Values{}
	for k, v := range params {
		form.Set(k, v)
	}
	endpoint := strings.TrimSpace(s.cfg.Endpoint)
	endpoint = strings.TrimPrefix(endpoint, "https://")
	endpoint = strings.TrimPrefix(endpoint, "http://")
	reqURL := "https://" + endpoint + "/"
	req, err := http.NewRequest(http.MethodPost, reqURL, strings.NewReader(form.Encode()))
	if err != nil {
		return fmt.Errorf("构造短信请求失败：%w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := s.cfg.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("请求阿里云短信接口失败：%w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("读取阿里云短信响应失败：%w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("阿里云短信返回状态码 %d：%s", resp.StatusCode, string(body))
	}
	var result struct {
		Code    string `json:"Code"`
		Message string `json:"Message"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return fmt.Errorf("解析阿里云短信响应失败：%w，原文：%s", err, string(body))
	}
	if result.Code != "OK" {
		return fmt.Errorf("阿里云短信发送失败：Code=%s Message=%s", result.Code, result.Message)
	}
	return nil
}

// SMSConfig 短信通道配置。
type SMSConfig struct {
	Mode    string
	Phones  []string
	Aliyun  AliyunConfig
	Tencent TencentConfig
}

// BuildSender 根据 Mode 构造短信发送器。
func (c SMSConfig) BuildSender() (SmsSender, error) {
	switch strings.ToLower(strings.TrimSpace(c.Mode)) {
	case "mock":
		return &MockSmsSender{}, nil
	case "aliyun":
		return NewAliyunSMSSender(c.Aliyun)
	case "tencent":
		return NewTencentSMSSender(c.Tencent)
	default:
		return nil, ErrSMSNotConfigured
	}
}

// BuildSMSMessage 构造纯文本短信正文，带【sentinel】前缀以标识发送方。
func BuildSMSMessage(event, name, target, at, errMsg string) string {
	switch event {
	case "down":
		msg := fmt.Sprintf("【sentinel 告警】%s 宕机，目标 %s，时间 %s", name, target, at)
		if errMsg != "" {
			msg += "，错误：" + errMsg
		}
		return msg
	case "recovered":
		return fmt.Sprintf("【sentinel 恢复】%s 已恢复，目标 %s，时间 %s", name, target, at)
	default:
		return fmt.Sprintf("【sentinel】%s %s，目标 %s，时间 %s", name, event, target, at)
	}
}
