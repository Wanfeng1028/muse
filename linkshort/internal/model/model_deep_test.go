package model

import (
	"sync"
	"testing"
	"time"
)

func strPtr(s string) *string { return &s }

func timePtr(t time.Time) *time.Time { return &t }

func int64Ptr(n int64) *int64 { return &n }

func mustUTC(t *testing.T, s string) time.Time {
	t.Helper()
	parsed, err := time.Parse(time.RFC3339, s)
	if err != nil {
		t.Fatalf("解析时间失败 %q: %v", s, err)
	}
	return parsed.UTC()
}

// 用例 1：短码碰撞 —— 相同 Slug 视为同一标识，不同 Slug 不相等。
func TestLinkSlugCollision(t *testing.T) {
	now := mustUTC(t, "2024-05-01T08:00:00Z")
	base := Link{
		ID:        1,
		Slug:      "abc123",
		URL:       "https://example.com/a",
		Title:     "第一条",
		Clicks:    0,
		Enabled:   true,
		CreatedAt: now,
		UpdatedAt: now,
	}
	dup := base
	dup.ID = 2
	dup.URL = "https://example.com/b"
	dup.Title = "第二条"

	if base.Slug != dup.Slug {
		t.Fatalf("相同短码应相等: %q vs %q", base.Slug, dup.Slug)
	}
	if base.ID == dup.ID {
		t.Fatalf("不同记录主键应不同: %d vs %d", base.ID, dup.ID)
	}
	if base.URL == dup.URL {
		t.Fatalf("不同目标链接不应相等: %q vs %q", base.URL, dup.URL)
	}

	other := base
	other.Slug = "abc124"
	if base.Slug == other.Slug {
		t.Fatalf("不同短码不应相等: %q vs %q", base.Slug, other.Slug)
	}
	if len(base.Slug) != len(other.Slug) {
		t.Fatalf("短码长度应一致: %d vs %d", len(base.Slug), len(other.Slug))
	}
}

// 用例 2：过期边界 —— ExpiresAt 为 nil 永不过期；等于当前时刻视为过期。
func TestLinkExpiryBoundary(t *testing.T) {
	now := mustUTC(t, "2024-06-01T12:00:00Z")

	never := Link{ID: 1, Slug: "never", URL: "https://example.com/never", Enabled: true, ExpiresAt: nil, CreatedAt: now, UpdatedAt: now}
	if never.ExpiresAt != nil {
		t.Fatalf("未设置过期时间时应为 nil，实际: %v", never.ExpiresAt)
	}

	expired := Link{ID: 2, Slug: "expired", URL: "https://example.com/expired", Enabled: true, ExpiresAt: timePtr(now), CreatedAt: now, UpdatedAt: now}
	if expired.ExpiresAt == nil {
		t.Fatal("已设置过期时间时不应为 nil")
	}
	if !expired.ExpiresAt.Equal(now) {
		t.Fatalf("过期时间应等于 %v，实际: %v", now, *expired.ExpiresAt)
	}
	if !expired.ExpiresAt.UTC().Equal(now.UTC()) {
		t.Fatalf("过期时间 UTC 应等于 %v，实际: %v", now.UTC(), expired.ExpiresAt.UTC())
	}

	future := Link{ID: 3, Slug: "future", URL: "https://example.com/future", Enabled: true, ExpiresAt: timePtr(now.Add(time.Hour)), CreatedAt: now, UpdatedAt: now}
	if !future.ExpiresAt.After(now) {
		t.Fatalf("未来过期时间应晚于 %v，实际: %v", now, *future.ExpiresAt)
	}
	if future.ExpiresAt.Equal(now) {
		t.Fatal("未来过期时间不应等于当前时刻")
	}
}

