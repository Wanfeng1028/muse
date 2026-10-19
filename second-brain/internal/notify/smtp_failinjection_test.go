package notify

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"mime"
	"net"
	"strings"
	"sync"
	"testing"
	"time"
)

// smtpScriptStep 描述 fake SMTP 服务器的一条处理步骤。
//
// expectPrefix: 期望从客户端读到的命令前缀；为空表示不读直接发送响应。
// reply:        发送给客户端的响应行（自动补 CRLF）。
// closeAfter:   发送响应后是否立刻关闭连接。
type smtpScriptStep struct {
	expectPrefix string
	reply        string
	closeAfter   bool
	// dataPhase 为 true 时表示这是 DATA 步骤：先发 reply（354），再读取正文直到单独 "." 行。
	dataPhase bool
}

// scriptedSMTPServer 是最小可用的假 SMTP 服务器，用脚本驱动响应。
//
// 每条步骤会（可选）读取一行客户端命令，校验前缀匹配后回写响应。
// 所有读取到的命令会被累积到 received，供测试断言 DATA 内容。
type scriptedSMTPServer struct {
	ln       net.Listener
	script   []smtpScriptStep
	ready    chan struct{}
	received []string
	mu       sync.Mutex
	wg       sync.WaitGroup
}

// newFakeSMTPServer 启动 fake 服务器并返回实例。
// ready 在 accept 循环就绪（listener 已绑定）后关闭。
func newFakeSMTPServer(t *testing.T, script []smtpScriptStep) *scriptedSMTPServer {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听 fake SMTP 端口失败: %v", err)
	}
	s := &scriptedSMTPServer{
		ln:     ln,
		script: script,
		ready:  make(chan struct{}),
	}
	s.wg.Add(1)
	go s.serve()
	close(s.ready)
	t.Cleanup(func() {
		_ = ln.Close()
		s.wg.Wait()
	})
	return s
}

// addr 返回 "host:port"。
func (s *scriptedSMTPServer) addr() string {
	return s.ln.Addr().String()
}

// host 返回监听地址的 host 部分。
func (s *scriptedSMTPServer) host() string {
	h, _, _ := net.SplitHostPort(s.addr())
	return h
}

// port 返回监听地址的 port 部分（整数）。
func (s *scriptedSMTPServer) port(t *testing.T) int {
	t.Helper()
	_, p, err := net.SplitHostPort(s.addr())
	if err != nil {
		t.Fatalf("解析 fake SMTP 地址失败: %v", err)
	}
	var n int
	if _, err := fmt.Sscanf(p, "%d", &n); err != nil {
		t.Fatalf("解析 fake SMTP 端口失败: %v", err)
	}
	return n
}

// waitReady 阻塞直到服务器开始 accept。
func (s *scriptedSMTPServer) waitReady() {
	<-s.ready
}

// receivedLines 返回已收到的所有行（去掉 CRLF）。
func (s *scriptedSMTPServer) receivedLines() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]string, len(s.received))
	copy(out, s.received)
	return out
}

// receivedJoined 返回所有收到的行拼接结果，便于 strings.Contains 检查。
func (s *scriptedSMTPServer) receivedJoined() string {
	return strings.Join(s.receivedLines(), "\n")
}

func (s *scriptedSMTPServer) record(line string) {
	s.mu.Lock()
	s.received = append(s.received, line)
	s.mu.Unlock()
}

// serve 接受一个连接并按 script 执行。测试场景均为单连接，够用。
func (s *scriptedSMTPServer) serve() {
	defer s.wg.Done()
	conn, err := s.ln.Accept()
	if err != nil {
		return
	}
	defer conn.Close()

	// 设置读写超时，避免测试挂死。
	_ = conn.SetDeadline(time.Now().Add(8 * time.Second))

	br := bufio.NewReader(conn)
	bw := bufio.NewWriter(conn)

	for _, step := range s.script {
		if step.expectPrefix != "" {
			line, err := br.ReadString('\n')
			if err != nil {
				return
			}
			trimmed := strings.TrimRight(line, "\r\n")
			s.record(trimmed)
			if !strings.HasPrefix(trimmed, step.expectPrefix) {
				// 命令不匹配，静默关闭，让客户端侧报错。
				return
			}

		}
		if step.reply != "" {
			if _, err := bw.WriteString(step.reply + "\r\n"); err != nil {
				return
			}
			if err := bw.Flush(); err != nil {
				return
			}
		}
		if step.dataPhase {
			// DATA 阶段：354 已发出，现在读取正文直到单独的 "." 行。
			for {
				dl, err := br.ReadString('\n')
				if err != nil {
					return
				}
				s.record(strings.TrimRight(dl, "\r\n"))
				if dl == ".\r\n" || dl == ".\n" {
					break
				}
			}
		}
		if step.closeAfter {
			return
		}
	}

	// 若脚本走完客户端仍有输出（如 QUIT 之后），继续读到连接关闭为止。
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			return
		}
		s.record(strings.TrimRight(line, "\r\n"))
	}
}

