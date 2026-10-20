package infer

import (
	"os"
	"path/filepath"
	"testing"
)

// TestNormalizeComparableSameInstant 验证同一时刻的不同时区写法规范化后完全一致，
// "2026-10-20T18:00:00+08:00" 与 "2026-10-20T10:00:00Z" 表示同一时刻。
func TestNormalizeComparableSameInstant(t *testing.T) {
	a := NormalizeComparable("2026-10-20T18:00:00+08:00")
	b := NormalizeComparable("2026-10-20T10:00:00Z")
	if a != "2026-10-20T10:00:00Z" {
		t.Fatalf("东八区写法规范化结果错误：期望 %q，实际 %q", "2026-10-20T10:00:00Z", a)
	}
	if b != "2026-10-20T10:00:00Z" {
		t.Fatalf("UTC 写法规范化结果错误：期望 %q，实际 %q", "2026-10-20T10:00:00Z", b)
	}
	if a != b {
		t.Fatalf("同一时刻的两种写法规范化后应相等：%q != %q", a, b)
	}
}

// TestNormalizeComparableHalfHourOffset 验证半小时时区偏移 "+05:30" 规范化正确，
// "2026-10-20T15:30:00+05:30" 即 "2026-10-20T10:00:00Z"。
func TestNormalizeComparableHalfHourOffset(t *testing.T) {
	got := NormalizeComparable("2026-10-20T15:30:00+05:30")
	if got != "2026-10-20T10:00:00Z" {
		t.Fatalf("半小时时区规范化错误：期望 %q，实际 %q", "2026-10-20T10:00:00Z", got)
	}
}

// TestNormalizeComparableNoColonOffset 验证无冒号偏移 "+0800" 的行为。
// 源码 parseDatetime 使用 time.RFC3339 布局，RFC3339 要求偏移形如 "+08:00"，
// 因此 "+0800" 无法解析，NormalizeComparable 按不可解析原样返回。
func TestNormalizeComparableNoColonOffset(t *testing.T) {
	got := NormalizeComparable("2026-10-20T18:00:00+0800")
	if got != "2026-10-20T18:00:00+0800" {
		t.Fatalf("无冒号偏移不可解析时应原样返回：期望 %q，实际 %q", "2026-10-20T18:00:00+0800", got)
	}
}

// TestNormalizeComparableMaxAmongMixedZones 验证 "Z" 与 "+08:00" 混排时，
// 规范化后字符串可直接比较得出最大值（字典序与时刻序一致，均为 UTC Z 结尾）。
func TestNormalizeComparableMaxAmongMixedZones(t *testing.T) {
	vals := []string{
		"2026-10-20T18:00:00+08:00", // 10:00Z
		"2026-10-20T10:00:00Z",     // 10:00Z
		"2026-10-20T19:00:00+08:00", // 11:00Z
		"2026-10-20T09:00:00Z",     // 09:00Z
	}
	norm := make([]string, len(vals))
	for i, v := range vals {
		norm[i] = NormalizeComparable(v)
	}
	max := norm[0]
	for _, n := range norm[1:] {
		if n > max {
			max = n
		}
	}
	if max != "2026-10-20T11:00:00Z" {
		t.Fatalf("混排时区最大值判定错误：期望 %q，实际 %q", "2026-10-20T11:00:00Z", max)
	}
}