// 用例 3：限次焚毁边界 —— MaxVisits 与 Clicks 在边界上的关系。
func TestLinkMaxVisitsBoundary(t *testing.T) {
	now := mustUTC(t, "2024-07-01T00:00:00Z")

	unlimited := Link{ID: 1, Slug: "unlimited", URL: "https://example.com/u", Enabled: true, MaxVisits: nil, Clicks: 100, CreatedAt: now, UpdatedAt: now}
	if unlimited.MaxVisits != nil {
		t.Fatalf("不限次访问时 MaxVisits 应为 nil，实际: %v", *unlimited.MaxVisits)
	}

	one := Link{ID: 2, Slug: "one", URL: "https://example.com/one", Enabled: true, MaxVisits: int64Ptr(1), Clicks: 0, CreatedAt: now, UpdatedAt: now}
	if one.MaxVisits == nil || *one.MaxVisits != 1 {
		t.Fatalf("MaxVisits 应为 1，实际: %v", one.MaxVisits)
	}
	if one.Clicks >= *one.MaxVisits {
		t.Fatalf("点击数 %d 应小于上限 %d", one.Clicks, *one.MaxVisits)
	}
	one.Clicks = 1
	if one.Clicks < *one.MaxVisits {
		t.Fatalf("点击数 %d 应不小于上限 %d", one.Clicks, *one.MaxVisits)
	}

	five := Link{ID: 3, Slug: "five", URL: "https://example.com/five", Enabled: true, MaxVisits: int64Ptr(5), Clicks: 4, CreatedAt: now, UpdatedAt: now}
	if five.Clicks >= *five.MaxVisits {
		t.Fatalf("点击数 %d 应小于上限 %d", five.Clicks, *five.MaxVisits)
	}
	five.Clicks = 5
	if five.Clicks != *five.MaxVisits {
		t.Fatalf("点击数 %d 应等于上限 %d", five.Clicks, *five.MaxVisits)
	}
}

// 用例 4：阅后即焚状态流转 —— Burn 开关与 BurnedAt 的组合。
func TestLinkBurnStateTransition(t *testing.T) {
	now := mustUTC(t, "2024-08-01T09:30:00Z")

	normal := Link{ID: 1, Slug: "normal", URL: "https://example.com/n", Enabled: true, Burn: false, BurnedAt: nil, PurgeAfterBurn: false, CreatedAt: now, UpdatedAt: now}
	if normal.Burn {
		t.Fatal("普通链接 Burn 应为 false")
	}
	if normal.BurnedAt != nil {
		t.Fatalf("未销毁时 BurnedAt 应为 nil，实际: %v", normal.BurnedAt)
	}
	if normal.PurgeAfterBurn {
		t.Fatal("默认 PurgeAfterBurn 应为 false")
	}

	burned := Link{ID: 2, Slug: "burned", URL: "https://example.com/b", Enabled: false, Burn: true, BurnedAt: timePtr(now), PurgeAfterBurn: true, CreatedAt: now, UpdatedAt: now}
	if !burned.Burn {
		t.Fatal("阅后即焚链接 Burn 应为 true")
	}
	if burned.BurnedAt == nil {
		t.Fatal("已销毁时 BurnedAt 不应为 nil")
	}
	if !burned.BurnedAt.Equal(now) {
		t.Fatalf("销毁时间应为 %v，实际: %v", now, *burned.BurnedAt)
	}
	if !burned.PurgeAfterBurn {
		t.Fatal("开启彻底删除后 PurgeAfterBurn 应为 true")
	}

	pending := Link{ID: 3, Slug: "pending", URL: "https://example.com/p", Enabled: true, Burn: true, BurnedAt: nil, PurgeAfterBurn: false, CreatedAt: now, UpdatedAt: now}
	if !pending.Burn {
		t.Fatal("待销毁链接 Burn 应为 true")
	}
	if pending.BurnedAt != nil {
		t.Fatalf("待销毁链接 BurnedAt 应为 nil，实际: %v", pending.BurnedAt)
	}
}

