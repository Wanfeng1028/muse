package notify

import (
	"crypto/tls"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"sentinel/internal/log"
)

func TestSmsDeepValidatePhone(t *testing.T) {
	log.Init("error")

	cases := []struct {
		name    string
		phone   string
		wantErr bool
	}{
		{"合法大陆号码", "13800138000", false},
		{"合法大陆号码带空白", "  13800138000  ", false},
		{"合法国际号码", "+8613800138000", false},
		{"空字符串", "", true},
		{"只有空白", "   ", true},
		{"大陆号码少一位", "1380013800", true},
		{"大陆号码多一位", "138001380000", true},
		{"大陆号码以 2 开头", "12800138000", true},
		{"国际号码无加号", "8613800138000", true},
		{"国际号码位数不足", "+123456", true},
		{"国际号码位数超限", "+1234567890123456", true},
		{"含字母", "1380013800a", true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := ValidatePhone(tc.phone)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("ValidatePhone(%q) 期望报错，实际返回 nil", tc.phone)
				}
				if !strings.Contains(err.Error(), "非法") {
					t.Fatalf("ValidatePhone(%q) 错误信息应包含“非法”，实际为 %v", tc.phone, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("ValidatePhone(%q) 期望通过，实际报错 %v", tc.phone, err)
			}
		})
	}
}

func TestSmsDeepParsePhones(t *testing.T) {
	log.Init("error")

	cases := []struct {
		name    string
		input   string
		want    []string
		wantErr bool
	}{
		{"空字符串返回 nil", "", nil, false},
		{"只有逗号返回 nil", ",,,", nil, false},
		{"单个号码", "13800138000", []string{"13800138000"}, false},
		{"多个号码保序", "13800138000,13900139000,+8613700137000", []string{"13800138000", "13900139000", "+8613700137000"}, false},
		{"去重保序", "13800138000,13800138000,13900139000", []string{"13800138000", "13900139000"}, false},
		{"带空白与空项", " 13800138000 , , 13900139000 ", []string{"13800138000", "13900139000"}, false},
		{"含非法号码", "13800138000,abc", nil, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := ParsePhones(tc.input)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("ParsePhones(%q) 期望报错，实际返回 nil", tc.input)
				}
				if !strings.Contains(err.Error(), "非法") {
					t.Fatalf("ParsePhones(%q) 错误信息应包含“非法”，实际为 %v", tc.input, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("ParsePhones(%q) 期望通过，实际报错 %v", tc.input, err)
			}
			if len(got) != len(tc.want) {
				t.Fatalf("ParsePhones(%q) 长度期望 %d，实际 %d，结果 %v", tc.input, len(tc.want), len(got), got)
			}
			for i := range tc.want {
				if got[i] != tc.want[i] {
					t.Fatalf("ParsePhones(%q) 第 %d 项期望 %q，实际 %q", tc.input, i, tc.want[i], got[i])
				}
			}
		})
	}
}

func TestSmsDeepParsePhonesEmptyTargetReturnsNil(t *testing.T) {
	log.Init("error")

	got, err := ParsePhones("   ")
	if err != nil {
		t.Fatalf("ParsePhones 空目标期望 nil error，实际 %v", err)
	}
	if got != nil {
		t.Fatalf("ParsePhones 空目标期望 nil 切片，实际 %v", got)
	}

	got2, err2 := ParsePhones(",,,")
	if err2 != nil {
		t.Fatalf("ParsePhones 全逗号期望 nil error，实际 %v", err2)
	}
	if got2 != nil {
		t.Fatalf("ParsePhones 全逗号期望 nil 切片，实际 %v", got2)
	}
}

