package store

import (
	"database/sql"
	"errors"
	"testing"
)

// createTestPage 建一个状态页并返回其 ID。
func createTestPage(t *testing.T, s *Store, slug, title string) int64 {
	t.Helper()
	id, err := s.CreateStatusPage(1, slug, title)
	if err != nil {
		t.Fatalf("创建状态页失败: %v", err)
	}
	return id
}

// TestNewSubscriptionToken 校验 token 为 64 位 hex 且两次不同。
func TestNewSubscriptionToken(t *testing.T) {
	t1, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("生成 token 失败: %v", err)
	}
	t2, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("生成 token 失败: %v", err)
	}
	if len(t1) != 64 {
		t.Fatalf("token 长度应为 64，实际 %d", len(t1))
	}
	for _, c := range t1 {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			t.Fatalf("token 含非 hex 字符: %q", c)
		}
	}
	if t1 == t2 {
		t.Fatalf("两次生成的 token 不应相同")
	}
}

// TestCreateAndGetSubscription 创建后按 token 读回。
func TestCreateAndGetSubscription(t *testing.T) {
	s := newTestStore(t)
	pageID := createTestPage(t, s, "p1", "页面一")

	token, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("生成 token 失败: %v", err)
	}
	if _, err := s.CreateSubscription(pageID, "user@example.com", token); err != nil {
		t.Fatalf("创建订阅失败: %v", err)
	}

	sub, err := s.GetSubscriptionByToken(token)
	if err != nil {
		t.Fatalf("查询订阅失败: %v", err)
	}
	if sub.Email != "user@example.com" {
		t.Errorf("Email = %q", sub.Email)
	}
	if sub.Confirmed != 0 {
		t.Errorf("Confirmed = %d，应为 0", sub.Confirmed)
	}
	if sub.Token != token {
		t.Errorf("Token = %q，应为 %q", sub.Token, token)
	}
	if sub.PageID != pageID {
		t.Errorf("PageID = %d，应为 %d", sub.PageID, pageID)
	}
}

// TestCreateSubscriptionDuplicate 同页同邮箱重复订阅报 ErrDuplicateSubscription。
func TestCreateSubscriptionDuplicate(t *testing.T) {
	s := newTestStore(t)
	pageID := createTestPage(t, s, "p1", "页面一")

	if _, err := s.CreateSubscription(pageID, "user@example.com", "tk1"); err != nil {
		t.Fatalf("首次创建订阅失败: %v", err)
	}
	_, err := s.CreateSubscription(pageID, "user@example.com", "tk2")
	if !errors.Is(err, ErrDuplicateSubscription) {
		t.Fatalf("重复订阅应返回 ErrDuplicateSubscription，实际 %v", err)
	}
}

// TestConfirmSubscription 确认幂等：首次成功，再次返回 sql.ErrNoRows。
func TestConfirmSubscription(t *testing.T) {
	s := newTestStore(t)
	pageID := createTestPage(t, s, "p1", "页面一")

	if _, err := s.CreateSubscription(pageID, "user@example.com", "tk1"); err != nil {
		t.Fatalf("创建订阅失败: %v", err)
	}
	if err := s.ConfirmSubscription("tk1"); err != nil {
		t.Fatalf("确认订阅失败: %v", err)
	}

	sub, err := s.GetSubscriptionByToken("tk1")
	if err != nil {
		t.Fatalf("查询订阅失败: %v", err)
	}
	if sub.Confirmed != 1 {
		t.Errorf("Confirmed = %d，应为 1", sub.Confirmed)
	}
	if !sub.ConfirmedAt.Valid {
		t.Errorf("ConfirmedAt 应为有效时间")
	}

	if err := s.ConfirmSubscription("tk1"); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("重复确认应返回 sql.ErrNoRows，实际 %v", err)
	}
}

// TestConfirmSubscriptionMissing 不存在的 token 返回 sql.ErrNoRows。
func TestConfirmSubscriptionMissing(t *testing.T) {
	s := newTestStore(t)
	if err := s.ConfirmSubscription("不存在的token"); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("应返回 sql.ErrNoRows，实际 %v", err)
	}
}

