package config

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"os"
	"strconv"
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
