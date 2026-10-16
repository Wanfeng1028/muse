package notify

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func TestParseChannels(t *testing.T) {
	got := ParseChannels("smtp, wecom,SMTP,unknown,, ")
	want := []string{"smtp", "wecom"}
	if len(got) != len(want) {
		t.Fatalf("ParseChannels 结果长度期望 %d，实际 %d（%v）", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("ParseChannels 第 %d 项期望 %q，实际 %q（完整=%v）", i, want[i], got[i], got)
		}
	}

	empty := ParseChannels("")
	if len(empty) != 0 {
		t.Fatalf("空输入期望返回空切片，实际=%v", empty)
	}

	upper := ParseChannels("WEBHOOK")
	if len(upper) != 1 || upper[0] != "webhook" {
		t.Fatalf("ParseChannels(\"WEBHOOK\") 期望 [\"webhook\"]，实际=%v", upper)
	}
}

func TestNotify_TargetOverridesGlobal(t *testing.T) {
	fake := startFakeSMTP(t)

	var wecomHits int32
	wecomSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&wecomHits, 1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errcode":0,"errmsg":"ok"}`))
	}))
	defer wecomSrv.Close()

	n := Notifier{
		SMTP: SMTPConfig{
			Host: "127.0.0.1",
			Port: fake.port,
			From: "sentinel@example.com",
			To:   "a@example.com",
		},
		WeCom:    WeComConfig{WebhookURL: wecomSrv.URL},
		Channels: []string{"smtp", "wecom"},
	}

	errs := n.Notify(Target{NotifyChannels: "smtp"}, "down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("期望无错误，实际返回: %v", errs)
	}

	if len(fake.captured) == 0 {
		t.Error("期望 fake SMTP 收到 1 封邮件，实际未收到")
	}
	if got := atomic.LoadInt32(&wecomHits); got != 0 {
		t.Errorf("Target 指定 smtp 时企业微信不应收到请求，实际收到 %d 次", got)
	}
}

func TestNotify_BothChannels(t *testing.T) {
	fake := startFakeSMTP(t)

	var wecomHits int32
	wecomSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&wecomHits, 1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errcode":0,"errmsg":"ok"}`))
	}))
	defer wecomSrv.Close()

	n := Notifier{
		SMTP: SMTPConfig{
			Host: "127.0.0.1",
			Port: fake.port,
			From: "sentinel@example.com",
			To:   "a@example.com",
		},
		WeCom:    WeComConfig{WebhookURL: wecomSrv.URL},
		Channels: []string{"smtp", "wecom"},
	}

	errs := n.Notify(Target{}, "down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("期望无错误，实际返回: %v", errs)
	}

	if len(fake.captured) == 0 {
		t.Error("期望 fake SMTP 收到 1 封邮件，实际未收到")
	}
	if got := atomic.LoadInt32(&wecomHits); got != 1 {
		t.Errorf("期望企业微信收到 1 次请求，实际收到 %d 次", got)
	}
}

func TestNotify_DefaultWebhook(t *testing.T) {
	var hits int32
	var body []byte

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		body, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := Notifier{WebhookURL: srv.URL}
	errs := n.Notify(Target{}, "down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("期望无错误，实际返回: %v", errs)
	}

	if got := atomic.LoadInt32(&hits); got != 1 {
		t.Fatalf("期望 webhook 收到 1 次 POST，实际 %d 次", got)
	}
	if !strings.Contains(string(body), "down") {
		t.Errorf("webhook 请求体应包含 \"down\"，实际=%s", string(body))
	}
}

func TestNotify_WebhookSkippedWhenNoURL(t *testing.T) {
	n := Notifier{}
	errs := n.Notify(Target{}, "down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if len(errs) != 0 {
		t.Fatalf("全空配置期望无错误，实际返回: %v", errs)
	}
}

func TestNotify_PartialFailure(t *testing.T) {
	var wecomHits int32
	wecomSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&wecomHits, 1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errcode":0,"errmsg":"ok"}`))
	}))
	defer wecomSrv.Close()

	n := Notifier{
		SMTP: SMTPConfig{
			Host: "127.0.0.1",
			Port: 59998,
			From: "sentinel@example.com",
			To:   "a@example.com",
		},
		WeCom:    WeComConfig{WebhookURL: wecomSrv.URL},
		Channels: []string{"smtp", "wecom"},
	}

	errs := n.Notify(Target{}, "down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if len(errs) != 1 {
		t.Fatalf("期望恰好 1 个渠道失败，实际返回 %d 个错误: %v", len(errs), errs)
	}
	if got := atomic.LoadInt32(&wecomHits); got != 1 {
		t.Errorf("smtp 失败不应影响企业微信，期望收到 1 次请求，实际 %d 次", got)
	}

	_ = json.Marshal
}
