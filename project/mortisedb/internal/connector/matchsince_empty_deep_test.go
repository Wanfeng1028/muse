package connector

import (
	"testing"
)

// 在测什么：matchSince 在增量列值为空（空串或 nil）时按"未知时间=有变更"放行，
// 不静默丢行；非空值走规范化后比较，且 since 中水位线为空串的列跳过比较。

// TestMatchSinceEmptyMap：since 为空 map 时恒为 true，任何行都应放行。
func TestMatchSinceEmptyMap(t *testing.T) {
	row := Row{"id": int64(1), "updated_at": "2026-10-20 11:00:00"}
	if !matchSince(row, map[string]string{}) {
		t.Fatalf("since 为空 map 时应恒为 true，实际为 false")
	}
}

// TestMatchSinceEmptyWatermarkSkipsColumn：since 中某列水位线为空串时跳过该列比较，返回 true。
func TestMatchSinceEmptyWatermarkSkipsColumn(t *testing.T) {
	row := Row{"updated_at": "2026-10-20 11:00:00"}
	since := map[string]string{"updated_at": ""}
	if !matchSince(row, since) {
		t.Fatalf("水位线为空串时应跳过该列比较并返回 true，实际为 false")
	}
}

// TestMatchSinceRowValueEmptyString：行值为空串、水位线为日期时放行（未知时间=有变更）。
func TestMatchSinceRowValueEmptyString(t *testing.T) {
	row := Row{"updated_at": ""}
	since := map[string]string{"updated_at": "2026-10-20T10:00:00Z"}
	if !matchSince(row, since) {
		t.Fatalf("行值为空串时应放行返回 true，实际为 false")
	}
}

// TestMatchSinceRowValueNil：行值为 nil 时放行（未知时间=有变更）。
func TestMatchSinceRowValueNil(t *testing.T) {
	row := Row{"updated_at": nil}
	since := map[string]string{"updated_at": "2026-10-20T10:00:00Z"}
	if !matchSince(row, since) {
		t.Fatalf("行值为 nil 时应放行返回 true，实际为 false")
	}
}

// TestMatchSinceRowValueGreater：行值日期大于水位线（不同格式写法）应返回 true。
// "2026-10-20 11:00:00" 规范化后为 2026-10-20T11:00:00Z，晚于水位线 2026-10-20T10:00:00Z。
func TestMatchSinceRowValueGreater(t *testing.T) {
	row := Row{"updated_at": "2026-10-20 11:00:00"}
	since := map[string]string{"updated_at": "2026-10-20T10:00:00Z"}
	if !matchSince(row, since) {
		t.Fatalf("行值日期大于水位线时应返回 true，实际为 false")
	}
}

// TestMatchSinceRowValueEqualWithOffset：行值带时区偏移，规范化后等于水位线应返回 false。
// "2026-10-20T18:00:00+08:00" 等价于 2026-10-20T10:00:00Z，等于水位线。
func TestMatchSinceRowValueEqualWithOffset(t *testing.T) {
	row := Row{"updated_at": "2026-10-20T18:00:00+08:00"}
	since := map[string]string{"updated_at": "2026-10-20T10:00:00Z"}
	if matchSince(row, since) {
		t.Fatalf("行值规范化后等于水位线时应返回 false，实际为 true")
	}
}

// TestMatchSinceRowValueLessWithOffset：行值带时区偏移，规范化后小于水位线应返回 false。
// "2026-10-20T17:00:00+08:00" 等价于 2026-10-20T09:00:00Z，早于水位线。
func TestMatchSinceRowValueLessWithOffset(t *testing.T) {
	row := Row{"updated_at": "2026-10-20T17:00:00+08:00"}
	since := map[string]string{"updated_at": "2026-10-20T10:00:00Z"}
	if matchSince(row, since) {
		t.Fatalf("行值规范化后小于水位线时应返回 false，实际为 true")
	}
}

// TestMatchSincePlainText：纯文本列按字符串比较，大于水位线返回 true，小于返回 false。
func TestMatchSincePlainText(t *testing.T) {
	since := map[string]string{"name": "bravo"}
	if !matchSince(Row{"name": "zulu"}, since) {
		t.Fatalf("纯文本 \"zulu\" 大于水位线 \"bravo\" 时应返回 true，实际为 false")
	}
	if matchSince(Row{"name": "alpha"}, since) {
		t.Fatalf("纯文本 \"alpha\" 小于水位线 \"bravo\" 时应返回 false，实际为 true")
	}
}

// TestMatchSinceMultipleColumns：多列 since 时任一列不满足即 false；
// 空值列跳过不影响其他列判定。
func TestMatchSinceMultipleColumns(t *testing.T) {
	since := map[string]string{
		"updated_at": "2026-10-20T10:00:00Z",
		"name":       "bravo",
	}

	// 两列都满足：updated_at 更大且 name 更大 → true
	rowBoth := Row{"updated_at": "2026-10-20 11:00:00", "name": "zulu"}
	if !matchSince(rowBoth, since) {
		t.Fatalf("两列均满足时应返回 true，实际为 false")
	}

	// 一列不满足（name 更小）→ false
	rowOneFails := Row{"updated_at": "2026-10-20 11:00:00", "name": "alpha"}
	if matchSince(rowOneFails, since) {
		t.Fatalf("任一列不满足时应返回 false，实际为 true")
	}

	// 空值列跳过，仅按 updated_at 判定（更大）→ true
	rowSkipEmpty := Row{"updated_at": "2026-10-20 11:00:00", "name": ""}
	if !matchSince(rowSkipEmpty, since) {
		t.Fatalf("空值列跳过、其余列满足时应返回 true，实际为 false")
	}

	// 空值列跳过，仅按 updated_at 判定（更小）→ false
	rowSkipEmptyFail := Row{"updated_at": "2026-10-20 09:00:00", "name": ""}
	if matchSince(rowSkipEmptyFail, since) {
		t.Fatalf("空值列跳过、其余列不满足时应返回 false，实际为 true")
	}
}
