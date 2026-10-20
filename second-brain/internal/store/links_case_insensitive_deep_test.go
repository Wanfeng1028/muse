package store

import (
	"testing"
)

func TestLinkCaseInsensitiveMatchPreservesOriginalCase(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "My Note", Body: "B 正文"})
	if err != nil {
		t.Fatalf("CreateNote(B) failed: %v", err)
	}
	if b.ID == 0 {
		t.Fatalf("expected B.ID nonzero, got %d", b.ID)
	}

	a, err := st.CreateNote(Note{Title: "A", Body: "看 [[my note]] 小写引用"})
	if err != nil {
		t.Fatalf("CreateNote(A) failed: %v", err)
	}
	if a.ID == 0 {
		t.Fatalf("expected A.ID nonzero, got %d", a.ID)
	}
	if a.ID == b.ID {
		t.Fatalf("expected distinct IDs for A and B, both got %d", a.ID)
	}

	bl, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(%d) failed: %v", b.ID, err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected len(bl)==1, got %d (%+v)", len(bl), bl)
	}
	if bl[0].ID != a.ID {
		t.Fatalf("expected bl[0].ID==%d (A), got %d", a.ID, bl[0].ID)
	}
	if bl[0].TargetTitle != "my note" {
		t.Fatalf("expected bl[0].TargetTitle==%q (original written case), got %q", "my note", bl[0].TargetTitle)
	}
}