// 用例 5：访问画像聚合 —— Visit 记录按 LinkID 与 IPHash 聚合计数。
func TestVisitProfileAggregation(t *testing.T) {
	base := mustUTC(t, "2024-09-01T10:00:00Z")
	visits := []Visit{
		{ID: 1, LinkID: 7, TS: base, IPHash: "hash-a", UA: "UA-1", Referer: "https://ref.example.com/1"},
		{ID: 2, LinkID: 7, TS: base.Add(time.Second), IPHash: "hash-a", UA: "UA-1", Referer: "https://ref.example.com/1"},
		{ID: 3, LinkID: 7, TS: base.Add(2 * time.Second), IPHash: "hash-b", UA: "UA-2", Referer: "https://ref.example.com/2"},
		{ID: 4, LinkID: 8, TS: base.Add(3 * time.Second), IPHash: "hash-a", UA: "UA-3", Referer: "https://ref.example.com/3"},
	}

	byLink := map[int64]int64{}
	byIP := map[string]int64{}
	byReferer := map[string]int64{}
	for _, v := range visits {
		byLink[v.LinkID]++
		byIP[v.IPHash]++
		byReferer[v.Referer]++
	}

	if byLink[7] != 3 {
		t.Fatalf("LinkID=7 访问数应为 3，实际: %d", byLink[7])
	}
	if byLink[8] != 1 {
		t.Fatalf("LinkID=8 访问数应为 1，实际: %d", byLink[8])
	}
	if byIP["hash-a"] != 3 {
		t.Fatalf("IPHash=hash-a 访问数应为 3，实际: %d", byIP["hash-a"])
	}
	if byIP["hash-b"] != 1 {
		t.Fatalf("IPHash=hash-b 访问数应为 1，实际: %d", byIP["hash-b"])
	}
	if byReferer["https://ref.example.com/1"] != 2 {
		t.Fatalf("Referer 1 访问数应为 2，实际: %d", byReferer["https://ref.example.com/1"])
	}
	if byReferer["https://ref.example.com/3"] != 1 {
		t.Fatalf("Referer 3 访问数应为 1，实际: %d", byReferer["https://ref.example.com/3"])
	}

	stats := []NamedStat{
		{Name: "hash-a", Clicks: byIP["hash-a"]},
		{Name: "hash-b", Clicks: byIP["hash-b"]},
	}
	if stats[0].Clicks != 3 {
		t.Fatalf("hash-a 统计应为 3，实际: %d", stats[0].Clicks)
	}
	if stats[1].Clicks != 1 {
		t.Fatalf("hash-b 统计应为 1，实际: %d", stats[1].Clicks)
	}
}

// 用例 6：DailyStat 日期聚合 —— 按 UTC 日期切分统计。
func TestDailyStatAggregation(t *testing.T) {
	day1 := mustUTC(t, "2024-10-01T23:59:59Z")
	day2 := mustUTC(t, "2024-10-02T00:00:00Z")
	day2Later := mustUTC(t, "2024-10-02T12:30:00Z")

	visits := []Visit{
		{ID: 1, LinkID: 1, TS: day1, IPHash: "h1", UA: "UA", Referer: "r1"},
		{ID: 2, LinkID: 1, TS: day2, IPHash: "h2", UA: "UA", Referer: "r1"},
		{ID: 3, LinkID: 1, TS: day2Later, IPHash: "h3", UA: "UA", Referer: "r2"},
	}

	byDate := map[string]int64{}
	for _, v := range visits {
		key := v.TS.UTC().Format("2006-01-02")
		byDate[key]++
	}

	stats := []DailyStat{
		{Date: "2024-10-01", Clicks: byDate["2024-10-01"]},
		{Date: "2024-10-02", Clicks: byDate["2024-10-02"]},
	}
	if len(stats) != 2 {
		t.Fatalf("应有 2 天统计，实际: %d", len(stats))
	}
	if stats[0].Date != "2024-10-01" {
		t.Fatalf("第一天日期应为 2024-10-01，实际: %s", stats[0].Date)
	}
	if stats[0].Clicks != 1 {
		t.Fatalf("第一天点击数应为 1，实际: %d", stats[0].Clicks)
	}
	if stats[1].Date != "2024-10-02" {
		t.Fatalf("第二天日期应为 2024-10-02，实际: %s", stats[1].Date)
	}
	if stats[1].Clicks != 2 {
		t.Fatalf("第二天点击数应为 2，实际: %d", stats[1].Clicks)
	}
}

// 用例 7：限流判定 —— 同 IP 在时间窗口内计数不超过阈值。
func TestRateLimitWindow(t *testing.T) {
	start := mustUTC(t, "2024-11-01T00:00:00Z")
	window := time.Minute
	limit := int64(3)

	events := []time.Time{
		start,
		start.Add(10 * time.Second),
		start.Add(20 * time.Second),
		start.Add(30 * time.Second),
		start.Add(70 * time.Second),
	}

	allowed := int64(0)
	blocked := int64(0)
	for i, ts := range events {
		count := int64(0)
		for _, other := range events[:i] {
			if ts.Sub(other) < window {
				count++
			}
		}
		if count < limit {
			allowed++
		} else {
			blocked++
		}
	}

	if allowed != 4 {
		t.Fatalf("窗口内允许数应为 4，实际: %d", allowed)
	}
	if blocked != 1 {
		t.Fatalf("窗口内拦截数应为 1，实际: %d", blocked)
	}
	if allowed+blocked != int64(len(events)) {
		t.Fatalf("允许+拦截应等于事件总数 %d，实际: %d", len(events), allowed+blocked)
	}
}

