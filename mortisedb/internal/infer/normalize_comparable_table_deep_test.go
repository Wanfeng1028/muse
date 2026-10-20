package infer

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// TestNormalizeComparableLayouts 逐一核对 NormalizeComparable 对全部支持布局的
// 规范化行为：合法输入必须转成 RFC3339 UTC；非法输入必须原样返回。
func TestNormalizeComparableLayouts(t *testing.T) {
	cases := []struct {
		name string // 用例说明
		in   string // 输入
		want string // 期望输出
	}{
		// 合法：RFC3339 带 Z（已经是 UTC）
		{"RFC3339_Z", "2024-01-02T03:04:05Z", "2024-01-02T03:04:05Z"},
		// 合法：RFC3339 带偏移，应转成 UTC
		{"RFC3339_offset", "2024-01-02T03:04:05+08:00", "2024-01-01T19:04:05Z"},
		// 合法：无时区的 T 分隔
		{"no_zone_T", "2024-01-02T03:04:05", "2024-01-02T03:04:05Z"},
		// 合法：空格分隔
		{"space_sep", "2024-01-02 03:04:05", "2024-01-02T03:04:05Z"},
		// 合法：只有年月日
		{"date_only", "2024-01-02", "2024-01-02T00:00:00Z"},
		// 合法：斜杠分隔日期
		{"slash_date", "2024/01/02", "2024-01-02T00:00:00Z"},
		// 合法：斜杠分隔带时间
		{"slash_datetime", "2024/01/02 03:04:05", "2024-01-02T03:04:05Z"},
		// 合法：前后带空格（parseDatetime 内部 TrimSpace）
		{"padded", "  2024-01-02 03:04:05  ", "2024-01-02T03:04:05Z"},
		// 毫秒：Go 的 time.RFC3339 布局解析会接受小数秒并保留，
		// 格式化时 RFC3339 不带小数秒，故输出仍为整秒。
		{"millis_Z", "2024-01-02T03:04:05.000Z", "2024-01-02T03:04:05Z"},
		// 非法：原样返回
		{"invalid_text", "not-a-date", "not-a-date"},
		{"empty", "", ""},
		{"chinese", "中文", "中文"},
		{"pure_number", "12345", "12345"},
		// 非法：只有时分秒，不匹配任何布局
		{"time_only", "03:04:05", "03:04:05"},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := NormalizeComparable(c.in)
			if got != c.want {
				t.Fatalf("NormalizeComparable(%q) = %q, 期望 %q", c.in, got, c.want)
			}
		})
	}
}

// TestNormalizeComparableRFC3339RoundTrip 验证凡是 IsDateTime 判定为真的输入，
// 其 NormalizeComparable 输出都能被 time.Parse(time.RFC3339) 解析成功。
func TestNormalizeComparableRFC3339RoundTrip(t *testing.T) {
	inputs := []string{
		"2024-01-02T03:04:05Z",
		"2024-01-02T03:04:05+08:00",
		"2024-01-02T03:04:05",
		"2024-01-02 03:04:05",
		"2024-01-02 03:04",
		"2024-01-02",
		"2024/01/02",
		"2024/01/02 03:04:05",
		"2024-01-02T03:04:05.000Z",
	}
	for _, in := range inputs {
		if !IsDateTime(in) {
			t.Fatalf("IsDateTime(%q) = false, 期望 true", in)
		}
		out := NormalizeComparable(in)
		if _, err := time.Parse(time.RFC3339, out); err != nil {
			t.Fatalf("NormalizeComparable(%q) = %q 无法按 RFC3339 解析: %v", in, out, err)
		}
	}
}

// TestIsDateTimeFalseForIllegal 验证非法输入 IsDateTime 返回 false。
func TestIsDateTimeFalseForIllegal(t *testing.T) {
	inputs := []string{
		"not-a-date",
		"",
		"中文",
		"12345",
		"03:04:05",
	}
	for _, in := range inputs {
		if IsDateTime(in) {
			t.Fatalf("IsDateTime(%q) = true, 期望 false", in)
		}
	}
}

// TestParseValueDatetimeNormalizes 验证 DATETIME 解析后统一为 RFC3339 UTC。
func TestParseValueDatetimeNormalizes(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"2024-01-02T03:04:05+08:00", "2024-01-01T19:04:05Z"},
		{"2024-01-02 03:04:05", "2024-01-02T03:04:05Z"},
		{"2024-01-02", "2024-01-02T00:00:00Z"},
	}
	for _, c := range cases {
		got, err := ParseValue(c.in, "DATETIME")
		if err != nil {
			t.Fatalf("ParseValue(%q, DATETIME) 返回错误: %v", c.in, err)
		}
		s, ok := got.(string)
		if !ok {
			t.Fatalf("ParseValue(%q, DATETIME) 返回类型 = %T, 期望 string", c.in, got)
		}
		if s != c.want {
			t.Fatalf("ParseValue(%q, DATETIME) = %q, 期望 %q", c.in, s, c.want)
		}
	}
}

