package notify

import (
	"crypto/tls"
	"encoding/base64"
	"fmt"
	"mime"
	"net"
	"net/smtp"
	"strings"
	"time"

	"sentinel/internal/log"
)

// SMTPConfig 描述 SMTP 邮件告警配置。
type SMTPConfig struct {
	Host     string // SMTP 服务器地址，空表示未配置
	Port     int    // 端口，<=0 时默认 25
	Username string // 鉴权用户名，空表示不鉴权
	Password string // 鉴权密码
	From     string // 发件人地址
	To       string // 收件人地址，逗号分隔支持多个
}

// SMTPNotifier 通过 SMTP 发送告警邮件。
type SMTPNotifier struct {
	Config SMTPConfig
}

// splitRecipients 按逗号切分收件人，去空格、去空项。
func splitRecipients(to string) []string {
	var out []string
	for _, part := range strings.Split(to, ",") {
		addr := strings.TrimSpace(part)
		if addr != "" {
			out = append(out, addr)
		}
	}
	return out
}

// buildSubject 依据 event 构造主题原文。
func buildSubject(event, name string) string {
	switch event {
	case "down":
		return fmt.Sprintf("[sentinel] 告警：%s 宕机", name)
	case "recovered":
		return fmt.Sprintf("[sentinel] 恢复：%s 已恢复", name)
	default:
		return fmt.Sprintf("[sentinel] %s：%s", event, name)
	}
}

// buildBody 构造正文内容，按行组织。
func buildBody(event, name, target, at, errMsg string) string {
	var b strings.Builder
	b.WriteString("监控名称: ")
	b.WriteString(name)
	b.WriteString("\r\n")
	b.WriteString("目标: ")
	b.WriteString(target)
	b.WriteString("\r\n")
	b.WriteString("时间: ")
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
		b.WriteString("事件: 恢复\r\n")
	} else {
		b.WriteString("事件: ")
		b.WriteString(event)
		b.WriteString("\r\n")
		if errMsg != "" {
			b.WriteString("错误信息: ")
			b.WriteString(errMsg)
			b.WriteString("\r\n")
		}
	}
	return b.String()
}

// buildMessage 组装完整 RFC822 消息（含头部与正文）。
func buildMessage(cfg SMTPConfig, recipients []string, event, name, target, at, errMsg string) []byte {
	subject := buildSubject(event, name)
	encodedSubject := mime.BEncoding.Encode("utf-8", subject)

	var b strings.Builder
	b.WriteString("From: ")
	b.WriteString(cfg.From)
	b.WriteString("\r\n")
	b.WriteString("To: ")
	b.WriteString(strings.Join(recipients, ", "))
	b.WriteString("\r\n")
	b.WriteString("Subject: ")
	b.WriteString(encodedSubject)
	b.WriteString("\r\n")
	b.WriteString("MIME-Version: 1.0\r\n")
	b.WriteString("Content-Type: text/plain; charset=utf-8\r\n")
	b.WriteString("Content-Transfer-Encoding: base64\r\n")
	b.WriteString("\r\n")
	b.WriteString(base64.StdEncoding.EncodeToString([]byte(buildBody(event, name, target, at, errMsg))))
	return []byte(b.String())
}

