package notify

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"net"
	"net/textproto"
	"strconv"
	"strings"
	"testing"
	"time"
)

// fakeSMTPServer 启动一个最小可用的 SMTP 服务端，用于真实驱动 SMTPSender。
// 返回地址与关闭函数。行为由 handler 决定。
func fakeSMTPServer(t *testing.T, handler func(tp *textproto.Conn, dataCh chan<- string) error) (string, <-chan string, func()) {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	done := make(chan struct{})
	dataCh := make(chan string, 1)
	go func() {
		defer close(done)
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer func() { _ = c.Close() }()
				tp := textproto.NewConn(c)
				if err := handler(tp, dataCh); err != nil {
					_ = tp.PrintfLine("421 handler error")
				}
			}(conn)
		}
	}()
	return ln.Addr().String(), dataCh, func() { _ = ln.Close(); <-done }
}

// happyHandler 是一个标准的接收流程，最终把 DATA 内容写入 dataCh。
func happyHandler(tp *textproto.Conn, dataCh chan<- string) error {
	if err := tp.PrintfLine("220 fake ESMTP"); err != nil {
		return err
	}
	for {
		line, err := tp.ReadLine()
		if err != nil {
			return err
		}
		upper := strings.ToUpper(line)
		switch {
		case strings.HasPrefix(upper, "EHLO"), strings.HasPrefix(upper, "HELO"):
			if err := tp.PrintfLine("250 fake"); err != nil {
				return err
			}
		case strings.HasPrefix(upper, "AUTH"):
			if err := tp.PrintfLine("235 ok"); err != nil {
				return err
			}
		case strings.HasPrefix(upper, "MAIL FROM"):
			if err := tp.PrintfLine("250 ok"); err != nil {
				return err
			}
		case strings.HasPrefix(upper, "RCPT TO"):
			if err := tp.PrintfLine("250 ok"); err != nil {
				return err
			}
		case strings.HasPrefix(upper, "DATA"):
			if err := tp.PrintfLine("354 go"); err != nil {
				return err
			}
			var body strings.Builder
			for {
				dl, err := tp.ReadLine()
				if err != nil {
					return err
				}
				if dl == "." {
					break
				}
				body.WriteString(dl)
				body.WriteString("\r\n")
			}
			dataCh <- body.String()
			if err := tp.PrintfLine("250 queued"); err != nil {
				return err
			}
		case strings.HasPrefix(upper, "QUIT"):
			_ = tp.PrintfLine("221 bye")
			return nil
		case strings.HasPrefix(upper, "RSET"):
			if err := tp.PrintfLine("250 ok"); err != nil {
				return err
			}
		default:
			if err := tp.PrintfLine("250 ok"); err != nil {
				return err
			}
		}
	}
}

func TestSMTPSender_Name(t *testing.T) {
	s := NewSMTPSender("h", 25, "", "", "a@b.c", false)
	if got := s.Name(); got != "smtp" {
		t.Fatalf("Name() = %q, 期望 smtp", got)
	}
	if s.host != "h" || s.port != 25 || s.useTLS {
		t.Fatalf("构造结果字段不符: host=%q port=%d useTLS=%v", s.host, s.port, s.useTLS)
	}
}

func TestSMTPSender_Send_HostEmpty(t *testing.T) {
	s := NewSMTPSender("", 25, "", "", "a@b.c", false)
	err := s.Send(context.Background(), Message{To: "x@y.z", Subject: "s"})
	if err == nil {
		t.Fatal("空主机应报错")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("错误应包装 ErrConn, 实际 %v", err)
	}
	if !strings.Contains(err.Error(), "未配置 SMTP 主机") {
		t.Fatalf("错误信息应含原因, 实际 %v", err)
	}
}

func TestSMTPSender_Send_DialError(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	_, portStr, _ := net.SplitHostPort(ln.Addr().String())
	port, _ := strconv.Atoi(portStr)
	_ = ln.Close()

	s := NewSMTPSender("127.0.0.1", port, "", "", "a@b.c", false)
	err = s.Send(context.Background(), Message{To: "x@y.z", Subject: "s"})
	if err == nil {
		t.Fatal("连接已关闭端口应报错")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("错误应包装 ErrConn, 实际 %v", err)
	}
	if !strings.Contains(err.Error(), "失败") {
		t.Fatalf("错误信息应含失败原因, 实际 %v", err)
	}
}

