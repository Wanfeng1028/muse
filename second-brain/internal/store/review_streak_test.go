package store

import (
	"context"
	"testing"
	"time"
)

func TestReviewStreakEmpty(t *testing.T) {
	s := newTestStore(t)
	today := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)
	got, err := s.ReviewStreak(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewStreak 失败: %v", err)
	}
	if got.CurrentStreak != 0 {
		t.Errorf("Current 应为 0, 得到 %d", got.CurrentStreak)
	}
	if got.LongestStreak != 0 {
		t.Errorf("Longest 应为 0, 得到 %d", got.LongestStreak)
	}
	if got.TotalDays != 0 {
		t.Errorf("TotalDays 应为 0, 得到 %d", got.TotalDays)
	}
	if got.LastReviewedDate != "" {
		t.Errorf("LastReviewedDate 应为空, 得到 %q", got.LastReviewedDate)
	}
}

func TestReviewStreakLongestAndCurrent(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	// 5个不同日期的复习记录：06-01/02/03连续3天, 06-05/06连续2天
	dates := []string{
		"2024-06-01T12:00:00Z",
		"2024-06-02T12:00:00Z",
		"2024-06-03T12:00:00Z",
		"2024-06-05T12:00:00Z",
		"2024-06-06T12:00:00Z",
	}
	for _, d := range dates {
		note, err := s.CreateNote(Note{Title: "X", Body: "x"})
		if err != nil {
			t.Fatalf("CreateNote 失败: %v", err)
		}
		if _, err = s.RecordReview(ctx, note.ID, 4, today, DefaultUser); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
		if _, err = s.db.Exec(`UPDATE reviews SET last_reviewed_at=? WHERE note_id=? AND user_id=?`, d, note.ID, DefaultUser); err != nil {
			t.Fatalf("更新日期失败: %v", err)
		}
	}

	got, err := s.ReviewStreak(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewStreak 失败: %v", err)
	}
	if got.TotalDays != 5 {
		t.Errorf("TotalDays 应为 5, 得到 %d", got.TotalDays)
	}
	if got.LongestStreak != 3 {
		t.Errorf("Longest 应为 3, 得到 %d", got.LongestStreak)
	}
	if got.LastReviewedDate != "2024-06-06" {
		t.Errorf("LastReviewedDate 应为 2024-06-06, 得到 %q", got.LastReviewedDate)
	}
	if got.CurrentStreak != 2 {
		t.Errorf("Current 应为 2, 得到 %d", got.CurrentStreak)
	}
}

func TestReviewStreakYesterdayFallback(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	// 同上数据的5条复习记录
	dates := []string{
		"2024-06-01T12:00:00Z",
		"2024-06-02T12:00:00Z",
		"2024-06-03T12:00:00Z",
		"2024-06-05T12:00:00Z",
		"2024-06-06T12:00:00Z",
	}
	for _, d := range dates {
		note, err := s.CreateNote(Note{Title: "X", Body: "x"})
		if err != nil {
			t.Fatalf("CreateNote 失败: %v", err)
		}
		if _, err = s.RecordReview(ctx, note.ID, 4, base, DefaultUser); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
		if _, err = s.db.Exec(`UPDATE reviews SET last_reviewed_at=? WHERE note_id=? AND user_id=?`, d, note.ID, DefaultUser); err != nil {
			t.Fatalf("更新日期失败: %v", err)
		}
	}

	// today=06-07, 当天无复习, 昨天有复习, Current=2
	day7 := time.Date(2024, 6, 7, 12, 0, 0, 0, time.Local)
	got, err := s.ReviewStreak(day7, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewStreak 失败: %v", err)
	}
	if got.CurrentStreak != 2 {
		t.Errorf("today=06-07 时 Current 应为 2, 得到 %d", got.CurrentStreak)
	}

	// today=06-09, 昨天06-08也无复习, Current=0, Longest仍为3
	day9 := time.Date(2024, 6, 9, 12, 0, 0, 0, time.Local)
	got, err = s.ReviewStreak(day9, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewStreak 失败: %v", err)
	}
	if got.CurrentStreak != 0 {
		t.Errorf("today=06-09 时 Current 应为 0, 得到 %d", got.CurrentStreak)
	}
	if got.LongestStreak != 3 {
		t.Errorf("today=06-09 时 Longest 应为 3, 得到 %d", got.LongestStreak)
	}
}

func TestReviewStreakUserIsolation(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	// DefaultUser 造 06-06 一天
	note, err := s.CreateNote(Note{Title: "X", Body: "x"})
	if err != nil {
		t.Fatalf("CreateNote 失败: %v", err)
	}
	if _, err = s.RecordReview(ctx, note.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}

	// alice 造 06-01 至 06-03 三天
	aliceDates := []string{
		"2024-06-01T12:00:00Z",
		"2024-06-02T12:00:00Z",
		"2024-06-03T12:00:00Z",
	}
	for _, d := range aliceDates {
		n, err := s.CreateNote(Note{Title: "X", Body: "x"})
		if err != nil {
			t.Fatalf("CreateNote 失败: %v", err)
		}
		if _, err = s.RecordReview(ctx, n.ID, 4, today, "alice"); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
		if _, err = s.db.Exec(`UPDATE reviews SET last_reviewed_at=? WHERE note_id=? AND user_id=?`, d, n.ID, "alice"); err != nil {
			t.Fatalf("更新日期失败: %v", err)
		}
	}

	// 断言 DefaultUser
	got, err := s.ReviewStreak(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewStreak 失败: %v", err)
	}
	if got.TotalDays != 1 {
		t.Errorf("DefaultUser TotalDays 应为 1, 得到 %d", got.TotalDays)
	}
	if got.LongestStreak != 1 {
		t.Errorf("DefaultUser Longest 应为 1, 得到 %d", got.LongestStreak)
	}

	// 断言 alice
	got, err = s.ReviewStreak(today, "alice")
	if err != nil {
		t.Fatalf("ReviewStreak 失败: %v", err)
	}
	if got.TotalDays != 3 {
		t.Errorf("alice TotalDays 应为 3, 得到 %d", got.TotalDays)
	}
	if got.LongestStreak != 3 {
		t.Errorf("alice Longest 应为 3, 得到 %d", got.LongestStreak)
	}
}
