package store

import (
	"context"
	"testing"
	"time"
)

func TestReviewMastery(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()

	a, err := s.CreateNote(Note{Title: "A", Body: "a", Tags: []string{"数学"}})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}
	b, err := s.CreateNote(Note{Title: "B", Body: "b", Tags: []string{"数学"}})
	if err != nil {
		t.Fatalf("CreateNote B: %v", err)
	}
	c, err := s.CreateNote(Note{Title: "C", Body: "c", Tags: []string{"英语"}})
	if err != nil {
		t.Fatalf("CreateNote C: %v", err)
	}
	d, err := s.CreateNote(Note{Title: "D", Body: "d"})
	if err != nil {
		t.Fatalf("CreateNote D: %v", err)
	}

	// A 昨天复习（grade 5 → due 落到今天），B 今天复习（due 明天）：数学 Due=1
	yesterday := today.AddDate(0, 0, -1)
	if _, err := s.RecordReview(ctx, a.ID, 5, yesterday, DefaultUser); err != nil {
		t.Fatalf("RecordReview A: %v", err)
	}
	if _, err := s.RecordReview(ctx, b.ID, 3, today, DefaultUser); err != nil {
		t.Fatalf("RecordReview B: %v", err)
	}
	if err := s.SetHardMark(b.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark B: %v", err)
	}
	if _, err := s.RecordReview(ctx, c.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("RecordReview C: %v", err)
	}
	if _, err := s.RecordReview(ctx, d.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("RecordReview D: %v", err)
	}
	// 把 C 的 due_date 改到明天，英语 Due=0
	tomorrow := today.AddDate(0, 0, 1).Format("2006-01-02")
	if _, err := s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`,
		tomorrow, c.ID, DefaultUser); err != nil {
		t.Fatalf("UPDATE due_date: %v", err)
	}

	m, err := s.ReviewMastery(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewMastery: %v", err)
	}
	if len(m) != 2 {
		t.Fatalf("len=%d, want 2", len(m))
	}
	// 按 Total DESC，数学在前
	if m[0].Tag != "数学" {
		t.Fatalf("m[0].Tag=%q, want 数学", m[0].Tag)
	}
	if m[0].Total != 2 || m[0].Hard != 1 || m[0].Due != 1 {
		t.Fatalf("数学 = %+v, want Total=2 Hard=1 Due=1", m[0])
	}
	if m[0].AvgEF != 2.48 {
		t.Fatalf("数学 AvgEF=%v, want 2.48", m[0].AvgEF)
	}
	if m[1].Tag != "英语" || m[1].Total != 1 || m[1].Hard != 0 || m[1].Due != 0 {
		t.Fatalf("英语 = %+v, want Total=1 Hard=0 Due=0", m[1])
	}
	if m[1].AvgEF != 2.5 {
		t.Fatalf("英语 AvgEF=%v, want 2.5", m[1].AvgEF)
	}

	// 多用户隔离
	m2, err := s.ReviewMastery(today, "other")
	if err != nil {
		t.Fatalf("ReviewMastery other: %v", err)
	}
	if len(m2) != 0 {
		t.Fatalf("other len=%d, want 0", len(m2))
	}
}
