// internal/api/push_test.go
package api

import (
	"bufio"
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newPushTestServer(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })

	mux := http.NewServeMux()
	RegisterPushRoutes(mux, st, config.Load())
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv, st
}

func TestPushSettingsRedaction(t *testing.T) {
	t.Setenv("SB_SMTP_HOST", "smtp.example.com")
	t.Setenv("SB_SMTP_PORT", "587")
	t.Setenv("SB_SMTP_USER", "user")
	t.Setenv("SB_SMTP_PASS", "s3cr3t-for-test")
	t.Setenv("SB_WEBHOOK_URL", "https://example.com/hook")
	t.Setenv("SB_WEBHOOK_SECRET", "s3cr3t-for-test")

	srv, _ := newPushTestServer(t)
	resp, err := http.Get(srv.URL + "/api/push/settings")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if bytes.Contains(body, []byte("s3cr3t-for-test")) {
		t.Fatalf("响应泄露密钥: %s", string(body))
	}
	if !bytes.Contains(body, []byte("smtp.example.com")) {
		t.Fatalf("响应缺少 smtpHost: %s", string(body))
	}
}

func TestPushSettingsPutInvalidTime(t *testing.T) {
	srv, _ := newPushTestServer(t)
	payload := `{"time":"25:99"}`
	req, _ := http.NewRequest(http.MethodPut, srv.URL+"/api/push/settings", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("put: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d", resp.StatusCode)
	}
}

func TestPushSettingsPutRejectsPassword(t *testing.T) {
	srv, _ := newPushTestServer(t)
	payload := `{"password":"s3cr3t-for-test"}`
	req, _ := http.NewRequest(http.MethodPut, srv.URL+"/api/push/settings", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("put: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if bytes.Contains(body, []byte("s3cr3t-for-test")) {
		t.Fatalf("响应泄露密钥: %s", string(body))
	}
}

func TestPushTestWebhookSignature(t *testing.T) {
	secret := "s3cr3t-for-test"
	var mu sync.Mutex
	var gotBody []byte
	var gotSig string
	var gotEvent string

	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		mu.Lock()
		gotBody = body
		gotSig = r.Header.Get("X-Signature")
		gotEvent = r.Header.Get("X-Event")
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer receiver.Close()

	t.Setenv("SB_WEBHOOK_URL", receiver.URL)
	t.Setenv("SB_WEBHOOK_SECRET", secret)

	srv, _ := newPushTestServer(t)
	payload := `{"channel":"webhook"}`
	resp, err := http.Post(srv.URL+"/api/push/test", "application/json", strings.NewReader(payload))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d body=%s", resp.StatusCode, string(body))
	}

	mu.Lock()
	defer mu.Unlock()
	if gotEvent != "review.digest" {
		t.Fatalf("event = %q", gotEvent)
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(gotBody)
	want := "sha256=" + hex.EncodeToString(mac.Sum(nil))
	if gotSig != want {
		t.Fatalf("signature mismatch: got %q want %q", gotSig, want)
	}
}

// fakeSMTP 是一个最小 SMTP 服务器，收到 DATA 内容后通过通道传出。
type fakeSMTP struct {
	ln       net.Listener
	dataCh   chan string
	quitOnce sync.Once
}

func startFakeSMTP(t *testing.T) *fakeSMTP {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	f := &fakeSMTP{ln: ln, dataCh: make(chan string, 1)}
	go f.serve()
	t.Cleanup(func() { _ = ln.Close() })
	return f
}

func (f *fakeSMTP) Addr() (string, int) {
	host, portStr, _ := net.SplitHostPort(f.ln.Addr().String())
	port := 0
	for _, c := range portStr {
		if c < '0' || c > '9' {
			break
		}
		port = port*10 + int(c-'0')
	}
	return host, port
}

func (f *fakeSMTP) serve() {
	for {
		conn, err := f.ln.Accept()
		if err != nil {
			return
		}
		go f.handle(conn)
	}
}

func (f *fakeSMTP) handle(conn net.Conn) {
	defer conn.Close()
	br := bufio.NewReader(conn)
	bw := bufio.NewWriter(conn)
	writeLine := func(s string) {
		_, _ = bw.WriteString(s + "\r\n")
		_ = bw.Flush()
	}
	writeLine("220 fake SMTP")

	inData := false
	var dataBuf strings.Builder
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			return
		}
		if inData {
			if strings.TrimRight(line, "\r\n") == "." {
				inData = false
				writeLine("250 OK")
				f.dataCh <- dataBuf.String()
				continue
			}
			dataBuf.WriteString(line)
			continue
		}
		upper := strings.ToUpper(strings.TrimSpace(line))
		switch {
		case strings.HasPrefix(upper, "EHLO"), strings.HasPrefix(upper, "HELO"):
			writeLine("250 OK")
		case strings.HasPrefix(upper, "AUTH"):
			writeLine("235 OK")
		case strings.HasPrefix(upper, "MAIL FROM"), strings.HasPrefix(upper, "RCPT TO"):
			writeLine("250 OK")
		case strings.HasPrefix(upper, "DATA"):
			writeLine("354 End data with <CR><LF>.<CR><LF>")
			inData = true
		case strings.HasPrefix(upper, "QUIT"):
			writeLine("221 Bye")
			return
		default:
			writeLine("250 OK")
		}
	}
}

func TestPushTestSMTP(t *testing.T) {
	f := startFakeSMTP(t)
	host, port := f.Addr()

	t.Setenv("SB_SMTP_HOST", host)
	t.Setenv("SB_SMTP_PORT", itoaPush(port))
	t.Setenv("SB_SMTP_TLS", "false")
	t.Setenv("SB_MAIL_TO", "dest@example.com")

	srv, _ := newPushTestServer(t)
	payload := `{"channel":"smtp"}`
	resp, err := http.Post(srv.URL+"/api/push/test", "application/json", strings.NewReader(payload))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d body=%s", resp.StatusCode, string(body))
	}

	select {
	case data := <-f.dataCh:
		if !strings.Contains(data, "Subject:") {
			t.Fatalf("DATA 缺少 Subject: %s", data)
		}
		if !strings.Contains(data, "复习") && !strings.Contains(data, "review") && !strings.Contains(data, "Review") {
			t.Fatalf("DATA 缺少正文标题: %s", data)
		}
	case <-time.After(5 * time.Second):
		t.Fatalf("超时未收到 SMTP DATA")
	}
}

func itoaPush(n int) string {
	if n == 0 {
		return "0"
	}
	var b [20]byte
	i := len(b)
	neg := n < 0
	if neg {
		n = -n
	}
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}
