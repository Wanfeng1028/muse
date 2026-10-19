package store

import (
	"context"
	"testing"
	"time"
)

// 构造 n=3 的状态：两次 grade=4（interval: 1 → 6），EF 保持 2.5。
// 第三次 grade=3 时标准 SM-2 给出 interval=round(6*2.5)=15。
func TestHardMarkHalvesIntervalOnHardGrade(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()

	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("review 1: %v", err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("review 2: %v", err)
	}
	if err := s.SetHardMark(n.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark: %v", err)
	}
	st, err := s.RecordReview(ctx, n.ID, 3, today, DefaultUser)
	if err != nil {
		t.Fatalf("review 3: %v", err)
	}
	if st.IntervalDays != 7 {
		t.Fatalf("IntervalDays=%d, want 7 (15 减半)", st.IntervalDays)
	}
	wantDue := today.UTC().AddDate(0, 0, 7).Format("2006-01-02")
	if st.DueDate != wantDue {
		t.Fatalf("DueDate=%q, want %q", st.DueDate, wantDue)
	}
	// 标记本身不受影响
	if hard, _ := s.GetHardMark(n.ID, DefaultUser); !hard {
		t.Fatalf("hard 标记丢失")
	}
}

func TestHardMarkNoPenaltyWithoutMark(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()
	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("review 1: %v", err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("review 2: %v", err)
	}
	st, err := s.RecordReview(ctx, n.ID, 3, today, DefaultUser)
	if err != nil {
		t.Fatalf("review 3: %v", err)
	}
	if st.IntervalDays != 15 {
		t.Fatalf("IntervalDays=%d, want 15 (无标记不惩罚)", st.IntervalDays)
	}
}

func TestHardMarkNoPenaltyOnGoodGrade(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()
	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("review 1: %v", err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("review 2: %v", err)
	}
	if err := s.SetHardMark(n.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark: %v", err)
	}
	// grade=4（良好）即使标记困难也不惩罚
	st, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser)
	if err != nil {
		t.Fatalf("review 3: %v", err)
	}
	if st.IntervalDays != 15 {
		t.Fatalf("IntervalDays=%d, want 15 (良好不惩罚)", st.IntervalDays)
	}
}
