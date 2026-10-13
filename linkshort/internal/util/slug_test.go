package util

import (
	"strings"
	"testing"
)

// TestGenerate_长度与字符集 验证 Generate 生成的随机串长度正确且字符集符合预期
func TestGenerate_长度与字符集(t *testing.T) {
	allowed := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	allowedSet := map[byte]struct{}{}
	for i := 0; i < len(allowed); i++ {
		allowedSet[allowed[i]] = struct{}{}
	}

	for _, n := range []int{0, 1, 6, 8, 16, 64} {
		s, err := Generate(n)
		if err != nil {
			t.Fatalf("Generate(%d) 返回错误: %v", n, err)
		}
		if len(s) != n {
			t.Errorf("Generate(%d) 长度错误: 期望 %d，实际 %d（值=%q）", n, n, len(s), s)
		}
		for i := 0; i < len(s); i++ {
			if _, ok := allowedSet[s[i]]; !ok {
				t.Errorf("Generate(%d) 包含非法字符 %q（完整值=%q）", n, s[i], s)
			}
		}
	}
}

// TestGenerate_两次生成不同 验证两次生成结果不相同（极小概率冲突视为可接受）
func TestGenerate_两次生成不同(t *testing.T) {
	a, err := Generate(16)
	if err != nil {
		t.Fatalf("Generate(16) 第一次返回错误: %v", err)
	}
	b, err := Generate(16)
	if err != nil {
		t.Fatalf("Generate(16) 第二次返回错误: %v", err)
	}
	if a == b {
		t.Errorf("两次 Generate(16) 结果相同，期望不同: %q", a)
	}
}

// TestIsValidSlug_正反例 验证合法 slug 返回 true，非法返回 false
func TestIsValidSlug_正反例(t *testing.T) {
	valid := []string{
		"a",
		"abc",
		"AbC123",
		"a-b_c",
		"x_y-z",
		strings.Repeat("a", 64),
	}
	for _, s := range valid {
		if !IsValidSlug(s) {
			t.Errorf("IsValidSlug(%q) 期望 true，实际 false", s)
		}
	}

	invalid := []string{
		"",
		"中文",
		"hello world",
		"a/b",
		"a.b",
		"a@b",
		"a#b",
		strings.Repeat("a", 65),
		"tab\tchar",
	}
	for _, s := range invalid {
		if IsValidSlug(s) {
			t.Errorf("IsValidSlug(%q) 期望 false，实际 true", s)
		}
	}
}
