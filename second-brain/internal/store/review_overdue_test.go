package store

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func TestListOverdueReviews_EmptyStore(t *testing.T) {
	s := newTestStore(t)
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	got, err := s.ListOverdueReviews(base, 50, DefaultUser)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got == nil {
		t.Errorf("expected non-nil empty slice, got nil")
	}
	if len(got) != 0 {
		t.Errorf("expected 0 items, got %d", len(got))
	}
}

func TestListOverdueReviews_FilterOrderAndUser(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	seq := 0
	createWithDue := func(user string, dueOffset int) string {
		seq++
		title := fmt.Sprintf("note-%d", seq)
		note, err := s.CreateNote(Note{Title: title, Body: "body"})
		if err != nil {
			t.Fatalf("CreateNote: %v", err)
		}
		if _, err := s.RecordReview(ctx, note.ID, 3, base, user); err != nil {
			t.Fatalf("RecordReview: %v", err)
		}
		dueStr := base.AddDate(0, 0, dueOffset).Format("2006-01-02")
		if _, err := s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, dueStr, note.ID, user); err != nil {
			t.Fatalf("UPDATE reviews: %v", err)
		}
		return title
	}

	overdue10 := createWithDue(DefaultUser, -10)
	overdue1 := createWithDue(DefaultUser, -1)
	createWithDue(DefaultUser, 0)
	createWithDue(DefaultUser, 1)
	createWithDue("other-user", -5)

	got, err := s.ListOverdueReviews(base, 50, DefaultUser)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 overdue items, got %d", len(got))
	}
	if got[0].Note.Title != overdue10 || got[0].OverdueDays != 10 {
		t.Errorf("got[0] = %q overdueDays %d, want %q 10", got[0].Note.Title, got[0].OverdueDays, overdue10)
	}
	if got[1].Note.Title != overdue1 || got[1].OverdueDays != 1 {
		t.Errorf("got[1] = %q overdueDays %d, want %q 1", got[1].Note.Title, got[1].OverdueDays, overdue1)
	}
	if got[0].Note.Tags == nil {
		t.Errorf("expected non-nil Tags for overdue item")
	}
}

func TestListOverdueReviews_LimitClamping(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	for i := 0; i < 3; i++ {
		note, err := s.CreateNote(Note{Title: fmt.Sprintf("n%d", i), Body: "b"})
		if err != nil {
			t.Fatalf("CreateNote: %v", err)
		}
		if _, err := s.RecordReview(ctx, note.ID, 3, base, DefaultUser); err != nil {
			t.Fatalf("RecordReview: %v", err)
		}
		dueStr := base.AddDate(0, 0, -1-i).Format("2006-01-02")
		if _, err := s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, dueStr, note.ID, DefaultUser); err != nil {
			t.Fatalf("UPDATE reviews: %v", err)
		}
	}

	if got, _ := s.ListOverdueReviews(base, 1, DefaultUser); len(got) != 1 {
		t.Errorf("limit=1: got %d items, want 1", len(got))
	}
	if got, _ := s.ListOverdueReviews(base, 0, DefaultUser); len(got) != 3 {
		t.Errorf("limit=0 (default 50): got %d items, want 3", len(got))
	}
	if got, _ := s.ListOverdueReviews(base, 999, DefaultUser); len(got) != 3 {
		t.Errorf("limit=999 (clamped to 200): got %d items, want 3", len(got))
	}
}
