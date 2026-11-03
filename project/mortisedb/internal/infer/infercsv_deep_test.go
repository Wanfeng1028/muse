package infer

import (
	"os"
	"path/filepath"
	"testing"
)

// 以下测试用于保证 infer 包基础工具与文件系统测试路径可用，
// 使用 t.TempDir() 避免依赖固定路径。

// TestInferCSVUsesTempDir 在测：InferCSV 在临时目录下的正常推断，列名与类型符合预期。
func TestInferCSVUsesTempDir(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "a.csv")
	content := "id,name,score\n1,alice,1.5\n2,bob,2.5\n"
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("写入临时 CSV 失败: %v", err)
	}
	cols, err := InferCSV(p, ",")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	if len(cols) != 3 {
		t.Fatalf("列数应为 3，实际 %d", len(cols))
	}
	if cols[0].Name != "id" || cols[0].Type != "INTEGER" {
		t.Fatalf("第 0 列应为 id/INTEGER，实际 %s/%s", cols[0].Name, cols[0].Type)
	}
	if cols[1].Name != "name" || cols[1].Type != "TEXT" {
		t.Fatalf("第 1 列应为 name/TEXT，实际 %s/%s", cols[1].Name, cols[1].Type)
	}
	if cols[2].Name != "score" || cols[2].Type != "REAL" {
		t.Fatalf("第 2 列应为 score/REAL，实际 %s/%s", cols[2].Name, cols[2].Type)
	}
}

// TestUnifyTypesPromotion 在测：类型提升规则 INTEGER+REAL→REAL、出现 TEXT→TEXT、BOOLEAN+INTEGER→INTEGER。
func TestUnifyTypesPromotion(t *testing.T) {
	if got := UnifyTypes([]string{"INTEGER", "REAL"}); got != "REAL" {
		t.Fatalf("INTEGER+REAL 应提升为 REAL，实际 %s", got)
	}
	if got := UnifyTypes([]string{"INTEGER", "TEXT"}); got != "TEXT" {
		t.Fatalf("出现 TEXT 应为 TEXT，实际 %s", got)
	}
	if got := UnifyTypes([]string{"BOOLEAN", "INTEGER"}); got != "INTEGER" {
		t.Fatalf("BOOLEAN+INTEGER 应为 INTEGER，实际 %s", got)
	}
	if got := UnifyTypes([]string{"", ""}); got != "TEXT" {
		t.Fatalf("全空应为 TEXT，实际 %s", got)
	}
	if got := UnifyTypes([]string{}); got != "TEXT" {
		t.Fatalf("空切片应为 TEXT，实际 %s", got)
	}
}

// TestParseValueRoundTrip 在测：ParseValue 对 INTEGER/REAL/BOOLEAN/DATETIME/TEXT 的解析结果。
func TestParseValueRoundTrip(t *testing.T) {
	v, err := ParseValue("42", "INTEGER")
	if err != nil {
		t.Fatalf("解析 INTEGER 失败: %v", err)
	}
	if iv, ok := v.(int64); !ok || iv != 42 {
		t.Fatalf("INTEGER 应为 int64(42)，实际 %#v", v)
	}

	v, err = ParseValue("1.5", "REAL")
	if err != nil {
		t.Fatalf("解析 REAL 失败: %v", err)
	}
	if fv, ok := v.(float64); !ok || fv != 1.5 {
		t.Fatalf("REAL 应为 float64(1.5)，实际 %#v", v)
	}

	v, err = ParseValue("true", "BOOLEAN")
	if err != nil {
		t.Fatalf("解析 BOOLEAN 失败: %v", err)
	}
	if bv, ok := v.(int64); !ok || bv != 1 {
		t.Fatalf("BOOLEAN true 应为 int64(1)，实际 %#v", v)
	}

	v, err = ParseValue("否", "BOOLEAN")
	if err != nil {
		t.Fatalf("解析 BOOLEAN 否 失败: %v", err)
	}
	if bv, ok := v.(int64); !ok || bv != 0 {
		t.Fatalf("BOOLEAN 否 应为 int64(0)，实际 %#v", v)
	}

	v, err = ParseValue("2024-01-02 00:00:00", "DATETIME")
	if err != nil {
		t.Fatalf("解析 DATETIME 失败: %v", err)
	}
	if sv, ok := v.(string); !ok || sv != "2024-01-02T00:00:00Z" {
		t.Fatalf("DATETIME 应归一化为 RFC3339 UTC，实际 %#v", v)
	}

	v, err = ParseValue("hello", "TEXT")
	if err != nil {
		t.Fatalf("解析 TEXT 失败: %v", err)
	}
	if sv, ok := v.(string); !ok || sv != "hello" {
		t.Fatalf("TEXT 应原样返回，实际 %#v", v)
	}

	v, err = ParseValue("", "INTEGER")
	if err != nil {
		t.Fatalf("空串解析 INTEGER 不应报错: %v", err)
	}
	if v != nil {
		t.Fatalf("空串应返回 nil，实际 %#v", v)
	}
}

// TestNormalizeComparableDateTime 在测：NormalizeComparable 对可解析日期统一为 RFC3339，
// 对不可解析文本原样返回。
func TestNormalizeComparableDateTime(t *testing.T) {
	if got := NormalizeComparable("2024-01-02 00:00:00"); got != "2024-01-02T00:00:00Z" {
		t.Fatalf("日期字符串应规范化为 RFC3339 UTC，实际 %s", got)
	}
	if got := NormalizeComparable("not-a-date"); got != "not-a-date" {
		t.Fatalf("不可解析文本应原样返回，实际 %s", got)
	}
}

// TestIsDateTime 在测：IsDateTime 与 parseDatetime 同口径。
func TestIsDateTime(t *testing.T) {
	if !IsDateTime("2024-01-02") {
		t.Fatalf("2024-01-02 应可解析为日期时间")
	}
	if IsDateTime("definitely-not-date") {
		t.Fatalf("非日期字符串不应被判定为日期时间")
	}
}

// TestSQLiteTypeMapping 在测：SQLiteType 的映射规则。
func TestSQLiteTypeMapping(t *testing.T) {
	cases := map[string]string{
		"BOOLEAN":  "INTEGER",
		"INTEGER":  "INTEGER",
		"REAL":     "REAL",
		"TEXT":     "TEXT",
		"DATETIME": "DATETIME",
		"UNKNOWN":  "TEXT",
	}
	for in, want := range cases {
		if got := SQLiteType(in); got != want {
			t.Fatalf("SQLiteType(%q) 应为 %q，实际 %q", in, want, got)
		}
	}
}

// TestStringify 在测：Stringify 对 nil/string/[]byte/其他值的转换。
func TestStringify(t *testing.T) {
	if got := Stringify(nil); got != "" {
		t.Fatalf("nil 应转为空串，实际 %q", got)
	}
	if got := Stringify("abc"); got != "abc" {
		t.Fatalf("string 应原样返回，实际 %q", got)
	}
	if got := Stringify([]byte("xy")); got != "xy" {
		t.Fatalf("[]byte 应转为字符串，实际 %q", got)
	}
	if got := Stringify(int64(7)); got != "7" {
		t.Fatalf("int64(7) 应为 \"7\"，实际 %q", got)
	}
}
