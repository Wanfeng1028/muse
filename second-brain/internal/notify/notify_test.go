package notify

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestBuildDigestMessageSubject(t *testing.T) {
	date := time.Date(2025, 10, 16, 8, 30, 0, 0, time.UTC)
	items := []DigestItem{
		{Title: "A", OverdueDays: 1},
		{Title: "B", OverdueDays: 0},
		{Title: "C", OverdueDays: 3},
		{Title: "D", OverdueDays: 2},
		{Title: "E", OverdueDays: 5},
	}
	msg := BuildDigestMessage(date, items, DigestStats{}, "a@b.com")
	want := "第二大脑 · 10月16日复习提醒（5 篇待复习）"
	if msg.Subject != want {
		t.Fatalf("subject = %q, want %q", msg.Subject, want)
	}
	if msg.To != "a@b.com" {
		t.Fatalf("to = %q", msg.To)
	}
}

func TestBuildDigestMessageEmpty(t *testing.T) {
	date := time.Date(2025, 10, 16, 8, 30, 0, 0, time.UTC)
	msg := BuildDigestMessage(date, nil, DigestStats{}, "a@b.com")
	if !strings.Contains(msg.Subject, "今日无待复习") {
		t.Fatalf("subject = %q, want 今日无待复习", msg.Subject)
	}
	if !strings.Contains(msg.HTMLBody, "今天没有到期的笔记，好好休息") {
		t.Fatalf("html body missing empty message")
	}
}

func TestBuildDigestMessageHTMLEscaping(t *testing.T) {
	date := time.Date(2025, 10, 16, 8, 30, 0, 0, time.UTC)
	items := []DigestItem{
		{Title: `<script>alert(1)</script>`, Snippet: `<b>bold</b>`, Tags: []string{`<i>tag</i>`}, OverdueDays: 2},
	}
	msg := BuildDigestMessage(date, items, DigestStats{}, "a@b.com")
	if strings.Contains(msg.HTMLBody, "<script>") {
		t.Fatalf("html body contains unescaped <script>")
	}
	if !strings.Contains(msg.HTMLBody, "&lt;script&gt;") {
		t.Fatalf("html body missing escaped script")
	}
	if strings.Contains(msg.HTMLBody, "<b>bold</b>") {
		t.Fatalf("html body contains unescaped snippet")
	}
	if strings.Contains(msg.HTMLBody, "<i>tag</i>") {
		t.Fatalf("html body contains unescaped tag")
	}
}

func TestBuildDigestMessageTextOverdue(t *testing.T) {
	date := time.Date(2025, 10, 16, 8, 30, 0, 0, time.UTC)
	items := []DigestItem{
		{Title: "我的笔记", Snippet: "摘要内容", Tags: []string{"go"}, OverdueDays: 3},
	}
	msg := BuildDigestMessage(date, items, DigestStats{Streak: 4}, "a@b.com")
	if !strings.Contains(msg.TextBody, "逾期 3 天") {
		t.Fatalf("text body missing overdue days: %q", msg.TextBody)
	}
	if !strings.Contains(msg.TextBody, "我的笔记") {
		t.Fatalf("text body missing title")
	}
	if !strings.Contains(msg.TextBody, "打开第二大脑开始复习") {
		t.Fatalf("text body missing footer")
	}
	if !strings.Contains(msg.TextBody, "连续复习 4 天") {
		t.Fatalf("text body missing streak")
	}
}

func TestWebhookSendSuccess(t *testing.T) {
	const secret = "test-secret-value"
	var gotSig string
	var gotBody []byte

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotSig = r.Header.Get("X-Signature")
		body, _ := io.ReadAll(r.Body)
		gotBody = body
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	s := NewWebhookSender(srv.URL, secret, 2*time.Second)
	msg := Message{Subject: "subj", TextBody: "text", HTMLBody: "<p>hi</p>"}
	if err := s.Send(context.Background(), msg); err != nil {
		t.Fatalf("Send error: %v", err)
	}

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(gotBody)
	wantSig := "sha256=" + hex.EncodeToString(mac.Sum(nil))
	if gotSig != wantSig {
		t.Fatalf("signature = %q, want %q", gotSig, wantSig)
	}

	var payload map[string]any
	if err := json.Unmarshal(gotBody, &payload); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if payload["event"] != "review.digest" {
		t.Fatalf("event = %v", payload["event"])
	}
	if payload["subject"] != "subj" {
		t.Fatalf("subject = %v", payload["subject"])
	}
	if payload["text"] != "text" {
		t.Fatalf("text = %v", payload["text"])
	}
	if payload["html"] != "<p>hi</p>" {
		t.Fatalf("html = %v", payload["html"])
	}
	if _, ok := payload["items"]; !ok {
		t.Fatalf("missing items field")
	}
}

func TestWebhookSendNon2xx(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	}))
	defer srv.Close()

	s := NewWebhookSender(srv.URL, "", 2*time.Second)
	err := s.Send(context.Background(), Message{Subject: "s"})
	if err == nil {
		t.Fatalf("expected error")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Fatalf("error missing status: %v", err)
	}
	if !strings.Contains(err.Error(), "boom") {
		t.Fatalf("error missing body: %v", err)
	}
}

func TestWebhookSendTimeout(t *testing.T) {
	block := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-block
	}))
	defer func() {
		close(block)
		srv.Close()
	}()

	s := NewWebhookSender(srv.URL, "", 50*time.Millisecond)
	err := s.Send(context.Background(), Message{Subject: "s"})
	if err == nil {
		t.Fatalf("expected timeout error")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("error = %v, want ErrConn wrap", err)
	}
}

func TestSMTPSenderUnreachable(t *testing.T) {
	s := NewSMTPSender("127.0.0.1", 1, "user", "pass", "from@example.com", false)
	if s.Name() != "smtp" {
		t.Fatalf("name = %q", s.Name())
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	err := s.Send(ctx, Message{To: "to@example.com", Subject: "s", TextBody: "t"})
	if err == nil {
		t.Fatalf("expected error")
	}
	if !errors.Is(err, ErrConn) {
		t.Fatalf("error = %v, want ErrConn", err)
	}
}
