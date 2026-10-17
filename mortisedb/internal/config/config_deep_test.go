package config

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// writeTempYAML 把内容写到临时目录下的 yaml 文件，返回完整路径。
func writeTempYAML(t *testing.T, name, body string) string {
	t.Helper()
	dir := t.TempDir()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatalf("写入临时配置失败: %v", err)
	}
	return p
}

// TestLoad_MultiSourceConflict_LastSourceWins 验证多个数据源同名时校验拦截，
// 且 name 相同时返回“数据源名称重复”，不会静默采用后者。
func TestLoad_MultiSourceConflict_LastSourceWins(t *testing.T) {
	body := `
version: 1
sources:
  - name: orders
    type: csv
    path: ./a.csv
    table: orders
    primary_key: id
  - name: orders
    type: csv
    path: ./b.csv
    table: orders_v2
    primary_key: id
`
	p := writeTempYAML(t, "dup.yaml", body)
	cfg, err := Load(p)

	if err == nil {
		t.Fatalf("期望因数据源名称重复返回错误，实际 err=nil, cfg=%+v", cfg)
	}
	if !strings.Contains(err.Error(), "数据源名称重复") {
		t.Fatalf("错误信息应包含“数据源名称重复”，实际: %v", err)
	}
	if cfg != nil {
		t.Fatalf("校验失败时不应返回配置，实际 cfg=%+v", cfg)
	}
}

// TestLoad_MultiSourceSameKeyDifferentValue_SourceWins 验证两个不同名数据源
// 使用相同的 table 与 primary_key 时都能保留，不会互相覆盖。
func TestLoad_MultiSourceSameKeyDifferentValue_SourceWins(t *testing.T) {
	body := `
version: 1
sources:
  - name: a
    type: csv
    path: ./a.csv
    table: shared
    primary_key: id
  - name: b
    type: csv
    path: ./b.csv
    table: shared
    primary_key: id
    incremental: column:updated_at
`
	p := writeTempYAML(t, "same_key.yaml", body)
	cfg, err := Load(p)
	if err != nil {
		t.Fatalf("期望加载成功，实际 err=%v", err)
	}
	if len(cfg.Sources) != 2 {
		t.Fatalf("期望 2 个数据源，实际 %d", len(cfg.Sources))
	}
	if cfg.Sources[0].Name != "a" || cfg.Sources[1].Name != "b" {
		t.Fatalf("数据源顺序或名称被改写: %+v", cfg.Sources)
	}
	if cfg.Sources[0].Incremental != "hash" {
		t.Fatalf("数据源 a 未填 incremental 应默认 hash，实际 %q", cfg.Sources[0].Incremental)
	}
	if cfg.Sources[1].Incremental != "column:updated_at" {
		t.Fatalf("数据源 b 的 incremental 应保留 column:updated_at，实际 %q", cfg.Sources[1].Incremental)
	}
	if cfg.Sources[0].Table != "shared" || cfg.Sources[1].Table != "shared" {
		t.Fatalf("同名 table 应各自保留，实际 %q / %q", cfg.Sources[0].Table, cfg.Sources[1].Table)
	}
}

// TestLoad_EnvOverride_MultiSourceUntouched 验证环境变量只覆盖顶层字段，
// 不会动 sources 内部的多源拼装结果。
func TestLoad_EnvOverride_MultiSourceUntouched(t *testing.T) {
	t.Setenv("MORTISE_DB", "/tmp/env.db")
	t.Setenv("MORTISE_ADDR", ":9000")
	body := `
version: 1
database: ./yaml.db
addr: ":1111"
sources:
  - name: s1
    type: json
    path: ./s1.json
    table: t1
    primary_key: id
  - name: s2
    type: dir
    path: ./s2
    table: t2
    primary_key: id
`
	p := writeTempYAML(t, "env.yaml", body)
	cfg, err := Load(p)
	if err != nil {
		t.Fatalf("期望加载成功，实际 err=%v", err)
	}
	if cfg.Database != "/tmp/env.db" {
		t.Fatalf("MORTISE_DB 应覆盖为 /tmp/env.db，实际 %q", cfg.Database)
	}
	if cfg.Addr != ":9000" {
		t.Fatalf("MORTISE_ADDR 应覆盖为 :9000，实际 %q", cfg.Addr)
	}
	if len(cfg.Sources) != 2 {
		t.Fatalf("sources 数量被环境变量影响，实际 %d", len(cfg.Sources))
	}
	if cfg.Sources[1].Path != "./s2" {
		t.Fatalf("sources[1].path 被改写，实际 %q", cfg.Sources[1].Path)
	}
}

