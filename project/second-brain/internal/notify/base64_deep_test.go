package notify

import (
	"encoding/base64"
	"strings"
	"testing"
)

func TestBase64StdDeep(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{
			name: "empty string",
			in:   "",
			want: "",
		},
		{
			name: "ascii simple",
			in:   "hello",
			want: "aGVsbG8=",
		},
		{
			name: "chinese title",
			in:   "复习计划",
			want: "5aSN5Lmg6K6h5YiS",
		},
		{
			name: "emoji surrogate",
			in:   "📚",
			want: "8J+Tmg==",
		},
		{
			name: "wiki link nested",
			in:   "[[笔记A]] 引用 [[笔记B]]",
			want: "W1vnrJTorrBBXV0g5byV55SoIFtb56yU6K6wQl1d",
		},
		{
			name: "newline and tab",
			in:   "line1\nline2\tend",
			want: "bGluZTEKbGluZTIJZW5k",
		},
		{
			name: "single padding equals",
			in:   "ab",
			want: "YWI=",
		},
		{
			name: "double padding equals",
			in:   "a",
			want: "YQ==",
		},
		{
			name: "no padding three bytes",
			in:   "abc",
			want: "YWJj",
		},
		{
			name: "leap day 2024-02-29",
			in:   "2024-02-29",
			want: "MjAyNC0wMi0yOQ==",
		},
		{
			name: "timezone offset utc+8",
			in:   "2024-03-01T00:00:00+08:00",
			want: "MjAyNC0wMy0wMVQwMDowMDowMCswODowMA==",
		},
		{
			name: "zip slip path",
			in:   "../../../etc/passwd",
			want: "Li4vLi4vLi4vZXRjL3Bhc3N3ZA==",
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := base64Std(tc.in)

			if got != tc.want {
				t.Fatalf("base64Std(%q) = %q, want %q", tc.in, got, tc.want)
			}

			decoded, err := base64.StdEncoding.DecodeString(got)
			if err != nil {
				t.Fatalf("DecodeString(%q) unexpected error: %v", got, err)
			}

			if string(decoded) != tc.in {
				t.Fatalf("round trip decoded = %q, want %q", string(decoded), tc.in)
			}
		})
	}
}

func TestBase64StdStdEncodingAlphabet(t *testing.T) {
	in := "scheduling"
	got := base64Std(in)

	if strings.ContainsAny(got, "-_") {
		t.Fatalf("base64Std(%q) = %q, must not contain URL-safe chars '-' or '_'", in, got)
	}

	if !strings.HasSuffix(got, "=") {
		t.Fatalf("base64Std(%q) = %q, expected standard padding '='", in, got)
	}

	want := "c2NoZWR1bGluZw=="
	if got != want {
		t.Fatalf("base64Std(%q) = %q, want %q", in, got, want)
	}
}

func TestBase64StdDoesNotMutateInput(t *testing.T) {
	in := "[[双链]]"
	before := in
	_ = base64Std(in)

	if in != before {
		t.Fatalf("input mutated: before=%q after=%q", before, in)
	}

	got := base64Std(in)
	want := "W1vlj4zpk75dXQ=="
	if got != want {
		t.Fatalf("base64Std(%q) = %q, want %q", in, got, want)
	}
}