// TestParseValueBoolean 验证 BOOLEAN 解析映射到 int64(1)/int64(0)。
func TestParseValueBoolean(t *testing.T) {
	trueCases := []string{"true", "TRUE", "1", "是"}
	for _, in := range trueCases {
		got, err := ParseValue(in, "BOOLEAN")
		if err != nil {
			t.Fatalf("ParseValue(%q, BOOLEAN) 返回错误: %v", in, err)
		}
		if got != int64(1) {
			t.Fatalf("ParseValue(%q, BOOLEAN) = %v, 期望 int64(1)", in, got)
		}
	}
	falseCases := []string{"false", "FALSE", "0", "否"}
	for _, in := range falseCases {
		got, err := ParseValue(in, "BOOLEAN")
		if err != nil {
			t.Fatalf("ParseValue(%q, BOOLEAN) 返回错误: %v", in, err)
		}
		if got != int64(0) {
			t.Fatalf("ParseValue(%q, BOOLEAN) = %v, 期望 int64(0)", in, got)
		}
	}
	if _, err := ParseValue("maybe", "BOOLEAN"); err == nil {
		t.Fatalf("ParseValue(\"maybe\", BOOLEAN) 期望返回错误, 实际为 nil")
	}
}

// TestParseValueIntegerRealTextEmpty 验证其余类型的解析语义。
func TestParseValueIntegerRealTextEmpty(t *testing.T) {
	// INTEGER
	got, err := ParseValue("42", "INTEGER")
	if err != nil {
		t.Fatalf("ParseValue(\"42\", INTEGER) 返回错误: %v", err)
	}
	if got != int64(42) {
		t.Fatalf("ParseValue(\"42\", INTEGER) = %v, 期望 int64(42)", got)
	}
	if _, err := ParseValue("abc", "INTEGER"); err == nil {
		t.Fatalf("ParseValue(\"abc\", INTEGER) 期望返回错误, 实际为 nil")
	}

	// REAL
	rgot, err := ParseValue("3.5", "REAL")
	if err != nil {
		t.Fatalf("ParseValue(\"3.5\", REAL) 返回错误: %v", err)
	}
	if rgot != 3.5 {
		t.Fatalf("ParseValue(\"3.5\", REAL) = %v, 期望 3.5", rgot)
	}

	// TEXT 原样
	tgot, err := ParseValue("hello", "TEXT")
	if err != nil {
		t.Fatalf("ParseValue(\"hello\", TEXT) 返回错误: %v", err)
	}
	if tgot != "hello" {
		t.Fatalf("ParseValue(\"hello\", TEXT) = %v, 期望 \"hello\"", tgot)
	}

	// 空串返回 nil
	egot, err := ParseValue("", "INTEGER")
	if err != nil {
		t.Fatalf("ParseValue(\"\", INTEGER) 返回错误: %v", err)
	}
	if egot != nil {
		t.Fatalf("ParseValue(\"\", INTEGER) = %v, 期望 nil", egot)
	}
}

// TestUnifyTypes 验证类型提升规则。
func TestUnifyTypesDeep(t *testing.T) {
	cases := []struct {
		name string
		in   []string
		want string
	}{
		{"empty_slice", []string{}, "TEXT"},
		{"all_empty", []string{"", ""}, "TEXT"},
		{"integer_real", []string{"INTEGER", "REAL"}, "REAL"},
		{"with_text", []string{"INTEGER", "TEXT"}, "TEXT"},
		{"boolean_integer", []string{"BOOLEAN", "INTEGER"}, "INTEGER"},
		{"only_boolean", []string{"BOOLEAN"}, "BOOLEAN"},
		{"only_datetime", []string{"DATETIME", "DATETIME"}, "DATETIME"},
		{"datetime_with_integer", []string{"DATETIME", "INTEGER"}, "TEXT"},
		{"only_integer", []string{"INTEGER"}, "INTEGER"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := UnifyTypes(c.in)
			if got != c.want {
				t.Fatalf("UnifyTypes(%v) = %q, 期望 %q", c.in, got, c.want)
			}
		})
	}
}

// TestSQLiteType 验证推断类型到 SQLite 类型的映射。
func TestSQLiteType(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"BOOLEAN", "INTEGER"},
		{"INTEGER", "INTEGER"},
		{"REAL", "REAL"},
		{"TEXT", "TEXT"},
		{"DATETIME", "DATETIME"},
		{"UNKNOWN", "TEXT"},
		{"", "TEXT"},
	}
	for _, c := range cases {
		got := SQLiteType(c.in)
		if got != c.want {
			t.Fatalf("SQLiteType(%q) = %q, 期望 %q", c.in, got, c.want)
		}
	}
}

