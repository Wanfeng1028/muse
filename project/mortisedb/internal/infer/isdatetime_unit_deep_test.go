package infer

import (
	"strings"
	"testing"
	"time"
)

// TestIsDateTime 用表驱动方式验证 IsDateTime 与 parseDatetime 的口径一致性：
// 7 种合法布局各给 2 例（含时区偏移、前后空格），以及一批非法值应返回 false。
func TestIsDateTimeUnit(t *testing.T) {
	valid := []struct {
		name string
		in   string
	}{
		// RFC3339（含时区偏移）
		{"rfc3339_utc", "2026-10-20T12:34:56Z"},
		{"rfc3339_offset", "2026-10-20T12:34:56+08:00"},
		// "2006-01-02 15:04:05"
		{"space_seconds", "2026-10-20 12:34:56"},
		{"space_seconds_trim", "  2026-10-20 12:34:56  "},
		// "2006-01-02T15:04:05"
		{"t_seconds", "2026-10-20T12:34:56"},
		{"t_seconds_trim", " 2026-10-20T12:34:56 "},
		// "2006-01-02 15:04"
		{"space_minutes", "2026-10-20 12:34"},
		{"space_minutes_trim", "\t2026-10-20 12:34\t"},
		// "2006-01-02"
		{"date_only", "2026-10-20"},
		{"date_only_trim", " 2026-10-20 "},
		// "2006/01/02"
		{"slash_date", "2026/10/20"},
		{"slash_date_trim", "  2026/10/20   "},
		// "2006/01/02 15:04:05"
		{"slash_seconds", "2026/10/20 12:34:56"},
		{"slash_seconds_trim", " 2026/10/20 12:34:56 "},
	}

	for _, tc := range valid {
		tc := tc
		t.Run("valid_"+tc.name, func(t *testing.T) {
			if !IsDateTime(tc.in) {
				t.Fatalf("IsDateTime(%q) 期望 true，实际 false", tc.in)
			}
			// 与 parseDatetime 同口径：能解析就必须能得到无错误的时间
			if _, err := parseDatetime(tc.in); err != nil {
				t.Fatalf("parseDatetime(%q) 期望无错误，实际 %v", tc.in, err)
			}
		})
	}

	invalid := []struct {
		name string
		in   string
	}{
		{"empty", ""},
		{"spaces_only", "   "},
		{"tab_only", "\t\t"},
		{"not_a_date", "not-a-date"},
		{"bad_month", "2026-13-01"},
		{"bad_day", "2026-02-30"},
		{"bad_hour", "2026-10-20T25:00:00Z"},
		{"time_only", "12:00:00"},
		{"digits_only", "20261020"},
		{"chinese_today", "今天"},
	}

	for _, tc := range invalid {
		tc := tc
		t.Run("invalid_"+tc.name, func(t *testing.T) {
			if IsDateTime(tc.in) {
				t.Fatalf("IsDateTime(%q) 期望 false，实际 true", tc.in)
			}
			if _, err := parseDatetime(tc.in); err == nil {
				t.Fatalf("parseDatetime(%q) 期望报错，实际无错误", tc.in)
			}
		})
	}
}

// TestNormalizeComparable 验证 NormalizeComparable 的规范化口径：
// 可解析日期统一转 RFC3339（长度 20，含 'T'，以 'Z' 或时区偏移结尾）；
// 不可解析的值必须原样返回。
func TestNormalizeComparable(t *testing.T) {
	parsable := []struct {
		name string
		in   string
	}{
		{"rfc3339_utc", "2026-10-20T12:34:56Z"},
		{"rfc3339_offset", "2026-10-20T12:34:56+08:00"},
		{"space_seconds", "2026-10-20 12:34:56"},
		{"space_seconds_trim", "  2026-10-20 12:34:56  "},
		{"t_seconds", "2026-10-20T12:34:56"},
		{"t_seconds_trim", " 2026-10-20T12:34:56 "},
		{"space_minutes", "2026-10-20 12:34"},
		{"space_minutes_trim", "\t2026-10-20 12:34\t"},
		{"date_only", "2026-10-20"},
		{"date_only_trim", " 2026-10-20 "},
		{"slash_date", "2026/10/20"},
		{"slash_date_trim", "  2026/10/20   "},
		{"slash_seconds", "2026/10/20 12:34:56"},
		{"slash_seconds_trim", " 2026/10/20 12:34:56 "},
	}

	for _, tc := range parsable {
		tc := tc
		t.Run("parsable_"+tc.name, func(t *testing.T) {
			if !IsDateTime(tc.in) {
				t.Fatalf("前置条件失败：IsDateTime(%q) 期望 true", tc.in)
			}
			got := NormalizeComparable(tc.in)
			if len(got) != 20 {
				t.Fatalf("NormalizeComparable(%q) 长度期望 20，实际 %d，值 %q", tc.in, len(got), got)
			}
			if !strings.Contains(got, "T") {
				t.Fatalf("NormalizeComparable(%q) 期望包含 'T'，实际 %q", tc.in, got)
			}
			// 统一转 UTC，因此应以 'Z' 结尾（RFC3339 的 UTC 形式）
			if !strings.HasSuffix(got, "Z") {
				t.Fatalf("NormalizeComparable(%q) 期望以 'Z' 结尾，实际 %q", tc.in, got)
			}
			// 必须能被 time.RFC3339 反解析
			if _, err := time.Parse(time.RFC3339, got); err != nil {
				t.Fatalf("NormalizeComparable(%q)=%q 不是合法 RFC3339: %v", tc.in, got, err)
			}
		})
	}

	nonParsable := []struct {
		name string
		in   string
	}{
		{"empty", ""},
		{"spaces_only", "   "},
		{"tab_only", "\t\t"},
		{"not_a_date", "not-a-date"},
		{"bad_month", "2026-13-01"},
		{"bad_day", "2026-02-30"},
		{"bad_hour", "2026-10-20T25:00:00Z"},
		{"time_only", "12:00:00"},
		{"digits_only", "20261020"},
		{"chinese_today", "今天"},
	}

	for _, tc := range nonParsable {
		tc := tc
		t.Run("nonparsable_"+tc.name, func(t *testing.T) {
			if IsDateTime(tc.in) {
				t.Fatalf("前置条件失败：IsDateTime(%q) 期望 false", tc.in)
			}
			got := NormalizeComparable(tc.in)
			if got != tc.in {
				t.Fatalf("NormalizeComparable(%q) 期望原样返回 %q，实际 %q", tc.in, tc.in, got)
			}
		})
	}
}

