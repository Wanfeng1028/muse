package store

import (
	"strings"
	"testing"
)

func TestNormalizeUser_TrimAndLower(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"leading and trailing spaces", "  Alice  ", "alice"},
		{"mixed case", "ALICE", "alice"},
		{"mixed case with spaces", "  AlIcE  ", "alice"},
		{"tab and newline", "\tBob\n", "bob"},
		{"only spaces", "     ", DefaultUser},
		{"carriage return", "\r\nCarol\r\n", "carol"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := NormalizeUser(tc.in)
			if got != tc.want {
				t.Fatalf("NormalizeUser(%q) = %q, want %q", tc.in, got, tc.want)
			}
			if got != strings.ToLower(strings.TrimSpace(tc.in)) && tc.in != "" && strings.TrimSpace(tc.in) != "" {
				t.Fatalf("result %q not equal to lowercase trimmed input %q", got, strings.ToLower(strings.TrimSpace(tc.in)))
			}
		})
	}
}

func TestNormalizeUser_EmptyFallback(t *testing.T) {
	cases := []struct {
		name string
		in   string
	}{
		{"empty string", ""},
		{"single space", " "},
		{"multiple spaces", "        "},
		{"tab only", "\t"},
		{"newline only", "\n"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := NormalizeUser(tc.in)
			if got != DefaultUser {
				t.Fatalf("NormalizeUser(%q) = %q, want %q", tc.in, got, DefaultUser)
			}
			if got == "" {
				t.Fatalf("NormalizeUser(%q) returned empty string, must fall back to %q", tc.in, DefaultUser)
			}
		})
	}
}

func TestNormalizeUser_TruncateAt64(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"exactly 64", strings.Repeat("a", 64), strings.Repeat("a", 64)},
		{"65 chars", strings.Repeat("a", 65), strings.Repeat("a", 64)},
		{"100 chars", strings.Repeat("b", 100), strings.Repeat("b", 64)},
		{"64 then spaces then 10", strings.Repeat("c", 64) + "          ", strings.Repeat("c", 64)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := NormalizeUser(tc.in)
			if got != tc.want {
				t.Fatalf("NormalizeUser(len=%d) = %q (len=%d), want %q (len=%d)", len(tc.in), got, len(got), tc.want, len(tc.want))
			}
			if len(got) > 64 {
				t.Fatalf("NormalizeUser result length %d exceeds 64", len(got))
			}
		})
	}
}

func TestNormalizeUser_TruncateAfterTrim(t *testing.T) {
	in := "   " + strings.Repeat("D", 70) + "   "
	got := NormalizeUser(in)
	want := strings.Repeat("d", 64)
	if got != want {
		t.Fatalf("NormalizeUser(trim then truncate) = %q, want %q", got, want)
	}
	if strings.ContainsAny(got, " \t\n\r") {
		t.Fatalf("result %q still contains whitespace after normalization", got)
	}
}

func TestNormalizeUser_UnicodeLengthSemantics(t *testing.T) {
	// 注：产品按字节截断（len(user) 为字节数），64 个中文（192 字节）会被截断到 64 字节。
	// 这可能切分 UTF-8 序列，是已知边界行为，此处仅锁定当前语义。
	cn := strings.Repeat("张", 64)
	got := NormalizeUser(cn)
	if len(got) != 64 {
		t.Fatalf("NormalizeUser(64 chinese chars) 应按字节截断到 64，实际 len=%d", len(got))
	}

	cnLong := strings.Repeat("张", 70)
	gotLong := NormalizeUser(cnLong)
	if len(gotLong) != 64 {
		t.Fatalf("expected truncation to 64 bytes, got %d bytes", len(gotLong))
	}
	if gotLong != cnLong[:64] {
		t.Fatalf("expected byte truncation of original string, got %q", gotLong)
	}
}

func TestNormalizeUser_DefaultConstantIsLocal(t *testing.T) {
	if DefaultUser != "local" {
		t.Fatalf("DefaultUser = %q, want %q", DefaultUser, "local")
	}
	if NormalizeUser("") != DefaultUser {
		t.Fatalf("empty input must map to DefaultUser %q", DefaultUser)
	}
	if NormalizeUser(DefaultUser) != DefaultUser {
		t.Fatalf("DefaultUser %q must be idempotent under NormalizeUser", DefaultUser)
	}
}

func TestNormalizeUser_MultiUserIsolationByDistinctKeys(t *testing.T) {
	users := []string{"Alice", "alice", " ALICE ", "Bob", "bob", "Carol"}
	seen := make(map[string]string)
	for _, u := range users {
		norm := NormalizeUser(u)
		if prev, ok := seen[norm]; ok {
			if norm != "alice" && norm != "bob" {
				t.Fatalf("unexpected collision: %q and %q both normalize to %q", prev, u, norm)
			}
		}
		seen[norm] = u
	}
	if _, ok := seen["alice"]; !ok {
		t.Fatalf("alice variants did not collapse to key %q", "alice")
	}
	if _, ok := seen["bob"]; !ok {
		t.Fatalf("bob variants did not collapse to key %q", "bob")
	}
	if _, ok := seen["carol"]; !ok {
		t.Fatalf("carol key missing")
	}
	if len(seen) != 3 {
		t.Fatalf("expected 3 distinct user keys after normalization, got %d: %v", len(seen), seen)
	}
}

func TestNormalizeUser_Idempotent(t *testing.T) {
	inputs := []string{
		"",
		"  ",
		"Alice",
		"  ALICE  ",
		strings.Repeat("x", 100),
		"\tBob\n",
		"local",
		"LOCAL",
	}
	for _, in := range inputs {
		once := NormalizeUser(in)
		twice := NormalizeUser(once)
		if once != twice {
			t.Fatalf("NormalizeUser not idempotent for %q: once=%q twice=%q", in, once, twice)
		}
	}
}

func TestNormalizeUser_NoWhitespaceInOutput(t *testing.T) {
	inputs := []string{
		"  Alice  ",
		"\t\nBob\r\n",
		"    ",
		"",
		"  " + strings.Repeat("Z", 80) + "  ",
	}
	for _, in := range inputs {
		got := NormalizeUser(in)
		if got != strings.TrimSpace(got) {
			t.Fatalf("NormalizeUser(%q) = %q still has surrounding whitespace", in, got)
		}
		if strings.ContainsAny(got, " \t\n\r") && got != DefaultUser {
			t.Fatalf("NormalizeUser(%q) = %q contains internal whitespace, expected none", in, got)
		}
	}
}

func TestNormalizeUser_TruncationBoundaryExact(t *testing.T) {
	for n := 63; n <= 66; n++ {
		in := strings.Repeat("q", n)
		got := NormalizeUser(in)
		if n <= 64 {
			if got != in {
				t.Fatalf("len=%d expected unchanged, got len=%d", n, len(got))
			}
		} else {
			if got != in[:64] {
				t.Fatalf("len=%d expected truncate to 64, got len=%d", n, len(got))
			}
		}
		if len(got) > 64 {
			t.Fatalf("len=%d produced result length %d over 64", n, len(got))
		}
	}
}
