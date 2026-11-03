package store

import (
	"strings"
	"testing"
)

const (
	testP256DH = "dGVzdC1wMjU2ZGg"
	testAuth   = "dGVzdC1hdXRo"
)

func TestUpsertAndList(t *testing.T) {
	st := newTestStore(t)
	user := "alice"

	sub1, err := st.UpsertSubscription(user, "https://push.example.com/a", testP256DH, testAuth)
	if err != nil {
		t.Fatalf("写入订阅1失败: %v", err)
	}
	sub2, err := st.UpsertSubscription(user, "https://push.example.com/b", "dGVzdC1wMjU2ZGgtMg", "dGVzdC1hdXRoLTI")
	if err != nil {
		t.Fatalf("写入订阅2失败: %v", err)
	}
	if sub1.ID == sub2.ID {
		t.Fatalf("两条订阅 ID 不应相同, 均为 %d", sub1.ID)
	}

	list, err := st.ListSubscriptionsForUser(user)
	if err != nil {
		t.Fatalf("列出订阅失败: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("期望列出 2 条订阅, 实际 %d 条", len(list))
	}
	for _, s := range list {
		if s.User != user {
			t.Fatalf("订阅归属用户应为 %q, 实际 %q", user, s.User)
		}
		if s.CreatedAt == "" {
			t.Fatalf("订阅 %d 的 CreatedAt 不应为空", s.ID)
		}
		if s.P256DH == "" || s.Auth == "" {
			t.Fatalf("订阅 %d 的密钥字段不应为空", s.ID)
		}
	}
}

func TestUpsertUpdate(t *testing.T) {
	st := newTestStore(t)
	user := "bob"
	endpoint := "https://push.example.com/upd"

	first, err := st.UpsertSubscription(user, endpoint, testP256DH, testAuth)
	if err != nil {
		t.Fatalf("首次写入失败: %v", err)
	}
	second, err := st.UpsertSubscription(user, endpoint, "bmV3LXAyNTZkaA", "bmV3LWF1dGg")
	if err != nil {
		t.Fatalf("二次写入失败: %v", err)
	}
	if first.ID != second.ID {
		t.Fatalf("同一 endpoint 幂等更新应复用 ID, 首次 %d 二次 %d", first.ID, second.ID)
	}

	list, err := st.ListSubscriptionsForUser(user)
	if err != nil {
		t.Fatalf("列出订阅失败: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("幂等更新后应只有 1 条订阅, 实际 %d 条", len(list))
	}
	if list[0].P256DH != "bmV3LXAyNTZkaA" {
		t.Fatalf("p256dh 应被更新为 %q, 实际 %q", "bmV3LXAyNTZkaA", list[0].P256DH)
	}
	if list[0].Auth != "bmV3LWF1dGg" {
		t.Fatalf("auth 应被更新为 %q, 实际 %q", "bmV3LWF1dGg", list[0].Auth)
	}
}

func TestUpsertValidation(t *testing.T) {
	st := newTestStore(t)
	user := "carol"

	cases := []struct {
		name     string
		endpoint string
		p256dh   string
		auth     string
	}{
		{"http 开头", "http://push.example.com/x", testP256DH, testAuth},
		{"空 p256dh", "https://push.example.com/x", "", testAuth},
		{"空 auth", "https://push.example.com/x", testP256DH, ""},
		{"超长 endpoint", "https://push.example.com/" + strings.Repeat("a", 2049), testP256DH, testAuth},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, err := st.UpsertSubscription(user, c.endpoint, c.p256dh, c.auth); err == nil {
				t.Fatalf("非法输入 %q 应返回错误, 实际 nil", c.name)
			}
		})
	}
}