// TestIsDateTimeAndNormalizeComparableAgree 验证两者口径一致性：
// IsDateTime 为 true 的输入，NormalizeComparable 必返回 RFC3339 形态
// （长度 20，含 'T'，以 'Z' 或时区偏移结尾，且可被 time.RFC3339 解析）。
func TestIsDateTimeAndNormalizeComparableAgree(t *testing.T) {
	inputs := []string{
		"2026-10-20T12:34:56Z",
		"2026-10-20T12:34:56+08:00",
		"2026-10-20T12:34:56-05:00",
		"2026-10-20 12:34:56",
		"  2026-10-20 12:34:56  ",
		"2026-10-20T12:34:56",
		" 2026-10-20T12:34:56 ",
		"2026-10-20 12:34",
		"\t2026-10-20 12:34\t",
		"2026-10-20",
		" 2026-10-20 ",
		"2026/10/20",
		"  2026/10/20   ",
		"2026/10/20 12:34:56",
		" 2026/10/20 12:34:56 ",
		// 非法输入一并参与，验证"为 false 时原样返回"
		"",
		"   ",
		"not-a-date",
		"2026-13-01",
		"2026-02-30",
		"2026-10-20T25:00:00Z",
		"12:00:00",
		"20261020",
		"今天",
	}

	for _, in := range inputs {
		in := in
		t.Run(in, func(t *testing.T) {
			ok := IsDateTime(in)
			got := NormalizeComparable(in)
			if ok {
				if len(got) != 20 {
					t.Fatalf("IsDateTime(%q)=true，NormalizeComparable 长度期望 20，实际 %d，值 %q", in, len(got), got)
				}
				if !strings.Contains(got, "T") {
					t.Fatalf("IsDateTime(%q)=true，NormalizeComparable 期望含 'T'，实际 %q", in, got)
				}
				if !strings.HasSuffix(got, "Z") && !strings.ContainsAny(got[19:], "+-") {
					t.Fatalf("IsDateTime(%q)=true，NormalizeComparable 期望以 'Z' 或时区偏移结尾，实际 %q", in, got)
				}
				if _, err := time.Parse(time.RFC3339, got); err != nil {
					t.Fatalf("IsDateTime(%q)=true，NormalizeComparable=%q 不是合法 RFC3339: %v", in, got, err)
				}
			} else {
				if got != in {
					t.Fatalf("IsDateTime(%q)=false，NormalizeComparable 期望原样返回 %q，实际 %q", in, in, got)
				}
			}
		})
	}
}

// TestParseDatetimeLayouts 直接验证 parseDatetime 对 7 种布局的解析结果，
// 确保与 IsDateTime 使用同一套布局。
func TestParseDatetimeLayouts(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want time.Time
	}{
		{"rfc3339_utc", "2026-10-20T12:34:56Z", time.Date(2026, 10, 20, 12, 34, 56, 0, time.UTC)},
		{"rfc3339_offset", "2026-10-20T12:34:56+08:00", time.Date(2026, 10, 20, 12, 34, 56, 0, time.FixedZone("", 8*3600))},
		{"space_seconds", "2026-10-20 12:34:56", time.Date(2026, 10, 20, 12, 34, 56, 0, time.UTC)},
		{"t_seconds", "2026-10-20T12:34:56", time.Date(2026, 10, 20, 12, 34, 56, 0, time.UTC)},
		{"space_minutes", "2026-10-20 12:34", time.Date(2026, 10, 20, 12, 34, 0, 0, time.UTC)},
		{"date_only", "2026-10-20", time.Date(2026, 10, 20, 0, 0, 0, 0, time.UTC)},
		{"slash_date", "2026/10/20", time.Date(2026, 10, 20, 0, 0, 0, 0, time.UTC)},
		{"slash_seconds", "2026/10/20 12:34:56", time.Date(2026, 10, 20, 12, 34, 56, 0, time.UTC)},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got, err := parseDatetime(tc.in)
			if err != nil {
				t.Fatalf("parseDatetime(%q) 期望无错误，实际 %v", tc.in, err)
			}
			if !got.Equal(tc.want) {
				t.Fatalf("parseDatetime(%q) 期望 %v，实际 %v", tc.in, tc.want, got)
			}
		})
	}
}
