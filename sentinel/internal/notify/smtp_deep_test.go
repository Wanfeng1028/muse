package notify

import (
	"bufio"
	"encoding/base64"
	"fmt"
	"mime"
	"net"
	"strings"
	"sync"
	"testing"
	"time"
)

// smtpStub 是一个最小的 SMTP 服务端桩，用于真实跑通 dialSMTP/sendOnce 的协议交互。
type smtpStub struct {
	ln        net.Listener
	addr      string
	mu        sync.Mutex
	conns     int
	authCalls int
	mailFrom  []string
	rcptTo    []string
	dataBlobs []string
	quit      int
}

func newSMTPStub(t *testing.T) *smtpStub {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	s := &smtpStub{ln: ln, addr: ln.Addr().String()}
	go s.serve()
	t.Cleanup(func() { _ = ln.Close() })
	return s
}

func (s *smtpStub) hostPort(t *testing.T) (string, int) {
	t.Helper()
	host, portStr, err := net.SplitHostPort(s.addr)
	if err != nil {
		t.Fatalf("拆分地址失败: %v", err)
	}
	var port int
	if _, err := fmt.Sscanf(portStr, "%d", &port); err != nil {
		t.Fatalf("解析端口失败: %v", err)
	}
	return host, port
}

func (s *smtpStub) serve() {
	for {
		conn, err := s.ln.Accept()
		if err != nil {
			return
		}
		s.mu.Lock()
		s.conns++
		s.mu.Unlock()
		go s.handle(conn)
	}
}

func (s *smtpStub) handle(conn net.Conn) {
	defer conn.Close()
	r := bufio.NewReader(conn)
	w := bufio.NewWriter(conn)
	write := func(line string) {
		_, _ = w.WriteString(line + "\r\n")
		_ = w.Flush()
	}
	write("220 stub ESMTP ready")
	var inData bool
	var dataBuf strings.Builder
	for {
		line, err := r.ReadString('\n')
		if err != nil {
			return
		}
		line = strings.TrimRight(line, "\r\n")
		if inData {
			if line == "." {
				inData = false
				s.mu.Lock()
				s.dataBlobs = append(s.dataBlobs, dataBuf.String())
				s.mu.Unlock()
				dataBuf.Reset()
				write("250 OK queued")
				continue
			}
			dataBuf.WriteString(line)
			dataBuf.WriteString("\r\n")
			continue
		}
		upper := strings.ToUpper(line)
		switch {
		case strings.HasPrefix(upper, "EHLO"), strings.HasPrefix(upper, "HELO"):
			write("250 stub")
		case strings.HasPrefix(upper, "AUTH"):
			s.mu.Lock()
			s.authCalls++
			s.mu.Unlock()
			write("235 authenticated")
		case strings.HasPrefix(upper, "MAIL FROM"):
			s.mu.Lock()
			s.mailFrom = append(s.mailFrom, line)
			s.mu.Unlock()
			write("250 OK")
		case strings.HasPrefix(upper, "RCPT TO"):
			s.mu.Lock()
			s.rcptTo = append(s.rcptTo, line)
			s.mu.Unlock()
			write("250 OK")
		case strings.HasPrefix(upper, "DATA"):
			inData = true
			write("354 send data")
		case strings.HasPrefix(upper, "QUIT"):
			s.mu.Lock()
			s.quit++
			s.mu.Unlock()
			write("221 bye")
			return
		default:
			write("250 OK")
		}
	}
}

func (s *smtpStub) snapshot() (conns, authCalls, quits int, rcpt []string, blobs []string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rcpt = append(rcpt, s.rcptTo...)
	blobs = append(blobs, s.dataBlobs...)
	return s.conns, s.authCalls, s.quit, rcpt, blobs
}