// TestNormalizeComparableWatermarkIncrement 模拟水位线推进语义：
// 首轮水位线为同一时刻的两种写法（规范化后相同）；
// 次轮追加 11:00Z 应大于水位线（被拉取 1 行）；
// 追加 09:00Z 应不大于水位线（不被拉取 0 行）。
func TestNormalizeComparableWatermarkIncrement(t *testing.T) {
	firstA := NormalizeComparable("2026-10-20T18:00:00+08:00")
	firstB := NormalizeComparable("2026-10-20T10:00:00Z")
	if firstA != firstB {
		t.Fatalf("首轮两条数据应表示同一时刻，规范化后不相等：%q != %q", firstA, firstB)
	}
	watermark := firstA
	if watermark != "2026-10-20T10:00:00Z" {
		t.Fatalf("首轮水位线错误：期望 %q，实际 %q", "2026-10-20T10:00:00Z", watermark)
	}

	// 次轮追加 19:00+08:00 = 11:00Z，应被拉取（> 水位线）
	pulled := 0
	next := NormalizeComparable("2026-10-20T19:00:00+08:00")
	if next > watermark {
		pulled++
	}
	if pulled != 1 {
		t.Fatalf("11:00Z 应被拉取 1 行，实际 %d 行", pulled)
	}

	// 再次追加 17:00+08:00 = 09:00Z，不应被拉取（<= 水位线）
	pulled = 0
	next = NormalizeComparable("2026-10-20T17:00:00+08:00")
	if next > watermark {
		pulled++
	}
	if pulled != 0 {
		t.Fatalf("09:00Z 不应被拉取，期望 0 行，实际 %d 行", pulled)
	}
}

// TestNormalizeComparableWatermarkAlwaysUTCZ 验证规范化后的水位线恒为 UTC Z 结尾，
// 不含本地时区残留。
func TestNormalizeComparableWatermarkAlwaysUTCZ(t *testing.T) {
	got := NormalizeComparable("2026-10-20T18:00:00+08:00")
	if len(got) == 0 || got[len(got)-1] != 'Z' {
		t.Fatalf("水位线应以 Z 结尾，实际 %q", got)
	}
	// 不能出现 "+" 偏移写法
	for i := 0; i < len(got); i++ {
		if got[i] == '+' {
			t.Fatalf("水位线不应残留本地时区偏移：%q", got)
		}
	}
}

// TestInferCSVThenNormalizeDatetimeColumn 端到端：CSV 中混合时区写法应被推断为 DATETIME，
// 且解析后统一为 UTC RFC3339，验证与水位线比较同口径。
func TestInferCSVThenNormalizeDatetimeColumn(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "a.csv")
	content := "id,updated_at\n1,2026-10-20T18:00:00+08:00\n2,2026-10-20T10:00:00Z\n"
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	cols, err := InferCSV(p, "")
	if err != nil {
		t.Fatalf("推断 CSV 列类型失败: %v", err)
	}
	if len(cols) != 2 {
		t.Fatalf("列数错误：期望 2，实际 %d", len(cols))
	}
	if cols[0].Name != "id" || cols[0].Type != "INTEGER" {
		t.Fatalf("id 列推断错误：期望 INTEGER，实际 %s(%s)", cols[0].Type, cols[0].Name)
	}
	if cols[1].Name != "updated_at" || cols[1].Type != "DATETIME" {
		t.Fatalf("updated_at 列推断错误：期望 DATETIME，实际 %s(%s)", cols[1].Type, cols[1].Name)
	}
	v, err := ParseValue("2026-10-20T18:00:00+08:00", "DATETIME")
	if err != nil {
		t.Fatalf("解析 DATETIME 失败: %v", err)
	}
	s, ok := v.(string)
	if !ok {
		t.Fatalf("DATETIME 解析结果应为字符串，实际 %T", v)
	}
	if s != "2026-10-20T10:00:00Z" {
		t.Fatalf("DATETIME 解析应统一为 UTC RFC3339：期望 %q，实际 %q", "2026-10-20T10:00:00Z", s)
	}
}

// TestIsDateTimeConsistentWithNormalize 验证 IsDateTime 与 NormalizeComparable 同口径：
// 可解析的时区写法返回 true，无冒号偏移返回 false。
func TestIsDateTimeConsistentWithNormalize(t *testing.T) {
	if !IsDateTime("2026-10-20T18:00:00+08:00") {
		t.Fatalf("带冒号偏移应可解析为日期时间")
	}
	if !IsDateTime("2026-10-20T10:00:00Z") {
		t.Fatalf("UTC 写法应可解析为日期时间")
	}
	if !IsDateTime("2026-10-20T15:30:00+05:30") {
		t.Fatalf("半小时偏移应可解析为日期时间")
	}
	if IsDateTime("2026-10-20T18:00:00+0800") {
		t.Fatalf("无冒号偏移不应被解析为日期时间（与 NormalizeComparable 同口径）")
	}
}