package infer

import (
	"os"
	"path/filepath"
	"testing"
)

// TestParseValueDateTimeIsDateTime 验证 ParseValue 与 IsDateTime 对同一批日期字面量的判定口径一致：
// 能被 ParseValue("DATETIME") 成功解析的字符串，IsDateTime 也必须为 true，反之亦然。
func TestParseValueDateTimeIsDateTime(t *testing.T) {
	inputs := []string{
		"2006-01-02T15:04:05Z",
		"2006-01-02 15:04:05",
		"2006-01-02T15:04:05",
		"2006-01-02 15:04",
		"2006-01-02",
		"2006/01/02",
		"2006/01/02 15:04:05",
	}
	for _, s := range inputs {
		v, err := ParseValue(s, "DATETIME")
		if err != nil {
			t.Fatalf("ParseValue(%q, DATETIME) 期望成功，实际报错: %v", s, err)
		}
		if v == nil {
			t.Fatalf("ParseValue(%q, DATETIME) 期望非 nil", s)
		}
		if !IsDateTime(s) {
			t.Fatalf("IsDateTime(%q) 期望 true", s)
		}
	}

	bad := []string{"", "not-a-date", "2006-13-40", "abcd", "12:00:00"}
	for _, s := range bad {
		if IsDateTime(s) {
			t.Fatalf("IsDateTime(%q) 期望 false", s)
		}
	}
}


// TestUnifyTypes 验证类型提升规则：INTEGER+REAL→REAL；出现 TEXT→TEXT；
// BOOLEAN+INTEGER→INTEGER；DATETIME 仅当全部为日期才保留；空→TEXT。
func TestUnifyTypesTextFallback(t *testing.T) {
	cases := []struct {
		name string
		in   []string
		want string
	}{
		{"空切片", []string{}, "TEXT"},
		{"全空值", []string{"", ""}, "TEXT"},
		{"整数", []string{"INTEGER", "INTEGER"}, "INTEGER"},
		{"整数加实数", []string{"INTEGER", "REAL"}, "REAL"},
		{"布尔加整数", []string{"BOOLEAN", "INTEGER"}, "INTEGER"},
		{"布尔单独", []string{"BOOLEAN"}, "BOOLEAN"},
		{"混入文本", []string{"INTEGER", "TEXT"}, "TEXT"},
		{"全日期", []string{"DATETIME", "DATETIME"}, "DATETIME"},
		{"日期混整数", []string{"DATETIME", "INTEGER"}, "TEXT"},
		{"日期混实数", []string{"DATETIME", "REAL"}, "TEXT"},
		{"日期混布尔", []string{"DATETIME", "BOOLEAN"}, "TEXT"},
		{"空值加整数", []string{"", "INTEGER"}, "INTEGER"},
	}
	for _, c := range cases {
		got := UnifyTypes(c.in)
		if got != c.want {
			t.Fatalf("%s: UnifyTypes(%v) 期望 %q，实际 %q", c.name, c.in, c.want, got)
		}
	}
}

