package store

import (
	"strings"
	"testing"
)

func TestBacklinksBasic(t *testing.T) {
	s := newTestStore(t)

	b, err := s.CreateNote(Note{Title: "Beta", Body: "B 的正文"})
	if err != nil {
		t.Fatalf("CreateNote Beta: %v", err)
	}
	a, err := s.CreateNote(Note{Title: "Alpha", Body: "前言内容 [[Beta]] 后记内容"})
	if err != nil {
		t.Fatalf("CreateNote Alpha: %v", err)
	}

	got, err := s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("want 1 backlink, got %d", len(got))
	}
	bl := got[0]
	if bl.ID != a.ID {
		t.Errorf("ID = %d, want %d", bl.ID, a.ID)
	}
	if bl.Title != "Alpha" {
		t.Errorf("Title = %q, want %q", bl.Title, "Alpha")
	}
	if bl.TargetTitle != "Beta" {
		t.Errorf("TargetTitle = %q, want %q", bl.TargetTitle, "Beta")
	}
	if !strings.Contains(bl.Snippet, "[[Beta]]") {
		t.Errorf("Snippet %q should contain [[Beta]]", bl.Snippet)
	}
	if len([]rune(bl.Snippet)) > 2*snippetContextRunes+len([]rune("[[Beta]]"))+2 {
		t.Errorf("Snippet too long: %q (%d runes)", bl.Snippet, len([]rune(bl.Snippet)))
	}
	if bl.CreatedAt == "" {
		t.Errorf("CreatedAt should not be empty")
	}
}

func TestBacklinksNoReferences(t *testing.T) {
	s := newTestStore(t)

	b, err := s.CreateNote(Note{Title: "Beta", Body: "无引用"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := s.CreateNote(Note{Title: "Alpha", Body: "没有链接"}); err != nil {
		t.Fatalf("CreateNote Alpha: %v", err)
	}

	got, err := s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks: %v", err)
	}
	if got == nil {
		t.Fatalf("Backlinks returned nil, want non-nil empty slice")
	}
	if len(got) != 0 {
		t.Fatalf("want 0 backlinks, got %d", len(got))
	}
}

func TestBacklinksMultipleOrderedDesc(t *testing.T) {
	s := newTestStore(t)

	b, err := s.CreateNote(Note{Title: "Beta", Body: "目标"})
	if err != nil {
		t.Fatalf("CreateNote Beta: %v", err)
	}
	a, err := s.CreateNote(Note{Title: "Alpha", Body: "引用 [[Beta]] 一次"})
	if err != nil {
		t.Fatalf("CreateNote Alpha: %v", err)
	}
	c, err := s.CreateNote(Note{Title: "Charlie", Body: "引用 [[Beta]] 二次"})
	if err != nil {
		t.Fatalf("CreateNote Charlie: %v", err)
	}
	if !(a.ID < c.ID) {
		t.Fatalf("expected Alpha id %d < Charlie id %d", a.ID, c.ID)
	}

	got, err := s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("want 2 backlinks, got %d", len(got))
	}
	if got[0].ID != c.ID {
		t.Errorf("first backlink ID = %d, want %d (Charlie)", got[0].ID, c.ID)
	}
	if got[1].ID != a.ID {
		t.Errorf("second backlink ID = %d, want %d (Alpha)", got[1].ID, a.ID)
	}
}

func TestBacklinksAfterSourceDeleted(t *testing.T) {
	s := newTestStore(t)

	b, err := s.CreateNote(Note{Title: "Beta", Body: "目标"})
	if err != nil {
		t.Fatalf("CreateNote Beta: %v", err)
	}
	a, err := s.CreateNote(Note{Title: "Alpha", Body: "引用 [[Beta]]"})
	if err != nil {
		t.Fatalf("CreateNote Alpha: %v", err)
	}

	got, err := s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks before delete: %v", err)
	}
	if len(got) != 1 || got[0].ID != a.ID {
		t.Fatalf("before delete: want 1 backlink from %d, got %+v", a.ID, got)
	}

	if err := s.DeleteNote(a.ID); err != nil {
		t.Fatalf("DeleteNote: %v", err)
	}

	got, err = s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks after delete: %v", err)
	}
	if got == nil {
		t.Fatalf("after delete: got nil, want non-nil empty slice")
	}
	if len(got) != 0 {
		t.Fatalf("after delete: want 0 backlinks, got %d", len(got))
	}
}

func TestBacklinksAfterLinkRemoved(t *testing.T) {
	s := newTestStore(t)

	b, err := s.CreateNote(Note{Title: "Beta", Body: "目标"})
	if err != nil {
		t.Fatalf("CreateNote Beta: %v", err)
	}
	a, err := s.CreateNote(Note{Title: "Alpha", Body: "引用 [[Beta]] 存在"})
	if err != nil {
		t.Fatalf("CreateNote Alpha: %v", err)
	}

	got, err := s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks before update: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("before update: want 1, got %d", len(got))
	}

	a.Body = "现在没有链接了"
	if _, err := s.UpdateNote(a); err != nil {
		t.Fatalf("UpdateNote: %v", err)
	}

	got, err = s.Backlinks(b.ID)
	if err != nil {
		t.Fatalf("Backlinks after update: %v", err)
	}
	if got == nil {
		t.Fatalf("after update: got nil, want non-nil empty slice")
	}
	if len(got) != 0 {
		t.Fatalf("after update: want 0 backlinks, got %d", len(got))
	}
}

func TestBacklinksResolveOnCreate(t *testing.T) {
	s := newTestStore(t)

	a, err := s.CreateNote(Note{Title: "Alpha", Body: "先写 [[Gamma]] 稍后创建"})
	if err != nil {
		t.Fatalf("CreateNote Alpha: %v", err)
	}

	got, err := s.Backlinks(999999)
	if err != nil {
		t.Fatalf("Backlinks unknown id: %v", err)
	}
	if got == nil || len(got) != 0 {
		t.Fatalf("unknown id: want non-nil empty, got %+v", got)
	}

	g, err := s.CreateNote(Note{Title: "Gamma", Body: "目标出现"})
	if err != nil {
		t.Fatalf("CreateNote Gamma: %v", err)
	}

	got, err = s.Backlinks(g.ID)
	if err != nil {
		t.Fatalf("Backlinks Gamma: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("want 1 backlink for Gamma, got %d", len(got))
	}
	if got[0].ID != a.ID {
		t.Errorf("backlink ID = %d, want %d", got[0].ID, a.ID)
	}
	if got[0].TargetTitle != "Gamma" {
		t.Errorf("TargetTitle = %q, want %q", got[0].TargetTitle, "Gamma")
	}
	if !strings.Contains(got[0].Snippet, "[[Gamma]]") {
		t.Errorf("Snippet %q should contain [[Gamma]]", got[0].Snippet)
	}
}
