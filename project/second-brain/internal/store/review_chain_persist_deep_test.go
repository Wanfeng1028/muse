package store

import (
	"context"
	"math"
	"testing"
	"time"
)

func TestReviewChainPersistAcrossDays(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()

	note, err := st.CreateNote(Note{Title: "持久化链", Body: "内容"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if note.ID == 0 {
		t.Fatalf("expected non-zero note ID, got %d", note.ID)
	}

	day1 := time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC)
	day2 := time.Date(2026, 5, 2, 0, 0, 0, 0, time.UTC)
	day3 := time.Date(2026, 5, 8, 0, 0, 0, 0, time.UTC)
	day4 := time.Date(2026, 5, 9, 0, 0, 0, 0, time.UTC)
	day12 := time.Date(2026, 5, 12, 0, 0, 0, 0, time.UTC)

	// 第一天：grade=5 → Repetitions=1, IntervalDays=1, DueDate=2026-05-02
	s1, err := st.RecordReview(ctx, note.ID, 5, day1, DefaultUser)
	if err != nil {
		t.Fatalf("RecordReview day1 failed: %v", err)
	}
	if s1.Repetitions != 1 {
		t.Fatalf("day1 Repetitions: want 1, got %d", s1.Repetitions)
	}
	if s1.IntervalDays != 1 {
		t.Fatalf("day1 IntervalDays: want 1, got %d", s1.IntervalDays)
	}
	if s1.DueDate != "2026-05-02" {
		t.Fatalf("day1 DueDate: want 2026-05-02, got %q", s1.DueDate)
	}

	// 落库重读：应与返回值一致
	got1, err := st.GetReviewState(note.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetReviewState after day1 failed: %v", err)
	}
	if got1.Repetitions != 1 {
		t.Fatalf("persisted day1 Repetitions: want 1, got %d", got1.Repetitions)
	}
	if got1.IntervalDays != 1 {
		t.Fatalf("persisted day1 IntervalDays: want 1, got %d", got1.IntervalDays)
	}
	if got1.DueDate != "2026-05-02" {
		t.Fatalf("persisted day1 DueDate: want 2026-05-02, got %q", got1.DueDate)
	}
	if math.Abs(got1.EF-s1.EF) > 1e-9 {
		t.Fatalf("persisted day1 EF: want %v, got %v", s1.EF, got1.EF)
	}

	// 第二天：grade=5 → Repetitions=2, IntervalDays=6, DueDate=2026-05-08
	s2, err := st.RecordReview(ctx, note.ID, 5, day2, DefaultUser)
	if err != nil {
		t.Fatalf("RecordReview day2 failed: %v", err)
	}
	if s2.Repetitions != 2 {
		t.Fatalf("day2 Repetitions: want 2, got %d", s2.Repetitions)
	}
	if s2.IntervalDays != 6 {
		t.Fatalf("day2 IntervalDays: want 6, got %d", s2.IntervalDays)
	}
	if s2.DueDate != "2026-05-08" {
		t.Fatalf("day2 DueDate: want 2026-05-08, got %q", s2.DueDate)
	}

	got2, err := st.GetReviewState(note.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetReviewState after day2 failed: %v", err)
	}
	if got2.Repetitions != 2 {
		t.Fatalf("persisted day2 Repetitions: want 2, got %d", got2.Repetitions)
	}
	if got2.IntervalDays != 6 {
		t.Fatalf("persisted day2 IntervalDays: want 6, got %d", got2.IntervalDays)
	}
	if got2.DueDate != "2026-05-08" {
		t.Fatalf("persisted day2 DueDate: want 2026-05-08, got %q", got2.DueDate)
	}

	// 第三天：grade=0 → Repetitions=0, IntervalDays=1, DueDate=2026-05-09
	s3, err := st.RecordReview(ctx, note.ID, 0, day3, DefaultUser)
	if err != nil {
		t.Fatalf("RecordReview day3 failed: %v", err)
	}
	if s3.Repetitions != 0 {
		t.Fatalf("day3 Repetitions: want 0, got %d", s3.Repetitions)
	}
	if s3.IntervalDays != 1 {
		t.Fatalf("day3 IntervalDays: want 1, got %d", s3.IntervalDays)
	}
	if s3.DueDate != "2026-05-09" {
		t.Fatalf("day3 DueDate: want 2026-05-09, got %q", s3.DueDate)
	}

	got3, err := st.GetReviewState(note.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetReviewState after day3 failed: %v", err)
	}
	if got3.Repetitions != 0 {
		t.Fatalf("persisted day3 Repetitions: want 0, got %d", got3.Repetitions)
	}
	if got3.IntervalDays != 1 {
		t.Fatalf("persisted day3 IntervalDays: want 1, got %d", got3.IntervalDays)
	}
	if got3.DueDate != "2026-05-09" {
		t.Fatalf("persisted day3 DueDate: want 2026-05-09, got %q", got3.DueDate)
	}

	// ListDueReviews(day4=2026-05-09)：笔记到期，OverdueDays=0
	due1, err := st.ListDueReviews(day4, 50, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews day4 failed: %v", err)
	}
	found1 := false
	for _, dr := range due1 {
		if dr.Note.ID == note.ID {
			found1 = true
			if dr.DueDate != "2026-05-09" {
				t.Fatalf("ListDueReviews day4 DueDate: want 2026-05-09, got %q", dr.DueDate)
			}
			if dr.OverdueDays != 0 {
				t.Fatalf("ListDueReviews day4 OverdueDays: want 0, got %d", dr.OverdueDays)
			}
		}
	}
	if !found1 {
		t.Fatalf("ListDueReviews day4: note %d not found in due list", note.ID)
	}

	// ListDueReviews(2026-05-12)：同一笔记 OverdueDays=3
	due2, err := st.ListDueReviews(day12, 50, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews day12 failed: %v", err)
	}
	found2 := false
	for _, dr := range due2 {
		if dr.Note.ID == note.ID {
			found2 = true
			if dr.DueDate != "2026-05-09" {
				t.Fatalf("ListDueReviews day12 DueDate: want 2026-05-09, got %q", dr.DueDate)
			}
			if dr.OverdueDays != 3 {
				t.Fatalf("ListDueReviews day12 OverdueDays: want 3, got %d", dr.OverdueDays)
			}
		}
	}
	if !found2 {
		t.Fatalf("ListDueReviews day12: note %d not found in due list", note.ID)
	}
}