package config

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"os"
)

// Config 保存服务运行时所需的全部配置项。
type Config struct {
	Addr     string // HTTP 监听地址，如 ":8080"
	DBPath   string // sqlite 数据库文件路径
	AdminKey string // 管理接口密钥；为空时自动生成
	BaseURL  string // 短链公共前缀；为空时使用请求 Host
}

// 环境变量名。
const (
	envAddr     = "LINKSHORT_ADDR"
	envDB       = "LINKSHORT_DB"
	envAdminKey = "LINKSHORT_ADMIN_KEY"
	envBaseURL  = "LINKSHORT_BASE_URL"
)

// FromEnv 从环境变量加载配置，缺省值在文档中说明。
// 当 LINKSHORT_ADMIN_KEY 为空时，自动生成 32 位 hex 并打印提示。
func FromEnv() *Config {
	cfg := &Config{
		Addr:     getenvDefault(envAddr, ":8080"),
		DBPath:   getenvDefault(envDB, "./data/linkshort.db"),
		AdminKey: os.Getenv(envAdminKey),
		BaseURL:  os.Getenv(envBaseURL),
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