// TestStringify 验证值到字符串的统一转换。
func TestStringifyDeep(t *testing.T) {
	if got := Stringify(nil); got != "" {
		t.Fatalf("Stringify(nil) = %q, 期望空串", got)
	}
	if got := Stringify("abc"); got != "abc" {
		t.Fatalf("Stringify(\"abc\") = %q, 期望 \"abc\"", got)
	}
	if got := Stringify([]byte("xyz")); got != "xyz" {
		t.Fatalf("Stringify([]byte(\"xyz\")) = %q, 期望 \"xyz\"", got)
	}
	if got := Stringify(int64(7)); got != "7" {
		t.Fatalf("Stringify(int64(7)) = %q, 期望 \"7\"", got)
	}
}

// TestInferCSV 验证 CSV 列类型推断：表头、空行跳过、类型提升。
func TestInferCSVNormTable(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "a.csv")
	content := "id,name,score,active,created_at\n" +
		"1,alice,1.5,true,2024-01-02\n" +
		"2,bob,2.5,false,2024-01-03\n" +
		"\n" +
		"3,carol,3,true,2024-01-04\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	cols, err := InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	want := []Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
		{Name: "score", Type: "REAL"},
		{Name: "active", Type: "BOOLEAN"},
		{Name: "created_at", Type: "DATETIME"},
	}
	if len(cols) != len(want) {
		t.Fatalf("InferCSV 列数 = %d, 期望 %d", len(cols), len(want))
	}
	for i := range want {
		if cols[i] != want[i] {
			t.Fatalf("第 %d 列 = %+v, 期望 %+v", i, cols[i], want[i])
		}
	}
}

// TestInferCSVCustomDelimiter 验证自定义分隔符。
func TestInferCSVCustomDelimiterNorm(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "b.csv")
	content := "id|name\n1|alice\n2|bob\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	cols, err := InferCSV(path, "|")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	want := []Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
	}
	if len(cols) != len(want) {
		t.Fatalf("InferCSV 列数 = %d, 期望 %d", len(cols), len(want))
	}
	for i := range want {
		if cols[i] != want[i] {
			t.Fatalf("第 %d 列 = %+v, 期望 %+v", i, cols[i], want[i])
		}
	}
}

// TestInferCSVInvalidDelimiter 验证多字符分隔符被拒绝。
func TestInferCSVInvalidDelimiter(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "c.csv")
	if err := os.WriteFile(path, []byte("id\n1\n"), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	if _, err := InferCSV(path, "||"); err == nil {
		t.Fatalf("InferCSV 使用多字符分隔符期望返回错误, 实际为 nil")
	}
}

// TestInferJSON 验证顶层数组的 JSON 列推断与列顺序（按首次出现）。
func TestInferJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "a.json")
	content := `[
		{"id": 123, "name": "alice", "active": true, "score": 1.5, "created_at": "2024-01-02"},
		{"id": 456, "name": "bob", "active": false, "score": 2, "created_at": "2024-01-03"}
	]`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	cols, err := InferJSON(path, "")
	if err != nil {
		t.Fatalf("InferJSON 返回错误: %v", err)
	}
	want := []Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
		{Name: "active", Type: "BOOLEAN"},
		{Name: "score", Type: "REAL"},
		{Name: "created_at", Type: "DATETIME"},
	}
	if len(cols) != len(want) {
		t.Fatalf("InferJSON 列数 = %d, 期望 %d", len(cols), len(want))
	}
	for i := range want {
		if cols[i] != want[i] {
			t.Fatalf("第 %d 列 = %+v, 期望 %+v", i, cols[i], want[i])
		}
	}
}

// TestInferJSONRoot 验证通过 root 路径导航到嵌套数组。
func TestInferJSONRootNorm(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "b.json")
	content := `{"data": {"items": [{"id": 123, "name": "alice"}]}}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	cols, err := InferJSON(path, "data.items")
	if err != nil {
		t.Fatalf("InferJSON 返回错误: %v", err)
	}
	want := []Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "name", Type: "TEXT"},
	}
	if len(cols) != len(want) {
		t.Fatalf("InferJSON 列数 = %d, 期望 %d", len(cols), len(want))
	}
	for i := range want {
		if cols[i] != want[i] {
			t.Fatalf("第 %d 列 = %+v, 期望 %+v", i, cols[i], want[i])
		}
	}
}

// TestInferJSONRootMissingField 验证 root 路径字段缺失时报错。
func TestInferJSONRootMissingField(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "c.json")
	content := `{"data": {"other": []}}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	if _, err := InferJSON(path, "data.items"); err == nil {
		t.Fatalf("InferJSON root 缺字段期望返回错误, 实际为 nil")
	}
}

