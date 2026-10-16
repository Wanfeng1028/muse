package config

import (
	"fmt"
	"strconv"
	"strings"
)

// 合法渠道集合，元素均为小写。
var validEscalationChannels = map[string]struct{}{
	"webhook": {},
	"smtp":    {},
	"wecom":   {},
	"sms":     {},
}

// parseEscalation 解析告警升级配置。
// 格式为 "分钟:渠道,渠道;分钟:渠道"，分号分隔级别，冒号分隔分钟与渠道，逗号分隔渠道。
// 分钟为正整数（1~525600），各级分钟必须严格递增；渠道大小写不敏感，统一转小写并去重保序。
// 空输入返回 nil, nil；任何非法输入返回包含原始非法片段的中文错误。
func parseEscalation(raw string) ([]EscalationLevel, error) {
	if strings.TrimSpace(raw) == "" {
		return nil, nil
	}

	segments := strings.Split(raw, ";")
	levels := make([]EscalationLevel, 0, len(segments))
	prevMinutes := 0

	for _, seg := range segments {
		trimmed := strings.TrimSpace(seg)
		if trimmed == "" {
			return nil, fmt.Errorf("非法的升级配置片段: %q", seg)
		}

		colonIdx := strings.Index(trimmed, ":")
		if colonIdx < 0 {
			return nil, fmt.Errorf("非法的升级配置片段: %q，缺少冒号分隔符", trimmed)
		}

		minutesStr := strings.TrimSpace(trimmed[:colonIdx])
		channelsStr := strings.TrimSpace(trimmed[colonIdx+1:])

		minutes, err := strconv.Atoi(minutesStr)
		if err != nil {
			return nil, fmt.Errorf("非法的升级配置片段: %q，分钟不是数字", trimmed)
		}
		if minutes < 1 || minutes > 525600 {
			return nil, fmt.Errorf("非法的升级配置片段: %q，分钟必须在 1~525600 之间", trimmed)
		}
		if minutes <= prevMinutes {
			return nil, fmt.Errorf("非法的升级配置片段: %q，各级分钟必须严格递增", trimmed)
		}

		if channelsStr == "" {
			return nil, fmt.Errorf("非法的升级配置片段: %q，渠道为空", trimmed)
		}

		channelParts := strings.Split(channelsStr, ",")
		channels := make([]string, 0, len(channelParts))
		seen := make(map[string]struct{}, len(channelParts))
		for _, cp := range channelParts {
			name := strings.ToLower(strings.TrimSpace(cp))
			if name == "" {
				continue
			}
			if _, ok := validEscalationChannels[name]; !ok {
				continue
			}
			if _, ok := seen[name]; ok {
				continue
			}
			seen[name] = struct{}{}
			channels = append(channels, name)
		}

		if len(channels) == 0 {
			return nil, fmt.Errorf("非法的升级配置片段: %q，没有合法的渠道", trimmed)
		}

		levels = append(levels, EscalationLevel{
			AfterMinutes: minutes,
			Channels:     channels,
		})
		prevMinutes = minutes
	}

	return levels, nil
}
