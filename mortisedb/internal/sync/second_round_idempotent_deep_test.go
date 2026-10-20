package sync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
)

// 测试 InferCSV 采样 CSV 文件前 500 行推断列类型的基本语义。
// 覆盖：INTEGER、REAL、TEXT、BOOLEAN、DATETIME 五种类型，以及表头 BOM 去除。
func TestInferCSVBasicTypes(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "basic.csv")
	content := "id,score,name,active,created_at\n" +
		"1,1.5,alice,true,2024-01-02 03:04:05\n" +
		"2,2.5,bob,false,2024-02-03 04:05:06\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	cols, err := infer.InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	if len(cols) != 5 {
		t.Fatalf("期望 5 列，实际 %d 列", len(cols))
	}
	want := []infer.Column{
		{Name: "id", Type: "INTEGER"},
		{Name: "score", Type: "REAL"},
		{Name: "name", Type: "TEXT"},
		{Name: "active", Type: "BOOLEAN"},
		{Name: "created_at", Type: "DATETIME"},
	}
	for i, w := range want {
		if cols[i].Name != w.Name {
			t.Fatalf("第 %d 列名称期望 %q，实际 %q", i, w.Name, cols[i].Name)
		}
		if cols[i].Type != w.Type {
			t.Fatalf("第 %d 列类型期望 %q，实际 %q", i, w.Type, cols[i].Type)
		}
	}
}

// 测试 InferCSV 对带 BOM 表头的处理：BOM 应被去除，列名保持干净。
func TestInferCSVHeaderBOM(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bom.csv")
	content := "\ufeffid,name\n123,alice\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	cols, err := infer.InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	if len(cols) != 2 {
		t.Fatalf("期望 2 列，实际 %d 列", len(cols))
	}
	if cols[0].Name != "id" {
		t.Fatalf("BOM 未去除，期望首列名 %q，实际 %q", "id", cols[0].Name)
	}
	if cols[0].Type != "INTEGER" {
		t.Fatalf("首列类型期望 %q，实际 %q", "INTEGER", cols[0].Type)
	}
}

// 测试 InferCSV 对自定义分隔符的支持，这里使用竖线分隔。
func TestInferCSVCustomDelimiter(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "pipe.csv")
	content := "id|name\n1|alice\n2|bob\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	cols, err := infer.InferCSV(path, "|")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	if len(cols) != 2 {
		t.Fatalf("期望 2 列，实际 %d 列", len(cols))
	}
	if cols[0].Name != "id" || cols[0].Type != "INTEGER" {
		t.Fatalf("首列期望 id/INTEGER，实际 %s/%s", cols[0].Name, cols[0].Type)
	}
	if cols[1].Name != "name" || cols[1].Type != "TEXT" {
		t.Fatalf("次列期望 name/TEXT，实际 %s/%s", cols[1].Name, cols[1].Type)
	}
}

// 测试 InferCSV 对多字符分隔符的拒绝，应返回错误。
func TestInferCSVInvalidDelimiter(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "x.csv")
	if err := os.WriteFile(path, []byte("id\n1\n"), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}
	if _, err := infer.InferCSV(path, "||"); err == nil {
		t.Fatalf("多字符分隔符期望报错，实际返回 nil")
	}
}

// 测试 InferCSV 对列数不一致行的处理：多余列被截断，缺失列补空。
// 空值不参与类型推断，因此不会污染列类型。
func TestInferCSVRaggedRows(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "ragged.csv")
	content := "a,b,c\n" +
		"1,2,3,extra\n" +
		"4,5\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	cols, err := infer.InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	if len(cols) != 3 {
		t.Fatalf("期望 3 列，实际 %d 列", len(cols))
	}
	for i := 0; i < 3; i++ {
		if cols[i].Type != "INTEGER" {
			t.Fatalf("第 %d 列类型期望 INTEGER，实际 %q", i, cols[i].Type)
		}
	}
}

// 测试 InferCSV 跳过空行：空行不参与类型推断，也不应导致推断失败。
func TestInferCSVSkipEmptyRows(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "empty.csv")
	content := "id,name\n\n1,alice\n\n2,bob\n\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 CSV 失败: %v", err)
	}

	cols, err := infer.InferCSV(path, "")
	if err != nil {
		t.Fatalf("InferCSV 返回错误: %v", err)
	}
	if len(cols) != 2 {
		t.Fatalf("期望 2 列，实际 %d 列", len(cols))
	}
	if cols[0].Type != "INTEGER" {
		t.Fatalf("id 列期望 INTEGER，实际 %q", cols[0].Type)
	}
	if cols[1].Type != "TEXT" {
		t.Fatalf("name 列期望 TEXT，实际 %q", cols[1].Type)
	}
}

// 测试 InferJSON 在顶层数组、无 root 情况下的类型推断。
func TestInferJSONTopLevelArray(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "top.json")
	content := `[{"id":1,"name":"alice","score":1.5,"active":true},` +
		`{"id":2,"name":"bob","score":2.5,"active":false}]`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}

	cols, err := infer.InferJSON(path, "")
	if err != nil {
		t.Fatalf("InferJSON 返回错误: %v", err)
	}
	if len(cols) != 4 {
		t.Fatalf("期望 4 列，实际 %d 列", len(cols))
	}
	types := map[string]string{}
	for _, c := range cols {
		types[c.Name] = c.Type
	}
	if types["id"] != "INTEGER" {
		t.Fatalf("id 期望 INTEGER，实际 %q", types["id"])
	}
	if types["name"] != "TEXT" {
		t.Fatalf("name 期望 TEXT，实际 %q", types["name"])
	}
	if types["score"] != "REAL" {
		t.Fatalf("score 期望 REAL，实际 %q", types["score"])
	}
	if types["active"] != "BOOLEAN" {
		t.Fatalf("active 期望 BOOLEAN，实际 %q", types["active"])
	}
}

// 测试 InferJSON 按 root 路径导航到数组，例如 "data.items"。
func TestInferJSONRootNavigation(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "root.json")
	content := `{"data":{"items":[{"id":1},{"id":2}]}}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}

	cols, err := infer.InferJSON(path, "data.items")
	if err != nil {
		t.Fatalf("InferJSON 返回错误: %v", err)
	}
	if len(cols) != 1 {
		t.Fatalf("期望 1 列，实际 %d 列", len(cols))
	}
	if cols[0].Name != "id" || cols[0].Type != "INTEGER" {
		t.Fatalf("期望 id/INTEGER，实际 %s/%s", cols[0].Name, cols[0].Type)
	}
}

// 测试 InferJSON 在 root 路径缺少字段时返回错误。
func TestInferJSONRootMissing(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "missing.json")
	content := `{"data":{"items":[]}}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	if _, err := infer.InferJSON(path, "data.nope"); err == nil {
		t.Fatalf("root 缺少字段时期望报错，实际返回 nil")
	}
}

// 测试 InferJSON 对数组元素非对象的拒绝。
func TestInferJSONElementNotObject(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "scalar.json")
	content := `[1,2,3]`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("写入 JSON 失败: %v", err)
	}
	if _, err := infer.InferJSON(path, ""); err == nil {
		t.Fatalf("数组元素非对象期望报错，实际返回 nil")
	}
}
