package handler

import (
	"strings"
	"testing"
	"unicode/utf8"
)

// TestTruncateDeep 直接验证 handler 层 truncate(s, n) 的真实语义：
// 先按字节长度做快速路径，再按 rune 截断，保证不会把多字节 rune 砍断。
func TestTruncateDeep(t *testing.T) {
	// len(s) <= n：原样返回。
	{
		got := truncate("hello", 10)
		if got != "hello" {
			t.Fatalf("short ascii: want %q, got %q", "hello", got)
		}
	}
	{
		got := truncate("", 10)
		if got != "" {
			t.Fatalf("empty with n>0: want %q, got %q", "", got)
		}
	}
	{
		got := truncate("", 0)
		if got != "" {
			t.Fatalf("empty with n=0: want %q, got %q", "", got)
		}
	}

	// 超长纯 ASCII：n=256，300 字节输入返回前 256 个字符。
	{
		in := strings.Repeat("a", 300)
		got := truncate(in, 256)
		if len(got) != 256 {
			t.Fatalf("ascii 300 n=256: want length 256, got %d", len(got))
		}
		if got != in[:256] {
			t.Fatalf("ascii 300 n=256: content mismatch")
		}
	}

	// 多字节 rune 不被按字节砍断。
	// 100 个汉字 = 300 字节，rune 数 100 <= 256，原样返回。
	{
		in := strings.Repeat("汉", 100)
		got := truncate(in, 256)
		if got != in {
			t.Fatalf("han100 n=256: want full passthrough, got %q", got)
		}
		if utf8.RuneCountInString(got) != 100 {
			t.Fatalf("han100 n=256: want 100 runes, got %d", utf8.RuneCountInString(got))
		}
		if !utf8.ValidString(got) {
			t.Fatalf("han100 n=256: want valid utf-8")
		}
	}
	// 300 个汉字 = 900 字节，n=256 时返回恰好 256 个 rune，且合法 UTF-8。
	{
		in := strings.Repeat("汉", 300)
		got := truncate(in, 256)
		if utf8.RuneCountInString(got) != 256 {
			t.Fatalf("han300 n=256: want 256 runes, got %d", utf8.RuneCountInString(got))
		}
		if !utf8.ValidString(got) {
			t.Fatalf("han300 n=256: want valid utf-8, got invalid")
		}
		if got != strings.Repeat("汉", 256) {
			t.Fatalf("han300 n=256: content mismatch")
		}
	}

	// 边界：n=0 时超长输入返回空字符串。
	{
		got := truncate(strings.Repeat("a", 300), 0)
		if got != "" {
			t.Fatalf("ascii 300 n=0: want empty, got %q", got)
		}
	}
	{
		got := truncate(strings.Repeat("汉", 300), 0)
		if got != "" {
			t.Fatalf("han300 n=0: want empty, got %q", got)
		}
	}

	// referer 档 n=512 smoke：600 字节 ASCII 返回 512 字节。
	{
		in := strings.Repeat("r", 600)
		got := truncate(in, 512)
		if len(got) != 512 {
			t.Fatalf("ascii 600 n=512: want length 512, got %d", len(got))
		}
		if got != in[:512] {
			t.Fatalf("ascii 600 n=512: content mismatch")
		}
	}
}