// TestParseValue 验证各目标类型的解析语义：
// 空串返回 nil；BOOLEAN 接受 true/false/1/0/是/否；DATETIME 统一转 RFC3339 UTC 字符串。
func TestParseValueTextFb(t *testing.T) {
	// 空串返回 nil
	for _, typ := range []string{"INTEGER", "REAL", "BOOLEAN", "DATETIME", "TEXT"} {
		v, err := ParseValue("", typ)
		if err != nil {
			t.Fatalf("ParseValue(\"\", %s) 期望无错，实际 %v", typ, err)
		}
		if v != nil {
			t.Fatalf("ParseValue(\"\", %s) 期望 nil，实际 %v", typ, v)
		}
	}

	// INTEGER
	if v, err := ParseValue("42", "INTEGER"); err != nil {
		t.Fatalf("ParseValue(42, INTEGER) 期望无错，实际 %v", err)
	} else if got, ok := v.(int64); !ok || got != 42 {
		t.Fatalf("ParseValue(42, INTEGER) 期望 int64(42)，实际 %#v", v)
	}
	if _, err := ParseValue("not-int", "INTEGER"); err == nil {
		t.Fatalf("ParseValue(not-int, INTEGER) 期望报错")
	}

	// REAL
	if v, err := ParseValue("3.5", "REAL"); err != nil {
		t.Fatalf("ParseValue(3.5, REAL) 期望无错，实际 %v", err)
	} else if got, ok := v.(float64); !ok || got != 3.5 {
		t.Fatalf("ParseValue(3.5, REAL) 期望 float64(3.5)，实际 %#v", v)
	}

	// BOOLEAN 的六种可接受写法
	trueForms := []string{"true", "TRUE", "1", "是"}
	for _, s := range trueForms {
		v, err := ParseValue(s, "BOOLEAN")
		if err != nil {
			t.Fatalf("ParseValue(%q, BOOLEAN) 期望无错，实际 %v", s, err)
		}
		if got, ok := v.(int64); !ok || got != 1 {
			t.Fatalf("ParseValue(%q, BOOLEAN) 期望 int64(1)，实际 %#v", s, v)
		}
	}
	falseForms := []string{"false", "FALSE", "0", "否"}
	for _, s := range falseForms {
		v, err := ParseValue(s, "BOOLEAN")
		if err != nil {
			t.Fatalf("ParseValue(%q, BOOLEAN) 期望无错，实际 %v", s, err)
		}
		if got, ok := v.(int64); !ok || got != 0 {
			t.Fatalf("ParseValue(%q, BOOLEAN) 期望 int64(0)，实际 %#v", s, v)
		}
	}
	if _, err := ParseValue("maybe", "BOOLEAN"); err == nil {
		t.Fatalf("ParseValue(maybe, BOOLEAN) 期望报错")
	}

	// DATETIME 统一转 RFC3339 UTC
	v, err := ParseValue("2024-01-02 03:04:05", "DATETIME")
	if err != nil {
		t.Fatalf("ParseValue(DATETIME) 期望无错，实际 %v", err)
	}
	if got, ok := v.(string); !ok || got != "2024-01-02T03:04:05Z" {
		t.Fatalf("ParseValue(DATETIME) 期望 %q，实际 %#v", "2024-01-02T03:04:05Z", v)
	}
	if _, err := ParseValue("not-a-date", "DATETIME"); err == nil {
		t.Fatalf("ParseValue(not-a-date, DATETIME) 期望报错")
	}

	// TEXT 原样返回
	if v, err := ParseValue("hello", "TEXT"); err != nil {
		t.Fatalf("ParseValue(hello, TEXT) 期望无错，实际 %v", err)
	} else if got, ok := v.(string); !ok || got != "hello" {
		t.Fatalf("ParseValue(hello, TEXT) 期望 %q，实际 %#v", "hello", v)
	}
}

// TestSQLiteType 验证推断类型到 SQLite 列类型的映射：BOOLEAN→INTEGER，其余直映，未知→TEXT。
func TestSQLiteTypeTextFb(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"BOOLEAN", "INTEGER"},
		{"INTEGER", "INTEGER"},
		{"REAL", "REAL"},
		{"TEXT", "TEXT"},
		{"DATETIME", "DATETIME"},
		{"", "TEXT"},
		{"UNKNOWN", "TEXT"},
	}
	for _, c := range cases {
		if got := SQLiteType(c.in); got != c.want {
			t.Fatalf("SQLiteType(%q) 期望 %q，实际 %q", c.in, c.want, got)
		}
	}
}

