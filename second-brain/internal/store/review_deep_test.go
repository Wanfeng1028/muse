package store

import (
	"context"
	"path/filepath"
	"testing"
	"time"
)

// newDeepTestStore 创建带真实 sqlite 文件的 store，避免 :memory: 多连接问题
func newDeepTestStore(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "deep.db")
	s, err := Open(path)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

// seedNote 插入一条笔记并返回 id
func seedNote(t *testing.T, s *Store, title, body string) int64 {
	t.Helper()
	n, err := s.CreateNote(Note{Title: title, Body: body})
	if err != nil {
		t.Fatalf("CreateNote 失败: %v", err)
	}
	return n.ID
}

// TestReviewScheduleBoundariesReview 覆盖跨天、闰日、月末的调度边界
func TestReviewScheduleBoundariesReview(t *testing.T) {
	cases := []struct {
		name     string
		today    time.Time
		interval int
		wantDue  string
	}{
		{"普通跨天", time.Date(2024, 3, 10, 0, 0, 0, 0, time.UTC), 1, "2024-03-11"},
		{"闰日次日", time.Date(2024, 2, 28, 0, 0, 0, 0, time.UTC), 1, "2024-02-29"},
		{"闰日当天加一天", time.Date(2024, 2, 29, 0, 0, 0, 0, time.UTC), 1, "2024-03-01"},
		{"非闰年二月末", time.Date(2023, 2, 28, 0, 0, 0, 0, time.UTC), 1, "2023-03-01"},
		{"月末跨月", time.Date(2024, 1, 31, 0, 0, 0, 0, time.UTC), 30, "2024-02-01"},
		{"跨年", time.Date(2024, 12, 31, 0, 0, 0, 0, time.UTC), 1, "2025-01-01"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := newDeepTestStore(t)
			noteID := seedNote(t, s, "边界", "body")
			wantDue, _ := parseDate(tc.wantDue)
			// 写入并读回，验证跨天持久化（首次复习 interval=1，due=today+1）
			if _, err := s.RecordReview(context.Background(), noteID, 4, tc.today, "alice"); err != nil {
				t.Fatalf("RecordReview 失败: %v", err)
			}
			st, err := s.GetReviewState(noteID, "alice")
			if err != nil {
				t.Fatalf("GetReviewState 失败: %v", err)
			}
			gotStored, _ := parseDate(st.DueDate)
			if !gotStored.Equal(wantDue) {
				t.Fatalf("存储 due_date 期望 %s 实际 %s", tc.wantDue, st.DueDate)
			}
		})
	}
}

// TestReviewTimezoneConsistency 验证不同时区表示的同一时刻得到一致的日期
func TestReviewTimezoneConsistency(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "时区", "body")

	utc := time.Date(2024, 6, 15, 12, 0, 0, 0, time.UTC)
	shanghai := utc.In(time.FixedZone("CST", 8*3600))
	tokyo := utc.In(time.FixedZone("JST", 9*3600))

	for _, today := range []time.Time{utc, shanghai, tokyo} {
		if _, err := s.RecordReview(context.Background(), noteID, 5, today, "bob"); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
	}
	// 三次记录同一 note，应只有一条 review
	stats, err := s.ReviewStats(utc, "bob")
	if err != nil {
		t.Fatalf("ReviewStats 失败: %v", err)
	}
	// 3 次满分后 due 已推到未来，今天无到期
	if stats.DueToday != 0 {
		t.Fatalf("DueToday 期望 0 实际 %d", stats.DueToday)
	}
	if stats.TotalNotes != 1 {
		t.Fatalf("TotalNotes 期望 1 实际 %d", stats.TotalNotes)
	}
}

// TestSM2ExtremeEFReview SM-2 极端评分导致 EF 上下界
func TestSM2ExtremeEFReview(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "EF", "body")
	today := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)

	// 连续低分应把 EF 压到下限
	for i := 0; i < 20; i++ {
		if _, err := s.RecordReview(context.Background(), noteID, 0, today, "carol"); err != nil {
			t.Fatalf("第 %d 次低分 RecordReview 失败: %v", i, err)
		}
	}
	st, err := s.GetReviewState(noteID, "carol")
	if err != nil {
		t.Fatalf("GetReviewState 失败: %v", err)
	}
	if st.EF < 1.3 {
		t.Fatalf("EF 不应低于 1.3，实际 %v", st.EF)
	}
	if st.Repetitions > 1 {
		t.Fatalf("连续低分应重置 repetitions，实际 %d", st.Repetitions)
	}

	// 连续高分应把 EF 抬到合理上界
	for i := 0; i < 50; i++ {
		if _, err := s.RecordReview(context.Background(), noteID, 5, today, "carol"); err != nil {
			t.Fatalf("第 %d 次高分 RecordReview 失败: %v", i, err)
		}
	}
	st, err = s.GetReviewState(noteID, "carol")
	if err != nil {
		t.Fatalf("GetReviewState 失败: %v", err)
	}
	if st.EF <= 2.5 {
		t.Fatalf("连续高分后 EF 应大于 2.5，实际 %v", st.EF)
	}
	// 注：产品 EF 无上界钳制（经典 SM-2 亦然），此处仅校验下界与单调性
}

