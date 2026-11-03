package infer

import (
	"testing"
)

// 测试 detectType 对空值的处理：空值返回空字符串，不参与推断。
func TestDetectTypeEmpty(t *testing.T) {
	if got := detectType(""); got != "" {
		t.Fatalf("空字符串期望返回空，实际 %q", got)
	}
	if got := detectType("   "); got != "" {
		t.Fatalf("空白字符串期望返回空，实际 %q", got)
	}
}

// 测试 detectType 对 BOOLEAN 的识别：true/false/1/0/是/否。
func TestDetectTypeBoolean(t *testing.T) {
	cases := []string{"true", "false", "TRUE", "FALSE", "1", "0", "是", "否"}
	for _, c := range cases {
		if got := detectType(c); got != "BOOLEAN" {
			t.Fatalf("detectType(%q) 期望 BOOLEAN，实际 %q", c, got)
		}
	}
}

// 测试 detectType 对 INTEGER 与 REAL 的区分。
func TestDetectTypeNumeric(t *testing.T) {
	if got := detectType("42"); got != "INTEGER" {
		t.Fatalf("detectType(\"42\") 期望 INTEGER，实际 %q", got)
	}
	if got := detectType("3.14"); got != "REAL" {
		t.Fatalf("detectType(\"3.14\") 期望 REAL，实际 %q", got)
	}
	if got := detectType("-7"); got != "INTEGER" {
		t.Fatalf("detectType(\"-7\") 期望 INTEGER，实际 %q", got)
	}
}

// 测试 detectType 对 DATETIME 的识别，覆盖多种布局。
func TestDetectTypeDatetime(t *testing.T) {
	cases := []string{
		"2024-01-02",
		"2024-01-02 03:04:05",
		"2024-01-02T03:04:05",
		"2024-01-02 03:04",
		"2024/01/02",
		"2024/01/02 03:04:05",
		"2024-01-02T03:04:05Z",
	}
	for _, c := range cases {
		if got := detectType(c); got != "DATETIME" {
			t.Fatalf("detectType(%q) 期望 DATETIME，实际 %q", c, got)
		}
	}
}

// 测试 detectType 对普通文本返回 TEXT。
func TestDetectTypeText(t *testing.T) {
	if got := detectType("hello"); got != "TEXT" {
		t.Fatalf("detectType(\"hello\") 期望 TEXT，实际 %q", got)
	}
}

// 测试 detectJSONType 对 JSON 原生值的推断。
func TestDetectJSONType(t *testing.T) {
	if got := detectJSONType(nil); got != "" {
		t.Fatalf("nil 期望空，实际 %q", got)
	}
	if got := detectJSONType(true); got != "BOOLEAN" {
		t.Fatalf("bool 期望 BOOLEAN，实际 %q", got)
	}
	if got := detectJSONType(float64(1)); got != "INTEGER" {
		t.Fatalf("整数值 float64 期望 INTEGER，实际 %q", got)
	}
	if got := detectJSONType(float64(1.5)); got != "REAL" {
		t.Fatalf("非整数值 float64 期望 REAL，实际 %q", got)
	}
	if got := detectJSONType("2024-01-02"); got != "DATETIME" {
		t.Fatalf("日期字符串期望 DATETIME，实际 %q", got)
	}
	// 嵌套对象转 JSON 字符串后视为 TEXT
	if got := detectJSONType(map[string]any{"a": 1}); got != "TEXT" {
		t.Fatalf("嵌套对象期望 TEXT，实际 %q", got)
	}
}

// 测试 UnifyTypes 的类型提升规则。
func TestUnifyTypesIdempotent(t *testing.T) {
	if got := UnifyTypes(nil); got != "TEXT" {
		t.Fatalf("空切片期望 TEXT，实际 %q", got)
	}
	if got := UnifyTypes([]string{"", ""}); got != "TEXT" {
		t.Fatalf("全空值期望 TEXT，实际 %q", got)
	}
	if got := UnifyTypes([]string{"INTEGER", "REAL"}); got != "REAL" {
		t.Fatalf("INTEGER+REAL 期望 REAL，实际 %q", got)
	}
	if got := UnifyTypes([]string{"INTEGER", "BOOLEAN"}); got != "INTEGER" {
		t.Fatalf("INTEGER+BOOLEAN 期望 INTEGER，实际 %q", got)
	}
	if got := UnifyTypes([]string{"BOOLEAN"}); got != "BOOLEAN" {
		t.Fatalf("BOOLEAN 期望 BOOLEAN，实际 %q", got)
	}
	if got := UnifyTypes([]string{"INTEGER", "TEXT"}); got != "TEXT" {
		t.Fatalf("出现 TEXT 期望 TEXT，实际 %q", got)
	}
	if got := UnifyTypes([]string{"DATETIME", "DATETIME"}); got != "DATETIME" {
		t.Fatalf("全 DATETIME 期望 DATETIME，实际 %q", got)
	}
	if got := UnifyTypes([]string{"DATETIME", "INTEGER"}); got != "TEXT" {
		t.Fatalf("DATETIME+INTEGER 期望 TEXT，实际 %q", got)
	}
}