func TestSMTPSender_Send_AuthRejected(t *testing.T) {
	addr, _, stop := fakeSMTPServer(t, func(tp *textproto.Conn, _ chan<- string) error {
		if err := tp.PrintfLine("220 fake"); err != nil {
			return err
		}
		for {
			line, err := tp.ReadLine()
			if err != nil {
				return err
			}
			u := strings.ToUpper(line)
			switch {
			case strings.HasPrefix(u, "EHLO"), strings.HasPrefix(u, "HELO"):
				if err := tp.PrintfLine("250 fake"); err != nil {
					return err
				}
			case strings.HasPrefix(u, "AUTH"):
				if err := tp.PrintfLine("535 bad credentials"); err != nil {
					return err
				}
			case strings.HasPrefix(u, "QUIT"):
				_ = tp.PrintfLine("221 bye")
				return nil
			default:
				if err := tp.PrintfLine("250 ok"); err != nil {
					return err
				}
			}
		}
	})
	defer stop()

	host, portStr, _ := net.SplitHostPort(addr)
	port, _ := strconv.Atoi(portStr)
	s := NewSMTPSender(host, port, "user", "pass", "from@a.b", false)
	err := s.Send(context.Background(), Message{To: "x@y.z", Subject: "s"})
	if err == nil {
		t.Fatal("认证被拒应报错")
	}
	if !errors.Is(err, ErrAuth) {
		t.Fatalf("错误应包装 ErrAuth, 实际 %v", err)
	}
	if !strings.Contains(err.Error(), "认证") {
		t.Fatalf("错误信息应含认证, 实际 %v", err)
	}
}

func TestSplitRecipients(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want []string
	}{
		{"单收件人", "a@b.c", []string{"a@b.c"}},
		{"逗号分隔", "a@b.c,d@e.f", []string{"a@b.c", "d@e.f"}},
		{"分号分隔", "a@b.c;d@e.f", []string{"a@b.c", "d@e.f"}},
		{"混合与空白", " a@b.c , ; d@e.f ", []string{"a@b.c", "d@e.f"}},
		{"空串", "", []string{}},
		{"仅分隔符", " , ; ", []string{}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := splitRecipients(tc.in)
			if len(got) != len(tc.want) {
				t.Fatalf("长度不符: got=%v want=%v", got, tc.want)
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Fatalf("第 %d 项不符: got=%q want=%q", i, got[i], tc.want[i])
				}
			}
		})
	}
}

func TestEncodeSubject(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"纯 ASCII 原样", "hello world", "hello world"},
		{"中文需编码", "你好", "=?UTF-8?B?" + base64Std("你好") + "?="},
		{"混合含非 ASCII", "hi 晚风", "=?UTF-8?B?" + base64Std("hi 晚风") + "?="},
		{"空串", "", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := encodeSubject(tc.in)
			if got != tc.want {
				t.Fatalf("got=%q want=%q", got, tc.want)
			}
			if tc.in != "" && strings.ContainsAny(tc.in, "你好晚风") {
				if !strings.HasPrefix(got, "=?UTF-8?B?") {
					t.Fatalf("非 ASCII 应以 RFC2047 编码开头, got=%q", got)
				}
			}
		})
	}
}

func TestBuildMIME_Structure(t *testing.T) {
	msg := Message{
		To:       "x@y.z",
		Subject:  "hi 晚风",
		TextBody: "纯文本内容",
		HTMLBody: "<p>html</p>",
	}
	raw := string(buildMIME("from@a.b", msg))

	checks := []struct {
		desc string
		want string
	}{
		{"From 头", "From: from@a.b\r\n"},
		{"To 头", "To: x@y.z\r\n"},
		{"MIME 版本", "MIME-Version: 1.0\r\n"},
		{"boundary 声明", "Content-Type: multipart/alternative; boundary=\"second-brain-boundary\"\r\n"},
		{"plain 段", "Content-Type: text/plain; charset=UTF-8\r\n"},
		{"html 段", "Content-Type: text/html; charset=UTF-8\r\n"},
		{"正文文本", "纯文本内容\r\n"},
		{"正文 html", "<p>html</p>\r\n"},
		{"结束 boundary", "--second-brain-boundary--\r\n"},
	}
	for _, c := range checks {
		if !strings.Contains(raw, c.want) {
			t.Fatalf("%s 缺失, want 含 %q", c.desc, c.want)
		}
	}
	if strings.Contains(raw, msg.Subject) {
		t.Fatalf("非 ASCII 主题不应明文出现, raw=%q", raw)
	}
	if !strings.Contains(raw, "=?UTF-8?B?"+base64Std("hi 晚风")+"?=") {
		t.Fatalf("主题应做 RFC2047 编码, raw=%q", raw)
	}
}

