// Package seed 负责在数据库为空时写入示例监控数据。
package seed

import (
	"time"

	"sentinel/internal/store"
)

// EnsureSeed 在监控列表为空时插入两条默认禁用（enabled=0）的示例监控。
// 已存在任何监控时不做任何操作，避免覆盖用户数据。
func EnsureSeed(s *store.Store) {
	monitors, err := s.ListMonitors()
	if err != nil {
		// 查询失败时直接返回，交由调用方在上层处理数据库错误。
		return
	}
	if len(monitors) > 0 {
		return
	}

	now := time.Now().UTC().Format(time.RFC3339)

	examples := []store.Monitor{
		{
			Name:           "示例站点",
			Kind:           "http",
			Target:         "https://example.com",
			Method:         "GET",
			ExpectedStatus: 200,
			TimeoutSec:     10,
			IntervalSec:    300,
			Enabled:        0,
			WebhookURL:     "",
			CreatedAt:      now,
			UpdatedAt:      now,
		},
		{
			Name:           "示例 TCP 端口",
			Kind:           "tcp",
			Target:         "example.com:80",
			Method:         "GET",
			ExpectedStatus: 200,
			TimeoutSec:     5,
			IntervalSec:    300,
			Enabled:        0,
			WebhookURL:     "",
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}

	for i := range examples {
		// 逐条写入，忽略单条失败以避免中断整体种子流程。
		_, _ = s.CreateMonitor(examples[i])
	}
}
