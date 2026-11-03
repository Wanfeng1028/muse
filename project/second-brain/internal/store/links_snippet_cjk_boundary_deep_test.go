package store

import (
	"strings"
	"testing"
)

func TestSnippetCJKLongLineRuneBoundary(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "目标", Body: "B"})
	if err != nil {
		t.Fatalf("CreateNote target failed: %v", err)
	}

	body := strings.Repeat("汉", 60) + "[[目标]]" + strings.Repeat("字", 60)
	a, err := st.CreateNote(Note{Title: "A", Body: body})
	if err != nil {
		t.Fatalf("CreateNote source failed: %v", err)
	}
	_ = a

	bl, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks failed: %v", err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected len(bl)==1, got %d", len(bl))
	}

	snip := bl[0].Snippet

	if !strings.HasPrefix(snip, "…") {
		t.Errorf("expected snippet to start with %q (leading context truncated), got %q", "…", snip)
	}
	if !strings.HasSuffix(snip, "…") {
		t.Errorf("expected snippet to end with %q (trailing context truncated), got %q", "…", snip)
	}
	if !strings.Contains(snip, "[[目标]]") {
		t.Errorf("expected snippet to contain %q, got %q", "[[目标]]", snip)
	}

	gotRunes := len([]rune(snip))
	if gotRunes != 88 {
		t.Errorf("expected len([]rune(snippet))==88 (1+40+6+40+1), got %d for snippet %q", gotRunes, snip)
	}
}