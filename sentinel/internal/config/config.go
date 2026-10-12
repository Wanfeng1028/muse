// Package config 负责加载 sentinel 运行所需的配置。
// 配置项来源于环境变量，并提供默认值与路径解析能力。
package config

import (
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
)

// Config 保存运行期配置。
type Config struct {
	DBPath     string // SQLite 数据库文件路径（绝对路径）
	Host       string // 监听地址
	Port       int    // 监听端口
	WebhookURL string // 全局 webhook 地址（可为空）
}

// ProjectRoot 通过 runtime.Caller 定位当前源码文件，向上查找包含 go.mod 的目录。
// 若找不到 go.mod，则返回源码文件所在目录。
func ProjectRoot() string {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		// 极端情况下的兜底：返回当前工作目录
		wd, err := os.Getwd()
		if err != nil {
			return "."
		}
		return wd
	}
	dir := filepath.Dir(file)
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			// 到达文件系统根目录仍未找到 go.mod
			return filepath.Dir(file)
		}
		dir = parent
	}
}

// Load 读取环境变量并返回配置。
// 环境变量：SENTINEL_DB、SENTINEL_HOST、SENTINEL_PORT、SENTINEL_WEBHOOK_URL。
func Load() Config {
	root := ProjectRoot()

	// SENTINEL_DB：默认 data/sentinel.db，相对路径拼到项目根目录
	dbPath := os.Getenv("SENTINEL_DB")
	if dbPath == "" {
		dbPath = "data/sentinel.db"
	}
	if !filepath.IsAbs(dbPath) {
		dbPath = filepath.Join(root, dbPath)
	}

	// SENTINEL_HOST：默认 127.0.0.1
	host := os.Getenv("SENTINEL_HOST")
	if host == "" {
		host = "127.0.0.1"
	}

	// SENTINEL_PORT：默认 8200，非法值回退默认
	port := 8200
	if v := os.Getenv("SENTINEL_PORT"); v != "" {
		if p, err := strconv.Atoi(v); err == nil && p > 0 && p <= 65535 {
			port = p
		}
	}

	// SENTINEL_WEBHOOK_URL：默认空
	webhookURL := os.Getenv("SENTINEL_WEBHOOK_URL")

	return Config{
		DBPath:     dbPath,
		Host:       host,
		Port:       port,
		WebhookURL: webhookURL,
	}
}

// Addr 返回 host:port 形式的监听地址。
func (c Config) Addr() string {
	return net.JoinHostPort(c.Host, strconv.Itoa(c.Port))
}