func TestDeleteIsolation(t *testing.T) {
	st := newTestStore(t)
	epA := "https://push.example.com/a"
	epB := "https://push.example.com/b"

	if _, err := st.UpsertSubscription("alice", epA, testP256DH, testAuth); err != nil {
		t.Fatalf("写入 alice 订阅失败: %v", err)
	}
	if _, err := st.UpsertSubscription("bob", epB, testP256DH, testAuth); err != nil {
		t.Fatalf("写入 bob 订阅失败: %v", err)
	}

	deleted, err := st.DeleteSubscriptionForUser("alice", epB)
	if err != nil {
		t.Fatalf("alice 删除 bob 的 endpoint 出错: %v", err)
	}
	if deleted {
		t.Fatalf("alice 删除 bob 的 endpoint 应返回 false, 实际 true")
	}
	bobCount, err := st.CountSubscriptionsForUser("bob")
	if err != nil {
		t.Fatalf("统计 bob 订阅失败: %v", err)
	}
	if bobCount != 1 {
		t.Fatalf("bob 的订阅应仍存在, 期望 1 条实际 %d 条", bobCount)
	}

	deleted, err = st.DeleteSubscriptionForUser("alice", epA)
	if err != nil {
		t.Fatalf("alice 删除自己的 endpoint 出错: %v", err)
	}
	if !deleted {
		t.Fatalf("alice 删除自己的 endpoint 应返回 true, 实际 false")
	}
	aliceCount, err := st.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计 alice 订阅失败: %v", err)
	}
	if aliceCount != 0 {
		t.Fatalf("alice 的订阅应被删除, 期望 0 条实际 %d 条", aliceCount)
	}
}

func TestCountAndUserNormalize(t *testing.T) {
	st := newTestStore(t)
	endpoint := "https://push.example.com/norm"

	if _, err := st.UpsertSubscription("  Alice ", endpoint, testP256DH, testAuth); err != nil {
		t.Fatalf("写入带空格大写用户失败: %v", err)
	}
	count, err := st.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计小写用户失败: %v", err)
	}
	if count != 1 {
		t.Fatalf("大小写/空格用户应归一为同一用户, 期望 1 条实际 %d 条", count)
	}

	list, err := st.ListSubscriptionsForUser("ALICE")
	if err != nil {
		t.Fatalf("列出大写用户失败: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("大写查询应命中同一用户, 期望 1 条实际 %d 条", len(list))
	}
	if list[0].User != "alice" {
		t.Fatalf("存储的用户名应归一为 %q, 实际 %q", "alice", list[0].User)
	}
}

func TestEndpointReassign(t *testing.T) {
	st := newTestStore(t)
	endpoint := "https://push.example.com/reassign"

	if _, err := st.UpsertSubscription("alice", endpoint, testP256DH, testAuth); err != nil {
		t.Fatalf("alice 写入失败: %v", err)
	}
	if _, err := st.UpsertSubscription("bob", endpoint, "Ym9iLXAyNTZkaA", "Ym9iLWF1dGg"); err != nil {
		t.Fatalf("bob 重新占用 endpoint 失败: %v", err)
	}

	aliceCount, err := st.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计 alice 失败: %v", err)
	}
	if aliceCount != 0 {
		t.Fatalf("endpoint 改属后 alice 应查不到, 期望 0 条实际 %d 条", aliceCount)
	}
	bobList, err := st.ListSubscriptionsForUser("bob")
	if err != nil {
		t.Fatalf("列出 bob 失败: %v", err)
	}
	if len(bobList) != 1 {
		t.Fatalf("bob 应查到 1 条订阅, 实际 %d 条", len(bobList))
	}
	if bobList[0].Endpoint != endpoint {
		t.Fatalf("bob 的 endpoint 应为 %q, 实际 %q", endpoint, bobList[0].Endpoint)
	}
	if bobList[0].P256DH != "Ym9iLXAyNTZkaA" {
		t.Fatalf("改属后 p256dh 应为 %q, 实际 %q", "Ym9iLXAyNTZkaA", bobList[0].P256DH)
	}
}