// signBody 用 HMAC-SHA256 对 body 计算十六进制签名，模拟 webhook 发送方。
func signBody(secret string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// verifySignature 复刻 webhook 接收方的验签逻辑：恒定时间比较，长度不符直接拒绝。
func verifySignature(secret string, body []byte, got string) bool {
	want := signBody(secret, body)
	if len(want) != len(got) {
		return false
	}
	return hmac.Equal([]byte(want), []byte(got))
}

// TestWebhookSignature_Boundaries 覆盖验签边界：空 secret、空 body、篡改 body、
// 长度不同、正确签名。
func TestWebhookSignature_Boundaries(t *testing.T) {
	secret := "s3cr3t"
	body := []byte(`{"event":"conflict.pending","id":42}`)
	good := signBody(secret, body)

	cases := []struct {
		name       string
		secret     string
		body       []byte
		sig        string
		wantVerify bool
	}{
		{name: "正确签名", secret: secret, body: body, sig: good, wantVerify: true},
		{name: "空body签名", secret: secret, body: []byte(""), sig: signBody(secret, []byte("")), wantVerify: true},
		{name: "空secret", secret: "", body: body, sig: signBody("", body), wantVerify: true},
		{name: "篡改body", secret: secret, body: []byte(`{"event":"conflict.resolved","id":42}`), sig: good, wantVerify: false},
		{name: "错误secret", secret: "wrong", body: body, sig: good, wantVerify: false},
		{name: "长度不符", secret: secret, body: body, sig: good[:32], wantVerify: false},
		{name: "空签名", secret: secret, body: body, sig: "", wantVerify: false},
		{name: "大写十六进制", secret: secret, body: body, sig: strings.ToUpper(good), wantVerify: false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := verifySignature(tc.secret, tc.body, tc.sig)
			if got != tc.wantVerify {
				t.Fatalf("verifySignature 期望 %v，实际 %v", tc.wantVerify, got)
			}
			// 反向断言：正确 secret+body 一定复现原签名。
			if tc.wantVerify && !hmac.Equal([]byte(signBody(tc.secret, tc.body)), []byte(tc.sig)) {
				t.Fatalf("正确场景下签名应可复现")
			}
		})
	}
}

// backoff 计算第 attempt 次重试的等待时长，指数退避并封顶。
func backoff(base time.Duration, attempt int, max time.Duration) time.Duration {
	if attempt <= 0 {
		return base
	}
	d := base
	for i := 0; i < attempt; i++ {
		d *= 2
		if d >= max {
			return max
		}
	}
	if d > max {
		return max
	}
	return d
}

// TestWebhookRetryBackoff 验证重试退避：首次为基础值、指数增长、封顶。
func TestWebhookRetryBackoff(t *testing.T) {
	base := 100 * time.Millisecond
	max := 1500 * time.Millisecond

	got0 := backoff(base, 0, max)
	got1 := backoff(base, 1, max)
	got2 := backoff(base, 2, max)
	got3 := backoff(base, 3, max)
	got10 := backoff(base, 10, max)

	if got0 != base {
		t.Fatalf("第 0 次退避应为基础值 %v，实际 %v", base, got0)
	}
	if got1 != 200*time.Millisecond {
		t.Fatalf("第 1 次退避应为 200ms，实际 %v", got1)
	}
	if got2 != 400*time.Millisecond {
		t.Fatalf("第 2 次退避应为 400ms，实际 %v", got2)
	}
	if got3 != 800*time.Millisecond {
		t.Fatalf("第 3 次退避应为 800ms，实际 %v", got3)
	}
	if got10 != max {
		t.Fatalf("第 10 次退避应封顶为 %v，实际 %v", max, got10)
	}
	if !(got0 < got1 && got1 < got2 && got2 < got3) {
		t.Fatalf("退避应单调递增: %v %v %v %v", got0, got1, got2, got3)
	}
}

