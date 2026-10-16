package notify

import (
	"fmt"
	"strings"
)

// Target 描述一次告警的目标级渠道配置。
type Target struct {
	MonitorID      int64  // 监控目标 ID，用于 webhook 持久化队列入队；<=0 则走同步发送
	WebhookURL     string // 目标级 webhook 地址，空则回退全局
	NotifyChannels string // 目标级渠道（逗号分隔），空表示使用全局默认
}

// ParseChannels 解析逗号分隔的渠道名字符串，返回去重、保序的合法渠道名。
// 合法渠道：webhook、smtp、wecom；大小写不敏感；非法名直接丢弃；空输入返回空切片。
func ParseChannels(s string) []string {
	out := make([]string, 0)
	if strings.TrimSpace(s) == "" {
		return out
	}
	seen := make(map[string]bool)
	for _, part := range strings.Split(s, ",") {
		name := strings.ToLower(strings.TrimSpace(part))
		if name == "" {
			continue
		}
		if name != "webhook" && name != "smtp" && name != "wecom" {
			continue
		}
		if seen[name] {
			continue
		}
		seen[name] = true
		out = append(out, name)
	}
	return out
}

// Notify 按渠道分发告警：
//  1. 渠道确定：Target.NotifyChannels 非空则解析它，否则用 n.Channels，再为空则默认 ["webhook"]。
//  2. webhook：目标级 WebhookURL 优先、全局 n.WebhookURL 回退，两者皆空则跳过（不算错误）；
//     若 n.Queue 非空且 t.MonitorID > 0，则改为调用 n.Queue.EnqueueWebhook 持久化入队异步投递；
//     否则调用 n.Send 同步发送。
//  3. smtp：调用 SMTPNotifier{Config: n.SMTP}.SendAlert(event, name, target, at, errMsg)。
//  4. wecom：调用 WeComNotifier{Config: n.WeCom}.SendMarkdown(event, name, target, at, errMsg)。
//
// 各渠道独立发送、一个失败不影响其他；返回所有失败渠道的 error，无失败返回 nil。
func (n Notifier) Notify(t Target, event, name, target, at, errMsg string) []error {
	var channels []string
	if strings.TrimSpace(t.NotifyChannels) != "" {
		channels = ParseChannels(t.NotifyChannels)
	} else if len(n.Channels) > 0 {
		channels = n.Channels
	} else {
		channels = []string{"webhook"}
	}

	var errs []error
	for _, ch := range channels {
		switch ch {
		case "webhook":
			url := strings.TrimSpace(t.WebhookURL)
			if url == "" {
				url = strings.TrimSpace(n.WebhookURL)
			}
			if url == "" {
				continue
			}
			if n.Queue != nil && t.MonitorID > 0 {
				if err := n.Queue.EnqueueWebhook(t.MonitorID, url, event, name, target, at, errMsg); err != nil {
					errs = append(errs, fmt.Errorf("webhook 入队失败: %w", err))
				}
				continue
			}
			if err := n.Send(url, event, name, target, at, errMsg); err != nil {
				errs = append(errs, fmt.Errorf("webhook 渠道发送失败: %w", err))
			}
		case "smtp":
			sn := SMTPNotifier{Config: n.SMTP}
			if err := sn.SendAlert(event, name, target, at, errMsg); err != nil {
				errs = append(errs, fmt.Errorf("smtp 渠道发送失败: %w", err))
			}
		case "wecom":
			wn := WeComNotifier{Config: n.WeCom}
			if err := wn.SendMarkdown(event, name, target, at, errMsg); err != nil {
				errs = append(errs, fmt.Errorf("wecom 渠道发送失败: %w", err))
			}
		}
	}
	if len(errs) == 0 {
		return nil
	}
	return errs
}
