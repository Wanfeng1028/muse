package infer

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestUnifyTypes(t *testing.T) {
	cases := []struct {
		name string
		in   []string
		want string
	}{
		{"int+real->real", []string{"INTEGER", "REAL"}, "REAL"},
		{"real+int->real", []string{"REAL", "INTEGER"}, "REAL"},
		{"int+text->text", []string{"INTEGER", "TEXT"}, "TEXT"},
		{"text+int->text", []string{"TEXT", "INTEGER"}, "TEXT"},
		{"bool+int->int", []string{"BOOLEAN", "INTEGER"}, "INTEGER"},
		{"int+bool->int", []string{"INTEGER", "BOOLEAN"}, "INTEGER"},
		{"all datetime->datetime", []string{"DATETIME", "DATETIME"}, "DATETIME"},
		{"datetime+text->text", []string{"DATETIME", "TEXT"}, "TEXT"},
		{"empty->text", []string{}, "TEXT"},
		{"single integer", []string{"INTEGER"}, "INTEGER"},
		{"bool only", []string{"BOOLEAN"}, "BOOLEAN"},
		{"real only", []string{"REAL"}, "REAL"},
		{"datetime only", []string{"DATETIME"}, "DATETIME"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := UnifyTypes(c.in)
			if got != c.want {
				t.Fatalf("UnifyTypes(%v)=%q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestParseValue(t *testing.T) {
	cases := []struct {
		name string
		s    string
		typ  string
		want any
	}{
		{"empty->nil", "", "TEXT", nil},
		{"empty int->nil", "", "INTEGER", nil},
		{"bool true", "true", "BOOLEAN", int64(1)},
		{"bool false", "false", "BOOLEAN", int64(0)},
		{"bool 1", "1", "BOOLEAN", int64(1)},
		{"bool 0", "0", "BOOLEAN", int64(0)},
		{"bool yes cn", "是", "BOOLEAN", int64(1)},
		{"bool no cn", "否", "BOOLEAN", int64(0)},
		{"datetime space", "2024-01-02 03:04:05", "DATETIME", "2024-01-02T03:04:05Z"},
		{"datetime date", "2024-01-02", "DATETIME", "2024-01-02T00:00:00Z"},
		{"datetime rfc3339", "2024-01-02T03:04:05Z", "DATETIME", "2024-01-02T03:04:05Z"},
		{"integer", "42", "INTEGER", int64(42)},
		{"integer negative", "-7", "INTEGER", int64(-7)},
		{"real", "3.14", "REAL", 3.14},
		{"text", "hello", "TEXT", "hello"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := ParseValue(c.s, c.typ)
			if err != nil {
				t.Fatalf("ParseValue(%q,%q) error: %v", c.s, c.typ, err)
			}
			if got != c.want {
				t.Fatalf("ParseValue(%q,%q)=%v(%T), want %v(%T)", c.s, c.typ, got, got, c.want, c.want)
			}
		})
	}
	if _, err := ParseValue("notint", "INTEGER"); err == nil {
		t.Fatalf("ParseValue should error for invalid integer")
	}
	if _, err := ParseValue("notreal", "REAL"); err == nil {
		t.Fatalf("ParseValue should error for invalid real")
	}
	if _, err := ParseValue("2024-13-99", "DATETIME"); err == nil {
		t.Fatalf("ParseValue should error for invalid datetime")
	}
}

func TestInferCSV(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "t.csv")
	content := "id,name,score,flag\n1,alice,3.5,true\n2,bob,,false\n3,,7,true\n"
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	cols, err := InferCSV(p, "")
	if err != nil {
		t.Fatalf("InferCSV error: %v", err)
	}
	if len(cols) != 4 {
		t.Fatalf("expected 4 cols, got %d: %+v", len(cols), cols)
	}
	if cols[0].Name != "id" || cols[0].Type != "INTEGER" {
		t.Fatalf("col0=%+v", cols[0])
	}
	if cols[1].Name != "name" || cols[1].Type != "TEXT" {
		t.Fatalf("col1=%+v", cols[1])
	}
	if cols[2].Name != "score" || cols[2].Type != "REAL" {
		t.Fatalf("col2=%+v", cols[2])
	}
	if cols[3].Name != "flag" || cols[3].Type != "BOOLEAN" {
		t.Fatalf("col3=%+v", cols[3])
	}
}

func TestInferCSVCustomDelimiter(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "t.csv")
	content := "a;b\n1;2\n"
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	cols, err := InferCSV(p, ";")
	if err != nil {
		t.Fatalf("InferCSV error: %v", err)
	}
	if len(cols) != 2 || cols[0].Name != "a" || cols[1].Name != "b" {
		t.Fatalf("unexpected cols: %+v", cols)
	}
}

func TestInferJSONTopLevel(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "t.json")
	content := `[{"id":1,"name":"a","meta":{"x":1}},{"id":2,"name":"b","meta":{"x":2}}]`
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	cols, err := InferJSON(p, "")
	if err != nil {
		t.Fatalf("InferJSON error: %v", err)
	}
	m := map[string]string{}
	for _, c := range cols {
		m[c.Name] = c.Type
	}
	if m["id"] != "INTEGER" {
		t.Fatalf("id type=%q", m["id"])
	}
	if m["name"] != "TEXT" {
		t.Fatalf("name type=%q", m["name"])
	}
	if m["meta"] != "TEXT" {
		t.Fatalf("meta type=%q", m["meta"])
	}
}

func TestInferJSONRoot(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "t.json")
	content := `{"data":{"items":[{"id":1},{"id":2}]}}`
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	cols, err := InferJSON(p, "data.items")
	if err != nil {
		t.Fatalf("InferJSON error: %v", err)
	}
	if len(cols) != 1 || cols[0].Name != "id" || cols[0].Type != "INTEGER" {
		t.Fatalf("unexpected cols: %+v", cols)
	}
}

func TestSQLiteTypeAndStringify(t *testing.T) {
	if SQLiteType("BOOLEAN") != "INTEGER" {
		t.Fatalf("BOOLEAN should map to INTEGER")
	}
	if SQLiteType("TEXT") != "TEXT" {
		t.Fatalf("TEXT should map to TEXT")
	}
	if Stringify(nil) != "" {
		t.Fatalf("nil should stringify to empty")
	}
	if Stringify(int64(5)) != "5" {
		t.Fatalf("int64 5 -> %q", Stringify(int64(5)))
	}
	if Stringify("abc") != "abc" {
		t.Fatalf("string abc -> %q", Stringify("abc"))
	}
}

var (
	_ = csv.NewReader
	_ = json.Marshal
	_ = io.Discard
	_ = fmt.Sprintf
	_ = strconv.Itoa
	_ = strings.TrimSpace
	_ = time.Now
)