// TestSMTPSend_HandshakeInterrupted 握手阶段连接被中断，应归类为 ErrConn。
func TestSMTPSend_HandshakeInterrupted(t *testing.T) {
	srv := newFakeSMTPServer(t, []smtpScriptStep{
		{reply: "220 fake ESMTP ready", closeAfter: true},
	})
	srv.waitReady()

	s := NewSMTPSender(srv.host(), srv.port(t), "", "", "from@example.com", false)
	msg := Message{To: "to@example.com", Subject: "握手抖动", TextBody: "hi"}
	err := s.Send(context.Background(), msg)
	if err == nil {
		t.Fatalf("期望握手中断返回错误，实际为 nil")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("期望 errors.Is(err, ErrConn)=true，实际 err=%v", err)
	}
	if errors.Is(err, ErrAuth) {
		t.Fatalf("握手中断不应归类为 ErrAuth，实际 err=%v", err)
	}
}

// TestSMTPSend_ConnectionRefused 端口无人监听，dial 失败应归类为 ErrConn。
func TestSMTPSend_ConnectionRefused(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("预占端口失败: %v", err)
	}
	addr := ln.Addr().String()
	if err := ln.Close(); err != nil {
		t.Fatalf("关闭预占端口失败: %v", err)
	}
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		t.Fatalf("解析地址失败: %v", err)
	}
	var port int
	if _, err := fmt.Sscanf(portStr, "%d", &port); err != nil {
		t.Fatalf("解析端口失败: %v", err)
	}

	s := NewSMTPSender(host, port, "", "", "from@example.com", false)
	msg := Message{To: "to@example.com", Subject: "连接被拒", TextBody: "hi"}
	err = s.Send(context.Background(), msg)
	if err == nil {
		t.Fatalf("期望连接被拒返回错误，实际为 nil")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("期望 errors.Is(err, ErrConn)=true，实际 err=%v", err)
	}
}

// TestSMTPSend_AuthRejected535 服务器完整走完 banner/EHLO 后 AUTH 返回 535，应归类为 ErrAuth。
func TestSMTPSend_AuthRejected535(t *testing.T) {
	srv := newFakeSMTPServer(t, []smtpScriptStep{
		{reply: "220 fake ESMTP ready"},
		{expectPrefix: "EHLO", reply: "250-fake\r\n250 AUTH PLAIN LOGIN"},
		{expectPrefix: "AUTH", reply: "535 5.7.8 bad credentials"},
		{expectPrefix: "QUIT", reply: "221 bye"},
	})
	srv.waitReady()

	s := NewSMTPSender(srv.host(), srv.port(t), "user@example.com", "wrong", "from@example.com", false)
	msg := Message{To: "to@example.com", Subject: "认证被拒", TextBody: "hi"}
	err := s.Send(context.Background(), msg)
	if err == nil {
		t.Fatalf("期望认证被拒返回错误，实际为 nil")
	}
	if !errors.Is(err, ErrAuth) {
		t.Fatalf("期望 errors.Is(err, ErrAuth)=true，实际 err=%v", err)
	}
	if errors.Is(err, ErrConn) {
		t.Fatalf("认证被拒不应归类为 ErrConn，实际 err=%v", err)
	}
}

// TestSMTPSend_FullDialogueSuccess 完整成功 roundtrip，验证 fake 服务器协议合法。
func TestSMTPSend_FullDialogueSuccess(t *testing.T) {
	const subject = "完整对话成功"
	srv := newFakeSMTPServer(t, []smtpScriptStep{
		{reply: "220 fake ESMTP ready"},
		{expectPrefix: "EHLO", reply: "250-fake\r\n250 AUTH PLAIN LOGIN"},
		{expectPrefix: "AUTH", reply: "235 2.7.0 authentication succeeded"},
		{expectPrefix: "MAIL FROM", reply: "250 OK"},
		{expectPrefix: "RCPT TO", reply: "250 OK"},
		{expectPrefix: "DATA", reply: "354 end with . on a line by itself", dataPhase: true},
		{reply: "250 OK queued"},
		{expectPrefix: "QUIT", reply: "221 bye"},
	})
	srv.waitReady()

	s := NewSMTPSender(srv.host(), srv.port(t), "user@example.com", "secret", "from@example.com", false)
	msg := Message{To: "to@example.com", Subject: subject, TextBody: "body text"}
	if err := s.Send(context.Background(), msg); err != nil {
		t.Fatalf("期望 Send 成功，实际 err=%v", err)
	}
	got := srv.receivedJoined()
	// Subject 按 RFC2047 编码传输，逐行找到 Subject 头解码后再断言。
	found := false
	for _, line := range strings.Split(got, "\n") {
		if strings.HasPrefix(line, "Subject:") {
			enc := strings.TrimSpace(strings.TrimPrefix(line, "Subject:"))
			dec, derr := new(mime.WordDecoder).DecodeHeader(enc)
			if derr != nil {
				t.Fatalf("解码 Subject 失败: %v", derr)
			}
			if dec != subject {
				t.Fatalf("解码后主题=%q, want %q", dec, subject)
			}
			found = true
		}
	}
	if !found {
		t.Fatalf("DATA 内容中未找到 Subject 头，实际收到: %q", got)
	}
}