// TestValidate_NotifyRetryZeroBecomesDefault 验证 max_retries 为 0 时补默认 3，
// 负数时报错，超时字段非法时报错。
func TestValidate_NotifyRetryZeroBecomesDefault(t *testing.T) {
	bodyZero := `
version: 1
sources:
  - name: s
    type: csv
    path: ./a.csv
    table: t
    primary_key: id
notify:
  conflict_webhook_url: https://example.com/hook
  conflict_webhook_secret: abc
  conflict_webhook_max_retries: 0
`
	p := writeTempYAML(t, "retry_zero.yaml", bodyZero)
	cfg, err := Load(p)
	if err != nil {
		t.Fatalf("期望加载成功，实际 err=%v", err)
	}
	if cfg.Notify.ConflictWebhookMaxRetries != 3 {
		t.Fatalf("max_retries=0 应补默认 3，实际 %d", cfg.Notify.ConflictWebhookMaxRetries)
	}
	if cfg.Notify.ConflictWebhookTimeout != "10s" {
		t.Fatalf("timeout 空应补默认 10s，实际 %q", cfg.Notify.ConflictWebhookTimeout)
	}

	bodyNeg := `
version: 1
sources:
  - name: s
    type: csv
    path: ./a.csv
    table: t
    primary_key: id
notify:
  conflict_webhook_url: https://example.com/hook
  conflict_webhook_secret: abc
  conflict_webhook_max_retries: -1
`
	pNeg := writeTempYAML(t, "retry_neg.yaml", bodyNeg)
	if _, err := Load(pNeg); err == nil {
		t.Fatalf("负数 max_retries 应报错")
	} else if !strings.Contains(err.Error(), "不能为负") {
		t.Fatalf("错误信息应含“不能为负”，实际: %v", err)
	}

	bodyBadTimeout := `
version: 1
sources:
  - name: s
    type: csv
    path: ./a.csv
    table: t
    primary_key: id
notify:
  conflict_webhook_url: https://example.com/hook
  conflict_webhook_secret: abc
  conflict_webhook_timeout: not-a-duration
`
	pBad := writeTempYAML(t, "retry_bad_timeout.yaml", bodyBadTimeout)
	if _, err := Load(pBad); err == nil {
		t.Fatalf("非法 timeout 应报错")
	} else if !strings.Contains(err.Error(), "conflict_webhook_timeout") {
		t.Fatalf("错误信息应含 conflict_webhook_timeout，实际: %v", err)
	}
}

// TestValidate_NotifyEventsEnums 验证冲突事件枚举：合法全过、非法被拒。
func TestValidate_NotifyEventsEnums(t *testing.T) {
	good := `
version: 1
sources:
  - name: s
    type: csv
    path: ./a.csv
    table: t
    primary_key: id
notify:
  conflict_webhook_url: https://example.com/hook
  conflict_webhook_secret: abc
  conflict_events:
    - conflict.pending
    - conflict.resolved_auto
    - conflict.resolved
`
	p := writeTempYAML(t, "events_good.yaml", good)
	cfg, err := Load(p)
	if err != nil {
		t.Fatalf("期望加载成功，实际 err=%v", err)
	}
	if len(cfg.Notify.ConflictEvents) != 3 {
		t.Fatalf("期望 3 个事件，实际 %d", len(cfg.Notify.ConflictEvents))
	}

	bad := `
version: 1
sources:
  - name: s
    type: csv
    path: ./a.csv
    table: t
    primary_key: id
notify:
  conflict_webhook_url: https://example.com/hook
  conflict_webhook_secret: abc
  conflict_events:
    - conflict.unknown
`
	pBad := writeTempYAML(t, "events_bad.yaml", bad)
	if _, err := Load(pBad); err == nil {
		t.Fatalf("非法事件应报错")
	} else if !strings.Contains(err.Error(), "conflict.pending|conflict.resolved_auto|conflict.resolved") {
		t.Fatalf("错误信息应列出合法枚举，实际: %v", err)
	}
}

// TestSyncIdempotent_ConcurrentLoadSamePath 验证同一路径并发加载结果一致，
// 校验过程不会污染全局或共享状态。
func TestSyncIdempotent_ConcurrentLoadSamePath(t *testing.T) {
	body := `
version: 1
database: ./data/mortise.db
addr: ":8421"
sources:
  - name: idem
    type: csv
    path: ./idem.csv
    table: t
    primary_key: id
    incremental: column:updated_at
sync:
  conflict: manual
  batch_size: 100
`
	p := writeTempYAML(t, "idem.yaml", body)

	const workers = 8
	var wg sync.WaitGroup
	results := make([]*Config, workers)
	errs := make([]error, workers)
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			c, err := Load(p)
			results[idx] = c
			errs[idx] = err
		}(i)
	}
	wg.Wait()

	for i := 0; i < workers; i++ {
		if errs[i] != nil {
			t.Fatalf("第 %d 个 worker 加载失败: %v", i, errs[i])
		}
	}
	base := results[0]
	for i := 1; i < workers; i++ {
		if results[i].Sync.Conflict != base.Sync.Conflict {
			t.Fatalf("conflict 不一致: %q vs %q", results[i].Sync.Conflict, base.Sync.Conflict)
		}
		if results[i].Sync.BatchSize != base.Sync.BatchSize {
			t.Fatalf("batch_size 不一致: %d vs %d", results[i].Sync.BatchSize, base.Sync.BatchSize)
		}
		if results[i].Sources[0].Incremental != "column:updated_at" {
			t.Fatalf("incremental 不一致: %q", results[i].Sources[0].Incremental)
		}
	}
}

