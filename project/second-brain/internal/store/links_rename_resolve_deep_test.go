package store

import "testing"

func TestRenameResolvesDanglingLink(t *testing.T) {
	st := newTestStore(t)

	a, err := st.CreateNote(Note{
		Title: "A",
		Body:  "等 [[未来标题]] 建好再看",
	})
	if err != nil {
		t.Fatalf("CreateNote(A) failed: %v", err)
	}
	if a.ID == 0 {
		t.Fatalf("CreateNote(A) returned zero ID, want non-zero")
	}

	b, err := st.CreateNote(Note{
		Title: "占位",
		Body:  "B 正文",
	})
	if err != nil {
		t.Fatalf("CreateNote(B) failed: %v", err)
	}
	if b.ID == 0 {
		t.Fatalf("CreateNote(B) returned zero ID, want non-zero")
	}

	blBefore, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(before rename) failed: %v", err)
	}
	if len(blBefore) != 0 {
		t.Fatalf("Backlinks(before rename) len = %d, want 0 (link should be dangling)", len(blBefore))
	}

	bg, err := st.GetNote(b.ID)
	if err != nil {
		t.Fatalf("GetNote(b) failed: %v", err)
	}
	if bg.Title != "占位" {
		t.Fatalf("GetNote(b).Title = %q, want %q", bg.Title, "占位")
	}
	bg.Title = "未来标题"

	updated, err := st.UpdateNote(bg)
	if err != nil {
		t.Fatalf("UpdateNote(rename to 未来标题) failed: %v", err)
	}
	if updated.Title != "未来标题" {
		t.Fatalf("UpdateNote returned Title = %q, want %q", updated.Title, "未来标题")
	}

	bl, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(after rename) failed: %v", err)
	}
	if len(bl) != 1 {
		t.Fatalf("Backlinks(after rename) len = %d, want 1 (dangling link should be resolved)", len(bl))
	}
	if bl[0].ID != a.ID {
		t.Fatalf("Backlinks(after rename)[0].ID = %d, want %d (note A)", bl[0].ID, a.ID)
	}
	if bl[0].TargetTitle != "未来标题" {
		t.Fatalf("Backlinks(after rename)[0].TargetTitle = %q, want %q", bl[0].TargetTitle, "未来标题")
	}
}