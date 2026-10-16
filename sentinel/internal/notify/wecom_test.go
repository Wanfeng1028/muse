package notify

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWeComNotifier_SendMarkdown(t *testing.T) {
	var gotBody []byte

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		gotBody = body
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errcode":0,"errmsg":"ok"}`))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: true}}
	err := n.SendMarkdown("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if err != nil {
		t.Fatalf("SendMarkdown 期望返回 nil，实际返回: %v", err)
	}

	if len(gotBody) == 0 {
		t.Fatal("服务端未收到任何请求体")
	}

	var payload struct {
		MsgType  string `json:"msgtype"`
		Markdown struct {
			Content       string   `json:"content"`
			MentionedList []string `json:"mentioned_list"`
		} `json:"markdown"`
	}
	if err := json.Unmarshal(gotBody, &payload); err != nil {
		t.Fatalf("解析请求 JSON 失败: %v，请求体=%s", err, string(gotBody))
	}

	if payload.MsgType != "markdown" {
		t.Errorf("msgtype 期望 \"markdown\"，实际 %q", payload.MsgType)
	}

	for _, want := range []string{"测试站点", "http://example.com", "宕机", "boom"} {
		if !strings.Contains(payload.Markdown.Content, want) {
			t.Errorf("markdown.content 缺少内容 %q，实际=%q", want, payload.Markdown.Content)
		}
	}

	if !strings.HasPrefix(payload.Markdown.Content, "@all") {
		t.Errorf("MentionAll=true 时 content 应以 \"@all\" 开头，实际=%q", payload.Markdown.Content)
	}

	if len(payload.Markdown.MentionedList) != 1 || payload.Markdown.MentionedList[0] != "@all" {
		t.Errorf("mentioned_list 期望 [\"@all\"]，实际=%v", payload.Markdown.MentionedList)
	}
}

func TestWeComNotifier_NoMention(t *testing.T) {
	var gotBody []byte

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		gotBody = body
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errcode":0,"errmsg":"ok"}`))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: false}}
	if err := n.SendMarkdown("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom"); err != nil {
		t.Fatalf("SendMarkdown 期望返回 nil，实际返回: %v", err)
	}

	var raw map[string]any
	if err := json.Unmarshal(gotBody, &raw); err != nil {
		t.Fatalf("解析请求 JSON 失败: %v，请求体=%s", err, string(gotBody))
	}

	md, ok := raw["markdown"].(map[string]any)
	if !ok {
		t.Fatalf("请求体缺少 markdown 对象，实际=%s", string(gotBody))
	}
	if _, exists := md["mentioned_list"]; exists {
		t.Errorf("MentionAll=false 时不应包含 mentioned_list 键，实际=%s", string(gotBody))
	}
}

func TestWeComNotifier_ErrCode(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"errcode":40001,"errmsg":"bad"}`))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: false}}
	err := n.SendMarkdown("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if err == nil {
		t.Fatal("errcode 非 0 时应返回非 nil 错误")
	}
}

func TestWeComNotifier_Non2xx(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("internal error"))
	}))
	defer srv.Close()

	n := WeComNotifier{Config: WeComConfig{WebhookURL: srv.URL, MentionAll: false}}
	err := n.SendMarkdown("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom")
	if err == nil {
		t.Fatal("HTTP 500 时应返回非 nil 错误")
	}
}

func TestWeComNotifier_SkipWhenNoURL(t *testing.T) {
	n := WeComNotifier{Config: WeComConfig{WebhookURL: "", MentionAll: false}}
	if err := n.SendMarkdown("down", "测试站点", "http://example.com", "2026-10-16T12:00:00Z", "boom"); err != nil {
		t.Fatalf("WebhookURL 为空时应直接返回 nil，实际返回: %v", err)
	}
}
