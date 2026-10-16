// Package config 负责从环境变量加载服务配置。
package config

import (
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config 保存服务运行所需的全部配置项。
type Config struct {
	Addr      string // 监听地址，如 ":8080"
	DBPath    string // SQLite 数据库文件路径
	DataDir   string // 数据目录
	Push      PushConfig
	Metrics   MetricsConfig   // 指标配置
	RateLimit RateLimitConfig // 限流配置
}

// PushConfig 保存主动复习外部推送的配置。
type PushConfig struct {
	Enabled         bool
	Time            string // "08:30"
	Timezone        string
	SMTPHost        string
	SMTPPort        int
	SMTPUser        string
	SMTPPass        string
	SMTPFrom        string
	SMTPTLS         bool
	MailTo          string
	WebhookURL      string
	WebhookSecret   string
	VAPIDPublicKey  string
	VAPIDPrivateKey string
	VAPIDSubject    string
}

// Load 从环境变量读取配置，未设置时使用默认值。
// 支持的变量：SB_ADDR、SB_DB、SB_DATA_DIR 以及 SB_PUSH_* / SB_SMTP_* / SB_WEBHOOK_* / SB_METRICS_* / SB_RATE_LIMIT_*。
// 若推送配置校验失败，直接 log.Fatalf 让服务启动失败。
func Load() Config {
	cfg := Config{
		Addr:    getEnv("SB_ADDR", ":8080"),
		DBPath:  getEnv("SB_DB", "data/second-brain.db"),
		DataDir: getEnv("SB_DATA_DIR", "data"),
		Push: PushConfig{
			Enabled:         getBoolEnv("SB_PUSH_ENABLED", false),
			Time:            getEnv("SB_PUSH_TIME", "08:30"),
			Timezone:        getEnv("SB_PUSH_TZ", "Asia/Shanghai"),
			SMTPHost:        os.Getenv("SB_SMTP_HOST"),
			SMTPPort:        getIntEnv("SB_SMTP_PORT", 587),
			SMTPUser:        os.Getenv("SB_SMTP_USER"),
			SMTPPass:        os.Getenv("SB_SMTP_PASS"),
			SMTPFrom:        os.Getenv("SB_SMTP_FROM"),
			SMTPTLS:         getBoolEnv("SB_SMTP_TLS", true),
			MailTo:          os.Getenv("SB_MAIL_TO"),
			WebhookURL:      os.Getenv("SB_WEBHOOK_URL"),
			WebhookSecret:   os.Getenv("SB_WEBHOOK_SECRET"),
			VAPIDPublicKey:  os.Getenv("SB_VAPID_PUBLIC_KEY"),
			VAPIDPrivateKey: os.Getenv("SB_VAPID_PRIVATE_KEY"),
			VAPIDSubject:    os.Getenv("SB_VAPID_SUBJECT"),
		},
	}
	cfg.Metrics = MetricsConfig{Enabled: getBoolEnv("SB_METRICS_ENABLED", true), Token: os.Getenv("SB_METRICS_TOKEN")}
	rps, ok := getFloatEnv("SB_RATE_LIMIT_RPS", 20)
	if !ok {
		log.Fatalf("SB_RATE_LIMIT_RPS 非法: %q", os.Getenv("SB_RATE_LIMIT_RPS"))
	}
	wrps, ok := getFloatEnv("SB_RATE_LIMIT_WRITE_RPS", 5)
	if !ok {
		log.Fatalf("SB_RATE_LIMIT_WRITE_RPS 非法: %q", os.Getenv("SB_RATE_LIMIT_WRITE_RPS"))
	}
	cfg.RateLimit = RateLimitConfig{Enabled: getBoolEnv("SB_RATE_LIMIT_ENABLED", true), RPS: rps, Burst: getIntEnv("SB_RATE_LIMIT_BURST", 40), WriteRPS: wrps, WriteBurst: getIntEnv("SB_RATE_LIMIT_WRITE_BURST", 10)}
	if err := cfg.Push.Validate(); err != nil {
		log.Fatalf("推送配置无效: %v", err)
	}
	if err := cfg.RateLimit.Validate(); err != nil {
		log.Fatalf("限流配置无效: %v", err)
	}
	return cfg
}

// Validate 校验推送配置。未启用时直接通过，避免因残缺的环境变量导致服务无法启动。
func (c PushConfig) Validate() error {
	if !c.Enabled {
		return nil
	}
	if c.Time != "" {
		if _, err := parseHHMM(c.Time); err != nil {
			return fmt.Errorf("SB_PUSH_TIME 非法: %w", err)
		}
	}
	if c.Timezone != "" {
		if _, err := time.LoadLocation(c.Timezone); err != nil {
			return fmt.Errorf("SB_PUSH_TZ 非法: %w", err)
		}
	}

	if c.SMTPHost != "" {
		if c.SMTPUser == "" || c.SMTPPass == "" || c.SMTPFrom == "" || c.MailTo == "" {
			return fmt.Errorf("配置了 SMTPHost 时，SMTPUser/SMTPPass/SMTPFrom/MailTo 均必填")
		}
	}
	if c.WebhookURL != "" {
		if !strings.HasPrefix(c.WebhookURL, "http://") && !strings.HasPrefix(c.WebhookURL, "https://") {
			return fmt.Errorf("SB_WEBHOOK_URL 必须以 http:// 或 https:// 开头")
		}
	}

	if c.Enabled {
		// VAPID 配好也算有推送通道：用户可能只用浏览器推送，不配邮件/webhook。
		if c.SMTPHost == "" && c.WebhookURL == "" && !c.VAPIDConfigured() {
			return fmt.Errorf("未配置任何推送通道")
		}
		if !c.vapidAllEmpty() && !c.VAPIDConfigured() {
			return fmt.Errorf("VAPID 配置不完整：SB_VAPID_PUBLIC_KEY / SB_VAPID_PRIVATE_KEY / SB_VAPID_SUBJECT 必须同时配置")
		}
	}
	return nil
}

// VAPIDConfigured 报告 VAPID 三项是否均已配置。
func (c PushConfig) VAPIDConfigured() bool {
	return c.VAPIDPublicKey != "" && c.VAPIDPrivateKey != "" && c.VAPIDSubject != ""
}

// vapidAllEmpty 报告 VAPID 三项是否均为空。
func (c PushConfig) vapidAllEmpty() bool {
	return c.VAPIDPublicKey == "" && c.VAPIDPrivateKey == "" && c.VAPIDSubject == ""
}

// parseHHMM 解析 "HH:MM"，要求 00:00–23:59。
func parseHHMM(s string) (time.Time, error) {
	t, err := time.Parse("15:04", s)
	if err != nil {
		return time.Time{}, fmt.Errorf("时间格式应为 HH:MM")
	}
	return t, nil
}

// getEnv 返回环境变量值，若为空则返回默认值。
func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// getBoolEnv 解析布尔环境变量，未设置或非法时返回默认值。
func getBoolEnv(key string, def bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return def
	}
}

