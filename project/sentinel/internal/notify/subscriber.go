// Package notify 订阅通知：状态页访客订阅 down/recovered 事件邮件扇出。
package notify

import (
	"fmt"
	"strings"
	"sync"

	"sentinel/internal/log"
	"sentinel/internal/store"
)

// Mailer 发送邮件的最小接口，便于测试注入内存实现。
type Mailer interface {
	SendMail(recipients []string, subject, body string) error
}

// SMTPMailer 用 SMTP 发送邮件的 Mailer 实现。
type SMTPMailer struct {
	Notifier SMTPNotifier
}

// SendMail 实现 Mailer 接口。
func (m SMTPMailer) SendMail(recipients []string, subject, body string) error {
	return m.Notifier.SendRaw(recipients, subject, body)
}

// SentMail 记录一次内存发送。
type SentMail struct {
	Recipients []string
	Subject    string
	Body       string
}

// MemoryMailer 内存 Mailer（测试用），记录所有发送。
type MemoryMailer struct {
	mu   sync.Mutex
	Sent []SentMail
}

// SendMail 记录发送内容，恒返回 nil。
func (m *MemoryMailer) SendMail(recipients []string, subject, body string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	cp := make([]string, len(recipients))
	copy(cp, recipients)
	m.Sent = append(m.Sent, SentMail{Recipients: cp, Subject: subject, Body: body})
	return nil
}

// Messages 返回已记录发送的副本。
func (m *MemoryMailer) Messages() []SentMail {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]SentMail, len(m.Sent))
	copy(out, m.Sent)
	return out
}

// SubscriberSource 提供订阅者查询。*store.Store 已实现该接口。
type SubscriberSource interface {
	ListPageIDsForMonitor(monitorID int64) ([]int64, error)
	ListConfirmedSubscribers(pageID int64) ([]store.Subscriber, error)
}

// BuildSubscriberSubject 构造订阅者通知主题。
func BuildSubscriberSubject(event, name string) string {
	switch event {
	case "down":
		return fmt.Sprintf("[sentinel] 服务状态通知：%s 宕机", name)
	case "recovered":
		return fmt.Sprintf("[sentinel] 服务状态通知：%s 已恢复", name)
	default:
		return fmt.Sprintf("[sentinel] 服务状态通知：%s %s", name, event)
	}
}

// BuildSubscriberBody 构造订阅者通知正文（纯文本）。
func BuildSubscriberBody(pageTitle, event, name, target, at, errMsg, unsubURL string) string {
	var b strings.Builder
	b.WriteString("您订阅的状态页「")
	b.WriteString(pageTitle)
	b.WriteString("」有服务状态变化：\r\n\r\n")
	b.WriteString("监控名称: ")
	b.WriteString(name)
	b.WriteString("\r\n目标: ")
	b.WriteString(target)
	b.WriteString("\r\n时间: ")
	b.WriteString(at)
	b.WriteString("\r\n")
	if event == "down" {
		b.WriteString("事件: 宕机\r\n")
		if errMsg != "" {
			b.WriteString("错误信息: ")
			b.WriteString(errMsg)
			b.WriteString("\r\n")
		}
	} else if event == "recovered" {
		b.WriteString("事件: 已恢复\r\n")
	} else {
		b.WriteString("事件: ")
		b.WriteString(event)
		b.WriteString("\r\n")
	}
	b.WriteString("\r\n退订本状态页通知：")
	b.WriteString(unsubURL)
	b.WriteString("\r\n")
	return b.String()
}

// NotifySubscribers 向包含该 monitor 的状态页的所有已确认订阅者发送事件邮件。
// 同一邮箱订阅多个页面只收一封（取首个页面的标题）。单个订阅者发送失败记日志并继续，
// src 查询失败返回 error。publicBaseURL 为空时退订链接用相对路径。
func NotifySubscribers(src SubscriberSource, mailer Mailer, publicBaseURL string, monitorID int64, event, name, target, at, errMsg string) error {
	pageIDs, err := src.ListPageIDsForMonitor(monitorID)
	if err != nil {
		return fmt.Errorf("查询状态页失败: %w", err)
	}
	seen := make(map[string]bool)
	for _, pid := range pageIDs {
		subs, err := src.ListConfirmedSubscribers(pid)
		if err != nil {
			log.Logger().Warn("查询订阅者失败", "page_id", pid, "error", err)
			continue
		}
		for _, sub := range subs {
			email := strings.ToLower(strings.TrimSpace(sub.Email))
			if email == "" || seen[email] {
				continue
			}
			seen[email] = true
			unsub := "/api/status/" + sub.PageSlug + "/unsubscribe?token=" + sub.Token
			if publicBaseURL != "" {
				unsub = publicBaseURL + unsub
			}
			subject := BuildSubscriberSubject(event, name)
			body := BuildSubscriberBody(sub.PageTitle, event, name, target, at, errMsg, unsub)
			if err := mailer.SendMail([]string{sub.Email}, subject, body); err != nil {
				log.Logger().Warn("发送订阅通知失败", "email", sub.Email, "event", event, "error", err)
			}
		}
	}
	return nil
}
