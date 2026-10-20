package store

import (
	"testing"
)

func TestSnippetFallbackWhenLinkRemovedFromBody(t *testing.T) {
	st := newTestStore(t)

	b, err := st.CreateNote(Note{Title: "B", Body: "B 正文"})
	if err != nil {
		t.Fatalf("CreateNote(B) failed: %v", err)
	}

	a, err := st.CreateNote(Note{Title: "A", Body: "第一行有 [[B]] 链接"})
	if err != nil {
		t.Fatalf("CreateNote(A) failed: %v", err)
	}

	bl, err := st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(b.ID) before body change failed: %v", err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected 1 backlink before body change, got %d", len(bl))
	}
	if bl[0].Snippet == "全新正文没有链接标记了" {
		t.Fatalf("unexpected snippet already equal to new body before change: %q", bl[0].Snippet)
	}

	newBody := "全新正文没有链接标记了"
	if _, err := st.db.Exec(`UPDATE notes SET body=? WHERE id=?`, newBody, a.ID); err != nil {
		t.Fatalf("UPDATE notes body failed: %v", err)
	}

	bl, err = st.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks(b.ID) after body change failed: %v", err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected 1 backlink after body change, got %d", len(bl))
	}
	if bl[0].ID != a.ID {
		t.Fatalf("expected backlink source id=%d, got %d", a.ID, bl[0].ID)
	}
	if bl[0].Title != "A" {
		t.Fatalf("expected backlink source title=%q, got %q", "A", bl[0].Title)
	}
	if bl[0].TargetTitle != "B" {
		t.Fatalf("expected backlink target title=%q, got %q", "B", bl[0].TargetTitle)
	}
	if bl[0].Snippet != newBody {
		t.Fatalf("expected snippet fallback to new body %q, got %q", newBody, bl[0].Snippet)
	}
}