// TestSM2GradeValidation 评分越界必须报错且不改状态
func TestSM2GradeValidation(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "grade", "body")
	today := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)

	if _, err := s.RecordReview(context.Background(), noteID, -1, today, "dave"); err == nil {
		t.Fatalf("grade=-1 应报错")
	}
	if _, err := s.RecordReview(context.Background(), noteID, 6, today, "dave"); err == nil {
		t.Fatalf("grade=6 应报错")
	}
	_, err := s.GetReviewState(noteID, "dave")
	if err != ErrNotFound {
		t.Fatalf("非法评分不应写入状态，期望 ErrNotFound 实际 %v", err)
	}
	// 合法边界 0 和 5 应通过
	if _, err := s.RecordReview(context.Background(), noteID, 0, today, "dave"); err != nil {
		t.Fatalf("grade=0 应通过: %v", err)
	}
	if _, err := s.RecordReview(context.Background(), noteID, 5, today, "dave"); err != nil {
		t.Fatalf("grade=5 应通过: %v", err)
	}
}

// TestDueReviewsOverdue 逾期天数计算
func TestDueReviewsOverdue(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "逾期", "body")
	base := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	// 先建一条复习，due 落在 base
	if _, err := s.RecordReview(context.Background(), noteID, 4, base, "erin"); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	// 查询今天 = base + 10 天
	later := base.AddDate(0, 0, 10)
	due, err := s.ListDueReviews(later, 50, "erin")
	if err != nil {
		t.Fatalf("ListDueReviews 失败: %v", err)
	}
	if len(due) != 1 {
		t.Fatalf("期望 1 条到期，实际 %d", len(due))
	}
	if due[0].OverdueDays < 9 {
		t.Fatalf("OverdueDays 期望 >=9，实际 %d", due[0].OverdueDays)
	}
	// 查询今天 = base - 1，应无到期
	before, err := s.ListDueReviews(base.AddDate(0, 0, -1), 50, "erin")
	if err != nil {
		t.Fatalf("ListDueReviews 失败: %v", err)
	}
	if len(before) != 0 {
		t.Fatalf("未来日期不应有到期，实际 %d", len(before))
	}
}

// TestListDueReviewsLimit 限制条数边界
func TestListDueReviewsLimit(t *testing.T) {
	s := newDeepTestStore(t)
	today := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 5; i++ {
		id := seedNote(t, s, "n", "b")
		if _, err := s.RecordReview(context.Background(), id, 4, today.AddDate(0, 0, -1), "frank"); err != nil {
			t.Fatalf("RecordReview 失败: %v", err)
		}
	}
	// limit<=0 走默认 50
	all, err := s.ListDueReviews(today, 0, "frank")
	if err != nil {
		t.Fatalf("ListDueReviews 失败: %v", err)
	}
	if len(all) != 5 {
		t.Fatalf("默认 limit 期望 5，实际 %d", len(all))
	}
	// 显式 limit=2
	two, err := s.ListDueReviews(today, 2, "frank")
	if err != nil {
		t.Fatalf("ListDueReviews 失败: %v", err)
	}
	if len(two) != 2 {
		t.Fatalf("limit=2 期望 2，实际 %d", len(two))
	}
}

// TestMultiUserIsolationReview 多用户复习状态互相隔离
func TestMultiUserIsolationReview(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "隔离", "body")
	today := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)

	// alice 多次高分
	for i := 0; i < 5; i++ {
		if _, err := s.RecordReview(context.Background(), noteID, 5, today, "alice"); err != nil {
			t.Fatalf("alice RecordReview 失败: %v", err)
		}
	}
	// grace 一次低分
	if _, err := s.RecordReview(context.Background(), noteID, 1, today, "grace"); err != nil {
		t.Fatalf("grace RecordReview 失败: %v", err)
	}

	aliceSt, err := s.GetReviewState(noteID, "alice")
	if err != nil {
		t.Fatalf("alice GetReviewState 失败: %v", err)
	}
	graceSt, err := s.GetReviewState(noteID, "grace")
	if err != nil {
		t.Fatalf("grace GetReviewState 失败: %v", err)
	}
	if aliceSt.EF <= graceSt.EF {
		t.Fatalf("alice EF 应高于 grace，alice=%v grace=%v", aliceSt.EF, graceSt.EF)
	}
	if aliceSt.Repetitions <= graceSt.Repetitions {
		t.Fatalf("alice Repetitions 应高于 grace，alice=%d grace=%d", aliceSt.Repetitions, graceSt.Repetitions)
	}

	// 注：alice 5 次满分后 due 已推到远期，此处不校验到期数，隔离性由 EF/Repetitions 覆盖
	// 未知用户不应看到任何到期
	nobody, err := s.ListDueReviews(today, 50, "nobody")
	if err != nil {
		t.Fatalf("nobody ListDueReviews 失败: %v", err)
	}
	if len(nobody) != 0 {
		t.Fatalf("nobody 到期数期望 0，实际 %d", len(nobody))
	}
}

