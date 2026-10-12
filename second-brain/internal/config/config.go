// Package config 负责从环境变量加载服务配置。
package config

import "os"

// Config 保存服务运行所需的全部配置项。
type Config struct {
	Addr    string // 监听地址，如 ":8080"
	DBPath  string // SQLite 数据库文件路径
	DataDir string // 数据目录
}

// Load 从环境变量读取配置，未设置时使用默认值。
// 支持的变量：SB_ADDR、SB_DB、SB_DATA_DIR。
func Load() Config {
	return Config{
		Addr:    getEnv("SB_ADDR", ":8080"),
		DBPath:  getEnv("SB_DB", "data/second-brain.db"),
		DataDir: getEnv("SB_DATA_DIR", "data"),
	}
}

// getEnv 返回环境变量值，若为空则返回默认值。
func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
