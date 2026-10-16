// Package config 负责从环境变量加载应用配置，并提供项目根目录与监听地址推导。
// 所有配置项在 Load 中逐项解析与校验，非法值返回中文错误信息。
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Config 描述应用运行时配置。
type Config struct {
	// ProjectRootDir 保存项目根目录的绝对路径（不可由环境变量直接设置）。
	ProjectRootDir string

	DBPath string

	Host string
	Port int

	WebhookURL string
	APIToken   string

	SMTPHost     string
	SMTPPort     int
	SMTPUsername string
	SMTPPassword string
	SMTPFrom     string
	SMTPTo       string

	WeComWebhookURL string
	WeComMentionAll bool

	NotifyChannels []string

	LogLevel string

	BackupDir       string
	BackupKeep      int
	BackupIntervalH int

	CheckConcurrency int
	CheckRetryMax    int
	SchedulerTickSec int
}

// Load 读取环境变量并返回解析后的配置。
// 若必填项缺失或任一项取值非法，返回中文错误信息说明变量名与期望取值范围。
func Load() (Config, error) {
	root, err := resolveProjectRoot()
	if err != nil {
		return Config{}, err
	}

	cfg := Config{
		ProjectRootDir: root,
	}

	// SENTINEL_DB：默认 data/sentinel.db（相对路径拼到项目根）。
	dbPath := strings.TrimSpace(os.Getenv("SENTINEL_DB"))
	if dbPath == "" {
		dbPath = filepath.Join("data", "sentinel.db")
	}
	if !filepath.IsAbs(dbPath) {
		dbPath = filepath.Join(root, dbPath)
	}
	cfg.DBPath = dbPath

	// SENTINEL_HOST：默认 127.0.0.1。
	host := strings.TrimSpace(os.Getenv("SENTINEL_HOST"))
	if host == "" {
		host = "127.0.0.1"
	}
	cfg.Host = host

	// SENTINEL_PORT：默认 8200，范围 1~65535。
	port, err := parseIntEnv("SENTINEL_PORT", 8200, 1, 65535)
	if err != nil {
		return Config{}, err
	}
	cfg.Port = port

	// SENTINEL_WEBHOOK_URL：可为空。
	cfg.WebhookURL = strings.TrimSpace(os.Getenv("SENTINEL_WEBHOOK_URL"))

	// SENTINEL_SMTP_HOST：可为空。
	cfg.SMTPHost = strings.TrimSpace(os.Getenv("SENTINEL_SMTP_HOST"))

	// SENTINEL_SMTP_PORT：默认 25，范围 1~65535。
	smtpPort, err := parseIntEnv("SENTINEL_SMTP_PORT", 25, 1, 65535)
	if err != nil {
		return Config{}, err
	}
	cfg.SMTPPort = smtpPort

	// SENTINEL_SMTP_USERNAME / SENTINEL_SMTP_PASSWORD / SENTINEL_SMTP_FROM / SENTINEL_SMTP_TO：可为空。
	cfg.SMTPUsername = strings.TrimSpace(os.Getenv("SENTINEL_SMTP_USERNAME"))
	cfg.SMTPPassword = strings.TrimSpace(os.Getenv("SENTINEL_SMTP_PASSWORD"))
	cfg.SMTPFrom = strings.TrimSpace(os.Getenv("SENTINEL_SMTP_FROM"))
	cfg.SMTPTo = strings.TrimSpace(os.Getenv("SENTINEL_SMTP_TO"))

	// SENTINEL_WECOM_WEBHOOK_URL：可为空。
	cfg.WeComWebhookURL = strings.TrimSpace(os.Getenv("SENTINEL_WECOM_WEBHOOK_URL"))

	// SENTINEL_WECOM_MENTION_ALL：默认 false。
	mentionAll, err := parseBoolEnv("SENTINEL_WECOM_MENTION_ALL", false)
	if err != nil {
		return Config{}, err
	}
	cfg.WeComMentionAll = mentionAll

	// SENTINEL_NOTIFY_CHANNELS：可为空；为空则默认 ["webhook"]。
	rawChannels := strings.TrimSpace(os.Getenv("SENTINEL_NOTIFY_CHANNELS"))
	if rawChannels == "" {
		cfg.NotifyChannels = []string{"webhook"}
	} else {
		seen := make(map[string]bool)
		channels := make([]string, 0)
		for _, part := range strings.Split(rawChannels, ",") {
			name := strings.ToLower(strings.TrimSpace(part))
			if name == "" {
				continue
			}
			if name != "webhook" && name != "smtp" && name != "wecom" {
				return Config{}, fmt.Errorf("环境变量 SENTINEL_NOTIFY_CHANNELS 取值 %q 非法：仅支持 webhook/smtp/wecom（逗号分隔）", name)
			}
			if seen[name] {
				continue
			}
			seen[name] = true
			channels = append(channels, name)
		}
		if len(channels) == 0 {
			cfg.NotifyChannels = []string{"webhook"}
		} else {
			cfg.NotifyChannels = channels
		}
	}

	// SENTINEL_API_TOKEN：必填。
	cfg.APIToken = strings.TrimSpace(os.Getenv("SENTINEL_API_TOKEN"))
	if cfg.APIToken == "" {
		return Config{}, errors.New("环境变量 SENTINEL_API_TOKEN 未设置：必须提供一个非空的 API 令牌，建议使用 `openssl rand -hex 32` 生成后写入环境变量")
	}

	// SENTINEL_LOG_LEVEL：默认 info。
	level := strings.TrimSpace(os.Getenv("SENTINEL_LOG_LEVEL"))
	if level == "" {
		level = "info"
	}
	cfg.LogLevel = level

	// SENTINEL_BACKUP_DIR：默认 data/backups（相对路径拼到项目根）。
	backupDir := strings.TrimSpace(os.Getenv("SENTINEL_BACKUP_DIR"))
	if backupDir == "" {
		backupDir = filepath.Join("data", "backups")
	}
	if !filepath.IsAbs(backupDir) {
		backupDir = filepath.Join(root, backupDir)
	}
	cfg.BackupDir = backupDir

	// SENTINEL_BACKUP_KEEP：默认 7，>=1。
	keep, err := parseIntEnv("SENTINEL_BACKUP_KEEP", 7, 1, 1<<31-1)
	if err != nil {
		return Config{}, err
	}
	cfg.BackupKeep = keep

	// SENTINEL_BACKUP_INTERVAL_H：默认 24，>=1。
	intervalH, err := parseIntEnv("SENTINEL_BACKUP_INTERVAL_H", 24, 1, 1<<31-1)
	if err != nil {
		return Config{}, err
	}
	cfg.BackupIntervalH = intervalH

	// SENTINEL_CHECK_CONCURRENCY：默认 10，范围 1~100。
	concurrency, err := parseIntEnv("SENTINEL_CHECK_CONCURRENCY", 10, 1, 100)
	if err != nil {
		return Config{}, err
	}
	cfg.CheckConcurrency = concurrency

	// SENTINEL_CHECK_RETRY_MAX：默认 3，范围 0~5。
	retryMax, err := parseIntEnv("SENTINEL_CHECK_RETRY_MAX", 3, 0, 5)
	if err != nil {
		return Config{}, err
	}
	cfg.CheckRetryMax = retryMax

	// SENTINEL_TICK_SEC：默认 5，范围 1~60。
	tick, err := parseIntEnv("SENTINEL_TICK_SEC", 5, 1, 60)
	if err != nil {
		return Config{}, err
	}
	cfg.SchedulerTickSec = tick

	return cfg, nil
}

