package web

import (
	"io/fs"
	"strings"
	"testing"
)

// TestStyleCSSAlertRuleClosed asserts the v0.18.1 fix: style.css ends with
// a closed .alert rule and its braces balance overall. Before the fix the
// file ended with an unclosed .alert rule (118 '{' vs 117 '}'), which a CSS
// parser drops; no page renders an .alert element, so the fix changes no
// visible page, it only restores stylesheet validity.
func TestStyleCSSAlertRuleClosed(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/style.css")
	if err != nil {
		t.Fatalf("read style.css: %v", err)
	}
	s := string(data)
	if open, close := strings.Count(s, "{"), strings.Count(s, "}"); open != close {
		t.Errorf("style.css braces unbalanced: %d '{' vs %d '}'", open, close)
	}
	idx := strings.LastIndex(s, ".alert {")
	if idx < 0 {
		t.Fatalf("style.css: .alert rule missing")
	}
	rest := s[idx:]
	if !strings.Contains(rest, "padding: var(--space-3) var(--space-4);") {
		t.Errorf("style.css: .alert rule lost its padding declaration")
	}
	if !strings.Contains(rest, "}") {
		t.Errorf("style.css: .alert rule still unclosed")
	}
	if tail := strings.TrimSpace(s); !strings.HasSuffix(tail, "}") {
		t.Errorf("style.css: file must end with the closed .alert rule, ends with %q", tail[len(tail)-20:])
	}
}
