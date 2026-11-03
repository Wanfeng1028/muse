package notify

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"net"
	"net/smtp"
	"net/textproto"
	"strconv"
	"strings"
	"time"
)

// SMTPSender 通过 SMTP 发送邮件通知。
type SMTPSender struct {
	host     string
	port     int
	username string
	password string
	from     string
	useTLS   bool
}

// NewSMTPSender 构造一个 SMTP 发送器。useTLS 为 true 时使用 STARTTLS。
func NewSMTPSender(host string, port int, username, password, from string, useTLS bool) *SMTPSender {
	return &SMTPSender{
		host:     host,
		port:     port,
		username: username,
		password: password,
		from:     from,
		useTLS:   useTLS,
	}
}

// Name 实现 Sender 接口。
func (s *SMTPSender) Name() string { return "smtp" }

// Send 实现 Sender 接口。
func (s *SMTPSender) Send(ctx context.Context, msg Message) error {
	if s.host == "" {
		return fmt.Errorf("%w: 未配置 SMTP 主机", ErrConn)
	}

	addr := net.JoinHostPort(s.host, strconv.Itoa(s.port))

	dialer := &net.Dialer{Timeout: 10 * time.Second}
	var conn net.Conn
	var err error
	if s.useTLS {
		conn, err = tls.DialWithDialer(dialer, "tcp", addr, &tls.Config{ServerName: s.host})
	} else {
		conn, err = dialer.DialContext(ctx, "tcp", addr)
	}
	if err != nil {
		return fmt.Errorf("%w: 连接 %s 失败: %v", ErrConn, addr, err)
	}

	client, err := smtp.NewClient(conn, s.host)
	if err != nil {
		_ = conn.Close()
		return fmt.Errorf("%w: 创建 SMTP 客户端失败: %v", ErrConn, err)
	}
	defer func() { _ = client.Close() }()

	if !s.useTLS {
		if ok, _ := client.Extension("STARTTLS"); ok {
			if err := client.StartTLS(&tls.Config{ServerName: s.host}); err != nil {
				return fmt.Errorf("%w: STARTTLS 失败: %v", ErrConn, err)
			}
		}
	}

	if s.username != "" {
		auth := smtp.PlainAuth("", s.username, s.password, s.host)
		if err := client.Auth(auth); err != nil {
			if isAuthErr(err) {
				return fmt.Errorf("%w: 认证被拒绝", ErrAuth)
			}
			return fmt.Errorf("%w: 认证失败: %v", ErrAuth, err)
		}
	}

	if err := client.Mail(s.from); err != nil {
		return fmt.Errorf("%w: MAIL FROM 失败: %v", ErrConn, err)
	}
	for _, rcpt := range splitRecipients(msg.To) {
		if err := client.Rcpt(rcpt); err != nil {
			return fmt.Errorf("%w: RCPT TO 失败: %v", ErrConn, err)
		}
	}

	w, err := client.Data()
	if err != nil {
		return fmt.Errorf("%w: DATA 失败: %v", ErrConn, err)
	}
	if _, err := w.Write(buildMIME(s.from, msg)); err != nil {
		_ = w.Close()
		return fmt.Errorf("%w: 写入邮件正文失败: %v", ErrConn, err)
	}
	if err := w.Close(); err != nil {
		return fmt.Errorf("%w: 关闭邮件正文失败: %v", ErrConn, err)
	}

	if err := client.Quit(); err != nil {
		return fmt.Errorf("%w: QUIT 失败: %v", ErrConn, err)
	}
	return nil
}

func isAuthErr(err error) bool {
	var tpErr *textproto.Error
	if errors.As(err, &tpErr) {
		return tpErr.Code == 535 || tpErr.Code == 534 || tpErr.Code == 530
	}
	msg := err.Error()
	return strings.Contains(msg, "535") || strings.Contains(msg, "authentication failed")
}

func splitRecipients(to string) []string {
	parts := strings.FieldsFunc(to, func(r rune) bool { return r == ',' || r == ';' })
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func buildMIME(from string, msg Message) []byte {
	const boundary = "second-brain-boundary"

	var b strings.Builder
	writeHeader := func(k, v string) {
		b.WriteString(k)
		b.WriteString(": ")
		b.WriteString(v)
		b.WriteString("\r\n")
	}
	writeHeader("From", from)
	writeHeader("To", msg.To)
	writeHeader("Subject", encodeSubject(msg.Subject))
	writeHeader("MIME-Version", "1.0")
	writeHeader("Content-Type", "multipart/alternative; boundary=\""+boundary+"\"")
	b.WriteString("\r\n")

	b.WriteString("--" + boundary + "\r\n")
	b.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	b.WriteString("Content-Transfer-Encoding: 8bit\r\n\r\n")
	b.WriteString(msg.TextBody)
	b.WriteString("\r\n")

	b.WriteString("--" + boundary + "\r\n")
	b.WriteString("Content-Type: text/html; charset=UTF-8\r\n")
	b.WriteString("Content-Transfer-Encoding: 8bit\r\n\r\n")
	b.WriteString(msg.HTMLBody)
	b.WriteString("\r\n")

	b.WriteString("--" + boundary + "--\r\n")
	return []byte(b.String())
}

// encodeSubject 对非 ASCII 主题做 RFC 2047 编码。
func encodeSubject(s string) string {
	ascii := true
	for i := 0; i < len(s); i++ {
		if s[i] >= 0x80 {
			ascii = false
			break
		}
	}
	if ascii {
		return s
	}
	return "=?UTF-8?B?" + base64Std(s) + "?="
}
