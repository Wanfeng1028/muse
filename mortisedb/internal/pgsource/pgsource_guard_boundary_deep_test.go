package pgsource

import (
	"strings"
	"testing"
	"time"
)

// TestGuardBoundaryEvasion 测白名单正则的边界，也就是它拦不住什么、又能拦住什么。
func TestGuardBoundaryEvasion(t *testing.T) {
	// 2026-10-19 加固：白名单升级为字面量/注释感知，不再放行 WITH 体内 DML。
	// 第一层现在会词法扫描剥离后的文本，WITH 体内出现 DELETE/UPDATE/INSERT/MERGE
	// 一律拒绝，零数据库往返。真正写保护仍由第二层只读事务和第三层只读账号兜底。
	err := AssertReadOnlySQL("WITH d AS (DELETE FROM t) SELECT 1")
	if err == nil {
		t.Fatalf("WITH 夹带写操作现在应当被拒绝，却通过了白名单")
	}
	if !strings.Contains(err.Error(), "只读") {
		t.Fatalf("错误信息里应当含 '只读'，实际: %v", err)
	}

	// 变更：以 SQL 注释开头现在被剥离，剥离后以 SELECT 开头，应当通过。
	if err := AssertReadOnlySQL("-- pick\nSELECT 1"); err != nil {
		t.Fatalf("注释剥离后以 SELECT 开头的语句现在应当通过，实际错误: %v", err)
	}

	// 变更：字符串字面量里的分号不再误杀，因为先剥离字面量再检查分号。
	if err := AssertReadOnlySQL("select 'a;b'"); err != nil {
		t.Fatalf("字符串里的分号现在不再误杀，应当通过，实际错误: %v", err)
	}

	// TABLE t 不是 select/with 开头，拒。
	if err := AssertReadOnlySQL("TABLE t"); err == nil {
		t.Fatalf("TABLE t 应当被拒绝")
	}

	// EXPLAIN 也不是允许的前缀，拒。
	if err := AssertReadOnlySQL("EXPLAIN SELECT 1"); err == nil {
		t.Fatalf("EXPLAIN SELECT 1 应当被拒绝")
	}

	// 前导空白加大小写混写，前缀正则带 (?is) 和 ^\s*，应当放过。
	if err := AssertReadOnlySQL(" \n\tSeLeCt 1 "); err != nil {
		t.Fatalf("前导空白加大小写混写应当通过，实际错误: %v", err)
	}
}

// TestEnsureReadOnlyConnStrBoundary 测连接串改写的边界情况。
func TestEnsureReadOnlyConnStrBoundary(t *testing.T) {
	// scheme 不是 postgres/postgresql，直接报错。
	if _, err := EnsureReadOnlyConnStr("mysql://u@h/db"); err == nil {
		t.Fatalf("mysql scheme 应当被拒绝")
	}

	// 原有参数要保留，同时补上只读参数。
	out, err := EnsureReadOnlyConnStr("postgres://u:p@h:5432/db?sslmode=disable")
	if err != nil {
		t.Fatalf("合法连接串不应报错: %v", err)
	}
	if !strings.Contains(out, "sslmode=disable") {
		t.Fatalf("原有 sslmode 参数应当保留，实际: %s", out)
	}
	if !strings.Contains(out, "default_transaction_read_only=on") {
		t.Fatalf("应当补上 default_transaction_read_only=on，实际: %s", out)
	}

	// 已经带了只读参数，就不该再塞一遍。
	already := "postgres://u@h/db?default_transaction_read_only=on"
	out2, err := EnsureReadOnlyConnStr(already)
	if err != nil {
		t.Fatalf("已带只读参数的串不应报错: %v", err)
	}
	if got := strings.Count(out2, "default_transaction_read_only"); got != 1 {
		t.Fatalf("只读参数应当只出现 1 次，实际出现 %d 次: %s", got, out2)
	}

	// postgresql 也是合法 scheme。
	if _, err := EnsureReadOnlyConnStr("postgresql://u@h/db"); err != nil {
		t.Fatalf("postgresql scheme 应当合法，实际错误: %v", err)
	}
}