// TestDeleteSubscriptionByToken 删除后查询报 sql.ErrNoRows，再删同样报错。
func TestDeleteSubscriptionByToken(t *testing.T) {
	s := newTestStore(t)
	pageID := createTestPage(t, s, "p1", "页面一")

	if _, err := s.CreateSubscription(pageID, "user@example.com", "tk1"); err != nil {
		t.Fatalf("创建订阅失败: %v", err)
	}
	if err := s.DeleteSubscriptionByToken("tk1"); err != nil {
		t.Fatalf("删除订阅失败: %v", err)
	}
	if _, err := s.GetSubscriptionByToken("tk1"); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("删除后查询应返回 sql.ErrNoRows，实际 %v", err)
	}
	if err := s.DeleteSubscriptionByToken("tk1"); !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("重复删除应返回 sql.ErrNoRows，实际 %v", err)
	}
}

// TestValidEmail 邮箱格式校验。
func TestValidEmail(t *testing.T) {
	if !ValidEmail("user@example.com") {
		t.Errorf("user@example.com 应为合法")
	}
	for _, bad := range []string{"bad", "a@b", "a b@c.com", "@c.com"} {
		if ValidEmail(bad) {
			t.Errorf("%q 应为非法", bad)
		}
	}
}

// TestNormalizeEmail 规整邮箱。
func TestNormalizeEmail(t *testing.T) {
	got := NormalizeEmail("  User@Example.COM ")
	if got != "user@example.com" {
		t.Fatalf("NormalizeEmail = %q", got)
	}
}

// TestListConfirmedSubscribers 只返回已确认订阅者，字段正确。
func TestListConfirmedSubscribers(t *testing.T) {
	s := newTestStore(t)
	pageID := createTestPage(t, s, "p1", "页面一")

	if _, err := s.CreateSubscription(pageID, "confirmed@example.com", "tk-conf"); err != nil {
		t.Fatalf("创建订阅失败: %v", err)
	}
	if err := s.ConfirmSubscription("tk-conf"); err != nil {
		t.Fatalf("确认订阅失败: %v", err)
	}
	if _, err := s.CreateSubscription(pageID, "pending@example.com", "tk-pend"); err != nil {
		t.Fatalf("创建订阅失败: %v", err)
	}

	subs, err := s.ListConfirmedSubscribers(pageID)
	if err != nil {
		t.Fatalf("查询订阅者失败: %v", err)
	}
	if len(subs) != 1 {
		t.Fatalf("应返回 1 个已确认订阅者，实际 %d", len(subs))
	}
	if subs[0].Email != "confirmed@example.com" {
		t.Errorf("Email = %q", subs[0].Email)
	}
	if subs[0].Token != "tk-conf" {
		t.Errorf("Token = %q", subs[0].Token)
	}
	if subs[0].PageTitle != "页面一" {
		t.Errorf("PageTitle = %q", subs[0].PageTitle)
	}
	if subs[0].PageSlug != "p1" {
		t.Errorf("PageSlug = %q", subs[0].PageSlug)
	}
}

// TestListPageIDsForMonitor 包含该 monitor 的页面列表。
func TestListPageIDsForMonitor(t *testing.T) {
	s := newTestStore(t)
	pageID := createTestPage(t, s, "p1", "页面一")

	monitorID, err := s.CreateMonitor(Monitor{
		Name: "站点A", Kind: "http", Target: "https://a.example",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 10, IntervalSec: 60,
		Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("创建 monitor 失败: %v", err)
	}
	if err := s.AddMonitorToPage(pageID, monitorID); err != nil {
		t.Fatalf("添加 monitor 到页面失败: %v", err)
	}

	ids, err := s.ListPageIDsForMonitor(monitorID)
	if err != nil {
		t.Fatalf("查询页面失败: %v", err)
	}
	if len(ids) != 1 || ids[0] != pageID {
		t.Fatalf("应返回 [%d]，实际 %v", pageID, ids)
	}

	other, err := s.CreateMonitor(Monitor{
		Name: "站点B", Kind: "http", Target: "https://b.example",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 10, IntervalSec: 60,
		Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("创建 monitor 失败: %v", err)
	}
	ids, err = s.ListPageIDsForMonitor(other)
	if err != nil {
		t.Fatalf("查询页面失败: %v", err)
	}
	if len(ids) != 0 {
		t.Fatalf("未关联页面应返回空，实际 %v", ids)
	}
}