// getIntEnv 解析整型环境变量，未设置或非法时返回默认值。
func getIntEnv(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(strings.TrimSpace(v))
	if err != nil {
		return def
	}
	return n
}

// MetricsConfig 指标导出配置。Token 为空表示 /metrics 无需鉴权。
type MetricsConfig struct {
	Enabled bool
	Token   string
}

// RateLimitConfig 限流配置。
// Enabled：是否开启限流，默认 true。
// RPS：读桶每秒补充令牌数，默认 20。
// Burst：读桶容量，默认 40。
// WriteRPS：写桶每秒补充令牌数，默认 5。
// WriteBurst：写桶容量，默认 10。
type RateLimitConfig struct {
	Enabled    bool
	RPS        float64
	Burst      int
	WriteRPS   float64
	WriteBurst int
}

// Validate 校验限流配置：关闭时直接通过；否则各参数必须为正。
func (c RateLimitConfig) Validate() error {
	if !c.Enabled {
		return nil
	}
	if c.RPS <= 0 {
		return fmt.Errorf("RPS 必须为正: %v", c.RPS)
	}
	if c.Burst <= 0 {
		return fmt.Errorf("Burst 必须为正: %v", c.Burst)
	}
	if c.WriteRPS <= 0 {
		return fmt.Errorf("WriteRPS 必须为正: %v", c.WriteRPS)
	}
	if c.WriteBurst <= 0 {
		return fmt.Errorf("WriteBurst 必须为正: %v", c.WriteBurst)
	}
	return nil
}

// getFloatEnv 解析浮点环境变量。未设置返回 (def, true)；设置但解析失败返回 (0, false)。
func getFloatEnv(key string, def float64) (float64, bool) {
	v := os.Getenv(key)
	if v == "" {
		return def, true
	}
	f, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
	if err != nil {
		return 0, false
	}
	return f, true
}