// 测试 ParseValue 对各目标类型的解析。
func TestParseValueIdem(t *testing.T) {
	if v, err := ParseValue("", "INTEGER"); err != nil || v != nil {
		t.Fatalf("空串期望 nil,nil，实际 %v,%v", v, err)
	}
	v, err := ParseValue("42", "INTEGER")
	if err != nil {
		t.Fatalf("解析 INTEGER 失败: %v", err)
	}
	if iv, ok := v.(int64); !ok || iv != 42 {
		t.Fatalf("INTEGER 期望 int64(42)，实际 %T %v", v, v)
	}
	v, err = ParseValue("3.5", "REAL")
	if err != nil {
		t.Fatalf("解析 REAL 失败: %v", err)
	}
	if fv, ok := v.(float64); !ok || fv != 3.5 {
		t.Fatalf("REAL 期望 float64(3.5)，实际 %T %v", v, v)
	}
	v, err = ParseValue("是", "BOOLEAN")
	if err != nil {
		t.Fatalf("解析 BOOLEAN 失败: %v", err)
	}
	if iv, ok := v.(int64); !ok || iv != 1 {
		t.Fatalf("BOOLEAN 是 期望 int64(1)，实际 %T %v", v, v)
	}
	v, err = ParseValue("否", "BOOLEAN")
	if err != nil {
		t.Fatalf("解析 BOOLEAN 失败: %v", err)
	}
	if iv, ok := v.(int64); !ok || iv != 0 {
		t.Fatalf("BOOLEAN 否 期望 int64(0)，实际 %T %v", v, v)
	}
	v, err = ParseValue("hello", "TEXT")
	if err != nil {
		t.Fatalf("解析 TEXT 失败: %v", err)
	}
	if sv, ok := v.(string); !ok || sv != "hello" {
		t.Fatalf("TEXT 期望 hello，实际 %T %v", v, v)
	}
}

// 测试 ParseValue 对 BOOLEAN 非法值返回错误。
func TestParseValueBooleanInvalid(t *testing.T) {
	if _, err := ParseValue("maybe", "BOOLEAN"); err == nil {
		t.Fatalf("非法 BOOLEAN 期望报错，实际返回 nil")
	}
}

// 测试 ParseValue 对 DATETIME 的解析统一为 RFC3339 UTC 字符串。
func TestParseValueDatetime(t *testing.T) {
	v, err := ParseValue("2024-01-02 03:04:05", "DATETIME")
	if err != nil {
		t.Fatalf("解析 DATETIME 失败: %v", err)
	}
	sv, ok := v.(string)
	if !ok {
		t.Fatalf("DATETIME 期望字符串，实际 %T", v)
	}
	if sv != "2024-01-02T03:04:05Z" {
		t.Fatalf("DATETIME 期望 RFC3339 UTC，实际 %q", sv)
	}
}

// 测试 IsDateTime 与 NormalizeComparable 的语义：可解析日期归一化为 RFC3339，不可解析原样返回。
func TestIsDateTimeAndNormalize(t *testing.T) {
	if !IsDateTime("2024-01-02") {
		t.Fatalf("2024-01-02 应可解析为日期时间")
	}
	if IsDateTime("hello") {
		t.Fatalf("hello 不应解析为日期时间")
	}
	if got := NormalizeComparable("2024-01-02 03:04:05"); got != "2024-01-02T03:04:05Z" {
		t.Fatalf("NormalizeComparable 期望 RFC3339，实际 %q", got)
	}
	if got := NormalizeComparable("hello"); got != "hello" {
		t.Fatalf("不可解析值应原样返回，实际 %q", got)
	}
}

// 测试 SQLiteType 的类型映射：BOOLEAN→INTEGER，其余直映，未知→TEXT。
func TestSQLiteTypeIdem(t *testing.T) {
	if got := SQLiteType("BOOLEAN"); got != "INTEGER" {
		t.Fatalf("BOOLEAN 期望 INTEGER，实际 %q", got)
	}
	if got := SQLiteType("INTEGER"); got != "INTEGER" {
		t.Fatalf("INTEGER 期望 INTEGER，实际 %q", got)
	}
	if got := SQLiteType("REAL"); got != "REAL" {
		t.Fatalf("REAL 期望 REAL，实际 %q", got)
	}
	if got := SQLiteType("TEXT"); got != "TEXT" {
		t.Fatalf("TEXT 期望 TEXT，实际 %q", got)
	}
	if got := SQLiteType("DATETIME"); got != "DATETIME" {
		t.Fatalf("DATETIME 期望 DATETIME，实际 %q", got)
	}
	if got := SQLiteType("UNKNOWN"); got != "TEXT" {
		t.Fatalf("未知类型期望 TEXT，实际 %q", got)
	}
}

// 测试 Stringify 对各类值的字符串化。
func TestStringifyIdem(t *testing.T) {
	if got := Stringify(nil); got != "" {
		t.Fatalf("nil 期望空串，实际 %q", got)
	}
	if got := Stringify("abc"); got != "abc" {
		t.Fatalf("字符串期望 abc，实际 %q", got)
	}
	if got := Stringify([]byte("xyz")); got != "xyz" {
		t.Fatalf("字节切片期望 xyz，实际 %q", got)
	}
	if got := Stringify(int64(7)); got != "7" {
		t.Fatalf("int64 期望 7，实际 %q", got)
	}
}