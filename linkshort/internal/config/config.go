package config

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log"
	"net"
	"os"
	"strconv"
	"strings"
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

	PasswordFailAlertThreshold   int           // 滑动窗口内单个短链密码失败触发告警的次数阈值
	PasswordFailAlertWindow      time.Duration // 滑动窗口时长
	PasswordFailAlertIPThreshold int           // 同一 IP 滑动窗口内密码失败触发告警的次数阈值
	AlertWebhookURL              string        // 告警 webhook 地址，复用备份告警的 LINKSHORT_ALERT_WEBHOOK_URL
	AlertWebhookURLs             []string      // 由 LINKSHORT_ALERT_WEBHOOK_URL 按逗号解析的多地址
	TrustedProxies               []net.IPNet   // 可信反向代理 IP/CIDR；为空表示不信任任何代理的 XFF 头
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

	envPasswordFailAlertThreshold   = "LINKSHORT_PASSWORD_FAIL_ALERT_THRESHOLD"
	envPasswordFailAlertWindow      = "LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW"
	envPasswordFailAlertIPThreshold = "LINKSHORT_PASSWORD_FAIL_ALERT_IP_THRESHOLD"
	envAlertWebhookURL              = "LINKSHORT_ALERT_WEBHOOK_URL"
	envTrustedProxies               = "LINKSHORT_TRUSTED_PROXIES"
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

// SplitWebhookURLs 把逗号分隔的 webhook 地址解析为去重保序的 slice。
// 每项 TrimSpace，丢弃空项，重复地址只保留首次出现；无有效项返回 nil。
func SplitWebhookURLs(s string) []string {
	var out []string
	seen := make(map[string]struct{})
	for _, part := range strings.Split(s, ",") {
		u := strings.TrimSpace(part)
		if u == "" {
			continue
		}
		if _, ok := seen[u]; ok {
			continue
		}
		seen[u] = struct{}{}
		out = append(out, u)
	}
	return out
}

// ParseTrustedProxies 解析逗号分隔的可信代理列表：每项为单个 IP（视为 /32 或 /128）
// 或 CIDR（如 10.0.0.0/8）。空字符串返回 nil；任一项非法返回指明该项的 error。
func ParseTrustedProxies(s string) ([]net.IPNet, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil, nil
	}
	var out []net.IPNet
	for _, part := range strings.Split(s, ",") {
		item := strings.TrimSpace(part)
		if item == "" {
			continue
		}
		if strings.Contains(item, "/") {
			_, ipnet, err := net.ParseCIDR(item)
			if err != nil {
				return nil, fmt.Errorf("无效的可信代理 %q: %v", item, err)
			}
			out = append(out, *ipnet)
			continue
		}
		ip := net.ParseIP(item)
		if ip == nil {
			return nil, fmt.Errorf("无效的可信代理 %q: 不是合法 IP 或 CIDR", item)
		}
		bits := 128
		if ip.To4() != nil {
			bits = 32
		}
		out = append(out, net.IPNet{IP: ip, Mask: net.CIDRMask(bits, bits)})
	}
	return out, nil
}

// IsTrustedProxy 判定给定 IP 是否落在可信代理名单内；名单为空时恒为 false。
func (c *Config) IsTrustedProxy(ip net.IP) bool {
	if ip == nil {
		return false
	}
	for _, ipnet := range c.TrustedProxies {
		if ipnet.Contains(ip) {
			return true
		}
	}
	return false
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

		PasswordFailAlertThreshold:   getenvIntDefault(envPasswordFailAlertThreshold, 10),
		PasswordFailAlertWindow:      getenvDurationDefault(envPasswordFailAlertWindow, 5*time.Minute),
		PasswordFailAlertIPThreshold: getenvIntDefault(envPasswordFailAlertIPThreshold, 20),
		AlertWebhookURL:              getenvDefault(envAlertWebhookURL, ""),
		AlertWebhookURLs:             SplitWebhookURLs(getenvDefault(envAlertWebhookURL, "")),
	}
	trusted, err := ParseTrustedProxies(os.Getenv(envTrustedProxies))
	if err != nil {
		log.Fatalf("LINKSHORT_TRUSTED_PROXIES 解析失败: %v", err)
	}
	cfg.TrustedProxies = trusted
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
	if cfg.PasswordFailAlertIPThreshold <= 0 {
		cfg.PasswordFailAlertIPThreshold = 20
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