func TestSmsDeepMockSenderSuccess(t *testing.T) {
	log.Init("error")

	m := &MockSmsSender{}
	if err := m.Send("13800138000", "验证码 123456"); err != nil {
		t.Fatalf("MockSmsSender.Send 期望成功，实际 %v", err)
	}
	if err := m.Send("13900139000", "验证码 654321"); err != nil {
		t.Fatalf("MockSmsSender.Send 第二次期望成功，实际 %v", err)
	}

	msgs := m.Messages()
	if len(msgs) != 2 {
		t.Fatalf("Messages 期望 2 条，实际 %d 条", len(msgs))
	}
	if msgs[0].Phone != "13800138000" || msgs[0].Message != "验证码 123456" {
		t.Fatalf("第 1 条记录不符，实际 %+v", msgs[0])
	}
	if msgs[1].Phone != "13900139000" || msgs[1].Message != "验证码 654321" {
		t.Fatalf("第 2 条记录不符，实际 %+v", msgs[1])
	}
	if _, err := time.Parse(time.RFC3339, msgs[0].At); err != nil {
		t.Fatalf("记录时间 At 不是 RFC3339 格式：%q，err=%v", msgs[0].At, err)
	}

	msgs[0].Phone = "mutated"
	if m.Messages()[0].Phone != "13800138000" {
		t.Fatalf("Messages 应返回副本，外部修改不应影响内部记录")
	}
}

func TestSmsDeepMockSenderInvalidPhoneNotRecorded(t *testing.T) {
	log.Init("error")

	m := &MockSmsSender{}
	err := m.Send("not-a-phone", "hi")
	if err == nil {
		t.Fatalf("MockSmsSender.Send 非法号码期望报错，实际 nil")
	}
	if !strings.Contains(err.Error(), "非法") {
		t.Fatalf("非法号码错误信息应包含“非法”，实际 %v", err)
	}
	if len(m.Messages()) != 0 {
		t.Fatalf("非法号码不应被记录，实际记录 %d 条", len(m.Messages()))
	}
}

func TestSmsDeepMockSenderFailInjection(t *testing.T) {
	log.Init("error")

	injected := errors.New("注入的网络错误")
	m := &MockSmsSender{FailCount: 2, FailErr: injected}

	for i := 0; i < 2; i++ {
		err := m.Send("13800138000", fmt.Sprintf("第 %d 次", i))
		if err == nil {
			t.Fatalf("第 %d 次发送期望报错，实际 nil", i+1)
		}
		if !errors.Is(err, injected) {
			t.Fatalf("第 %d 次发送期望注入错误，实际 %v", i+1, err)
		}
	}
	if len(m.Messages()) != 0 {
		t.Fatalf("失败注入期间不应记录，实际 %d 条", len(m.Messages()))
	}

	if err := m.Send("13800138000", "第三次"); err != nil {
		t.Fatalf("第 3 次发送期望成功，实际 %v", err)
	}
	if len(m.Messages()) != 1 {
		t.Fatalf("第 3 次发送后期望 1 条记录，实际 %d 条", len(m.Messages()))
	}
	if m.Messages()[0].Message != "第三次" {
		t.Fatalf("第 3 次记录内容不符，实际 %+v", m.Messages()[0])
	}
}

func TestSmsDeepMockSenderReset(t *testing.T) {
	log.Init("error")

	m := &MockSmsSender{FailCount: 1, FailErr: errors.New("x")}
	if err := m.Send("13800138000", "a"); err == nil {
		t.Fatalf("期望第一次因 FailCount 报错")
	}
	m.Reset()

	if m.FailCount != 0 || m.FailErr != nil {
		t.Fatalf("Reset 后 FailCount/FailErr 应清零，实际 FailCount=%d FailErr=%v", m.FailCount, m.FailErr)
	}
	if len(m.Messages()) != 0 {
		t.Fatalf("Reset 后记录应为空，实际 %d 条", len(m.Messages()))
	}
	if err := m.Send("13800138000", "after-reset"); err != nil {
		t.Fatalf("Reset 后发送期望成功，实际 %v", err)
	}
	if len(m.Messages()) != 1 || m.Messages()[0].Message != "after-reset" {
		t.Fatalf("Reset 后记录不符，实际 %+v", m.Messages())
	}
}

