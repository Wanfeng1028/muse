package store

import "testing"

func TestSearchNotesMatchesTags(t *testing.T) {
	s := newTestStore(t)

	noteA, err := s.CreateNote(Note{
		Title: "普通标题",
		Body:  "普通正文",
		Tags:  []string{"量子"},
	})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}

	if _, err := s.CreateNote(Note{
		Title: "无关",
		Body:  "无关内容",
	}); err != nil {
		t.Fatalf("CreateNote B: %v", err)
	}

	byTag, err := s.SearchNotes("量子")
	if err != nil {
		t.Fatalf("SearchNotes 量子: %v", err)
	}
	if len(byTag) != 1 {
		t.Fatalf("SearchNotes 量子: got %d notes, want 1", len(byTag))
	}
	if byTag[0].ID != noteA.ID {
		t.Fatalf("SearchNotes 量子: got ID %d, want %d", byTag[0].ID, noteA.ID)
	}

	byTitle, err := s.SearchNotes("普通")
	if err != nil {
		t.Fatalf("SearchNotes 普通: %v", err)
	}
	if len(byTitle) != 1 {
		t.Fatalf("SearchNotes 普通: got %d notes, want 1", len(byTitle))
	}
	if byTitle[0].ID != noteA.ID {
		t.Fatalf("SearchNotes 普通: got ID %d, want %d", byTitle[0].ID, noteA.ID)
	}

	none, err := s.SearchNotes("不存在的词xyz")
	if err != nil {
		t.Fatalf("SearchNotes 不存在的词xyz: %v", err)
	}
	if len(none) != 0 {
		t.Fatalf("SearchNotes 不存在的词xyz: got %d notes, want 0", len(none))
	}
}
