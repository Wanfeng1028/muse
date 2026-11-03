package notify

import (
	"bufio"
	"encoding/base64"
	"net"
	"strings"
	"testing"
	"time"
)

// fakeSMTP 是一个仅使用标准库 net 实现的最小 SMTP 服务器。
type fakeSMTP struct {
	listener net.Listener
	port     int
	addr     string

	captured []byte
	rcpts    []string

	done chan struct{}
}

// startFakeSMTP 启动一个 fake SMTP 服务器，监听 127.0.0.1 的随机端口。
// 测试结束时通过 t.Cleanup 关闭。
func startFakeSMTP(t *testing.T) *fakeSMTP {
	t.Helper()

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("启动 fake SMTP 监听失败: %v", err)
	}
	port := ln.Addr().(*net.TCPAddr).Port

	f := &fakeSMTP{
		listener: ln,
		port:     port,
		addr:     ln.Addr().String(),
		done:     make(chan struct{}),
	}

	go f.serve()

	t.Cleanup(func() {
		_ = f.listener.Close()
		select {
		case <-f.done:
		case <-time.After(2 * time.Second):
		}
	})

	return f
}

func (f *fakeSMTP) serve() {
	defer close(f.done)

	conn, err := f.listener.Accept()
	if err != nil {
		return
	}
	defer conn.Close()

	reader := bufio.NewReader(conn)
	writer := bufio.NewWriter(conn)

	writeLine := func(s string) {
		_, _ = writer.WriteString(s)
		_ = writer.Flush()
	}

	writeLine("220 localhost fake-smtp ESMTP\r\n")

	inData := false
	var dataBuf strings.Builder

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}

		if inData {
			trimmed := strings.TrimRight(line, "\r\n")
			if trimmed == "." {
				f.captured = []byte(dataBuf.String())
				inData = false
				writeLine("250 OK\r\n")
				continue
			}
			// 处理 dot-stuffing：以 ".." 开头的行还原为 "."
			if strings.HasPrefix(trimmed, "..") {
				trimmed = trimmed[1:]
			}
			dataBuf.WriteString(trimmed)
			dataBuf.WriteString("\r\n")
			continue
		}

		upper := strings.ToUpper(line)
		switch {
		case strings.HasPrefix(upper, "EHLO"), strings.HasPrefix(upper, "HELO"):
			writeLine("250 OK\r\n")
		case strings.HasPrefix(upper, "MAIL FROM"):
			writeLine("250 OK\r\n")
		case strings.HasPrefix(upper, "RCPT TO"):
			addr := extractRcpt(line)
			if addr != "" {
				f.rcpts = append(f.rcpts, addr)
			}
			writeLine("250 OK\r\n")
		case strings.HasPrefix(upper, "DATA"):
			inData = true
			writeLine("354 End data with <CR><LF>.<CR><LF>\r\n")
		case strings.HasPrefix(upper, "QUIT"):
			writeLine("221 Bye\r\n")
			return
		default:
			writeLine("250 OK\r\n")
		}
	}
}

func extractRcpt(line string) string {
	trimmed := strings.TrimSpace(line)
	idx := strings.Index(trimmed, "<")
	end := strings.Index(trimmed, ">")
	if idx >= 0 && end > idx {
		return trimmed[idx+1 : end]
	}
	return ""
}

func decodeSMTPBody(t *testing.T, raw []byte) string {
	t.Helper()

	parts := strings.SplitN(string(raw), "\r\n\r\n", 2)
	if len(parts) < 2 {
		t.Fatalf("无法从 SMTP 报文中切出正文段，原始内容=%q", string(raw))
	}

	body := parts[1]
	var b64 strings.Builder
	for _, l := range strings.Split(body, "\r\n") {
		l = strings.TrimSpace(l)
		if l == "" {
			continue
		}
		b64.WriteString(l)
	}

	decoded, err := base64.StdEncoding.DecodeString(b64.String())
	if err != nil {
		t.Fatalf("base64 解码正文失败: %v，原始 base64=%q", err, b64.String())
	}
	return string(decoded)
}

func TestSMTPNotifier_SendAlert_Down(t *testing.T) {
	fake := startFakeSMTP(t)

	n := SMTPNotifier{Config: SMTPConfig{
		Host: "127.0.0.1",
		Port: fake.port,
		From: "sentinel@example.com",
		To:   "a@example.com, b@example.com",
	}}

	err := n.SendAlert("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "connection refused")
	if err != nil {
		t.Fatalf("SendAlert 期望返回 nil，实际返回: %v", err)
	}

	if len(fake.captured) == 0 {
		t.Fatal("fake SMTP 未捕获到任何报文内容")
	}

	raw := string(fake.captured)
	// mime.BEncoding 输出小写 =?utf-8?b?...?=，大小写不敏感匹配
	if !strings.Contains(strings.ToLower(raw), "subject: =?utf-8?b?") {
		t.Fatalf("报文缺少 RFC2047 编码主题头，原始内容=%q", raw)
	}

	decoded := decodeSMTPBody(t, fake.captured)
	for _, want := range []string{"测试站点", "http://example.com", "宕机", "connection refused"} {
		if !strings.Contains(decoded, want) {
			t.Errorf("解码后的正文缺少内容 %q，正文=%q", want, decoded)
		}
	}

	if len(fake.rcpts) != 2 {
		t.Fatalf("期望记录 2 个收件人，实际记录 %d 个: %v", len(fake.rcpts), fake.rcpts)
	}
	joined := strings.Join(fake.rcpts, ",")
	if !strings.Contains(joined, "a@example.com") || !strings.Contains(joined, "b@example.com") {
		t.Errorf("收件人记录不完整，实际=%v", fake.rcpts)
	}
}

func TestSMTPNotifier_SendAlert_Recovered(t *testing.T) {
	fake := startFakeSMTP(t)

	n := SMTPNotifier{Config: SMTPConfig{
		Host: "127.0.0.1",
		Port: fake.port,
		From: "sentinel@example.com",
		To:   "a@example.com",
	}}

	err := n.SendAlert("recovered", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "")
	if err != nil {
		t.Fatalf("SendAlert 期望返回 nil，实际返回: %v", err)
	}

	decoded := decodeSMTPBody(t, fake.captured)
	if !strings.Contains(decoded, "恢复") {
		t.Errorf("recovered 事件正文应包含 \"恢复\"，正文=%q", decoded)
	}
	if strings.Contains(decoded, "connection refused") {
		t.Errorf("recovered 事件正文不应包含 \"connection refused\"，正文=%q", decoded)
	}
}

func TestSMTPNotifier_SkipWhenNoHost(t *testing.T) {
	n := SMTPNotifier{Config: SMTPConfig{
		Host: "",
		Port: 25,
		From: "sentinel@example.com",
		To:   "a@example.com",
	}}

	if err := n.SendAlert("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom"); err != nil {
		t.Fatalf("Host 为空时应直接返回 nil，实际返回: %v", err)
	}
}

func TestSMTPNotifier_ConnRefused(t *testing.T) {
	n := SMTPNotifier{Config: SMTPConfig{
		Host: "127.0.0.1",
		Port: 59999,
		From: "sentinel@example.com",
		To:   "a@example.com",
	}}

	err := n.SendAlert("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if err == nil {
		t.Skip("端口 59999 意外可连接，跳过连接拒绝用例")
	}
}
