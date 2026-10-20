package store

import (
	"context"
	"errors"
	"math"
	"strings"
	"testing"
	"time"
)

func TestReviewErrorPaths_InvalidGradeAndNotFound(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	user := DefaultUser

	note, err := st.CreateNote(Note{Title: "error-paths", Body: "body"})
	if err != nil {
		t.Fatalf("CreateNote failed: %v", err)
	}
	if note.ID == 0 {
		t.Fatalf("expected non-zero note id, got %d", note.ID)
	}

	today := time.Date(2026, 9, 1, 0, 0, 0, 0, time.UTC)

	// 1a. grade = 6 超出合法区间 [0,5]
	_, err = st.RecordReview(ctx, note.ID, 6, today, user)
	if err == nil {
		t.Fatalf("RecordReview grade=6 expected error, got nil")
	}
	if !strings.Contains(err.Error(), "无效的评分等级") {
		t.Fatalf("RecordReview grade=6 expected error containing %q, got %q", "无效的评分等级", err.Error())
	}

	// 1b. grade = -1 低于合法区间
	_, err = st.RecordReview(ctx, note.ID, -1, today, user)
	if err == nil {
		t.Fatalf("RecordReview grade=-1 expected error, got nil")
	}
	if !strings.Contains(err.Error(), "无效的评分等级") {
		t.Fatalf("RecordReview grade=-1 expected error containing %q, got %q", "无效的评分等级", err.Error())
	}

	// 2. 不存在的笔记 id 复习 -> ErrNotFound
	_, err = st.RecordReview(ctx, 999999, 5, today, user)
	if err == nil {
		t.Fatalf("RecordReview nonexistent note expected error, got nil")
	}
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("RecordReview nonexistent note expected errors.Is(err, ErrNotFound)=true, got err=%v", err)
	}

	// 3a. 刚创建的笔记，创建者拥有自动初始化的复习行 -> 返回初始状态
	state, err := st.GetReviewState(note.ID, user)
	if err != nil {
		t.Fatalf("GetReviewState on freshly created note expected nil error, got %v", err)
	}
	if math.Abs(state.EF-2.5) > 1e-9 {
		t.Errorf("GetReviewState initial EF expected 2.5 (tolerance 1e-9), got %v", state.EF)
	}
	if state.Repetitions != 0 {
		t.Errorf("GetReviewState initial Repetitions expected 0, got %d", state.Repetitions)
	}
	if state.IntervalDays != 0 {
		t.Errorf("GetReviewState initial IntervalDays expected 0, got %d", state.IntervalDays)
	}
	expectedDue := dateOnly(time.Now().UTC().AddDate(0, 0, 1))
	if state.DueDate != expectedDue {
		t.Errorf("GetReviewState initial DueDate expected %q, got %q", expectedDue, state.DueDate)
	}

	// 3b. 另一个用户对该笔记没有复习行 -> ErrNotFound
	_, err = st.GetReviewState(note.ID, "ghostuser")
	if err == nil {
		t.Fatalf("GetReviewState for ghostuser expected error, got nil")
	}
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetReviewState for ghostuser expected errors.Is(err, ErrNotFound)=true, got err=%v", err)
	}

	// 4. 不存在的笔记 id 查询状态 -> ErrNotFound
	_, err = st.GetReviewState(999999, user)
	if err == nil {
		t.Fatalf("GetReviewState nonexistent note expected error, got nil")
	}
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetReviewState nonexistent note expected errors.Is(err, ErrNotFound)=true, got err=%v", err)
	}
}