// 用例 8：备份健康判定 —— 备份时间与最大允许间隔决定是否健康。
func TestBackupHealthCheck(t *testing.T) {
	now := mustUTC(t, "2024-12-01T00:00:00Z")
	maxAge := 24 * time.Hour

	healthy := now.Add(-2 * time.Hour)
	unhealthy := now.Add(-48 * time.Hour)
	exact := now.Add(-maxAge)

	check := func(last time.Time) bool {
		return now.Sub(last) <= maxAge
	}

	if !check(healthy) {
		t.Fatalf("2 小时前的备份应健康，距现在: %v", now.Sub(healthy))
	}
	if check(unhealthy) {
		t.Fatalf("48 小时前的备份应不健康，距现在: %v", now.Sub(unhealthy))
	}
	if !check(exact) {
		t.Fatalf("刚好 %v 前的备份应健康", maxAge)
	}
	if now.Sub(healthy) != 2*time.Hour {
		t.Fatalf("健康备份间隔应为 2h，实际: %v", now.Sub(healthy))
	}
	if now.Sub(unhealthy) != 48*time.Hour {
		t.Fatalf("不健康备份间隔应为 48h，实际: %v", now.Sub(unhealthy))
	}
}

// 用例 9：并发访问同一链接 —— -race 下点击数聚合一致。
func TestConcurrentClicks(t *testing.T) {
	now := mustUTC(t, "2025-01-01T00:00:00Z")
	link := Link{ID: 1, Slug: "race", URL: "https://example.com/race", Enabled: true, Clicks: 0, CreatedAt: now, UpdatedAt: now}

	var mu sync.Mutex
	var wg sync.WaitGroup
	workers := 50
	perWorker := 20

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perWorker; j++ {
				mu.Lock()
				link.Clicks++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()

	expected := int64(workers * perWorker)
	if link.Clicks != expected {
		t.Fatalf("并发点击数应为 %d，实际: %d", expected, link.Clicks)
	}
	if link.Slug != "race" {
		t.Fatalf("并发后 Slug 应为 race，实际: %s", link.Slug)
	}
	if !link.Enabled {
		t.Fatal("并发后 Enabled 应保持 true")
	}
}

// 用例 10：密码哈希与启用状态组合判定。
func TestLinkPasswordAndEnabled(t *testing.T) {
	now := mustUTC(t, "2025-02-01T00:00:00Z")

	noPwd := Link{ID: 1, Slug: "open", URL: "https://example.com/open", Enabled: true, PasswordHash: nil, CreatedAt: now, UpdatedAt: now}
	if noPwd.PasswordHash != nil {
		t.Fatalf("未设密码时 PasswordHash 应为 nil，实际: %v", *noPwd.PasswordHash)
	}
	if !noPwd.Enabled {
		t.Fatal("未设密码的链接应处于启用状态")
	}

	withPwd := Link{ID: 2, Slug: "locked", URL: "https://example.com/locked", Enabled: true, PasswordHash: strPtr("$2a$10$abcdefghijklmnopqrstuv"), CreatedAt: now, UpdatedAt: now}
	if withPwd.PasswordHash == nil {
		t.Fatal("设置密码后 PasswordHash 不应为 nil")
	}
	if *withPwd.PasswordHash != "$2a$10$abcdefghijklmnopqrstuv" {
		t.Fatalf("密码哈希应为 $2a$10$abcdefghijklmnopqrstuv，实际: %s", *withPwd.PasswordHash)
	}
	if len(*withPwd.PasswordHash) == 0 {
		t.Fatal("密码哈希长度不应为 0")
	}

	disabled := Link{ID: 3, Slug: "off", URL: "https://example.com/off", Enabled: false, PasswordHash: strPtr("$2a$10$zzzzzzzzzzzzzzzzzzzzzz"), CreatedAt: now, UpdatedAt: now}
	if disabled.Enabled {
		t.Fatal("禁用链接 Enabled 应为 false")
	}
	if disabled.PasswordHash == nil {
		t.Fatal("禁用链接仍应保留密码哈希")
	}
}

// 用例 11：NamedStat 排序 —— 按点击量降序，相同点击量按名称升序。
func TestNamedStatSorting(t *testing.T) {
	stats := []NamedStat{
		{Name: "b", Clicks: 5},
		{Name: "a", Clicks: 5},
		{Name: "c", Clicks: 10},
		{Name: "d", Clicks: 1},
	}

	sortStats := func(s []NamedStat) {
		for i := 0; i < len(s); i++ {
			for j := i + 1; j < len(s); j++ {
				if s[j].Clicks > s[i].Clicks || (s[j].Clicks == s[i].Clicks && s[j].Name < s[i].Name) {
					s[i], s[j] = s[j], s[i]
				}
			}
		}
	}
	sortStats(stats)

	if stats[0].Name != "c" || stats[0].Clicks != 10 {
		t.Fatalf("第一名应为 c/10，实际: %s/%d", stats[0].Name, stats[0].Clicks)
	}
	if stats[1].Name != "a" || stats[1].Clicks != 5 {
		t.Fatalf("第二名应为 a/5，实际: %s/%d", stats[1].Name, stats[1].Clicks)
	}
	if stats[2].Name != "b" || stats[2].Clicks != 5 {
		t.Fatalf("第三名应为 b/5，实际: %s/%d", stats[2].Name, stats[2].Clicks)
	}
	if stats[3].Name != "d" || stats[3].Clicks != 1 {
		t.Fatalf("第四名应为 d/1，实际: %s/%d", stats[3].Name, stats[3].Clicks)
	}
}

// 用例 12：链接可访问性综合判定 —— 启用、未过期、未超限、未焚毁。
func TestLinkAccessibility(t *testing.T) {
	now := mustUTC(t, "2025-03-01T12:00:00Z")

	accessible := Link{ID: 1, Slug: "ok", URL: "https://example.com/ok", Enabled: true, ExpiresAt: timePtr(now.Add(time.Hour)), MaxVisits: int64Ptr(10), Clicks: 3, Burn: false, BurnedAt: nil, CreatedAt: now, UpdatedAt: now}
	if !accessible.Enabled {
		t.Fatal("可访问链接应处于启用状态")
	}
	if accessible.ExpiresAt != nil && !accessible.ExpiresAt.After(now) {
		t.Fatalf("可访问链接过期时间应晚于 %v，实际: %v", now, *accessible.ExpiresAt)
	}
	if accessible.MaxVisits != nil && accessible.Clicks >= *accessible.MaxVisits {
		t.Fatalf("可访问链接点击数 %d 应小于上限 %d", accessible.Clicks, *accessible.MaxVisits)
	}
	if accessible.BurnedAt != nil {
		t.Fatalf("可访问链接不应被销毁，实际: %v", *accessible.BurnedAt)
	}

	expiredDisabled := Link{ID: 2, Slug: "exp", URL: "https://example.com/exp", Enabled: false, ExpiresAt: timePtr(now.Add(-time.Hour)), MaxVisits: int64Ptr(1), Clicks: 1, Burn: true, BurnedAt: timePtr(now), CreatedAt: now, UpdatedAt: now}
	if expiredDisabled.Enabled {
		t.Fatal("过期禁用链接 Enabled 应为 false")
	}
	if expiredDisabled.ExpiresAt == nil || expiredDisabled.ExpiresAt.After(now) {
		t.Fatalf("过期链接过期时间应早于 %v", now)
	}
	if expiredDisabled.MaxVisits == nil || expiredDisabled.Clicks < *expiredDisabled.MaxVisits {
		t.Fatalf("超限链接点击数 %d 应不小于上限 %d", expiredDisabled.Clicks, *expiredDisabled.MaxVisits)
	}
	if expiredDisabled.BurnedAt == nil {
		t.Fatal("已销毁链接 BurnedAt 不应为 nil")
	}
	if !expiredDisabled.BurnedAt.Equal(now) {
		t.Fatalf("销毁时间应为 %v，实际: %v", now, *expiredDisabled.BurnedAt)
	}
}