func TestSmsDeepNewAliyunSMSSenderConfig(t *testing.T) {
	log.Init("error")

	cases := []struct {
		name    string
		cfg     AliyunConfig
		wantErr bool
	}{
		{"缺 AccessKeyID", AliyunConfig{AccessKeySecret: "s"}, true},
		{"缺 AccessKeySecret", AliyunConfig{AccessKeyID: "id"}, true},
		{"空白 ID", AliyunConfig{AccessKeyID: "   ", AccessKeySecret: "s"}, true},
		{"空白 Secret", AliyunConfig{AccessKeyID: "id", AccessKeySecret: "   "}, true},
		{"合法配置补默认值", AliyunConfig{AccessKeyID: "id", AccessKeySecret: "secret"}, false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s, err := NewAliyunSMSSender(tc.cfg)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("NewAliyunSMSSender 期望报错，实际 nil")
				}
				if !strings.Contains(err.Error(), "短信通道未配置") {
					t.Fatalf("错误信息应包含“短信通道未配置”，实际 %v", err)
				}
				return
			}
			if err != nil {
				t.Fatalf("NewAliyunSMSSender 期望成功，实际 %v", err)
			}
			if s.cfg.Endpoint != "dysmsapi.aliyuncs.com" {
				t.Fatalf("Endpoint 默认值应为 dysmsapi.aliyuncs.com，实际 %q", s.cfg.Endpoint)
			}
			if s.cfg.RegionID != "cn-hangzhou" {
				t.Fatalf("RegionID 默认值应为 cn-hangzhou，实际 %q", s.cfg.RegionID)
			}
			if s.cfg.HTTPClient == nil || s.cfg.HTTPClient.Timeout != 10*time.Second {
				t.Fatalf("HTTPClient 默认超时应为 10s，实际 %+v", s.cfg.HTTPClient)
			}
		})
	}
}

func TestSmsDeepAliyunSendInvalidPhoneNoRequest(t *testing.T) {
	log.Init("error")

	var hits int32
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		hits++
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	s, err := NewAliyunSMSSender(AliyunConfig{
		AccessKeyID:     "id",
		AccessKeySecret: "secret",
		SignName:        "sign",
		TemplateCode:    "SMS_1",
		Endpoint:        strings.TrimPrefix(srv.URL, "http://"),
		HTTPClient:      srv.Client(),
	})
	if err != nil {
		t.Fatalf("构造发送器失败：%v", err)
	}

	if err := s.Send("bad-phone", "hi"); err == nil {
		t.Fatalf("非法号码期望报错，实际 nil")
	} else if !strings.Contains(err.Error(), "非法") {
		t.Fatalf("非法号码错误信息应包含“非法”，实际 %v", err)
	}

	mu.Lock()
	got := hits
	mu.Unlock()
	if got != 0 {
		t.Fatalf("非法号码不应发起 HTTP 请求，实际请求 %d 次", got)
	}
}

func TestSmsDeepAliyunSendNetworkErrorRetries(t *testing.T) {
	log.Init("error")

	var mu sync.Mutex
	var hits int
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		hits++
		mu.Unlock()
		panic(http.ErrAbortHandler)
	}))
	defer srv.Close()

	cfg := AliyunConfig{
		AccessKeyID:     "id",
		AccessKeySecret: "secret",
		SignName:        "sign",
		TemplateCode:    "SMS_1",
		Endpoint:        strings.TrimPrefix(srv.URL, "https://"),
		HTTPClient:      srv.Client(),
	}
	s, err := NewAliyunSMSSender(cfg)
	if err != nil {
		t.Fatalf("构造发送器失败：%v", err)
	}

	start := time.Now()
	err = s.Send("13800138000", "hello")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatalf("网络错误期望最终报错，实际 nil")
	}
	if !strings.Contains(err.Error(), "共尝试 2 次") {
		t.Fatalf("错误信息应说明尝试 2 次，实际 %v", err)
	}
	if elapsed < 2*time.Second {
		t.Fatalf("重试间隔应至少 2s，实际耗时 %v", elapsed)
	}

	mu.Lock()
	got := hits
	mu.Unlock()
	if got != 2 {
		t.Fatalf("网络错误应尝试 2 次，实际 %d 次", got)
	}
}