// dialSMTP 建立到 SMTP 服务器的连接，返回客户端。
func dialSMTP(cfg SMTPConfig, port int) (*smtp.Client, error) {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	addr := net.JoinHostPort(cfg.Host, fmt.Sprintf("%d", port))

	if port == 465 {
		conn, err := tls.DialWithDialer(dialer, "tcp", addr, &tls.Config{ServerName: cfg.Host})
		if err != nil {
			return nil, fmt.Errorf("建立 SMTPS 连接失败: %w", err)
		}
		c, err := smtp.NewClient(conn, cfg.Host)
		if err != nil {
			_ = conn.Close()
			return nil, fmt.Errorf("创建 SMTP 客户端失败: %w", err)
		}
		return c, nil
	}

	conn, err := dialer.Dial("tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("建立 SMTP 连接失败: %w", err)
	}
	c, err := smtp.NewClient(conn, cfg.Host)
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("创建 SMTP 客户端失败: %w", err)
	}
	if err := c.Hello("localhost"); err != nil {
		_ = c.Close()
		return nil, fmt.Errorf("SMTP Hello 失败: %w", err)
	}
	if ok, _ := c.Extension("STARTTLS"); ok {
		if err := c.StartTLS(&tls.Config{ServerName: cfg.Host}); err != nil {
			_ = c.Close()
			return nil, fmt.Errorf("SMTP STARTTLS 失败: %w", err)
		}
	}
	return c, nil
}

// authenticate 在满足条件时执行 PlainAuth 鉴权。
func authenticate(c *smtp.Client, cfg SMTPConfig) error {
	if cfg.Username == "" {
		return nil
	}
	host, _, err := net.SplitHostPort(cfg.Host + ":25")
	_ = host
	if err != nil {
		// 非标准 host 形式时回退为原值
		host = cfg.Host
	}
	// 仅当已处于 TLS 或对端为 localhost 时才调用 PlainAuth。
	if ok, _ := c.Extension("STARTTLS"); ok {
		return fmt.Errorf("未完成 STARTTLS，拒绝发送明文凭据")
	}
	auth := smtp.PlainAuth("", cfg.Username, cfg.Password, host)
	if err := c.Auth(auth); err != nil {
		return fmt.Errorf("SMTP 鉴权失败: %w", err)
	}
	return nil
}

// SendAlert 发送告警邮件。event 取值 "down" 或 "recovered"。
// Config.Host 为空表示渠道未配置，直接返回 nil（跳过，不报错）。
func (n SMTPNotifier) SendAlert(event, name, target, at, errMsg string) error {
	cfg := n.Config
	if cfg.Host == "" {
		return nil
	}

	port := cfg.Port
	if port <= 0 {
		port = 25
	}

	recipients := splitRecipients(cfg.To)
	if len(recipients) == 0 {
		return fmt.Errorf("SMTP 收件人为空")
	}

	message := buildMessage(cfg, recipients, event, name, target, at, errMsg)

	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		err := sendOnce(cfg, port, recipients, message)
		if err == nil {
			return nil
		}
		lastErr = err
		log.Logger().Warn("发送 SMTP 邮件失败",
			"host", cfg.Host,
			"port", port,
			"attempt", attempt+1,
			"error", err,
		)
		if attempt < 2 {
			backoff := time.Duration(1<<uint(attempt)) * time.Second
			time.Sleep(backoff)
		}
	}

	return fmt.Errorf("SMTP 邮件发送失败: %w", lastErr)
}

// sendOnce 执行一次完整的邮件发送流程，任何一步失败都返回 error。
func sendOnce(cfg SMTPConfig, port int, recipients []string, message []byte) error {
	c, err := dialSMTP(cfg, port)
	if err != nil {
		return err
	}
	defer func() {
		_ = c.Quit()
		_ = c.Close()
	}()

	if err := authenticate(c, cfg); err != nil {
		return err
	}

	if err := c.Mail(cfg.From); err != nil {
		return fmt.Errorf("SMTP Mail 失败: %w", err)
	}
	for _, rcpt := range recipients {
		if err := c.Rcpt(rcpt); err != nil {
			return fmt.Errorf("SMTP Rcpt 失败: %w", err)
		}
	}

	w, err := c.Data()
	if err != nil {
		return fmt.Errorf("SMTP Data 失败: %w", err)
	}
	if _, err := w.Write(message); err != nil {
		_ = w.Close()
		return fmt.Errorf("写入邮件正文失败: %w", err)
	}
	if err := w.Close(); err != nil {
		return fmt.Errorf("关闭邮件正文失败: %w", err)
	}
	return nil
}