// 空目标 / 非法 URL / 超长字符串这类边界，直接作用于纯函数与消息组装，断言真实输出。
func TestSplitRecipients_Boundaries(t *testing.T) {
	cases := []struct {
		name string
		to   string
		want []string
	}{
		{"空字符串", "", nil},
		{"只有逗号", ",,,", nil},
		{"只有空白", "   ", nil},
		{"单个地址", "a@example.com", []string{"a@example.com"}},
		{"多地址带空格", " a@example.com , b@example.com ", []string{"a@example.com", "b@example.com"}},
		{"夹杂空项", "a@example.com,,b@example.com,", []string{"a@example.com", "b@example.com"}},
		{"非法地址原样保留", "not-an-email", []string{"not-an-email"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := splitRecipients(tc.to)
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

func TestBuildSubject_Events(t *testing.T) {
	cases := []struct {
		event string
		name  string
		want  string
	}{
		{"down", "svc-a", "[sentinel] 告警：svc-a 宕机"},
		{"recovered", "svc-a", "[sentinel] 恢复：svc-a 已恢复"},
		{"degraded", "svc-a", "[sentinel] degraded：svc-a"},
		{"", "svc-a", "[sentinel] ：svc-a"},
	}
	for _, tc := range cases {
		t.Run(tc.event, func(t *testing.T) {
			got := buildSubject(tc.event, tc.name)
			if got != tc.want {
				t.Fatalf("主题不符: got=%q want=%q", got, tc.want)
			}
			if !strings.Contains(got, tc.name) {
				t.Fatalf("主题应包含名称 %q: got=%q", tc.name, got)
			}
		})
	}
}

func TestBuildBody_DownWithAndWithoutErr(t *testing.T) {
	withErr := buildBody("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "连接超时")
	if !strings.Contains(withErr, "事件: 宕机") {
		t.Fatalf("应包含宕机事件行: %q", withErr)
	}
	if !strings.Contains(withErr, "错误信息: 连接超时") {
		t.Fatalf("应包含错误信息行: %q", withErr)
	}
	if !strings.Contains(withErr, "目标: http://t/1") {
		t.Fatalf("应包含目标行: %q", withErr)
	}

	noErr := buildBody("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "")
	if strings.Contains(noErr, "错误信息:") {
		t.Fatalf("空 errMsg 时不应输出错误信息行: %q", noErr)
	}

	rec := buildBody("recovered", "svc-a", "http://t/1", "2024-01-02 03:04:05", "不该出现")
	if !strings.Contains(rec, "事件: 恢复") {
		t.Fatalf("应包含恢复事件行: %q", rec)
	}
	if strings.Contains(rec, "错误信息:") {
		t.Fatalf("recovered 不应输出错误信息行: %q", rec)
	}

	other := buildBody("degraded", "svc-a", "http://t/1", "2024-01-02 03:04:05", "延迟高")
	if !strings.Contains(other, "事件: degraded") {
		t.Fatalf("未知事件应原样输出: %q", other)
	}
	if !strings.Contains(other, "错误信息: 延迟高") {
		t.Fatalf("未知事件带 errMsg 应输出错误信息: %q", other)
	}
}

func TestBuildMessage_HeadersAndBase64Body(t *testing.T) {
	cfg := SMTPConfig{From: "from@example.com"}
	recipients := []string{"a@example.com", "b@example.com"}
	msg := buildMessage(cfg, recipients, "down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "连接超时")
	text := string(msg)

	if !strings.Contains(text, "From: from@example.com\r\n") {
		t.Fatalf("缺少 From 头: %q", text)
	}
	if !strings.Contains(text, "To: a@example.com, b@example.com\r\n") {
		t.Fatalf("缺少 To 头: %q", text)
	}
	if !strings.Contains(text, "MIME-Version: 1.0\r\n") {
		t.Fatalf("缺少 MIME-Version 头: %q", text)
	}
	if !strings.Contains(text, "Content-Transfer-Encoding: base64\r\n") {
		t.Fatalf("缺少传输编码头: %q", text)
	}

	idx := strings.Index(text, "\r\n\r\n")
	if idx < 0 {
		t.Fatalf("缺少头部与正文分隔: %q", text)
	}
	bodyEncoded := text[idx+4:]
	decoded, err := base64.StdEncoding.DecodeString(bodyEncoded)
	if err != nil {
		t.Fatalf("正文不是合法 base64: %v", err)
	}
	if !strings.Contains(string(decoded), "监控名称: svc-a") {
		t.Fatalf("解码正文缺少监控名称: %q", string(decoded))
	}

	subjLine := ""
	for _, line := range strings.Split(text, "\r\n") {
		if strings.HasPrefix(line, "Subject: ") {
			subjLine = strings.TrimPrefix(line, "Subject: ")
			break
		}
	}
	if subjLine == "" {
		t.Fatalf("缺少 Subject 头: %q", text)
	}
	dec := new(mime.WordDecoder)
	plainSubject, err := dec.DecodeHeader(subjLine)
	if err != nil {
		t.Fatalf("主题解码失败: %v", err)
	}
	if plainSubject != "[sentinel] 告警：svc-a 宕机" {
		t.Fatalf("主题解码不符: %q", plainSubject)
	}
}

func TestBuildRawMessage_LongContent(t *testing.T) {
	long := strings.Repeat("x", 20000)
	recipients := []string{"a@example.com"}
	msg := buildRawMessage("from@example.com", recipients, "超长主题", long)
	text := string(msg)

	if !strings.Contains(text, "To: a@example.com\r\n") {
		t.Fatalf("缺少 To 头: %q", text[:200])
	}
	idx := strings.Index(text, "\r\n\r\n")
	if idx < 0 {
		t.Fatalf("缺少头部与正文分隔")
	}
	decoded, err := base64.StdEncoding.DecodeString(text[idx+4:])
	if err != nil {
		t.Fatalf("正文不是合法 base64: %v", err)
	}
	if len(decoded) != len(long) {
		t.Fatalf("解码正文长度不符: got=%d want=%d", len(decoded), len(long))
	}
	if string(decoded) != long {
		t.Fatalf("解码正文内容与原文不一致")
	}
}

// SendAlert 在 Host 为空时必须直接返回 nil，不发起任何网络连接。
func TestSendAlert_EmptyHostSkips(t *testing.T) {
	n := SMTPNotifier{Config: SMTPConfig{Host: "", To: "a@example.com"}}
	if err := n.SendAlert("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", ""); err != nil {
		t.Fatalf("Host 为空应返回 nil, got=%v", err)
	}
	n2 := SMTPNotifier{Config: SMTPConfig{Host: "", To: ""}}
	if err := n2.SendRaw([]string{"a@example.com"}, "s", "b"); err != nil {
		t.Fatalf("SendRaw Host 为空应返回 nil, got=%v", err)
	}
}

// To 为空时 SendAlert 应直接报“收件人为空”，且不进行重试退避（时间很短）。
func TestSendAlert_EmptyRecipients(t *testing.T) {
	n := SMTPNotifier{Config: SMTPConfig{Host: "127.0.0.1", Port: 2525, To: " , , "}}
	start := time.Now()
	err := n.SendAlert("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "")
	elapsed := time.Since(start)
	if err == nil {
		t.Fatalf("收件人为空应返回错误")
	}
	if !strings.Contains(err.Error(), "SMTP 收件人为空") {
		t.Fatalf("错误信息不符: %v", err)
	}
	if elapsed > 2*time.Second {
		t.Fatalf("收件人为空不应进入重试退避, 耗时=%v", elapsed)
	}

	nr := SMTPNotifier{Config: SMTPConfig{Host: "127.0.0.1", Port: 2525}}
	errRaw := nr.SendRaw(nil, "s", "b")
	if errRaw == nil || !strings.Contains(errRaw.Error(), "SMTP 收件人为空") {
		t.Fatalf("SendRaw 收件人为空应报错: %v", errRaw)
	}
}

// 网络错误注入：指向一个已关闭的端口，SendAlert 应重试 3 次后返回错误。
func TestSendAlert_NetworkErrorRetries(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	host, portStr, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		t.Fatalf("拆分地址失败: %v", err)
	}
	var port int
	if _, err := fmt.Sscanf(portStr, "%d", &port); err != nil {
		t.Fatalf("解析端口失败: %v", err)
	}
	_ = ln.Close()

	n := SMTPNotifier{Config: SMTPConfig{Host: host, Port: port, From: "from@example.com", To: "a@example.com"}}
	start := time.Now()
	err = n.SendAlert("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "连接超时")
	elapsed := time.Since(start)
	if err == nil {
		t.Fatalf("连接被拒应返回错误")
	}
	if !strings.Contains(err.Error(), "SMTP 邮件发送失败") {
		t.Fatalf("错误信息不符: %v", err)
	}
	if !strings.Contains(err.Error(), "建立 SMTP 连接失败") {
		t.Fatalf("底层错误应被包装: %v", err)
	}
	// 重试退避为 1s + 2s，总计应不少于 3 秒。
	if elapsed < 3*time.Second {
		t.Fatalf("未观察到重试退避, 耗时=%v", elapsed)
	}
}

// 探针超时注入：服务端接受连接但从不回 220 欢迎语，dialSMTP 阶段应被拨号超时打断。
func TestDialSMTP_Timeout(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("监听失败: %v", err)
	}
	defer ln.Close()
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			// 保持连接，不回任何内容，触发 smtp 客户端读取超时路径。
			_ = conn
		}
	}()
	host, portStr, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		t.Fatalf("拆分地址失败: %v", err)
	}
	var port int
	if _, err := fmt.Sscanf(portStr, "%d", &port); err != nil {
		t.Fatalf("解析端口失败: %v", err)
	}
	cfg := SMTPConfig{Host: host}
	c, err := dialSMTP(cfg, port)
	if err == nil {
		_ = c.Close()
		t.Fatalf("服务端不回欢迎语时应返回错误")
	}
	if !strings.Contains(err.Error(), "创建 SMTP 客户端失败") && !strings.Contains(err.Error(), "SMTP Hello 失败") {
		t.Fatalf("错误信息不符: %v", err)
	}
}

// DB 失败注入：数据源不可用表现为收件人列表为空/消息无法组装，返回明确错误且不重试。
func TestSendAlert_DataUnavailable(t *testing.T) {
	n := SMTPNotifier{Config: SMTPConfig{Host: "127.0.0.1", Port: 2525, From: "from@example.com", To: ""}}
	start := time.Now()
	err := n.SendAlert("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "")
	elapsed := time.Since(start)
	if err == nil {
		t.Fatalf("数据不可用（收件人为空）应返回错误")
	}
	if !strings.Contains(err.Error(), "SMTP 收件人为空") {
		t.Fatalf("错误信息不符: %v", err)
	}
	if elapsed > 2*time.Second {
		t.Fatalf("数据不可用不应触发重试退避, 耗时=%v", elapsed)
	}
}

// 正常路径：真实跑通 SMTP 交互，验证 From/To/DATA 与 QUIT 行为。
func TestSendAlert_SuccessAgainstStub(t *testing.T) {
	stub := newSMTPStub(t)
	host, port := stub.hostPort(t)
	n := SMTPNotifier{Config: SMTPConfig{
		Host: host,
		Port: port,
		From: "from@example.com",
		To:   "a@example.com, b@example.com",
	}}
	err := n.SendAlert("down", "svc-a", "http://t/1", "2024-01-02 03:04:05", "连接超时")
	if err != nil {
		t.Fatalf("发送应成功: %v", err)
	}
	conns, _, quits, rcpt, blobs := stub.snapshot()
	if conns < 1 {
		t.Fatalf("应至少建立一次连接, got=%d", conns)
	}
	if quits < 1 {
		t.Fatalf("应至少发送一次 QUIT, got=%d", quits)
	}
	if len(rcpt) != 2 {
		t.Fatalf("应投递 2 个收件人, got=%v", rcpt)
	}
	if !strings.Contains(rcpt[0], "a@example.com") || !strings.Contains(rcpt[1], "b@example.com") {
		t.Fatalf("收件人不符: %v", rcpt)
	}
	if len(blobs) != 1 {
		t.Fatalf("应收到 1 份 DATA, got=%d", len(blobs))
	}
	if !strings.Contains(blobs[0], "From: from@example.com") {
		t.Fatalf("DATA 缺少 From 头: %q", blobs[0])
	}
}

// 幂等：同样的 SendAlert 调用两次，每次都应完整走一遍协议并成功。
func TestSendAlert_Idempotent(t *testing.T) {
	stub := newSMTPStub(t)
	host, port := stub.hostPort(t)
	n := SMTPNotifier{Config: SMTPConfig{
		Host: host,
		Port: port,
		From: "from@example.com",
		To:   "a@example.com",
	}}
	for i := 0; i < 2; i++ {
		if err := n.SendAlert("recovered", "svc-a", "http://t/1", "2024-01-02 03:04:05", ""); err != nil {
			t.Fatalf("第 %d 次发送失败: %v", i+1, err)
		}
	}
	conns, _, _, rcpt, blobs := stub.snapshot()
	if conns < 2 {
		t.Fatalf("两次调用应建立至少两次连接, got=%d", conns)
	}
	if len(rcpt) != 2 {
		t.Fatalf("两次调用应投递 2 次收件人, got=%v", rcpt)
	}
	if len(blobs) != 2 {
		t.Fatalf("两次调用应收到 2 份 DATA, got=%d", len(blobs))
	}
	for i, blob := range blobs {
		if !strings.Contains(blob, "From: from@example.com") {
			t.Fatalf("第 %d 份 DATA 缺少 From 头", i+1)
		}
	}
}

// 并发：多 goroutine 同时调用 SendAlert，不 panic，且每份邮件都被投递。
func TestSendAlert_Concurrent(t *testing.T) {
	stub := newSMTPStub(t)
	host, port := stub.hostPort(t)
	n := SMTPNotifier{Config: SMTPConfig{
		Host: host,
		Port: port,
		From: "from@example.com",
		To:   "a@example.com",
	}}

	const workers = 8
	var wg sync.WaitGroup
	errCh := make(chan error, workers)
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			if err := n.SendAlert("down", fmt.Sprintf("svc-%d", idx), "http://t/1", "2024-01-02 03:04:05", "连接超时"); err != nil {
				errCh <- fmt.Errorf("worker %d: %w", idx, err)
			}
		}(i)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatalf("并发发送失败: %v", err)
	}

	conns, _, _, _, blobs := stub.snapshot()
	if conns < workers {
		t.Fatalf("应建立至少 %d 次连接, got=%d", workers, conns)
	}
	if len(blobs) < workers {
		t.Fatalf("应收到至少 %d 份 DATA, got=%d", workers, len(blobs))
	}
}