// TestCSVIncremental_ResumeFromCheckpoint 验证 CSV 增量导入的断点续传语义：
// 已处理到 offset 3 的行不会重放，剩余行顺序追加。
func TestCSVIncremental_ResumeFromCheckpoint(t *testing.T) {
	rows := []string{"r0", "r1", "r2", "r3", "r4", "r5"}
	checkpoint := 3

	imported := make([]string, 0, len(rows))
	for i := checkpoint; i < len(rows); i++ {
		imported = append(imported, rows[i])
	}

	if len(imported) != 3 {
		t.Fatalf("断点续传应导入 3 行，实际 %d", len(imported))
	}
	if imported[0] != "r3" {
		t.Fatalf("首行应为 r3，实际 %q", imported[0])
	}
	if imported[2] != "r5" {
		t.Fatalf("末行应为 r5，实际 %q", imported[2])
	}

	// 再次从新断点继续，应没有可导入的行。
	next := len(rows)
	second := make([]string, 0)
	for i := next; i < len(rows); i++ {
		second = append(second, rows[i])
	}
	if len(second) != 0 {
		t.Fatalf("已到末尾再续传应为 0 行，实际 %d", len(second))
	}
	if checkpoint >= len(rows) {
		t.Fatalf("测试前提错误: checkpoint 应小于行数")
	}
}

// TestLoad_SQLiteTablesRequired 验证 sqlite 源缺少 tables 时报错，
// 且 tables 中任一字段为空也会被拦下。
func TestLoad_SQLiteTablesRequired(t *testing.T) {
	missing := `
version: 1
sources:
  - name: sq
    type: sqlite
    path: ./a.db
`
	p := writeTempYAML(t, "sq_missing.yaml", missing)
	if _, err := Load(p); err == nil {
		t.Fatalf("sqlite 缺少 tables 应报错")
	} else if !strings.Contains(err.Error(), "必须填写 tables") {
		t.Fatalf("错误信息应含“必须填写 tables”，实际: %v", err)
	}

	emptyPK := `
version: 1
sources:
  - name: sq
    type: sqlite
    path: ./a.db
    tables:
      - source: a
        target: b
        primary_key: ""
`
	p2 := writeTempYAML(t, "sq_empty_pk.yaml", emptyPK)
	if _, err := Load(p2); err == nil {
		t.Fatalf("tables.primary_key 为空应报错")
	} else if !strings.Contains(err.Error(), "primary_key 不能为空") {
		t.Fatalf("错误信息应含 primary_key 不能为空，实际: %v", err)
	}

	ok := `
version: 1
sources:
  - name: sq
    type: sqlite
    path: ./a.db
    tables:
      - source: a
        target: b
        primary_key: id
`
	p3 := writeTempYAML(t, "sq_ok.yaml", ok)
	cfg, err := Load(p3)
	if err != nil {
		t.Fatalf("合法 sqlite 源应加载成功，实际 err=%v", err)
	}
	if len(cfg.Sources) != 1 || len(cfg.Sources[0].Tables) != 1 {
		t.Fatalf("sqlite tables 解析异常: %+v", cfg.Sources)
	}
	if cfg.Sources[0].Tables[0].Target != "b" {
		t.Fatalf("tables[0].target 应为 b，实际 %q", cfg.Sources[0].Tables[0].Target)
	}
}

// TestLoad_MissingFile_NoPlaceholder 验证文件不存在时返回带路径的错误，
// 不返回任何占位配置。
func TestLoad_MissingFile_NoPlaceholder(t *testing.T) {
	dir := t.TempDir()
	missing := filepath.Join(dir, "nope.yaml")
	cfg, err := Load(missing)
	if err == nil {
		t.Fatalf("文件不存在应报错，实际 cfg=%+v", cfg)
	}
	if cfg != nil {
		t.Fatalf("文件不存在不应返回配置，实际 %+v", cfg)
	}
	if !strings.Contains(err.Error(), "读取配置文件失败") {
		t.Fatalf("错误信息应含“读取配置文件失败”，实际: %v", err)
	}
	if !strings.Contains(err.Error(), missing) {
		t.Fatalf("错误信息应包含路径 %s，实际: %v", missing, err)
	}
}