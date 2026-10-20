package store

import (
	"testing"
)

func TestRenameTargetKeepsResolvedLinks(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "B", Body: "B 正文"})
	if err != nil {
		t.Fatalf("CreateNote(B) failed: %v", err)
	}
	if b.ID == 0 {
		t.Fatalf("CreateNote(B) returned zero ID, want non-zero")
	}

	a, err := st.CreateNote(Note{Title: "A", Body: "看 [[B]]"})
	if err != nil {
		t.Fatalf("CreateNote(A) failed: %v", err)
	}
	if a.ID == 0 {
		t.Fatalf("CreateNote(A) returned zero ID, want non-zero")
	}

	bg, err := st.GetNote(b.ID)
	if err != nil {
		t.Fatalf("GetNote(b.ID=%d) failed: %v", b.ID, err)
	}
	bg.Title = "B新标题"
	updated, err := st.UpdateNote(bg)
	if err != nil {
		t.Fatalf("UpdateNote(rename B to %q) failed: %v", bg.Title, err)
	}
	if updated.Title != "B新标题" {
		t.Fatalf("UpdateNote returned Title=%q, want %q", updated.Title, "B新标题")
	}

	bl, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(b.ID=%d) failed: %v", b.ID, err)
	}
	if len(bl) != 1 {
		t.Fatalf("Backlinks(b.ID=%d) len=%d, want 1 (backlink must stay ID-anchored after rename)", b.ID, len(bl))
	}
	if bl[0].ID != a.ID {
		t.Fatalf("Backlinks(b.ID=%d)[0].ID=%d, want a.ID=%d", b.ID, bl[0].ID, a.ID)
	}

	gd, err := st.Graph()
	if err != nil {
		t.Fatalf("Graph() failed: %v", err)
	}
	found := false
	for _, e := range gd.Edges {
		if e.Source == a.ID && e.Target == b.ID {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("Graph() Edges missing {Source:%d, Target:%d} after target rename; edges=%v", a.ID, b.ID, gd.Edges)
	}
}