// ProjectRoot 返回项目根目录绝对路径。
func (c Config) ProjectRoot() string {
	return c.ProjectRootDir
}

// Addr 返回 net/http 服务器使用的监听地址（host:port）。
func (c Config) Addr() string {
	return fmt.Sprintf("%s:%d", c.Host, c.Port)
}

// resolveProjectRoot 从当前工作目录向上查找 go.mod 文件，返回所在目录。
// 未找到时回退到当前工作目录。
func resolveProjectRoot() (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("无法获取当前工作目录：%w", err)
	}
	dir := wd
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "go.mod")); statErr == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return wd, nil
}

// parseIntEnv 解析整型环境变量，未设置时返回默认值。
// 解析失败或超出范围返回中文错误。
func parseIntEnv(name string, def, min, max int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return def, nil
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("环境变量 %s 取值 %q 非法：应为整数，范围 %d~%d", name, raw, min, max)
	}
	if v < min || v > max {
		return 0, fmt.Errorf("环境变量 %s 取值 %d 超出范围：应为 %d~%d", name, v, min, max)
	}
	return v, nil
}

// parseBoolEnv 解析布尔环境变量，未设置时返回默认值。
// 取值按小写识别 "1","true","yes","on" 为 true，"0","false","no","off" 为 false；
// 其他返回中文错误并点名变量。
func parseBoolEnv(name string, def bool) (bool, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return def, nil
	}
	switch strings.ToLower(raw) {
	case "1", "true", "yes", "on":
		return true, nil
	case "0", "false", "no", "off":
		return false, nil
	default:
		return false, fmt.Errorf("环境变量 %s 取值 %q 非法：应为布尔值（1/true/yes/on 或 0/false/no/off）", name, raw)
	}
}
