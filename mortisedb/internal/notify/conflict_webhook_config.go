package notify

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// ConflictWebhookConfig 从环境变量读冲突 webhook 配置。
// MORTISE_CONFLICT_WEBHOOK_URL 为空表示不启用。
// MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC 默认 10，非法值直接报错。
type ConflictWebhookConfig struct {
	URL     string
	Timeout time.Duration
	Enabled bool
}

// LoadConflictWebhookConfig 读取并校验环境变量。非法 timeout 返回 error。
func LoadConflictWebhookConfig() (ConflictWebhookConfig, error) {
	url := os.Getenv("MORTISE_CONFLICT_WEBHOOK_URL")

	timeoutSec := 10
	if raw := os.Getenv("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil {
			return ConflictWebhookConfig{}, fmt.Errorf("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC=%q is not a valid integer", raw)
		}
		if n <= 0 {
			return ConflictWebhookConfig{}, fmt.Errorf("MORTISE_CONFLICT_WEBHOOK_TIMEOUT_SEC=%d must be > 0", n)
		}
		timeoutSec = n
	}

	return ConflictWebhookConfig{
		URL:     url,
		Timeout: time.Duration(timeoutSec) * time.Second,
		Enabled: url != "",
	}, nil
}