func TestSmsDeepAliyunSendProbeTimeout(t *testing.T) {
	log.Init("error")

	var mu sync.Mutex
	var hits int
	release := make(chan struct{})
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		hits++
		mu.Unlock()
		<-release
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	defer close(release)

	cfg := AliyunConfig{
		AccessKeyID:     "id",
		AccessKeySecret: "secret",
		SignName:        "sign",
		TemplateCode:    "SMS_1",
		Endpoint:        strings.TrimPrefix(srv.URL, "https://"),
		HTTPClient:      &http.Client{Timeout: 300 * time.Millisecond, Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}},
	}
	s, err := NewAliyunSMSSender(cfg)
	if err != nil {
		t.Fatalf("构造发送器失败：%v", err)
	}

	start := time.Now()
	err = s.Send("13800138000", "hello")
	elapsed := time.Since(start)

	if err == nil {
		t.Fatalf("探针超时期望报错，实际 nil")
	}
	if !strings.Contains(err.Error(), "共尝试 2 次") {
		t.Fatalf("超时错误信息应说明尝试 2 次，实际 %v", err)
	}
	if elapsed > 5*time.Second {
		t.Fatalf("超时场景总耗时应远小于 5s，实际 %v", elapsed)
	}

	mu.Lock()
	got := hits
	mu.Unlock()
	if got != 2 {
		t.Fatalf("超时应尝试 2 次，实际 %d 次", got)
	}
}

func TestSmsDeepMockSenderConcurrent(t *testing.T) {
	log.Init("error")

	m := &MockSmsSender{}
	const goroutines = 50
	const perGoroutine = 4

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for g := 0; g < goroutines; g++ {
		go func(id int) {
			defer wg.Done()
			for i := 0; i < perGoroutine; i++ {
				phone := fmt.Sprintf("138%08d", id*perGoroutine+i)
				if err := m.Send(phone, fmt.Sprintf("g%d-i%d", id, i)); err != nil {
					t.Errorf("并发发送失败：phone=%s err=%v", phone, err)
				}
			}
		}(g)
	}
	wg.Wait()

	msgs := m.Messages()
	if len(msgs) != goroutines*perGoroutine {
		t.Fatalf("并发发送期望 %d 条，实际 %d 条", goroutines*perGoroutine, len(msgs))
	}
	seen := make(map[string]struct{}, len(msgs))
	for _, msg := range msgs {
		if _, dup := seen[msg.Phone]; dup {
			t.Fatalf("并发发送出现重复号码：%s", msg.Phone)
		}
		seen[msg.Phone] = struct{}{}
	}
}

func TestSmsDeepMockSenderIdempotentReset(t *testing.T) {
	log.Init("error")

	m := &MockSmsSender{FailCount: 3, FailErr: errors.New("boom")}
	if err := m.Send("13800138000", "x"); err == nil {
		t.Fatalf("首次发送期望因 FailCount 报错")
	}

	m.Reset()
	m.Reset()
	m.Reset()

	if m.FailCount != 0 {
		t.Fatalf("多次 Reset 后 FailCount 应为 0，实际 %d", m.FailCount)
	}
	if m.FailErr != nil {
		t.Fatalf("多次 Reset 后 FailErr 应为 nil，实际 %v", m.FailErr)
	}
	if len(m.Messages()) != 0 {
		t.Fatalf("多次 Reset 后记录应为空，实际 %d 条", len(m.Messages()))
	}

	if err := m.Send("13800138000", "y"); err != nil {
		t.Fatalf("多次 Reset 后发送应成功，实际 %v", err)
	}
	if len(m.Messages()) != 1 || m.Messages()[0].Message != "y" {
		t.Fatalf("多次 Reset 后记录不符，实际 %+v", m.Messages())
	}
}

func TestSmsDeepParsePhonesLongInput(t *testing.T) {
	log.Init("error")

	parts := make([]string, 0, 500)
	for i := 0; i < 500; i++ {
		parts = append(parts, fmt.Sprintf("138%08d", i))
	}
	input := strings.Join(parts, ",")

	got, err := ParsePhones(input)
	if err != nil {
		t.Fatalf("超长输入期望通过，实际 %v", err)
	}
	if len(got) != 500 {
		t.Fatalf("超长输入期望 500 个号码，实际 %d 个", len(got))
	}
	if got[0] != "13800000000" {
		t.Fatalf("首项应为 13800000000，实际 %s", got[0])
	}
	if got[499] != "13800000499" {
		t.Fatalf("末项应为 13800000499，实际 %s", got[499])
	}
}