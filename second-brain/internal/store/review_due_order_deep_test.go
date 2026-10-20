package store

import (
	"context"
	"testing"
	"time"
)

func TestListDueReviews_OrderByDueThenInterval(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()

	noteA, err := st.CreateNote(Note{Title: "A"})
	if err != nil {
		t.Fatalf("CreateNote A failed: %v", err)
	}
	noteB, err := st.CreateNote(Note{Title: "B"})
	if err != nil {
		t.Fatalf("CreateNote B failed: %v", err)
	}
	noteC, err := st.CreateNote(Note{Title: "C"})
	if err != nil {
		t.Fatalf("CreateNote C failed: %v", err)
	}

	day1 := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	day2 := time.Date(2026, 6, 2, 0, 0, 0, 0, time.UTC)
	day7 := time.Date(2026, 6, 7, 0, 0, 0, 0, time.UTC)
	day9 := time.Date(2026, 6, 9, 0, 0, 0, 0, time.UTC)

	if _, err := st.RecordReview(ctx, noteA.ID, 5, day1, DefaultUser); err != nil {
		t.Fatalf("RecordReview A day1 failed: %v", err)
	}
	stateA, err := st.RecordReview(ctx, noteA.ID, 5, day2, DefaultUser)
	if err != nil {
		t.Fatalf("RecordReview A day2 failed: %v", err)
	}
	if stateA.DueDate != "2026-06-08" {
		t.Fatalf("A DueDate expected 2026-06-08, got %q", stateA.DueDate)
	}
	if stateA.IntervalDays != 6 {
		t.Fatalf("A IntervalDays expected 6, got %d", stateA.IntervalDays)
	}

	stateB, err := st.RecordReview(ctx, noteB.ID, 5, day7, DefaultUser)
	if err != nil {
		t.Fatalf("RecordReview B failed: %v", err)
	}
	if stateB.DueDate != "2026-06-08" {
		t.Fatalf("B DueDate expected 2026-06-08, got %q", stateB.DueDate)
	}
	if stateB.IntervalDays != 1 {
		t.Fatalf("B IntervalDays expected 1, got %d", stateB.IntervalDays)
	}

	stateC, err := st.RecordReview(ctx, noteC.ID, 5, day9, DefaultUser)
	if err != nil {
		t.Fatalf("RecordReview C failed: %v", err)
	}
	if stateC.DueDate != "2026-06-10" {
		t.Fatalf("C DueDate expected 2026-06-10, got %q", stateC.DueDate)
	}
	if stateC.IntervalDays != 1 {
		t.Fatalf("C IntervalDays expected 1, got %d", stateC.IntervalDays)
	}

	today := time.Date(2026, 6, 10, 0, 0, 0, 0, time.UTC)
	due, err := st.ListDueReviews(today, 50, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews(2026-06-10) failed: %v", err)
	}
	if len(due) != 3 {
		t.Fatalf("ListDueReviews(2026-06-10) expected 3 results, got %d", len(due))
	}

	expectedOrder := []int64{noteB.ID, noteA.ID, noteC.ID}
	expectedDue := []string{"2026-06-08", "2026-06-08", "2026-06-10"}
	expectedInterval := []int{1, 6, 1}

	for i, want := range expectedOrder {
		if due[i].Note.ID != want {
			t.Fatalf("result[%d].Note.ID expected %d, got %d", i, want, due[i].Note.ID)
		}
		if due[i].DueDate != expectedDue[i] {
			t.Fatalf("result[%d].DueDate expected %q, got %q", i, expectedDue[i], due[i].DueDate)
		}
		if due[i].IntervalDays != expectedInterval[i] {
			t.Fatalf("result[%d].IntervalDays expected %d, got %d", i, expectedInterval[i], due[i].IntervalDays)
		}
	}

	earlier := time.Date(2026, 6, 7, 0, 0, 0, 0, time.UTC)
	empty, err := st.ListDueReviews(earlier, 50, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews(2026-06-07) failed: %v", err)
	}
	if len(empty) != 0 {
		t.Fatalf("ListDueReviews(2026-06-07) expected 0 results (none due yet), got %d", len(empty))
	}
}