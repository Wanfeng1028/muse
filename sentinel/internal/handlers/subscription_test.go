package handlers

import (
	"net/http"
	"regexp"
	"strings"
	"testing"

	"sentinel/internal/notify"
)

var tokenRe = regexp.MustCompile(`token=([0-9a-f]{64})`)

// extractToken 从邮件正文中提取订阅令牌。
func extractToken(t *testing.T, body string) string {
	t.Helper()
	m := tokenRe.FindStringSubmatch(body)
	if len(m) != 2 {
		t.Fatalf("未能从邮件正文中提取 token：%q", body)
	}
	return m[1]
}

func TestSubscribeConfirmUnsubscribeFlow(t *testing.T) {
	srv, _ := newTestServer(t)
	mm := &notify.MemoryMailer{}
	srv.SetMailer(mm)

	pageID, err := srv.store.CreateStatusPage(1, "news", "新闻页")
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	h := srv.Routes()

	// 1. 订阅
	rec, resp := doJSON(t, h, http.MethodPost, "/api/status/news/subscribe", `{"email":"Sub@Example.com"}`)
	if rec.Code != http.StatusCreated {
		t.Fatalf("订阅期望 201，实际 %d，body=%s", rec.Code, rec.Body.String())
	}
	if resp["status"] != "pending" {
		t.Fatalf("订阅状态期望 pending，实际 %v", resp["status"])
	}

	// 2. 确认邮件检查
	msgs := mm.Messages()
	if len(msgs) != 1 {
		t.Fatalf("期望 1 封邮件，实际 %d", len(msgs))
	}
	if len(msgs[0].Recipients) != 1 || msgs[0].Recipients[0] != "sub@example.com" {
		t.Fatalf("收件人期望 [sub@example.com]，实际 %v", msgs[0].Recipients)
	}
	if !strings.Contains(msgs[0].Subject, "新闻页") {
		t.Fatalf("确认邮件主题应含页面标题，实际 %q", msgs[0].Subject)
	}
	if !strings.Contains(msgs[0].Body, "/api/status/news/confirm?token=") {
		t.Fatalf("邮件正文缺少确认链接：%q", msgs[0].Body)
	}
	token := extractToken(t, msgs[0].Body)

	// 3. 点确认链接
	rec, _ = doJSON(t, h, http.MethodGet, "/api/status/news/confirm?token="+token, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("确认期望 200，实际 %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Fatalf("确认页 Content-Type 期望含 text/html，实际 %q", ct)
	}
	if !strings.Contains(rec.Body.String(), "订阅成功") {
		t.Fatalf("确认页缺少“订阅成功”：%q", rec.Body.String())
	}

	// 4. store 层已确认
	sub, err := srv.store.GetSubscriptionByPageEmail(pageID, "sub@example.com")
	if err != nil {
		t.Fatalf("查询订阅失败: %v", err)
	}
	if sub.Confirmed != 1 {
		t.Fatalf("订阅期望已确认，实际 Confirmed=%d", sub.Confirmed)
	}

	// 5. 再次订阅同邮箱 → already，不再发新邮件
	rec, resp = doJSON(t, h, http.MethodPost, "/api/status/news/subscribe", `{"email":"sub@example.com"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("重复订阅期望 200，实际 %d", rec.Code)
	}
	if resp["status"] != "already" {
		t.Fatalf("重复订阅状态期望 already，实际 %v", resp["status"])
	}
	if len(mm.Messages()) != 1 {
		t.Fatalf("重复订阅不应再发邮件，实际 %d 封", len(mm.Messages()))
	}

	// 6. 退订确认页
	rec, _ = doJSON(t, h, http.MethodGet, "/api/status/news/unsubscribe?token="+token, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("退订页期望 200，实际 %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "退订状态通知") {
		t.Fatalf("退订页缺少标题：%q", rec.Body.String())
	}

	// 7. 执行退订
	rec, resp = doJSON(t, h, http.MethodPost, "/api/status/news/unsubscribe", `{"token":"`+token+`"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("退订期望 200，实际 %d，body=%s", rec.Code, rec.Body.String())
	}
	if resp["status"] != "unsubscribed" {
		t.Fatalf("退订状态期望 unsubscribed，实际 %v", resp["status"])
	}

	// 8. 退订后确认链接失效
	rec, _ = doJSON(t, h, http.MethodGet, "/api/status/news/confirm?token="+token, "")
	if !strings.Contains(rec.Body.String(), "链接无效") {
		t.Fatalf("退订后确认页期望“链接无效”：%q", rec.Body.String())
	}
}

func TestSubscribe_BadInput(t *testing.T) {
	srv, _ := newTestServer(t)
	mm := &notify.MemoryMailer{}
	srv.SetMailer(mm)
	h := srv.Routes()

	if _, err := srv.store.CreateStatusPage(1, "news", "新闻页"); err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	rec, _ := doJSON(t, h, http.MethodPost, "/api/status/news/subscribe", `{"email":"bad"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法邮箱期望 400，实际 %d", rec.Code)
	}

	rec, _ = doJSON(t, h, http.MethodPost, "/api/status/nonexist/subscribe", `{"email":"a@b.com"}`)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("不存在的状态页期望 404，实际 %d", rec.Code)
	}

	rec, _ = doJSON(t, h, http.MethodPost, "/api/status/news/subscribe", `{"email":""}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("空邮箱期望 400，实际 %d", rec.Code)
	}
}

func TestSubscribe_NoMailer(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	if _, err := srv.store.CreateStatusPage(1, "news", "新闻页"); err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	rec, _ := doJSON(t, h, http.MethodPost, "/api/status/news/subscribe", `{"email":"a@b.com"}`)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("未配置邮件服务期望 500，实际 %d", rec.Code)
	}
}

func TestUnsubscribe_BadToken(t *testing.T) {
	srv, _ := newTestServer(t)
	mm := &notify.MemoryMailer{}
	srv.SetMailer(mm)
	h := srv.Routes()

	if _, err := srv.store.CreateStatusPage(1, "news", "新闻页"); err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}

	rec, _ := doJSON(t, h, http.MethodPost, "/api/status/news/unsubscribe", `{"token":"deadbeef"}`)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("无效 token 期望 404，实际 %d", rec.Code)
	}

	rec, _ = doJSON(t, h, http.MethodGet, "/api/status/news/unsubscribe?token=", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("空 token 退订页期望 200，实际 %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接无效") {
		t.Fatalf("空 token 退订页期望“链接无效”：%q", rec.Body.String())
	}
}
