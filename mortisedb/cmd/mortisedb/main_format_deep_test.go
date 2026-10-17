package main

import (
	"io"
	"os"
	"strings"
	"testing"
)

func TestFormatCell_Nil(t *testing.T) {
	got := formatCell(nil)
	if got != "NULL" {
		t.Fatalf("formatCell(nil) = %q, want %q", got, "NULL")
	}
}

func TestFormatCell_Bytes(t *testing.T) {
	got := formatCell([]byte("hello"))
	if got != "hello" {
		t.Fatalf("formatCell([]byte(\"hello\")) = %q, want %q", got, "hello")
	}
	empty := formatCell([]byte{})
	if empty != "" {
		t.Fatalf("formatCell([]byte{}) = %q, want %q", empty, "")
	}
}

func TestFormatCell_Primitives(t *testing.T) {
	if got := formatCell(int64(42)); got != "42" {
		t.Fatalf("formatCell(int64(42)) = %q, want %q", got, "42")
	}
	if got := formatCell(1.5); got != "1.5" {
		t.Fatalf("formatCell(1.5) = %q, want %q", got, "1.5")
	}
	if got := formatCell(true); got != "true" {
		t.Fatalf("formatCell(true) = %q, want %q", got, "true")
	}
	if got := formatCell("文本"); got != "文本" {
		t.Fatalf("formatCell(\"文本\") = %q, want %q", got, "文本")
	}
}

func TestFormatCell_Int(t *testing.T) {
	got := formatCell(7)
	if got != "7" {
		t.Fatalf("formatCell(7) = %q, want %q", got, "7")
	}
}

func TestFormatCell_NilVsEmptyString(t *testing.T) {
	if got := formatCell(""); got != "" {
		t.Fatalf("formatCell(\"\") = %q, want %q", got, "")
	}
	if got := formatCell(nil); got != "NULL" {
		t.Fatalf("formatCell(nil) = %q, want %q", got, "NULL")
	}
	if formatCell("") == formatCell(nil) {
		t.Fatalf("formatCell(\"\") and formatCell(nil) should differ, both = %q", formatCell(""))
	}
}

func TestFormatCell_BytesWithUTF8(t *testing.T) {
	got := formatCell([]byte("中文"))
	if got != "中文" {
		t.Fatalf("formatCell([]byte(\"中文\")) = %q, want %q", got, "中文")
	}
}

func TestFormatPrintTable_Output(t *testing.T) {
	old := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe() error: %v", err)
	}
	os.Stdout = w

	printTable([]string{"id", "name"}, [][]any{
		{int64(1), "张三"},
		{int64(2), nil},
	})

	if err := w.Close(); err != nil {
		t.Fatalf("w.Close() error: %v", err)
	}
	os.Stdout = old

	out, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("io.ReadAll error: %v", err)
	}
	s := string(out)

	for _, want := range []string{"id", "name", "张三", "NULL", "(2 行)"} {
		if !strings.Contains(s, want) {
			t.Fatalf("printTable output %q does not contain %q", s, want)
		}
	}
}

func TestFormatPrintTable_EmptyRows(t *testing.T) {
	old := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe() error: %v", err)
	}
	os.Stdout = w

	printTable([]string{"a"}, nil)

	if err := w.Close(); err != nil {
		t.Fatalf("w.Close() error: %v", err)
	}
	os.Stdout = old

	out, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("io.ReadAll error: %v", err)
	}
	s := string(out)

	if !strings.Contains(s, "(0 行)") {
		t.Fatalf("printTable output %q does not contain %q", s, "(0 行)")
	}
	if !strings.Contains(s, "a") {
		t.Fatalf("printTable output %q does not contain header %q", s, "a")
	}
}
