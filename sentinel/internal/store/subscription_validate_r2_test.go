package store

import (
	"strings"
	"testing"
)

func TestR2_NormalizeEmail(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{name: "trim_and_lower", in: "  Foo@Bar.COM ", want: "foo@bar.com"},
		{name: "already_normalized", in: "A@b.c", want: "a@b.c"},
		{name: "trim_edges", in: "  x@y.zz  ", want: "x@y.zz"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := NormalizeEmail(tt.in); got != tt.want {
				t.Fatalf("NormalizeEmail(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

func TestR2_ValidEmailBoundary(t *testing.T) {
	maxEmail := strings.Repeat("a", 64) + "@" + strings.Repeat("b", 63) + "." + strings.Repeat("c", 63) + "." + strings.Repeat("d", 61)
	if len(maxEmail) != 254 {
		t.Fatalf("maxEmail length = %d, want 254", len(maxEmail))
	}

	tests := []struct {
		name  string
		email string
		want  bool
	}{
		{name: "minimal_valid", email: "a@b.c", want: true},
		{name: "max_length_valid", email: maxEmail, want: true},
		{name: "too_short", email: "ab", want: false},
		{name: "two_at", email: "a@@b.c", want: false},
		{name: "no_dot_after_at", email: "a@bc", want: false},
		{name: "contains_space", email: "a@b .c", want: false},
		{name: "too_long", email: strings.Repeat("a", 250) + "@b.cd", want: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ValidEmail(tt.email); got != tt.want {
				t.Fatalf("ValidEmail(len=%d) = %v, want %v", len(tt.email), got, tt.want)
			}
		})
	}
}

func TestR2_NewSubscriptionToken(t *testing.T) {
	tok, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken() error = %v", err)
	}
	if len(tok) != 64 {
		t.Fatalf("token length = %d, want 64", len(tok))
	}

	tok2, err := NewSubscriptionToken()
	if err != nil {
		t.Fatalf("NewSubscriptionToken() second call error = %v", err)
	}
	if tok == tok2 {
		t.Fatalf("two generated tokens are equal: %q", tok)
	}
}
