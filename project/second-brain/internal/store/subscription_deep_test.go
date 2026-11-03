package store

import (
	"database/sql"
	"strings"
	"testing"

	_ "modernc.org/sqlite"
)

func openDeepTestStore(t *testing.T) *Store {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("打开内存数据库失败: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	if _, err := db.Exec(`CREATE TABLE push_subscriptions (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		user_id TEXT NOT NULL,
		endpoint TEXT NOT NULL UNIQUE,
		p256dh TEXT NOT NULL,
		auth TEXT NOT NULL,
		created_at TEXT NOT NULL
	)`); err != nil {
		t.Fatalf("建表失败: %v", err)
	}
	return &Store{db: db}
}

func TestUpsertSubscriptionValidationBoundaries(t *testing.T) {
	s := openDeepTestStore(t)

	endpointOk := "https://push.example.com/ok"
	p256dh256 := strings.Repeat("p", 256)
	auth128 := strings.Repeat("a", 128)
	endpoint2048 := "https://push.example.com/" + strings.Repeat("x", 2048-len("https://push.example.com/"))

	cases := []struct {
		name     string
		user     string
		endpoint string
		p256dh   string
		auth     string
		wantErr  string
	}{
		{
			name:     "endpoint 非 https 被拒",
			user:     "alice",
			endpoint: "http://push.example.com/a",
			p256dh:   "p1",
			auth:     "a1",
			wantErr:  "endpoint 必须以 https:// 开头",
		},
		{
			name:     "endpoint 空被拒",
			user:     "alice",
			endpoint: "",
			p256dh:   "p1",
			auth:     "a1",
			wantErr:  "endpoint 必须以 https:// 开头",
		},
		{
			name:     "endpoint 大小写前缀 HTTPS 被拒",
			user:     "alice",
			endpoint: "HTTPS://push.example.com/a",
			p256dh:   "p1",
			auth:     "a1",
			wantErr:  "endpoint 必须以 https:// 开头",
		},
		{
			name:     "endpoint 2049 超长被拒",
			user:     "alice",
			endpoint: endpoint2048 + "z",
			p256dh:   "p1",
			auth:     "a1",
			wantErr:  "endpoint 长度不能超过 2048",
		},
		{
			name:     "endpoint 恰好 2048 通过",
			user:     "alice",
			endpoint: endpoint2048,
			p256dh:   "p1",
			auth:     "a1",
			wantErr:  "",
		},
		{
			name:     "p256dh 空被拒",
			user:     "alice",
			endpoint: endpointOk + "/p-empty",
			p256dh:   "",
			auth:     "a1",
			wantErr:  "p256dh 不能为空",
		},
		{
			name:     "p256dh 257 超长被拒",
			user:     "alice",
			endpoint: endpointOk + "/p-long",
			p256dh:   p256dh256 + "q",
			auth:     "a1",
			wantErr:  "p256dh 长度不能超过 256",
		},
		{
			name:     "p256dh 恰好 256 通过",
			user:     "alice",
			endpoint: endpointOk + "/p-256",
			p256dh:   p256dh256,
			auth:     "a1",
			wantErr:  "",
		},
		{
			name:     "auth 空被拒",
			user:     "alice",
			endpoint: endpointOk + "/a-empty",
			p256dh:   "p1",
			auth:     "",
			wantErr:  "auth 不能为空",
		},
		{
			name:     "auth 129 超长被拒",
			user:     "alice",
			endpoint: endpointOk + "/a-long",
			p256dh:   "p1",
			auth:     auth128 + "b",
			wantErr:  "auth 长度不能超过 128",
		},
		{
			name:     "auth 恰好 128 通过",
			user:     "alice",
			endpoint: endpointOk + "/a-128",
			p256dh:   "p1",
			auth:     auth128,
			wantErr:  "",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := s.UpsertSubscription(tc.user, tc.endpoint, tc.p256dh, tc.auth)
			if tc.wantErr == "" {
				if err != nil {
					t.Fatalf("期望成功，实际报错: %v", err)
				}
				if got.Endpoint != tc.endpoint {
					t.Fatalf("endpoint 不一致，期望 %q 实际 %q", tc.endpoint, got.Endpoint)
				}
				if got.User != NormalizeUser(tc.user) {
					t.Fatalf("user 不一致，期望 %q 实际 %q", NormalizeUser(tc.user), got.User)
				}
				if got.ID == 0 {
					t.Fatalf("成功写入后 ID 应大于 0")
				}
				if got.P256DH != tc.p256dh {
					t.Fatalf("p256dh 不一致，期望长度 %d 实际长度 %d", len(tc.p256dh), len(got.P256DH))
				}
				if got.Auth != tc.auth {
					t.Fatalf("auth 不一致，期望长度 %d 实际长度 %d", len(tc.auth), len(got.Auth))
				}
				if got.CreatedAt == "" {
					t.Fatalf("createdAt 不应为空")
				}
			} else {
				if err == nil {
					t.Fatalf("期望报错 %q，实际无错", tc.wantErr)
				}
				if err.Error() != tc.wantErr {
					t.Fatalf("错误文案不一致，期望 %q 实际 %q", tc.wantErr, err.Error())
				}
				if got.ID != 0 || got.Endpoint != "" {
					t.Fatalf("失败时不应返回记录，实际 %+v", got)
				}
			}
		})
	}
}

func TestUpsertSubscriptionNormalizeUser(t *testing.T) {
	s := openDeepTestStore(t)

	raw := "  Alice@Example.COM  "
	got, err := s.UpsertSubscription(raw, "https://push.example.com/norm", "p1", "a1")
	if err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	normalized := NormalizeUser(raw)
	if got.User != normalized {
		t.Fatalf("user 未归一化，期望 %q 实际 %q", normalized, got.User)
	}
	if got.User != strings.ToLower(strings.TrimSpace(raw)) {
		t.Fatalf("归一化结果异常，期望 %q 实际 %q", strings.ToLower(strings.TrimSpace(raw)), got.User)
	}

	n, err := s.CountSubscriptionsForUser(raw)
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("原始输入也应归一化后统计为 1，实际 %d", n)
	}

	n2, err := s.CountSubscriptionsForUser(normalized)
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if n2 != 1 {
		t.Fatalf("归一化输入应统计为 1，实际 %d", n2)
	}
}

func TestUpsertSubscriptionEndpointGlobalUniqueReassignsUser(t *testing.T) {
	s := openDeepTestStore(t)

	endpoint := "https://push.example.com/shared"
	first, err := s.UpsertSubscription("alice", endpoint, "p-alice", "a-alice")
	if err != nil {
		t.Fatalf("首次写入失败: %v", err)
	}
	if first.User != NormalizeUser("alice") {
		t.Fatalf("首次归属应为 alice，实际 %q", first.User)
	}

	second, err := s.UpsertSubscription("bob", endpoint, "p-bob", "a-bob")
	if err != nil {
		t.Fatalf("二次写入失败: %v", err)
	}
	if second.User != NormalizeUser("bob") {
		t.Fatalf("endpoint 冲突后应归属 bob，实际 %q", second.User)
	}
	if second.P256DH != "p-bob" || second.Auth != "a-bob" {
		t.Fatalf("密钥应被覆盖，实际 p256dh=%q auth=%q", second.P256DH, second.Auth)
	}

	aliceCount, err := s.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计 alice 失败: %v", err)
	}
	if aliceCount != 0 {
		t.Fatalf("alice 不应再持有该订阅，实际 %d", aliceCount)
	}

	bobList, err := s.ListSubscriptionsForUser("bob")
	if err != nil {
		t.Fatalf("列出 bob 失败: %v", err)
	}
	if len(bobList) != 1 {
		t.Fatalf("bob 应持有 1 条订阅，实际 %d", len(bobList))
	}
	if bobList[0].Endpoint != endpoint {
		t.Fatalf("endpoint 不一致，期望 %q 实际 %q", endpoint, bobList[0].Endpoint)
	}
}

func TestDeleteSubscriptionForUserIsolation(t *testing.T) {
	s := openDeepTestStore(t)

	endpoint := "https://push.example.com/iso"
	if _, err := s.UpsertSubscription("alice", endpoint, "p1", "a1"); err != nil {
		t.Fatalf("写入 alice 失败: %v", err)
	}

	deleted, err := s.DeleteSubscriptionForUser("bob", endpoint)
	if err != nil {
		t.Fatalf("删除失败: %v", err)
	}
	if deleted {
		t.Fatalf("bob 未持有该订阅，不应删到记录")
	}

	aliceCount, err := s.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计 alice 失败: %v", err)
	}
	if aliceCount != 1 {
		t.Fatalf("alice 的订阅不应被误删，实际 %d", aliceCount)
	}

	deleted, err = s.DeleteSubscriptionForUser("alice", endpoint)
	if err != nil {
		t.Fatalf("删除失败: %v", err)
	}
	if !deleted {
		t.Fatalf("alice 持有该订阅，应删到记录")
	}

	aliceCount, err = s.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计 alice 失败: %v", err)
	}
	if aliceCount != 0 {
		t.Fatalf("删除后 alice 订阅数应为 0，实际 %d", aliceCount)
	}
}

func TestListSubscriptionsForUserOrderAndIsolation(t *testing.T) {
	s := openDeepTestStore(t)

	type seed struct {
		user     string
		endpoint string
		p256dh   string
		auth     string
		created  string
	}
	seeds := []seed{
		{"alice", "https://push.example.com/a1", "p1", "a1", "2024-02-29T00:00:00Z"},
		{"alice", "https://push.example.com/a2", "p2", "a2", "2024-03-01T00:00:00Z"},
		{"alice", "https://push.example.com/a3", "p3", "a3", "2024-03-01T00:00:00Z"},
		{"bob", "https://push.example.com/b1", "p4", "a4", "2024-03-02T00:00:00Z"},
	}
	for _, sd := range seeds {
		if _, err := s.db.Exec(
			`INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?)`,
			NormalizeUser(sd.user), sd.endpoint, sd.p256dh, sd.auth, sd.created,
		); err != nil {
			t.Fatalf("预置数据失败: %v", err)
		}
	}

	list, err := s.ListSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("列出 alice 失败: %v", err)
	}
	if len(list) != 3 {
		t.Fatalf("alice 应有 3 条订阅，实际 %d", len(list))
	}
	for _, sub := range list {
		if sub.User != NormalizeUser("alice") {
			t.Fatalf("列表出现非 alice 记录: %+v", sub)
		}
	}
	if list[0].Endpoint != "https://push.example.com/a3" {
		t.Fatalf("created_at 相同时应按 id 倒序，期望 a3 实际 %q", list[0].Endpoint)
	}
	if list[1].Endpoint != "https://push.example.com/a2" {
		t.Fatalf("期望第二条为 a2，实际 %q", list[1].Endpoint)
	}
	if list[2].Endpoint != "https://push.example.com/a1" {
		t.Fatalf("最旧记录应排最后，期望 a1 实际 %q", list[2].Endpoint)
	}

	bobList, err := s.ListSubscriptionsForUser("bob")
	if err != nil {
		t.Fatalf("列出 bob 失败: %v", err)
	}
	if len(bobList) != 1 {
		t.Fatalf("bob 应有 1 条订阅，实际 %d", len(bobList))
	}
	if bobList[0].Endpoint != "https://push.example.com/b1" {
		t.Fatalf("bob 记录不一致，实际 %q", bobList[0].Endpoint)
	}
}

func TestCountSubscriptionsForUserNormalizedAndIsolated(t *testing.T) {
	s := openDeepTestStore(t)

	for _, ep := range []string{
		"https://push.example.com/c1",
		"https://push.example.com/c2",
	} {
		if _, err := s.UpsertSubscription("Alice@Example.com", ep, "p1", "a1"); err != nil {
			t.Fatalf("写入失败: %v", err)
		}
	}
	if _, err := s.UpsertSubscription("bob@example.com", "https://push.example.com/c3", "p2", "a2"); err != nil {
		t.Fatalf("写入失败: %v", err)
	}

	n, err := s.CountSubscriptionsForUser("  ALICE@example.COM  ")
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if n != 2 {
		t.Fatalf("alice 应统计到 2 条，实际 %d", n)
	}

	nBob, err := s.CountSubscriptionsForUser("bob@example.com")
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if nBob != 1 {
		t.Fatalf("bob 应统计到 1 条，实际 %d", nBob)
	}

	nEmpty, err := s.CountSubscriptionsForUser("carol@example.com")
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if nEmpty != 0 {
		t.Fatalf("未知用户应统计到 0 条，实际 %d", nEmpty)
	}
}

func TestGetSubscriptionByEndpointNotFound(t *testing.T) {
	s := openDeepTestStore(t)

	got, err := s.getSubscriptionByEndpoint("https://push.example.com/missing")
	if err == nil {
		t.Fatalf("期望报错，实际无错")
	}
	if err.Error() != "订阅不存在" {
		t.Fatalf("错误文案不一致，期望 %q 实际 %q", "订阅不存在", err.Error())
	}
	if got.ID != 0 {
		t.Fatalf("未找到时 ID 应为 0，实际 %d", got.ID)
	}
	if got.Endpoint != "" {
		t.Fatalf("未找到时 endpoint 应为空，实际 %q", got.Endpoint)
	}
}

func TestUpsertSubscriptionCreatedAtRefreshedOnConflict(t *testing.T) {
	s := openDeepTestStore(t)

	endpoint := "https://push.example.com/refresh"
	if _, err := s.db.Exec(
		`INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?)`,
		NormalizeUser("alice"), endpoint, "p-old", "a-old", "2000-01-01T00:00:00Z",
	); err != nil {
		t.Fatalf("预置数据失败: %v", err)
	}

	got, err := s.UpsertSubscription("alice", endpoint, "p-new", "a-new")
	if err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	if got.CreatedAt == "2000-01-01T00:00:00Z" {
		t.Fatalf("冲突更新后 createdAt 应刷新，实际仍为旧值 %q", got.CreatedAt)
	}
	if got.P256DH != "p-new" || got.Auth != "a-new" {
		t.Fatalf("冲突更新后密钥应刷新，实际 p256dh=%q auth=%q", got.P256DH, got.Auth)
	}
	if got.User != NormalizeUser("alice") {
		t.Fatalf("归属用户应为 alice，实际 %q", got.User)
	}

	n, err := s.CountSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("统计失败: %v", err)
	}
	if n != 1 {
		t.Fatalf("冲突更新不应新增记录，实际 %d", n)
	}
}

func TestUpsertSubscriptionUnicodeEndpointAndKeys(t *testing.T) {
	s := openDeepTestStore(t)

	endpoint := "https://push.example.com/中文路径?标题=双链[[笔记]]"
	p256dh := "密钥p256dh中文值"
	auth := "认证auth中文值"

	got, err := s.UpsertSubscription("晚风", endpoint, p256dh, auth)
	if err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	if got.Endpoint != endpoint {
		t.Fatalf("endpoint 应原样存取，期望 %q 实际 %q", endpoint, got.Endpoint)
	}
	if got.P256DH != p256dh {
		t.Fatalf("p256dh 应原样存取，期望 %q 实际 %q", p256dh, got.P256DH)
	}
	if got.Auth != auth {
		t.Fatalf("auth 应原样存取，期望 %q 实际 %q", auth, got.Auth)
	}
	if got.User != NormalizeUser("晚风") {
		t.Fatalf("user 应归一化，期望 %q 实际 %q", NormalizeUser("晚风"), got.User)
	}

	list, err := s.ListSubscriptionsForUser("晚风")
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("应列出 1 条，实际 %d", len(list))
	}
	if list[0].Endpoint != endpoint {
		t.Fatalf("列表 endpoint 不一致，期望 %q 实际 %q", endpoint, list[0].Endpoint)
	}
}

func TestUpsertSubscriptionLengthMeasuredInBytes(t *testing.T) {
	s := openDeepTestStore(t)

	endpointOk := "https://push.example.com/bytes"
	multiByte256 := strings.Repeat("中", 85) // 255 字节，卡在 256 字节上限内
	multiByte128 := strings.Repeat("文", 42) // 126 字节

	got, err := s.UpsertSubscription("alice", endpointOk, multiByte256, multiByte128)
	if err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	if len(got.P256DH) != len(multiByte256) {
		t.Fatalf("p256dh 字节长度应保持 %d，实际 %d", len(multiByte256), len(got.P256DH))
	}
	if len(got.Auth) != len(multiByte128) {
		t.Fatalf("auth 字节长度应保持 %d，实际 %d", len(multiByte128), len(got.Auth))
	}

	tooLongP256dh := strings.Repeat("中", 86) + "x"
	_, err = s.UpsertSubscription("alice", endpointOk+"/p", tooLongP256dh, "a1")
	if err == nil {
		t.Fatalf("p256dh 字节数 259 应被拒")
	}
	if err.Error() != "p256dh 长度不能超过 256" {
		t.Fatalf("错误文案不一致，期望 %q 实际 %q", "p256dh 长度不能超过 256", err.Error())
	}

	tooLongAuth := strings.Repeat("文", 43) + "x"
	_, err = s.UpsertSubscription("alice", endpointOk+"/a", "p1", tooLongAuth)
	if err == nil {
		t.Fatalf("auth 字节数 130 应被拒")
	}
	if err.Error() != "auth 长度不能超过 128" {
		t.Fatalf("错误文案不一致，期望 %q 实际 %q", "auth 长度不能超过 128", err.Error())
	}
}

func TestUpsertSubscriptionEndpointWithControlCharacters(t *testing.T) {
	s := openDeepTestStore(t)

	endpoint := "https://push.example.com/path\n\r\t?q=1"
	got, err := s.UpsertSubscription("alice", endpoint, "p1", "a1")
	if err != nil {
		t.Fatalf("写入失败: %v", err)
	}
	if got.Endpoint != endpoint {
		t.Fatalf("endpoint 应原样存取，期望 %q 实际 %q", endpoint, got.Endpoint)
	}

	list, err := s.ListSubscriptionsForUser("alice")
	if err != nil {
		t.Fatalf("列出失败: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("应列出 1 条，实际 %d", len(list))
	}
	if list[0].Endpoint != endpoint {
		t.Fatalf("列表 endpoint 应原样返回，期望 %q 实际 %q", endpoint, list[0].Endpoint)
	}
}