// TestInferJSONNotArray 验证 root 指向非数组时报错。
func TestInferJSONNotArray(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "d.json")
	content := `{"data": {"items": {"id": 1}}}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	if _, err := InferJSON(path, "data.items"); err == nil {
		t.Fatalf("InferJSON root 非数组期望返回错误, 实际为 nil")
	}
}

// TestDetectJSONTypeNested 验证嵌套对象/数组按 TEXT 处理。
func TestDetectJSONTypeNested(t *testing.T) {
	var v any
	if err := json.Unmarshal([]byte(`{"a": {"b": 1}, "c": [1,2]}`), &v); err != nil {
		t.Fatalf("解析测试 JSON 失败: %v", err)
	}
	m := v.(map[string]any)
	if got := detectJSONType(m["a"]); got != "TEXT" {
		t.Fatalf("detectJSONType(嵌套对象) = %q, 期望 TEXT", got)
	}
	if got := detectJSONType(m["c"]); got != "TEXT" {
		t.Fatalf("detectJSONType(嵌套数组) = %q, 期望 TEXT", got)
	}
	if got := detectJSONType(nil); got != "" {
		t.Fatalf("detectJSONType(nil) = %q, 期望空串", got)
	}
	if got := detectJSONType(float64(3)); got != "INTEGER" {
		t.Fatalf("detectJSONType(3.0) = %q, 期望 INTEGER", got)
	}
	if got := detectJSONType(3.5); got != "REAL" {
		t.Fatalf("detectJSONType(3.5) = %q, 期望 REAL", got)
	}
}

// TestDetectType 验证单值字符串的类型推断。
func TestDetectType(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"", ""},
		{"   ", ""},
		{"true", "BOOLEAN"},
		{"False", "BOOLEAN"},
		{"1", "BOOLEAN"},
		{"0", "BOOLEAN"},
		{"是", "BOOLEAN"},
		{"否", "BOOLEAN"},
		{"123", "INTEGER"},
		{"-5", "INTEGER"},
		{"1.5", "REAL"},
		{"2024-01-02", "DATETIME"},
		{"2024-01-02 03:04:05", "DATETIME"},
		{"hello", "TEXT"},
		{"not-a-date", "TEXT"},
	}
	for _, c := range cases {
		got := detectType(c.in)
		if got != c.want {
			t.Fatalf("detectType(%q) = %q, 期望 %q", c.in, got, c.want)
		}
	}
}

// TestInferCSVFileNotFound 验证打开不存在文件时报错。
func TestInferCSVFileNotFound(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "nope.csv")
	if _, err := InferCSV(path, ""); err == nil {
		t.Fatalf("InferCSV 打开不存在文件期望返回错误, 实际为 nil")
	}
}

// TestInferJSONInvalidJSON 验证非法 JSON 报错。
func TestInferJSONInvalidJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.json")
	if err := os.WriteFile(path, []byte("{not json"), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	if _, err := InferJSON(path, ""); err == nil {
		t.Fatalf("InferJSON 非法 JSON 期望返回错误, 实际为 nil")
	}
}

// TestParseDatetimeBOMFree 验证 parseDatetime 对已知布局集合均可解析。
func TestParseDatetimeSupportedLayouts(t *testing.T) {
	layouts := []string{
		"2024-01-02T03:04:05Z",
		"2024-01-02 15:04:05",
		"2024-01-02T15:04:05",
		"2024-01-02 15:04",
		"2024-01-02",
		"2024/01/02",
		"2024/01/02 15:04:05",
	}
	// 这些字面量对应 isDatetime 支持的布局，逐一断言可解析。
	inputs := []string{
		"2024-01-02T03:04:05Z",
		"2024-01-02 03:04:05",
		"2024-01-02T03:04:05",
		"2024-01-02 03:04",
		"2024-01-02",
		"2024/01/02",
		"2024/01/02 03:04:05",
	}
	if len(inputs) != len(layouts) {
		t.Fatalf("测试用例数 %d 与布局数 %d 不一致", len(inputs), len(layouts))
	}
	for i, in := range inputs {
		if _, err := parseDatetime(in); err != nil {
			t.Fatalf("parseDatetime(%q) (布局 %q) 返回错误: %v", in, layouts[i], err)
		}
	}
}

// TestNormalizeComparableIdempotent 验证对已规范化的 RFC3339 输出再次规范化保持稳定。
func TestNormalizeComparableIdempotent(t *testing.T) {
	inputs := []string{
		"2024-01-02 03:04:05",
		"2024/01/02",
		"2024-01-02T03:04:05+08:00",
	}
	for _, in := range inputs {
		once := NormalizeComparable(in)
		twice := NormalizeComparable(once)
		if once != twice {
			t.Errorf("NormalizeComparable(%q) 幂等失败: 一次=%q 二次=%q", in, once, twice)
		}
	}
}