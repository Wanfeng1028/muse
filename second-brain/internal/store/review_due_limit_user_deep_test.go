package store

import (
	"context"
	"testing"
	"time"
)

func TestListDueReviews_LimitAndUserIsolation(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()

	// 构造 3 条笔记并都记录复习，使 due_date 为 2026-08-02（today 2026-08-01 + 1 天）
	ids := make([]int64, 3)
	for i := 0; i < 3; i++ {
		n, err := st.CreateNote(Note{
			Title: "limit-note",
			Body:  "body",
		})
		if err != nil {
			t.Fatalf("CreateNote[%d] failed: %v", i, err)
		}
		ids[i] = n.ID
		state, err := st.RecordReview(ctx, n.ID, 5, time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC), DefaultUser)
		if err != nil {
			t.Fatalf("RecordReview[%d] failed: %v", i, err)
		}
		if state.DueDate != "2026-08-02" {
			t.Fatalf("RecordReview[%d] 期望 DueDate=2026-08-02, 实际=%q", i, state.DueDate)
		}
	}
	_ = ids

	today := time.Date(2026, 8, 2, 0, 0, 0, 0, time.UTC)

	// limit<=0 回落默认 50，应返回全部 3 条
	gotZero, err := st.ListDueReviews(today, 0, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews(limit=0) failed: %v", err)
	}
	if len(gotZero) != 3 {
		t.Fatalf("ListDueReviews(limit=0) 期望 3 条, 实际=%d", len(gotZero))
	}

	// limit=-5 同样回落默认，应返回全部 3 条
	gotNeg, err := st.ListDueReviews(today, -5, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews(limit=-5) failed: %v", err)
	}
	if len(gotNeg) != 3 {
		t.Fatalf("ListDueReviews(limit=-5) 期望 3 条, 实际=%d", len(gotNeg))
	}

	// limit=2 应返回 2 条
	gotTwo, err := st.ListDueReviews(today, 2, DefaultUser)
	if err != nil {
		t.Fatalf("ListDueReviews(limit=2) failed: %v", err)
	}
	if len(gotTwo) != 2 {
		t.Fatalf("ListDueReviews(limit=2) 期望 2 条, 实际=%d", len(gotTwo))
	}

	// 多用户到期隔离：同一条笔记 noteX 分属 alice / bob
	noteX, err := st.CreateNote(Note{
		Title: "user-isolation-note",
		Body:  "body",
	})
	if err != nil {
		t.Fatalf("CreateNote(noteX) failed: %v", err)
	}

	if _, err := st.RecordReview(ctx, noteX.ID, 5, time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC), "alice"); err != nil {
		t.Fatalf("RecordReview(alice) failed: %v", err)
	}
	if _, err := st.RecordReview(ctx, noteX.ID, 5, time.Date(2026, 8, 5, 0, 0, 0, 0, time.UTC), "bob"); err != nil {
		t.Fatalf("RecordReview(bob) failed: %v", err)
	}

	aliceDue, err := st.ListDueReviews(time.Date(2026, 8, 2, 0, 0, 0, 0, time.UTC), 50, "alice")
	if err != nil {
		t.Fatalf("ListDueReviews(alice) failed: %v", err)
	}
	if !containsNote(aliceDue, noteX.ID) {
		t.Fatalf("ListDueReviews(alice) 期望包含 noteID=%d, 实际=%v", noteX.ID, dueNoteIDs(aliceDue))
	}
	if d := dueDateOf(aliceDue, noteX.ID); d != "2026-08-02" {
		t.Fatalf("alice noteID=%d 期望 DueDate=2026-08-02, 实际=%q", noteX.ID, d)
	}

	bobEarly, err := st.ListDueReviews(time.Date(2026, 8, 2, 0, 0, 0, 0, time.UTC), 50, "bob")
	if err != nil {
		t.Fatalf("ListDueReviews(bob, 2026-08-02) failed: %v", err)
	}
	if containsNote(bobEarly, noteX.ID) {
		t.Fatalf("bob 在 2026-08-02 期望未到期不含 noteID=%d, 实际=%v", noteX.ID, dueNoteIDs(bobEarly))
	}

	bobLater, err := st.ListDueReviews(time.Date(2026, 8, 6, 0, 0, 0, 0, time.UTC), 50, "bob")
	if err != nil {
		t.Fatalf("ListDueReviews(bob, 2026-08-06) failed: %v", err)
	}
	if !containsNote(bobLater, noteX.ID) {
		t.Fatalf("bob 在 2026-08-06 期望包含 noteID=%d, 实际=%v", noteX.ID, dueNoteIDs(bobLater))
	}
	if d := dueDateOf(bobLater, noteX.ID); d != "2026-08-06" {
		t.Fatalf("bob noteID=%d 期望 DueDate=2026-08-06, 实际=%q", noteX.ID, d)
	}
}

func containsNote(list []DueReview, id int64) bool {
	for _, dr := range list {
		if dr.Note.ID == id {
			return true
		}
	}
	return false
}

func dueDateOf(list []DueReview, id int64) string {
	for _, dr := range list {
		if dr.Note.ID == id {
			return dr.DueDate
		}
	}
	return ""
}

func dueNoteIDs(list []DueReview) []int64 {
	out := make([]int64, 0, len(list))
	for _, dr := range list {
		out = append(out, dr.Note.ID)
	}
	return out
}