package connector

import (
	"testing"
)

// 本文件测试 infer 包内与水位线增量比较相关的语义。
// 依据题目约定：matchSince 针对多列 since，每列独立判定，任一列不满足即 false，
// 空水位列跳过；行缺列（nil）按空值放行；未知列名视同行无该列，按空值放行。

// TestMatchSinceTwoColumnsBothSatisfied 在测：两列水位线都满足时返回 true。
func TestMatchSinceTwoColumnsBothSatisfied(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
		"created_at": "2024-01-02 00:00:00",
	}
	since := map[string]string{
		"updated_at": "2024-01-01 00:00:00",
		"created_at": "2024-01-01 00:00:00",
	}
	if !matchSince(row, since) {
		t.Fatalf("两列均满足水位线时应返回 true，实际 false")
	}
}

// TestMatchSinceOneColumnNotSatisfied 在测：任一列不满足即整体返回 false。
func TestMatchSinceOneColumnNotSatisfied(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
		"created_at": "2023-12-31 00:00:00",
	}
	since := map[string]string{
		"updated_at": "2024-01-01 00:00:00",
		"created_at": "2024-01-01 00:00:00",
	}
	if matchSince(row, since) {
		t.Fatalf("created_at 未达到水位线时应返回 false，实际 true")
	}
}

// TestMatchSinceEmptyWatermarkColumnSkipped 在测：某列水位线为空串时跳过该列，仅看另一列。
func TestMatchSinceEmptyWatermarkColumnSkipped(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
		"created_at": "2023-12-31 00:00:00",
	}
	since := map[string]string{
		"updated_at": "2024-01-01 00:00:00",
		"created_at": "",
	}
	if !matchSince(row, since) {
		t.Fatalf("空水位列应被跳过，仅 updated_at 满足时应返回 true，实际 false")
	}
}

// TestMatchSinceMissingColumnTreatedAsEmpty 在测：行缺少某列（nil）时该列按空值放行。
func TestMatchSinceMissingColumnTreatedAsEmpty(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
	}
	since := map[string]string{
		"updated_at": "2024-01-01 00:00:00",
		"created_at": "2024-01-01 00:00:00",
	}
	if !matchSince(row, since) {
		t.Fatalf("行缺少 created_at 时应按空值放行，整体应返回 true，实际 false")
	}
}

// TestMatchSinceMixedThreeColumns 在测：三列混合日期/文本/空时的独立判定。
// updated_at 为日期且满足，note 为文本且满足，extra 水位线为空跳过。
func TestMatchSinceMixedThreeColumns(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
		"note":       "b",
		"extra":      "zzz",
	}
	since := map[string]string{
		"updated_at": "2024-01-01 00:00:00",
		"note":       "a",
		"extra":      "",
	}
	if !matchSince(row, since) {
		t.Fatalf("三列混合场景（空列跳过、其余满足）应返回 true，实际 false")
	}
}

// TestMatchSinceUnknownColumnTreatedAsEmpty 在测：since 含未知列名时，行无该列，
// 按空值放行，不影响其余列的判定结果。
func TestMatchSinceUnknownColumnTreatedAsEmpty(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
	}
	since := map[string]string{
		"updated_at":   "2024-01-01 00:00:00",
		"unknown_col":  "2024-01-01 00:00:00",
	}
	if !matchSince(row, since) {
		t.Fatalf("未知列应视同行无该列并按空值放行，整体应返回 true，实际 false")
	}
}

// TestMatchSinceUnknownColumnNotBlocking 在测：未知列不满足也不应阻塞，
// 因为行无该列时按空值放行。
func TestMatchSinceUnknownColumnNotBlocking(t *testing.T) {
	row := map[string]any{
		"updated_at": "2024-01-02 00:00:00",
	}
	since := map[string]string{
		"updated_at":  "2024-01-01 00:00:00",
		"not_present": "2999-01-01 00:00:00",
	}
	if !matchSince(row, since) {
		t.Fatalf("未知列名对应行无该列，应按空值放行，整体应返回 true，实际 false")
	}
}

