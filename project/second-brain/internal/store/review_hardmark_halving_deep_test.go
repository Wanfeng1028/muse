package store

import (
	"context"
	"math"
	"testing"
	"time"
)

func TestHardMarkHalvingOnlyOnGrade3(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	user := DefaultUser

	// 创建两条笔记：H 会被标记困难，N 作为对照组不标记。
	hNote, err := st.CreateNote(Note{Title: "hard", Body: "h"})
	if err != nil {
		t.Fatalf("CreateNote H failed: %v", err)
	}
	nNote, err := st.CreateNote(Note{Title: "normal", Body: "n"})
	if err != nil {
		t.Fatalf("CreateNote N failed: %v", err)
	}

	// 标记 H 为困难卡片。
	if err := st.SetHardMark(hNote.ID, user, true); err != nil {
		t.Fatalf("SetHardMark(true) failed: %v", err)
	}

	// --- 笔记 H：grade=5 两次，均不应减半 ---
	h1, err := st.RecordReview(ctx, hNote.ID, 5, time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("H RecordReview grade=5 #1 failed: %v", err)
	}
	if h1.Repetitions != 1 {
		t.Fatalf("H grade=5 #1 Repetitions: want 1, got %d", h1.Repetitions)
	}
	if h1.IntervalDays != 1 {
		t.Fatalf("H grade=5 #1 IntervalDays: want 1, got %d", h1.IntervalDays)
	}

	h2, err := st.RecordReview(ctx, hNote.ID, 5, time.Date(2026, 7, 2, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("H RecordReview grade=5 #2 failed: %v", err)
	}
	if h2.Repetitions != 2 {
		t.Fatalf("H grade=5 #2 Repetitions: want 2, got %d", h2.Repetitions)
	}
	if h2.IntervalDays != 6 {
		t.Fatalf("H grade=5 #2 IntervalDays: want 6, got %d", h2.IntervalDays)
	}

	// --- 笔记 H：grade=3 触发减半，正常 16 -> 8 ---
	h3, err := st.RecordReview(ctx, hNote.ID, 3, time.Date(2026, 7, 8, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("H RecordReview grade=3 failed: %v", err)
	}
	if h3.Repetitions != 3 {
		t.Fatalf("H grade=3 Repetitions: want 3, got %d", h3.Repetitions)
	}
	if h3.IntervalDays != 8 {
		t.Fatalf("H grade=3 IntervalDays: want 8 (16 halved), got %d", h3.IntervalDays)
	}
	if h3.DueDate != "2026-07-16" {
		t.Fatalf("H grade=3 DueDate: want 2026-07-16, got %s", h3.DueDate)
	}
	if math.Abs(h3.EF-2.56) > 1e-9 {
		t.Fatalf("H grade=3 EF: want ~2.56, got %.12f", h3.EF)
	}

	// --- 笔记 N：对照组，未标记困难，grade=3 不减半 ---
	n1, err := st.RecordReview(ctx, nNote.ID, 5, time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("N RecordReview grade=5 #1 failed: %v", err)
	}
	if n1.IntervalDays != 1 {
		t.Fatalf("N grade=5 #1 IntervalDays: want 1, got %d", n1.IntervalDays)
	}

	n2, err := st.RecordReview(ctx, nNote.ID, 5, time.Date(2026, 7, 2, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("N RecordReview grade=5 #2 failed: %v", err)
	}
	if n2.IntervalDays != 6 {
		t.Fatalf("N grade=5 #2 IntervalDays: want 6, got %d", n2.IntervalDays)
	}

	n3, err := st.RecordReview(ctx, nNote.ID, 3, time.Date(2026, 7, 8, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("N RecordReview grade=3 failed: %v", err)
	}
	if n3.Repetitions != 3 {
		t.Fatalf("N grade=3 Repetitions: want 3, got %d", n3.Repetitions)
	}
	if n3.IntervalDays != 16 {
		t.Fatalf("N grade=3 IntervalDays: want 16 (no halving), got %d", n3.IntervalDays)
	}
	if math.Abs(n3.EF-2.56) > 1e-9 {
		t.Fatalf("N grade=3 EF: want ~2.56, got %.12f", n3.EF)
	}

	// --- 取消 H 的困难标记后，grade=3 不再减半 ---
	if err := st.SetHardMark(hNote.ID, user, false); err != nil {
		t.Fatalf("SetHardMark(false) failed: %v", err)
	}

	h4, err := st.RecordReview(ctx, hNote.ID, 3, time.Date(2026, 7, 16, 0, 0, 0, 0, time.UTC), user)
	if err != nil {
		t.Fatalf("H RecordReview after unmark failed: %v", err)
	}
	if h4.Repetitions != 4 {
		t.Fatalf("H unmarked grade=3 Repetitions: want 4, got %d", h4.Repetitions)
	}
	if h4.IntervalDays != 20 {
		t.Fatalf("H unmarked grade=3 IntervalDays: want 20, got %d", h4.IntervalDays)
	}
}