// TestStringify 验证任意值转字符串：nil→空串，string 原样，[]byte 转字符串，其余走 fmt。
func TestStringifyTextFb(t *testing.T) {
	if got := Stringify(nil); got != "" {
		t.Fatalf("Stringify(nil) 期望空串，实际 %q", got)
	}
	if got := Stringify("abc"); got != "abc" {
		t.Fatalf("Stringify(abc) 期望 %q，实际 %q", "abc", got)
	}
	if got := Stringify([]byte("bytes")); got != "bytes" {
		t.Fatalf("Stringify([]byte) 期望 %q，实际 %q", "bytes", got)
	}
	if got := Stringify(int64(7)); got != "7" {
		t.Fatalf("Stringify(int64(7)) 期望 %q，实际 %q", "7", got)
	}
}
// TestDetectTypeAndDetectJSONType 验证单值类型探测：
// 布尔字面量、整数、实数、日期、文本，以及 JSON 原生值的映射。
func TestDetectTypeAndDetectJSONType(t *testing.T) {
	typeCases := []struct {
		in   string
		want string
	}{
		{"", ""},
		{"   ", ""},
		{"true", "BOOLEAN"},
		{"FALSE", "BOOLEAN"},
		{"1", "BOOLEAN"},
		{"0", "BOOLEAN"},
		{"是", "BOOLEAN"},
		{"否", "BOOLEAN"},
		{"123", "INTEGER"},
		{"-45", "INTEGER"},
		{"1.5", "REAL"},
		{"2024-01-02", "DATETIME"},
		{"2024-01-02 03:04:05", "DATETIME"},
		{"hello", "TEXT"},
	}
	for _, c := range typeCases {
		if got := detectType(c.in); got != c.want {
			t.Fatalf("detectType(%q) 期望 %q，实际 %q", c.in, c.want, got)
		}
	}

	jsonCases := []struct {
		name string
		in   any
		want string
	}{
		{"nil", nil, ""},
		{"bool", true, "BOOLEAN"},
		{"整数值浮点", float64(3), "INTEGER"},
		{"小数浮点", 1.5, "REAL"},
		{"字符串", "hello", "TEXT"},
		{"字符串整数", "42", "INTEGER"},
		{"嵌套对象", map[string]any{"a": 1}, "TEXT"},
		{"嵌套数组", []any{1, 2}, "TEXT"},
	}
	for _, c := range jsonCases {
		if got := detectJSONType(c.in); got != c.want {
			t.Fatalf("%s: detectJSONType(%#v) 期望 %q，实际 %q", c.name, c.in, c.want, got)
		}
	}
}

// TestInferCSVSampleLimit 验证采样上限为 500 行：第 501 行的值不参与类型推断。
func TestInferCSVSampleLimit(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "limit.csv")

	// 前 500 行为整数，第 501 行为文本；若采样上限生效，则列类型仍为 INTEGER。
	var sb []byte
	sb = append(sb, []byte("v\n")...)
	for i := 0; i < 500; i++ {
		sb = append(sb, []byte("123\n")...)
	}
	sb = append(sb, []byte("text\n")...)
	if err := os.WriteFile(path, sb, 0o644); err != nil {
		t.Fatalf("写入采样上限 CSV 失败: %v", err)
	}
	cols, err := InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 期望无错，实际 %v", err)
	}
	if len(cols) != 1 {
		t.Fatalf("列数期望 1，实际 %d", len(cols))
	}
	if cols[0].Type != "INTEGER" {
		t.Fatalf("采样上限为 500，第 501 行文本不应参与推断，期望 INTEGER，实际 %q", cols[0].Type)
	}
}

// TestStringifyViaFile 通过临时文件确保 filepath 与 os 在真实路径场景下可用，
// 并复核 InferCSV 返回的列名与文件表头逐字一致。
func TestStringifyViaFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "header.csv")
	if err := os.WriteFile(path, []byte("col_a,col_b\n1,2\n"), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	cols, err := InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 期望无错，实际 %v", err)
	}
	if len(cols) != 2 {
		t.Fatalf("列数期望 2，实际 %d", len(cols))
	}
	if cols[0].Name != "col_a" || cols[1].Name != "col_b" {
		t.Fatalf("列名期望 [col_a col_b]，实际 [%s %s]", cols[0].Name, cols[1].Name)
	}
}