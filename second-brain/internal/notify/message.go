package notify

import (
	"fmt"
	"html"
	"strings"
	"time"
)

// Message 是一条待发送的通知内容。
type Message struct {
	To       string
	Subject  string
	TextBody string
	HTMLBody string
	DueCount int
	Items    []DigestItem
}

// DigestItem 是每日复习摘要里的单条笔记。
type DigestItem struct {
	Title       string
	Snippet     string
	Tags        []string
	DueDate     string
	OverdueDays int
}

// DigestStats 是每日复习摘要的统计信息。
type DigestStats struct {
	DueCount    int
	OverdueDays int
	Streak      int
}

// BuildDigestMessage 组装每日复习提醒。date 用于生成标题里的日期（Asia/Shanghai）。
func BuildDigestMessage(date time.Time, items []DigestItem, stats DigestStats, to string) Message {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		loc = time.UTC
	}
	local := date.In(loc)
	monthDay := fmt.Sprintf("%d月%d日", local.Month(), local.Day())

	var subject string
	if len(items) == 0 {
		subject = fmt.Sprintf("第二大脑 · %s复习提醒（今日无待复习）", monthDay)
	} else {
		subject = fmt.Sprintf("第二大脑 · %s复习提醒（%d 篇待复习）", monthDay, len(items))
	}

	return Message{
		To:       to,
		Subject:  subject,
		TextBody: buildText(items, stats),
		HTMLBody: buildHTML(items, stats),
		DueCount: len(items),
		Items:    items,
	}
}

func buildText(items []DigestItem, stats DigestStats) string {
	var b strings.Builder

	if len(items) == 0 {
		b.WriteString("今天没有到期的笔记，好好休息。\n")
	} else {
		fmt.Fprintf(&b, "今天有 %d 篇笔记到期了：\n\n", len(items))
		for i, it := range items {
			if it.OverdueDays > 0 {
				fmt.Fprintf(&b, "%d. %s（逾期 %d 天）\n", i+1, it.Title, it.OverdueDays)
			} else {
				fmt.Fprintf(&b, "%d. %s\n", i+1, it.Title)
			}
			if s := strings.TrimSpace(it.Snippet); s != "" {
				fmt.Fprintf(&b, "   %s\n", s)
			}
			if len(it.Tags) > 0 {
				fmt.Fprintf(&b, "   标签：%s\n", strings.Join(it.Tags, "、"))
			}
			b.WriteString("\n")
		}
	}

	if stats.Streak > 0 {
		fmt.Fprintf(&b, "你已经连续复习 %d 天了。\n", stats.Streak)
	}
	b.WriteString("打开第二大脑开始复习。\n")
	return b.String()
}

func buildHTML(items []DigestItem, stats DigestStats) string {
	var b strings.Builder

	b.WriteString(`<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:0;background-color:#f5f5f5;">`)
	b.WriteString(`<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5;padding:16px 0;"><tr><td align="center">`)
	b.WriteString(`<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background-color:#ffffff;border-radius:8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:#222222;">`)

	// 头部
	b.WriteString(`<tr><td style="padding:20px 24px 8px 24px;font-size:18px;font-weight:600;">第二大脑 · 复习提醒</td></tr>`)

	if len(items) == 0 {
		b.WriteString(`<tr><td style="padding:8px 24px 24px 24px;font-size:14px;line-height:22px;">今天没有到期的笔记，好好休息</td></tr>`)
	} else {
		fmt.Fprintf(&b, `<tr><td style="padding:8px 24px 8px 24px;font-size:14px;line-height:22px;">今天有 %d 篇笔记到期了：</td></tr>`, len(items))
		b.WriteString(`<tr><td style="padding:0 24px 8px 24px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">`)
		for _, it := range items {
			b.WriteString(`<tr><td style="padding:10px 0;border-top:1px solid #eeeeee;">`)
			title := html.EscapeString(it.Title)
			if it.OverdueDays > 0 {
				fmt.Fprintf(&b, `<div style="font-size:15px;font-weight:600;line-height:22px;">%s <span style="color:#c0392b;font-weight:400;">（逾期 %d 天）</span></div>`, title, it.OverdueDays)
			} else {
				fmt.Fprintf(&b, `<div style="font-size:15px;font-weight:600;line-height:22px;">%s</div>`, title)
			}
			if s := strings.TrimSpace(it.Snippet); s != "" {
				fmt.Fprintf(&b, `<div style="font-size:13px;line-height:20px;color:#555555;padding-top:4px;">%s</div>`, html.EscapeString(s))
			}
			if len(it.Tags) > 0 {
				b.WriteString(`<div style="font-size:12px;line-height:18px;color:#888888;padding-top:6px;">`)
				for _, tag := range it.Tags {
					fmt.Fprintf(&b, `<span style="display:inline-block;padding:1px 8px;margin-right:6px;background-color:#f0f0f0;border-radius:10px;">%s</span>`, html.EscapeString(tag))
				}
				b.WriteString(`</div>`)
			}
			b.WriteString(`</td></tr>`)
		}
		b.WriteString(`</table></td></tr>`)
	}

	if stats.Streak > 0 {
		fmt.Fprintf(&b, `<tr><td style="padding:8px 24px;font-size:13px;line-height:20px;color:#666666;">你已经连续复习 %d 天了。</td></tr>`, stats.Streak)
	}

	b.WriteString(`<tr><td style="padding:16px 24px 24px 24px;font-size:14px;line-height:22px;">打开第二大脑开始复习。</td></tr>`)
	b.WriteString(`</table></td></tr></table></body></html>`)

	return b.String()
}