// TestConfigValidateBoundary 测配置校验和默认值补全。
func TestConfigValidateBoundary(t *testing.T) {
	// ConnStr 空，报错。
	c1 := Config{Tables: []string{"t"}}
	if err := c1.Validate(); err == nil {
		t.Fatalf("ConnStr 为空时应当报错")
	}

	// Tables 空，报错。
	c2 := Config{ConnStr: "postgres://u@h/db"}
	if err := c2.Validate(); err == nil {
		t.Fatalf("Tables 为空时应当报错")
	}

	// CursorColumn 和 BatchSize 都空，应当补成默认值。
	c3 := Config{ConnStr: "postgres://u@h/db", Tables: []string{"t"}}
	if err := c3.Validate(); err != nil {
		t.Fatalf("合法配置不应报错: %v", err)
	}
	if c3.CursorColumn != "updated_at" {
		t.Fatalf("CursorColumn 应当补成 updated_at，实际: %q", c3.CursorColumn)
	}
	if c3.BatchSize != 1000 {
		t.Fatalf("BatchSize 应当补成 1000，实际: %d", c3.BatchSize)
	}

	// scheme 不对，报错。
	c4 := Config{ConnStr: "mysql://x", Tables: []string{"t"}}
	if err := c4.Validate(); err == nil {
		t.Fatalf("mysql 连接串应当校验失败")
	}
}

// TestNewFakeSourcePanicsOnInvalidConfig 空配置会触发 panic，属于 fail fast。
func TestNewFakeSourcePanicsOnInvalidConfig(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatalf("空配置构造 FakeSource 应当 panic")
		}
	}()
	NewFakeSource(Config{}, nil, nil, nil, nil)
}

// TestMapPGTypeBoundary 测类型映射里没被覆盖到的边角。
func TestMapPGTypeBoundary(t *testing.T) {
	// lo 是 large object，设计文档明确不读，落到默认 TEXT。
	if got := MapPGType("lo"); got != "TEXT" {
		t.Fatalf("MapPGType(\"lo\") 应当为 TEXT，实际: %s", got)
	}
	// 大小写不敏感，INTERVAL 归到 DATETIME。
	if got := MapPGType("INTERVAL"); got != "DATETIME" {
		t.Fatalf("MapPGType(\"INTERVAL\") 应当为 DATETIME，实际: %s", got)
	}
	// citext 不在表里，落默认。
	if got := MapPGType("citext"); got != "TEXT" {
		t.Fatalf("MapPGType(\"citext\") 应当为 TEXT，实际: %s", got)
	}
	// 空串也落默认。
	if got := MapPGType(""); got != "TEXT" {
		t.Fatalf("MapPGType(\"\") 应当为 TEXT，实际: %s", got)
	}
}

// TestCursorAdvanceTieBreak 测同一时间戳下用主键做 tie-break 的推进逻辑。
func TestCursorAdvanceTieBreak(t *testing.T) {
	t0 := time.Date(2026, 1, 2, 0, 0, 0, 0, time.UTC)

	// 同时间戳，主键 3 < 5，不推进。
	cur := Cursor{UpdatedAt: t0, LastPK: "5"}
	if ok := cur.Advance(t0, "3"); ok {
		t.Fatalf("主键变小不应推进")
	}
	if !cur.UpdatedAt.Equal(t0) || cur.LastPK != "5" {
		t.Fatalf("不推进时游标不应改变，实际: %+v", cur)
	}

	// 同时间戳，主键 9 > 5，推进且只改 LastPK。
	if ok := cur.Advance(t0, "9"); !ok {
		t.Fatalf("主键变大应当推进")
	}
	if cur.LastPK != "9" {
		t.Fatalf("推进后 LastPK 应当为 9，实际: %q", cur.LastPK)
	}

	// 时间倒退，不推进。
	before := t0.Add(-time.Hour)
	cur2 := Cursor{UpdatedAt: t0, LastPK: "5"}
	if ok := cur2.Advance(before, "z"); ok {
		t.Fatalf("时间倒退不应推进")
	}
}
