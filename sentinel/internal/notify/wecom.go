package notify

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"sentinel/internal/log"
)

// WeComConfig 描述企业微信群机器人 webhook 配置。
type WeComConfig struct {
	WebhookURL string // 群机器人 webhook 地址，空表示未配置
	MentionAll bool   // 是否 @全体成员
}

// WeComNotifier 通过企业微信群机器人发送 markdown 告警。
type WeComNotifier struct {
	Config WeComConfig
}

// wecomMarkdown 是 markdown 消息内容。
type wecomMarkdown struct {
	Content       string    `json:"content"`
	MentionedList *[]string `json:"mentioned_list,omitempty"`
}

// wecomPayload 是发送到企业微信 webhook 的 JSON 结构。
type wecomPayload struct {
	MsgType  string        `json:"msgtype"`
	Markdown wecomMarkdown `json:"markdown"`
}

// wecomResponse 是企业微信 webhook 的响应结构。
type wecomResponse struct {
	ErrCode int    `json:"errcode"`
	ErrMsg  string `json:"errmsg"`
}

// SendMarkdown 发送企业微信 markdown 告警消息。event 取值 "down" 或 "recovered"。
// Config.WebhookURL 为空表示渠道未配置，直接返回 nil（跳过，不报错）。
func (n WeComNotifier) SendMarkdown(event, name, target, at, errMsg string) error {
	url := n.Config.WebhookURL
	if url == "" {
		return nil
	}

	// 组装 markdown 正文
	var content string
	if n.Config.MentionAll {
		content += "@all\n"
	}
	if event == "down" {
		content += fmt.Sprintf("## 告警：%s 宕机\n", name)
	} else {
		content += fmt.Sprintf("## 恢复：%s 已恢复\n", name)
	}
	content += fmt.Sprintf("> 监控名称：%s\n", name)
	content += fmt.Sprintf("> 目标：%s\n", target)
	content += fmt.Sprintf("> 时间：%s\n", at)
	if event == "down" && errMsg != "" {
		content += fmt.Sprintf("> 错误信息：%s\n", errMsg)
	}

	// mentioned_list 仅在需要 @全体成员 时出现
	var mentioned *[]string
	if n.Config.MentionAll {
		list := []string{"@all"}
		mentioned = &list
	}

	body, err := json.Marshal(wecomPayload{
		MsgType: "markdown",
		Markdown: wecomMarkdown{
			Content:       content,
			MentionedList: mentioned,
		},
	})
	if err != nil {
		return fmt.Errorf("序列化企业微信通知失败: %w", err)
	}

	client := &http.Client{Timeout: 10 * time.Second}

	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("构造企业微信通知请求失败: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err == nil {
			respBody, readErr := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			_ = resp.Body.Close()
			if readErr != nil {
				err = fmt.Errorf("读取企业微信响应失败: %w", readErr)
			} else if resp.StatusCode < 200 || resp.StatusCode >= 300 {
				err = fmt.Errorf("非 2xx 状态码: %d, 响应: %s", resp.StatusCode, string(respBody))
			} else {
				var r wecomResponse
				if jsonErr := json.Unmarshal(respBody, &r); jsonErr != nil {
					err = fmt.Errorf("解析企业微信响应失败: %w", jsonErr)
				} else if r.ErrCode != 0 {
					err = fmt.Errorf("errcode: %d, errmsg: %s", r.ErrCode, r.ErrMsg)
				} else {
					return nil
				}
			}
		}

		lastErr = err
		log.Logger().Warn("发送企业微信 Webhook 失败",
			"url", url,
			"attempt", attempt+1,
			"error", err,
		)

		if attempt < 2 {
			backoff := time.Duration(1<<uint(attempt)) * time.Second
			time.Sleep(backoff)
		}
	}

	return fmt.Errorf("企业微信 Webhook 发送失败: %w", lastErr)
}