func TestIsAuthErr(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want bool
	}{
		{"535 textproto", &textproto.Error{Code: 535, Msg: "bad"}, true},
		{"534 textproto", &textproto.Error{Code: 534, Msg: "bad"}, true},
		{"530 textproto", &textproto.Error{Code: 530, Msg: "bad"}, true},
		{"550 textproto", &textproto.Error{Code: 550, Msg: "no"}, false},
		{"错误文本含 535", errors.New("server said 535 no"), true},
		{"错误文本含 authentication failed", errors.New("authentication failed"), true},
		{"普通错误", errors.New("io timeout"), false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := isAuthErr(tc.err)
			if got != tc.want {
				t.Fatalf("isAuthErr(%v) = %v, want %v", tc.err, got, tc.want)
			}
			if tc.want && tc.err == nil {
				t.Fatal("不应为 nil 错误")
			}
		})
	}
}

func TestSMTPSender_Send_HappyPath(t *testing.T) {
	addr, dataCh, stop := fakeSMTPServer(t, func(tp *textproto.Conn, ch chan<- string) error {
		return happyHandler(tp, ch)
	})
	defer stop()

	host, portStr, _ := net.SplitHostPort(addr)
	port, _ := strconv.Atoi(portStr)
	s := NewSMTPSender(host, port, "", "", "from@a.b", false)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	msg := Message{
		To:       "a@b.c;d@e.f",
		Subject:  "测试主题",
		TextBody: "text",
		HTMLBody: "<b>html</b>",
	}
	if err := s.Send(ctx, msg); err != nil {
		t.Fatalf("发送失败: %v", err)
	}
	select {
	case body := <-dataCh:
		if !strings.Contains(body, "From: from@a.b\r\n") {
			t.Fatalf("DATA 中缺 From, body=%q", body)
		}
		if !strings.Contains(body, "Content-Type: multipart/alternative") {
			t.Fatalf("DATA 中缺 multipart, body=%q", body)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("未收到 DATA 内容")
	}
}

func TestSMTPSender_Send_ServerDropBeforeData(t *testing.T) {
	addr, _, stop := fakeSMTPServer(t, func(tp *textproto.Conn, _ chan<- string) error {
		if err := tp.PrintfLine("220 fake"); err != nil {
			return err
		}
		_, _ = tp.ReadLine()
		if err := tp.PrintfLine("250 fake"); err != nil {
			return err
		}
		_, _ = tp.ReadLine()
		if err := tp.PrintfLine("550 mailbox unavailable"); err != nil {
			return err
		}
		_, _ = tp.ReadLine()
		return nil
	})
	defer stop()

	host, portStr, _ := net.SplitHostPort(addr)
	port, _ := strconv.Atoi(portStr)
	s := NewSMTPSender(host, port, "", "", "from@a.b", false)
	err := s.Send(context.Background(), Message{To: "x@y.z", Subject: "s"})
	if err == nil {
		t.Fatal("MAIL FROM 被拒应报错")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("错误应包装 ErrConn, 实际 %v", err)
	}
	if !strings.Contains(err.Error(), "MAIL FROM") {
		t.Fatalf("错误信息应指向 MAIL FROM, 实际 %v", err)
	}
}

func TestSMTPSender_Send_ContextCanceled(t *testing.T) {
	addr, _, stop := fakeSMTPServer(t, func(tp *textproto.Conn, _ chan<- string) error {
		if err := tp.PrintfLine("220 fake"); err != nil {
			return err
		}
		time.Sleep(2 * time.Second)
		_ = tp.PrintfLine("250 fake")
		return nil
	})
	defer stop()

	host, portStr, _ := net.SplitHostPort(addr)
	port, _ := strconv.Atoi(portStr)
	s := NewSMTPSender(host, port, "", "", "from@a.b", false)
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	err := s.Send(ctx, Message{To: "x@y.z", Subject: "s"})
	if err == nil {
		t.Fatal("上下文取消应导致发送失败")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("错误应包装 ErrConn, 实际 %v", err)
	}
	if !strings.Contains(err.Error(), "失败") {
		t.Fatalf("错误信息应含失败, 实际 %v", err)
	}
}

func TestSMTPSender_Send_MultipleRcpt(t *testing.T) {
	rcptCh := make(chan []string, 1)
	addr, _, stop := fakeSMTPServer(t, func(tp *textproto.Conn, _ chan<- string) error {
		if err := tp.PrintfLine("220 fake"); err != nil {
			return err
		}
		var rcpts []string
		for {
			line, err := tp.ReadLine()
			if err != nil {
				break
			}
			u := strings.ToUpper(line)
			switch {
			case strings.HasPrefix(u, "EHLO"), strings.HasPrefix(u, "HELO"):
				if err := tp.PrintfLine("250 fake"); err != nil {
					return err
				}
			case strings.HasPrefix(u, "MAIL FROM"):
				if err := tp.PrintfLine("250 ok"); err != nil {
					return err
				}
			case strings.HasPrefix(u, "RCPT TO"):
				rcpts = append(rcpts, line)
				if err := tp.PrintfLine("250 ok"); err != nil {
					return err
				}
			case strings.HasPrefix(u, "QUIT"):
				rcptCh <- rcpts
				_ = tp.PrintfLine("221 bye")
				return nil
			default:
				if err := tp.PrintfLine("250 ok"); err != nil {
					return err
				}
			}
		}
		rcptCh <- rcpts
		return nil
	})
	defer stop()

	host, portStr, _ := net.SplitHostPort(addr)
	port, _ := strconv.Atoi(portStr)
	s := NewSMTPSender(host, port, "", "", "from@a.b", false)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	to := "a@b.c, d@e.f; g@h.i"
	msg := Message{To: to, Subject: "s", TextBody: "t"}
	// 服务端在收到 DATA 后会断开，这里只关心 RCPT 数量，因此忽略发送结果。
	_ = s.Send(ctx, msg)

	select {
	case rcpts := <-rcptCh:
		if len(rcpts) != 3 {
			t.Fatalf("RCPT 数量 = %d, want 3, rcpts=%v", len(rcpts), rcpts)
		}
		wantContains := []string{"<a@b.c>", "<d@e.f>", "<g@h.i>"}
		for _, w := range wantContains {
			found := false
			for _, r := range rcpts {
				if strings.Contains(strings.ToLower(r), w) {
					found = true
					break
				}
			}
			if !found {
				t.Fatalf("RCPT 中缺 %q, rcpts=%v", w, rcpts)
			}
		}
	case <-time.After(3 * time.Second):
		t.Fatal("未收到 RCPT 记录")
	}
}

func TestBuildMIME_EmptyBodies(t *testing.T) {
	raw := string(buildMIME("from@a.b", Message{To: "x@y.z", Subject: "s"}))
	if !strings.Contains(raw, "Subject: s\r\n") {
		t.Fatalf("ASCII 主题应原样输出, raw=%q", raw)
	}
	parts := strings.Split(raw, "--second-brain-boundary")
	if len(parts) < 4 {
		t.Fatalf("boundary 分段数不足, 实际 %d, raw=%q", len(parts), raw)
	}
	if !strings.HasSuffix(raw, "--second-brain-boundary--\r\n") {
		t.Fatalf("应以结束 boundary 收尾, raw=%q", raw)
	}
}

func TestFakeServerScannerRoundtrip(t *testing.T) {
	addr, _, stop := fakeSMTPServer(t, func(tp *textproto.Conn, _ chan<- string) error {
		if err := tp.PrintfLine("220 fake"); err != nil {
			return err
		}
		_, _ = tp.ReadLine() // QUIT
		_ = tp.PrintfLine("221 bye")
		return nil
	})
	defer stop()

	conn, err := net.Dial("tcp", addr)
	if err != nil {
		t.Fatalf("拨号失败: %v", err)
	}
	defer func() { _ = conn.Close() }()

	br := bufio.NewReader(conn)
	line, err := br.ReadString('\n')
	if err != nil {
		t.Fatalf("读取问候失败: %v", err)
	}
	if !strings.HasPrefix(line, "220") {
		t.Fatalf("问候应以 220 开头, 实际 %q", line)
	}
	if _, err := fmt.Fprintf(conn, "QUIT\r\n"); err != nil {
		t.Fatalf("写 QUIT 失败: %v", err)
	}
	reply, err := br.ReadString('\n')
	if err != nil {
		t.Fatalf("读取 QUIT 回复失败: %v", err)
	}
	if !strings.HasPrefix(reply, "221") {
		t.Fatalf("QUIT 回复应以 221 开头, 实际 %q", reply)
	}
}