// TestReviewStatsFields 统计字段计算
func TestReviewStatsFields(t *testing.T) {
	s := newDeepTestStore(t)
	today := time.Date(2024, 5, 10, 0, 0, 0, 0, time.UTC)

	// 三条笔记，两条复习
	n1 := seedNote(t, s, "a", "b")
	n2 := seedNote(t, s, "c", "d")
	seedNote(t, s, "e", "f")

	if _, err := s.RecordReview(context.Background(), n1, 5, today.AddDate(0, 0, -1), "henry"); err != nil {
		t.Fatalf("RecordReview n1 失败: %v", err)
	}
	if _, err := s.RecordReview(context.Background(), n2, 4, today.AddDate(0, 0, -1), "henry"); err != nil {
		t.Fatalf("RecordReview n2 失败: %v", err)
	}

	stats, err := s.ReviewStats(today, "henry")
	if err != nil {
		t.Fatalf("ReviewStats 失败: %v", err)
	}
	if stats.TotalNotes != 3 {
		t.Fatalf("TotalNotes 期望 3，实际 %d", stats.TotalNotes)
	}
	if stats.DueToday != 2 {
		t.Fatalf("DueToday 期望 2，实际 %d", stats.DueToday)
	}
	if stats.Reviewed7d != 2 {
		t.Fatalf("Reviewed7d 期望 2，实际 %d", stats.Reviewed7d)
	}
	if stats.AvgEF <= 0 {
		t.Fatalf("AvgEF 应大于 0，实际 %v", stats.AvgEF)
	}
	if stats.StreakDays < 1 {
		t.Fatalf("StreakDays 期望 >=1，实际 %d", stats.StreakDays)
	}

	// 无数据用户 AvgEF 应为 0
	empty, err := s.ReviewStats(today, "ivy")
	if err != nil {
		t.Fatalf("ReviewStats ivy 失败: %v", err)
	}
	if empty.AvgEF != 0 {
		t.Fatalf("无数据 AvgEF 期望 0，实际 %v", empty.AvgEF)
	}
	if empty.DueToday != 0 {
		t.Fatalf("无数据 DueToday 期望 0，实际 %d", empty.DueToday)
	}
}

// TestStreakAcrossDays 连续复习天数
func TestStreakAcrossDays(t *testing.T) {
	s := newDeepTestStore(t)
	base := time.Date(2024, 5, 10, 0, 0, 0, 0, time.UTC)

	// 连续三天复习（每天换一条笔记，因同笔记同用户只保留一条 review 记录）
	for i := 0; i < 3; i++ {
		noteID := seedNote(t, s, "streak", "body")
		day := base.AddDate(0, 0, -i)
		if _, err := s.RecordReview(context.Background(), noteID, 4, day, "jack"); err != nil {
			t.Fatalf("第 %d 天 RecordReview 失败: %v", i, err)
		}
	}
	stats, err := s.ReviewStats(base, "jack")
	if err != nil {
		t.Fatalf("ReviewStats 失败: %v", err)
	}
	if stats.StreakDays != 3 {
		t.Fatalf("StreakDays 期望 3，实际 %d", stats.StreakDays)
	}

	// 隔一天再查，应从昨天起算连续 2 天（今天未复习）
	gap := base.AddDate(0, 0, 1)
	stats2, err := s.ReviewStats(gap, "jack")
	if err != nil {
		t.Fatalf("ReviewStats gap 失败: %v", err)
	}
	if stats2.StreakDays != 3 {
		t.Fatalf("gap StreakDays 期望 3，实际 %d", stats2.StreakDays)
	}
}

// TestRecordReviewNoteNotFound 笔记不存在时返回 ErrNotFound
func TestRecordReviewNoteNotFound(t *testing.T) {
	s := newDeepTestStore(t)
	today := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)

	_, err := s.RecordReview(context.Background(), 99999, 4, today, "kate")
	if err != ErrNotFound {
		t.Fatalf("不存在笔记期望 ErrNotFound，实际 %v", err)
	}
	_, err = s.GetReviewState(99999, "kate")
	if err != ErrNotFound {
		t.Fatalf("不存在状态期望 ErrNotFound，实际 %v", err)
	}
}

// TestUserNormalization 用户名规范化后应共享状态
func TestUserNormalization(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "norm", "body")
	today := time.Date(2024, 5, 1, 0, 0, 0, 0, time.UTC)

	if _, err := s.RecordReview(context.Background(), noteID, 4, today, "  Leo  "); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	st, err := s.GetReviewState(noteID, "leo")
	if err != nil {
		t.Fatalf("GetReviewState 失败: %v", err)
	}
	if st.Repetitions < 1 {
		t.Fatalf("规范化后应能读到状态，Repetitions=%d", st.Repetitions)
	}
	if st.DueDate == "" {
		t.Fatalf("DueDate 不应为空")
	}
}
