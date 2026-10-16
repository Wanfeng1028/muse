package config

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"os"
	"strconv"
	"time"
)

// Config 保存服务运行时所需的全部配置项。
type Config struct {
	Addr     string // HTTP 监听地址，如 ":8080"
	DBPath   string // sqlite 数据库文件路径
	AdminKey string // 管理接口密钥；为空时自动生成
	BaseURL  string // 短链公共前缀；为空时使用请求 Host

	RateLimitRPS     float64 // 限流速率，每秒 token 数
	RateLimitBurst   int     // 令牌桶容量
	RateLimitEnabled bool    // 是否启用限流

	BurnPurgeAfterDestroy bool // burn 销毁后是否彻底删除行（默认 false）

	PurgeInterval      time.Duration // 定时清理间隔
	PurgeRetentionDays int           // 保留天数

	BackupDir        string // 备份目录路径
	BackupMaxAgeDays int    // 备份最大允许天数；0 表示不检查过期

	PasswordFailAlertThreshold int           // 滑动窗口内单个短链密码失败触发告警的次数阈值
	PasswordFailAlertWindow    time.Duration // 滑动窗口时长
	AlertWebhookURL            string        // 告警 webhook 地址，复用备份告警的 LINKSHORT_ALERT_WEBHOOK_URL
}

// 环境变量名。
const (
	envAddr     = "LINKSHORT_ADDR"
	envDB       = "LINKSHORT_DB"
	envAdminKey = "LINKSHORT_ADMIN_KEY"
	envBaseURL  = "LINKSHORT_BASE_URL"

	envRateLimitRPS     = "LINKSHORT_RATE_LIMIT_RPS"
	envRateLimitBurst   = "LINKSHORT_RATE_LIMIT_BURST"
	envRateLimitEnabled = "LINKSHORT_RATE_LIMIT_ENABLED"

	envBurnPurgeAfterDestroy = "LINKSHORT_BURN_PURGE_AFTER_DESTROY"

	envPurgeInterval      = "LINKSHORT_PURGE_INTERVAL"
	envPurgeRetentionDays = "LINKSHORT_PURGE_RETENTION_DAYS"

	envBackupDir        = "LINKSHORT_BACKUP_DIR"
	envBackupMaxAgeDays = "LINKSHORT_BACKUP_MAX_AGE_DAYS"

	envPasswordFailAlertThreshold = "LINKSHORT_PASSWORD_FAIL_ALERT_THRESHOLD"
	envPasswordFailAlertWindow    = "LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW"
	envAlertWebhookURL            = "LINKSHORT_ALERT_WEBHOOK_URL"
)

// getenvFloatDefault 读取浮点型环境变量，解析失败返回默认值。
func getenvFloatDefault(key string, def float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return def
	}
	return f
}

// getenvIntDefault 读取整型环境变量，解析失败返回默认值。
func getenvIntDefault(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	i, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return i
}

// getenvBoolDefault 读取布尔型环境变量，解析失败返回默认值。
func getenvBoolDefault(key string, def bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}

// getenvDurationDefault 读取 duration 型环境变量，解析失败返回默认值。
func getenvDurationDefault(key string, def time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return def
	}
	return d
}

// FromEnv 从环境变量加载配置，缺省值在文档中说明。
// 当 LINKSHORT_ADMIN_KEY 为空时，自动生成 32 位 hex 并打印提示。
func FromEnv() *Config {
	cfg := &Config{
		Addr:     getenvDefault(envAddr, ":8080"),
		DBPath:   getenvDefault(envDB, "./data/linkshort.db"),
		AdminKey: os.Getenv(envAdminKey),
		BaseURL:  os.Getenv(envBaseURL),

		RateLimitRPS:     getenvFloatDefault(envRateLimitRPS, 20),
		RateLimitBurst:   getenvIntDefault(envRateLimitBurst, 40),
		RateLimitEnabled: getenvBoolDefault(envRateLimitEnabled, true),

		BurnPurgeAfterDestroy: getenvBoolDefault(envBurnPurgeAfterDestroy, false),

		PurgeInterval:      getenvDurationDefault(envPurgeInterval, 24*time.Hour),
		PurgeRetentionDays: getenvIntDefault(envPurgeRetentionDays, 7),

		BackupDir:        getenvDefault(envBackupDir, "./backups"),
		BackupMaxAgeDays: getenvIntDefault(envBackupMaxAgeDays, 7),

		PasswordFailAlertThreshold: getenvIntDefault(envPasswordFailAlertThreshold, 10),
		PasswordFailAlertWindow:    getenvDurationDefault(envPasswordFailAlertWindow, 5*time.Minute),
		AlertWebhookURL:            getenvDefault(envAlertWebhookURL, ""),
	}
	if cfg.PurgeInterval <= 0 {
		cfg.PurgeInterval = 24 * time.Hour
	}
	if cfg.PurgeRetentionDays < 0 {
		cfg.PurgeRetentionDays = 7
	}
	if cfg.BackupMaxAgeDays < 0 {
		cfg.BackupMaxAgeDays = 7
	}
	if cfg.PasswordFailAlertThreshold <= 0 {
		cfg.PasswordFailAlertThreshold = 10
	}
	if cfg.PasswordFailAlertWindow <= 0 {
		cfg.PasswordFailAlertWindow = 5 * time.Minute
	}
	if cfg.AdminKey == "" {

		generated, err := generateAdminKey()
		if err != nil {
			// 无法生成密钥时属于严重问题，直接以日志暴露并终止。
			log.Fatalf("generate admin key: %v", err)
		}
		cfg.AdminKey = generated
		log.Printf("[config] LINKSHORT_ADMIN_KEY 未设置，已自动生成：%s（请立即保存，重启后会变化）", generated)
	}
	return cfg
}

// getenvDefault 读取环境变量，为空时返回默认值。
func getenvDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// generateAdminKey 生成 32 位十六进制随机字符串（16 字节）。
func generateAdminKey() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}
