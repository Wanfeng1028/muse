package store

import (
	"context"
	"errors"
	"testing"
	"time"
)

// TestMigrateReviewsIsHardIdempotent 验证 Migrate 对已有 reviews 行幂等：
// 手动插入一行旧数据，重复迁移后数据不丢，且新增列取默认值。
func TestMigrateReviewsIsHardIdempotent(t *testing.T) {
	s := newTestStore(t)
	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	// CreateNote 会自动建一条 reviews 行，这里用 UPDATE 把它改成确定的旧值，
	// 再验证重复 Migrate 不报错且数据不丢。
	if _, err := s.db.Exec(
		`UPDATE reviews SET ef=?, interval_days=?, repetitions=?, due_date=?, last_reviewed_at=?, reviewed_count=?, is_hard=?
		 WHERE note_id=? AND user_id=?`,
		2.5, 0, 0, "2024-01-01", nil, 0, 0, n.ID, DefaultUser,
	); err != nil {
		t.Fatalf("更新 reviews 行: %v", err)
	}

	if err := Migrate(s.db); err != nil {
		t.Fatalf("Migrate 第二次调用应幂等，得到错误: %v", err)
	}

	var ef float64
	var isHard int
	if err := s.db.QueryRow(
		`SELECT ef, is_hard FROM reviews WHERE note_id = ? AND user_id = ?`,
		n.ID, DefaultUser,
	).Scan(&ef, &isHard); err != nil {
		t.Fatalf("查回 reviews 行: %v", err)
	}
	if ef != 2.5 {
		t.Fatalf("ef 数据丢失: 期望 2.5，实际 %v", ef)
	}
	if isHard != 0 {
		t.Fatalf("is_hard 期望 0，实际 %d", isHard)
	}
}

// TestSetHardMarkToggle 验证困难标记可置位与清除。
func TestSetHardMarkToggle(t *testing.T) {
	s := newTestStore(t)
	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	if err := s.SetHardMark(n.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark(true): %v", err)
	}
	got, err := s.GetHardMark(n.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetHardMark: %v", err)
	}
	if !got {
		t.Fatalf("置 true 后 GetHardMark 期望 true，实际 false")
	}

	if err := s.SetHardMark(n.ID, DefaultUser, false); err != nil {
		t.Fatalf("SetHardMark(false): %v", err)
	}
	got, err = s.GetHardMark(n.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetHardMark: %v", err)
	}
	if got {
		t.Fatalf("置 false 后 GetHardMark 期望 false，实际 true")
	}
}

// TestSetHardMarkNoteNotFound 验证笔记不存在时返回 ErrNotFound。
func TestSetHardMarkNoteNotFound(t *testing.T) {
	s := newTestStore(t)
	err := s.SetHardMark(99999, DefaultUser, true)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("期望 ErrNotFound，实际 %v", err)
	}
}

// TestSetHardMarkPreservedAfterReview 验证普通评分不会清掉困难标记。
func TestSetHardMarkPreservedAfterReview(t *testing.T) {
	s := newTestStore(t)
	n, err := s.CreateNote(Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}

	if err := s.SetHardMark(n.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark(true): %v", err)
	}
	st, err := s.GetReviewState(n.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetReviewState: %v", err)
	}
	if st.EF != 2.5 {
		t.Fatalf("初始 EF 期望 2.5，实际 %v", st.EF)
	}

	if _, err := s.RecordReview(context.Background(), n.ID, 4, time.Now().UTC(), DefaultUser); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}

	got, err := s.GetHardMark(n.ID, DefaultUser)
	if err != nil {
		t.Fatalf("GetHardMark: %v", err)
	}
	if !got {
		t.Fatalf("评分后困难标记被清掉，期望仍为 true")
	}
}

// TestListHardNotesOrderAndLimit 验证困难笔记按 last_reviewed_at NULL 优先排序，并支持 limit。
func TestListHardNotesOrderAndLimit(t *testing.T) {
	s := newTestStore(t)
	a, err := s.CreateNote(Note{Title: "A", Body: "a"})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}
	b, err := s.CreateNote(Note{Title: "B", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote B: %v", err)
	}

	if err := s.SetHardMark(a.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark A: %v", err)
	}
	if err := s.SetHardMark(b.ID, DefaultUser, true); err != nil {
		t.Fatalf("SetHardMark B: %v", err)
	}

	// 仅对 B 评分，产生 last_reviewed_at；A 保持 NULL。
	if _, err := s.RecordReview(context.Background(), b.ID, 4, time.Now().UTC(), DefaultUser); err != nil {
		t.Fatalf("RecordReview B: %v", err)
	}

	notes, err := s.ListHardNotes(DefaultUser, 0)
	if err != nil {
		t.Fatalf("ListHardNotes limit=0: %v", err)
	}
	if len(notes) != 2 {
		t.Fatalf("ListHardNotes limit=0 期望长度 2，实际 %d", len(notes))
	}
	if notes[0].ID != a.ID {
		t.Fatalf("NULL last_reviewed_at 应排最前，期望首条为 A(%d)，实际 %d", a.ID, notes[0].ID)
	}
	if notes[1].ID != b.ID {
		t.Fatalf("期望次条为 B(%d)，实际 %d", b.ID, notes[1].ID)
	}

	notes, err = s.ListHardNotes(DefaultUser, 1)
	if err != nil {
		t.Fatalf("ListHardNotes limit=1: %v", err)
	}
	if len(notes) != 1 {
		t.Fatalf("ListHardNotes limit=1 期望长度 1，实际 %d", len(notes))
	}
	if notes[0].ID != a.ID {
		t.Fatalf("limit=1 期望返回 A(%d)，实际 %d", a.ID, notes[0].ID)
	}
}
