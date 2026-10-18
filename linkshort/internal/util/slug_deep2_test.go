package util

import (
	"regexp"
	"strings"
	"testing"
)

func TestGenerateLengthSixDeep2(t *testing.T) {
	s, err := Generate(6)
	if err != nil {
		t.Fatalf("Generate(6) 返回错误: %v", err)
	}
	if len(s) != 6 {
		t.Fatalf("Generate(6) 长度期望 6，实际 %d", len(s))
	}
	for i := 0; i < len(s); i++ {
		if !strings.ContainsRune(base62Chars, rune(s[i])) {
			t.Fatalf("Generate(6) 第 %d 个字符 %q 不在 base62Chars 中", i, s[i])
		}
	}
}

func TestGenerateCharsetDeep2(t *testing.T) {
	for n := 1; n <= 32; n++ {
		s, err := Generate(n)
		if err != nil {
			t.Fatalf("Generate(%d) 返回错误: %v", n, err)
		}
		if len(s) != n {
			t.Fatalf("Generate(%d) 长度期望 %d，实际 %d", n, n, len(s))
		}
		for i := 0; i < len(s); i++ {
			if !strings.ContainsRune(base62Chars, rune(s[i])) {
				t.Fatalf("Generate(%d) 字符 %q 不在 base62Chars 中", n, s[i])
			}
		}
	}
}

func TestGenerateRandomnessDeep2(t *testing.T) {
	const rounds = 20
	seen := make(map[string]struct{}, rounds)
	dup := 0
	for i := 0; i < rounds; i++ {
		s, err := Generate(16)
		if err != nil {
			t.Fatalf("Generate(16) 返回错误: %v", err)
		}
		if _, ok := seen[s]; ok {
			dup++
		}
		seen[s] = struct{}{}
	}
	if dup > 0 {
		t.Fatalf("Generate(16) 在 %d 次调用中出现 %d 次重复，随机性不足", rounds, dup)
	}
}

func TestGenerateNonPositiveDeep2(t *testing.T) {
	for _, n := range []int{0, -1, -100} {
		s, err := Generate(n)
		if err != nil {
			t.Fatalf("Generate(%d) 期望返回 (\"\", nil)，实际 err=%v", n, err)
		}
		if s != "" {
			t.Fatalf("Generate(%d) 期望空串，实际 %q", n, s)
		}
	}
}

func TestGenerateOneDeep2(t *testing.T) {
	s, err := Generate(1)
	if err != nil {
		t.Fatalf("Generate(1) 返回错误: %v", err)
	}
	if len(s) != 1 {
		t.Fatalf("Generate(1) 长度期望 1，实际 %d", len(s))
	}
	if !strings.ContainsRune(base62Chars, rune(s[0])) {
		t.Fatalf("Generate(1) 字符 %q 不在 base62Chars 中", s[0])
	}
}

func TestIsValidSlugHyphenUnderscoreDeep2(t *testing.T) {
	cases := []string{
		"a-b",
		"a_b",
		"-",
		"_",
		"abc-def_ghi",
		"ABC-123_xyz",
		"A_B-C",
	}
	for _, c := range cases {
		if !IsValidSlug(c) {
			t.Fatalf("IsValidSlug(%q) 期望 true，实际 false", c)
		}
	}
}

func TestIsValidSlugEmptyDeep2(t *testing.T) {
	if IsValidSlug("") {
		t.Fatalf("IsValidSlug(\"\") 期望 false，实际 true")
	}
}

func TestIsValidSlugLengthBoundaryDeep2(t *testing.T) {
	s64 := strings.Repeat("a", 64)
	if !IsValidSlug(s64) {
		t.Fatalf("IsValidSlug(64 个字符) 期望 true，实际 false")
	}
	s65 := strings.Repeat("a", 65)
	if IsValidSlug(s65) {
		t.Fatalf("IsValidSlug(65 个字符) 期望 false，实际 true")
	}
}

func TestIsValidSlugInvalidCharsDeep2(t *testing.T) {
	cases := []string{
		"has space",
		"中文",
		"a/b",
		"a.b",
		"a@b",
		"a+b",
		"a\nb",
		"  ",
	}
	for _, c := range cases {
		if IsValidSlug(c) {
			t.Fatalf("IsValidSlug(%q) 期望 false，实际 true", c)
		}
	}
}

func TestErrInvalidSlugMessageDeep2(t *testing.T) {
	const want = "invalid slug format"
	if ErrInvalidSlug == nil {
		t.Fatalf("ErrInvalidSlug 期望非 nil，实际 nil")
	}
	if got := ErrInvalidSlug.Error(); got != want {
		t.Fatalf("ErrInvalidSlug.Error() 期望 %q，实际 %q", want, got)
	}
}

func TestSlugPatternDefinitionDeep2(t *testing.T) {
	if slugPattern == nil {
		t.Fatalf("slugPattern 期望非 nil，实际 nil")
	}
	if slugPattern.String() != `^[A-Za-z0-9_-]{1,64}$` {
		t.Fatalf("slugPattern 期望 %q，实际 %q", `^[A-Za-z0-9_-]{1,64}$`, slugPattern.String())
	}
}

func TestBase62CharsDefinitionDeep2(t *testing.T) {
	if len(base62Chars) != 62 {
		t.Fatalf("base62Chars 长度期望 62，实际 %d", len(base62Chars))
	}
	if base62Chars != "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" {
		t.Fatalf("base62Chars 内容与期望不一致: %q", base62Chars)
	}
	seen := make(map[rune]struct{}, 62)
	for _, r := range base62Chars {
		if _, ok := seen[r]; ok {
			t.Fatalf("base62Chars 中存在重复字符 %q", r)
		}
		seen[r] = struct{}{}
	}
}

func TestGenerateMatchesSlugPatternDeep2(t *testing.T) {
	re := regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)
	for n := 1; n <= 64; n++ {
		s, err := Generate(n)
		if err != nil {
			t.Fatalf("Generate(%d) 返回错误: %v", n, err)
		}
		if !re.MatchString(s) {
			t.Fatalf("Generate(%d) 结果 %q 不匹配 slug 正则", n, s)
		}
		if !IsValidSlug(s) {
			t.Fatalf("Generate(%d) 结果 %q 期望 IsValidSlug 为 true，实际 false", n, s)
		}
	}
}
