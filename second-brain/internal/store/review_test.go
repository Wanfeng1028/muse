package store

import (
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/review"
)

func TestReviewRowAutoCreated(t *testing.T) {
	s := newTestStore(t)
	today := time.Now().UTC().Truncate(24 * time.Hour)

	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	st, err := s.GetReviewState(n.ID)
	if err != nil {
		t.Fatalf("GetReviewState failed: %v", err)
	}
	if st.EF != 2.5 {
		t.Errorf("EF = %v, want 2.5", st.EF)
	}
	if st.IntervalDays != 0 {
		t.Errorf("IntervalDays = %d, want 0", st.IntervalDays)
	}
	if st.Repetitions != 0 {
		t.Errorf("Repetitions = %d, want 0", st.Repetitions)
	}
	want := today.AddDate(0, 0, 1).Format("2006-01-02")
	if st.DueDate != want {
		t.Errorf("DueDate = %q, want %q", st.DueDate, want)
	}
}

func TestRecordReviewProgress(t *testing.T) {
	s := newTestStore(t)
	today := time.Now().UTC().Truncate(24 * time.Hour)

	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	st, err := s.RecordReview(n.ID, int(review.GradeGood), today)
	if err != nil {
		t.Fatalf("RecordReview(good) failed: %v", err)
	}
	if st.IntervalDays != 1 {
		t.Errorf("after Good IntervalDays = %d, want 1", st.IntervalDays)
	}
	want := today.AddDate(0, 0, 1).Format("2006-01-02")
	if st.DueDate != want {
		t.Errorf("after Good DueDate = %q, want %q", st.DueDate, want)
	}

	st2, err := s.RecordReview(n.ID, int(review.GradeEasy), today)
	if err != nil {
		t.Fatalf("RecordReview(easy) failed: %v", err)
	}
	if st2.IntervalDays != 6 {
		t.Errorf("after Easy IntervalDays = %d, want 6", st2.IntervalDays)
	}
}

func TestListDueReviews(t *testing.T) {
	s := newTestStore(t)
	today := time.Now().UTC().Truncate(24 * time.Hour)

	var ids []int64
	for i := 0; i < 3; i++ {
		n, err := s.CreateNote(Note{Title: "n", Body: "b"})
		if err != nil {
			t.Fatalf("CreateNote failed: %v", err)
		}
		ids = append(ids, n.ID)
	}

	past1 := today.AddDate(0, 0, -3).Format("2006-01-02")
	past2 := today.AddDate(0, 0, -1).Format("2006-01-02")
	if _, err := s.db.Exec(`UPDATE reviews SET due_date = ? WHERE note_id = ?`, past1, ids[0]); err != nil {
		t.Fatalf("update due_date failed: %v", err)
	}
	if _, err := s.db.Exec(`UPDATE reviews SET due_date = ? WHERE note_id = ?`, past2, ids[1]); err != nil {
		t.Fatalf("update due_date failed: %v", err)
	}

	due, err := s.ListDueReviews(today, 10)
	if err != nil {
		t.Fatalf("ListDueReviews failed: %v", err)
	}
	if len(due) != 2 {
		t.Fatalf("len(due) = %d, want 2", len(due))
	}
	if due[0].DueDate > due[1].DueDate {
		t.Errorf("due reviews not sorted ascending: %q then %q", due[0].DueDate, due[1].DueDate)
	}
	for _, d := range due {
		if d.OverdueDays < 0 {
			t.Errorf("OverdueDays = %d, want >= 0", d.OverdueDays)
		}
	}
}

func TestReviewCascadeDelete(t *testing.T) {
	s := newTestStore(t)

	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if err := s.DeleteNote(n.ID); err != nil {
		t.Fatalf("DeleteNote failed: %v", err)
	}
	if _, err := s.GetReviewState(n.ID); err != ErrNotFound {
		t.Errorf("GetReviewState after delete err = %v, want ErrNotFound", err)
	}
}

func TestReviewStats(t *testing.T) {
	s := newTestStore(t)
	today := time.Now().UTC().Truncate(24 * time.Hour)

	n1, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	n2, err := s.CreateNote(Note{Title: "n2", Body: "b2"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := s.CreateNote(Note{Title: "n3", Body: "b3"}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	if _, err := s.db.Exec(`UPDATE reviews SET due_date = ? WHERE note_id = ?`, today.Format("2006-01-02"), n1.ID); err != nil {
		t.Fatalf("update due_date failed: %v", err)
	}
	if _, err := s.RecordReview(n2.ID, int(review.GradeGood), today); err != nil {
		t.Fatalf("RecordReview failed: %v", err)
	}

	stats, err := s.ReviewStats(today)
	if err != nil {
		t.Fatalf("ReviewStats failed: %v", err)
	}
	if stats.DueToday < 1 {
		t.Errorf("DueToday = %d, want >= 1", stats.DueToday)
	}
	if stats.TotalNotes != 3 {
		t.Errorf("TotalNotes = %d, want 3", stats.TotalNotes)
	}
	if stats.Reviewed7d < 1 {
		t.Errorf("Reviewed7d = %d, want >= 1", stats.Reviewed7d)
	}
	if !(stats.AvgEF > 0) {
		t.Errorf("AvgEF = %v, want > 0", stats.AvgEF)
	}
	if stats.StreakDays < 1 {
		t.Errorf("StreakDays = %d, want >= 1", stats.StreakDays)
	}
}

func TestDigestNotes(t *testing.T) {
	s := newTestStore(t)
	today := time.Now().UTC().Truncate(24 * time.Hour)

	overdue, err := s.CreateNote(Note{Title: "overdue", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := s.db.Exec(`UPDATE reviews SET due_date = ? WHERE note_id = ?`, today.AddDate(0, 0, -5).Format("2006-01-02"), overdue.ID); err != nil {
		t.Fatalf("update due_date failed: %v", err)
	}
	if _, err := s.CreateNote(Note{Title: "future1", Body: "b"}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if _, err := s.CreateNote(Note{Title: "future2", Body: "b"}); err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	digest, err := s.DigestNotes(today, 10)
	if err != nil {
		t.Fatalf("DigestNotes failed: %v", err)
	}
	if len(digest) == 0 {
		t.Fatalf("DigestNotes returned empty")
	}
	if digest[0].ID != overdue.ID {
		t.Errorf("digest[0].ID = %d, want overdue note %d", digest[0].ID, overdue.ID)
	}

	all, err := s.DigestNotes(today, 1000)
	if err != nil {
		t.Fatalf("DigestNotes large n failed: %v", err)
	}
	if len(all) != 3 {
		t.Errorf("len(all) = %d, want 3", len(all))
	}
}

func TestRecordReviewErrors(t *testing.T) {
	s := newTestStore(t)
	today := time.Now().UTC().Truncate(24 * time.Hour)

	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}

	if _, err := s.RecordReview(n.ID, 6, today); err == nil {
		t.Errorf("RecordReview(grade=6) err = nil, want error")
	}

	if _, err := s.RecordReview(999999, int(review.GradeGood), today); err != ErrNotFound {
		t.Errorf("RecordReview(missing) err = %v, want ErrNotFound", err)
	}
}
