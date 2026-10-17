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

	"sentinel/internal/notify"
)

// Config 描述应用运行时配置。
// EscalationLevel 告警升级的一级：故障持续 AfterMinutes 分钟未恢复时，用 Channels 渠道再通知一次。
type EscalationLevel struct {
	AfterMinutes int
	Channels     []string
}

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

	// SMSMode 短信通道模式：mock（默认，内存记录不真发）或 aliyun（阿里云短信）。
	SMSMode string
	// SMSPhones 短信全局默认接收号码；目标级 sms_phones 为空时回退到此。
	SMSPhones []string
	// SMSAccessKeyID / SMSAccessKeySecret 阿里云短信 AK。
	SMSAccessKeyID     string
	SMSAccessKeySecret string
	// SMSSignName / SMSTemplateCode 阿里云短信签名与模板 CODE。
	SMSSignName     string
	SMSTemplateCode string

	NotifyChannels []string

	// PublicURL 对外基地址（用于订阅邮件中的确认/退订链接），可为空。
	PublicURL string

	LogLevel string

	BackupDir       string
	BackupKeep      int
	BackupIntervalH int

	CheckConcurrency int
	CheckRetryMax    int
	SchedulerTickSec int

	// QueueMaxAttempts webhook 投递队列最大投递次数。
	QueueMaxAttempts int
	// QueueBaseBackoffSec webhook 投递队列指数退避基数（秒）。
	QueueBaseBackoffSec int
	// QueueTickSec webhook 投递队列 worker 扫描间隔（秒）。
	QueueTickSec int
	// QueueEnqueueRPS webhook 入队限流速率（每秒令牌数）；<=0 表示禁用入队限流。
	QueueEnqueueRPS float64
	// QueueEnqueueBurst webhook 入队限流桶容量。
	QueueEnqueueBurst int
	// BreakerFailureThreshold webhook 投递熔断：连续失败阈值。
	BreakerFailureThreshold int
	// BreakerOpenTimeoutSec webhook 投递熔断：断开后转半开探测的等待秒数。
	BreakerOpenTimeoutSec int

	// Escalation 告警升级链；空表示禁用。由 SENTINEL_ESCALATION 解析。
	Escalation []EscalationLevel
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

	// SENTINEL_SMS_MODE：默认 mock；仅支持 mock/aliyun。
	smsMode := strings.ToLower(strings.TrimSpace(os.Getenv("SENTINEL_SMS_MODE")))
	if smsMode == "" {
		smsMode = "mock"
	}
	if smsMode != "mock" && smsMode != "aliyun" {
		return Config{}, fmt.Errorf("环境变量 SENTINEL_SMS_MODE 取值 %q 非法：仅支持 mock/aliyun", smsMode)
	}
	cfg.SMSMode = smsMode

	// SENTINEL_SMS_PHONES：可选，逗号分隔；逐个校验手机号格式。
	if rawPhones := strings.TrimSpace(os.Getenv("SENTINEL_SMS_PHONES")); rawPhones != "" {
		phones, err := notify.ParsePhones(rawPhones)
		if err != nil {
			return Config{}, fmt.Errorf("环境变量 SENTINEL_SMS_PHONES 非法: %w", err)
		}
		cfg.SMSPhones = phones
	}

	// SENTINEL_SMS_ACCESS_KEY_ID / SENTINEL_SMS_ACCESS_KEY_SECRET。
	cfg.SMSAccessKeyID = strings.TrimSpace(os.Getenv("SENTINEL_SMS_ACCESS_KEY_ID"))
	cfg.SMSAccessKeySecret = strings.TrimSpace(os.Getenv("SENTINEL_SMS_ACCESS_KEY_SECRET"))

	// SENTINEL_SMS_SIGN_NAME / SENTINEL_SMS_TEMPLATE_CODE。
	cfg.SMSSignName = strings.TrimSpace(os.Getenv("SENTINEL_SMS_SIGN_NAME"))
	cfg.SMSTemplateCode = strings.TrimSpace(os.Getenv("SENTINEL_SMS_TEMPLATE_CODE"))

	// aliyun 模式要求 AK、签名、模板四项齐全，缺一不可（启动即校验）。
	if smsMode == "aliyun" {
		if cfg.SMSAccessKeyID == "" || cfg.SMSAccessKeySecret == "" {
			return Config{}, errors.New("环境变量 SENTINEL_SMS_MODE=aliyun 时必须同时设置 SENTINEL_SMS_ACCESS_KEY_ID 与 SENTINEL_SMS_ACCESS_KEY_SECRET")
		}
		if cfg.SMSSignName == "" || cfg.SMSTemplateCode == "" {
			return Config{}, errors.New("环境变量 SENTINEL_SMS_MODE=aliyun 时必须同时设置 SENTINEL_SMS_SIGN_NAME 与 SENTINEL_SMS_TEMPLATE_CODE")
		}
	}

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
			if name != "webhook" && name != "smtp" && name != "wecom" && name != "sms" {
				return Config{}, fmt.Errorf("环境变量 SENTINEL_NOTIFY_CHANNELS 取值 %q 非法：仅支持 webhook/smtp/wecom/sms（逗号分隔）", name)
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

	// SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS：默认 8，范围 1~20。
	qMaxAttempts, err := parseIntEnv("SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS", 8, 1, 20)
	if err != nil {
		return Config{}, err
	}
	cfg.QueueMaxAttempts = qMaxAttempts

	// SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC：默认 60，范围 5~3600。
	qBaseBackoff, err := parseIntEnv("SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC", 60, 5, 3600)
	if err != nil {
		return Config{}, err
	}
	cfg.QueueBaseBackoffSec = qBaseBackoff

	// SENTINEL_WEBHOOK_QUEUE_TICK_SEC：默认 15，范围 5~300。
	qTick, err := parseIntEnv("SENTINEL_WEBHOOK_QUEUE_TICK_SEC", 15, 5, 300)
	if err != nil {
		return Config{}, err
	}
	cfg.QueueTickSec = qTick

	// SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS：默认 20；0 表示禁用；非零必须在 0.1~10000。
	enqueueRPS, err := parseFloatEnv("SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS", 20, 0, 10000)
	if err != nil {
		return Config{}, err
	}
	if enqueueRPS != 0 && enqueueRPS < 0.1 {
		return Config{}, fmt.Errorf("环境变量 SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS 取值 %g 非法：0 表示禁用，非零应在 0.1~10000", enqueueRPS)
	}
	cfg.QueueEnqueueRPS = enqueueRPS

	// SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST：默认 40，范围 1~100000。
	enqueueBurst, err := parseIntEnv("SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST", 40, 1, 100000)
	if err != nil {
		return Config{}, err
	}
	cfg.QueueEnqueueBurst = enqueueBurst

	// SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD：默认 5，范围 1~100。
	breakerThreshold, err := parseIntEnv("SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD", 5, 1, 100)
	if err != nil {
		return Config{}, err
	}
	cfg.BreakerFailureThreshold = breakerThreshold

	// SENTINEL_WEBHOOK_BREAKER_OPEN_TIMEOUT_SEC：默认 300，范围 10~86400。
	breakerTimeout, err := parseIntEnv("SENTINEL_WEBHOOK_BREAKER_OPEN_TIMEOUT_SEC", 300, 10, 86400)
	if err != nil {
		return Config{}, err
	}
	cfg.BreakerOpenTimeoutSec = breakerTimeout
	// SENTINEL_PUBLIC_URL：可选；用于订阅邮件中的确认/退订链接。为空则用相对路径。

	publicURL := strings.TrimSpace(os.Getenv("SENTINEL_PUBLIC_URL"))
	if publicURL != "" && !strings.HasPrefix(publicURL, "http://") && !strings.HasPrefix(publicURL, "https://") {
		return Config{}, fmt.Errorf("环境变量 SENTINEL_PUBLIC_URL 取值 %q 非法：应以 http:// 或 https:// 开头", publicURL)
	}
	cfg.PublicURL = strings.TrimRight(publicURL, "/")

	// SENTINEL_ESCALATION：可选，格式 "15:wecom;30:wecom,smtp"。
	if escRaw := strings.TrimSpace(os.Getenv("SENTINEL_ESCALATION")); escRaw != "" {
		levels, err := parseEscalation(escRaw)
		if err != nil {
			return Config{}, fmt.Errorf("环境变量 SENTINEL_ESCALATION 非法: %w", err)
		}
		cfg.Escalation = levels
	}

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

// parseFloatEnv 解析浮点型环境变量，未设置时返回默认值。
// 解析失败或超出范围返回中文错误。
func parseFloatEnv(name string, def, min, max float64) (float64, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return def, nil
	}
	v, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0, fmt.Errorf("环境变量 %s 取值 %q 非法：应为数字，范围 %g~%g", name, raw, min, max)
	}
	if v < min || v > max {
		return 0, fmt.Errorf("环境变量 %s 取值 %g 超出范围：应为 %g~%g", name, v, min, max)
	}
	return v, nil
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
