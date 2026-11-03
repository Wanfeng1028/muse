package store

// 深测补强：遗忘曲线调度边界（时区/跨天/空笔记）。
// 模型生成 + 编排手工修正落盘（修正：RecordReview 返回双值；DueReview 取 ID 经 Note 字段；
// calcStreak 需 user 参数；测试3 的时间变量重命名避免遮蔽 *testing.T）。
// 锁定的语义均为当前产品行为：due_date 按 UTC 口径计算，dateOnly/streak 按调用方传入时间的墙钟口径。

import (
	"context"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/review"
)

func TestRecordReview_时区跨天DueUTC口径(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "标题", "内容")
	shanghai := time.FixedZone("CST", 8*3600)
	today := time.Date(2026, 1, 2, 0, 30, 0, 0, shanghai)
	ctx := context.Background()
	if _, err := s.RecordReview(ctx, noteID, 4, today, "u1"); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	state, err := s.GetReviewState(noteID, "u1")
	if err != nil {
		t.Fatalf("GetReviewState 失败: %v", err)
	}
	// due 按 UTC 口径：today.UTC()=2026-01-01 16:30，+1 天 = 2026-01-02
	if state.DueDate != "2026-01-02" {
		t.Errorf("期望 DueDate==2026-01-02，实际 %s", state.DueDate)
	}
}

func TestListDueReviews_跨天到期包含当日(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "标题", "内容")
	shanghai := time.FixedZone("CST", 8*3600)
	today := time.Date(2026, 1, 2, 0, 30, 0, 0, shanghai)
	ctx := context.Background()
	if _, err := s.RecordReview(ctx, noteID, 4, today, "u1"); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	dues, err := s.ListDueReviews(today, 50, "u1")
	if err != nil {
		t.Fatalf("ListDueReviews 失败: %v", err)
	}
	found := false
	for _, d := range dues {
		if d.Note.ID == noteID {
			found = true
			// due_date "2026-01-02" <= dateOnly(today) "2026-01-02"，含相等边界
			if d.OverdueDays != 0 {
				t.Errorf("期望 OverdueDays==0，实际 %d", d.OverdueDays)
			}
			if d.DueDate != "2026-01-02" {
				t.Errorf("期望 DueDate==2026-01-02，实际 %s", d.DueDate)
			}
		}
	}
	if !found {
		t.Fatalf("未找到笔记 %d", noteID)
	}
}

func TestDateOnly_AddDays_口径对照(t *testing.T) {
	shanghai := time.FixedZone("CST", 8*3600)
	tm := time.Date(2026, 1, 2, 0, 30, 0, 0, shanghai)
	localDate := dateOnly(tm)
	// addDays 语义下 +1 天，通过 review.InitialState 获取（DueDate = addDays(today,1)）
	utcDue := review.InitialState(tm).DueDate
	if localDate != utcDue {
		t.Errorf("dateOnly=%s, addDays+1=%s，应相等", localDate, utcDue)
	}
	// 边界含义：上海墙钟 00:30 建卡，due 即为本地当日（UTC 口径 +1 天恰好落回同一天）
	t.Logf("本地 00:30 建卡 due 即为本地当日: %s", localDate)
}

func TestStreak_UTC日期口径(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "标题", "内容")
	shanghai := time.FixedZone("CST", 8*3600)
	today := time.Date(2026, 1, 2, 12, 0, 0, 0, shanghai)
	ctx := context.Background()
	if _, err := s.RecordReview(ctx, noteID, 4, today, "u1"); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	// last_reviewed_at 置为 "2026-01-01T16:30:00Z"（上海墙钟 01-02 00:30）
	_, err := s.db.Exec("UPDATE reviews SET last_reviewed_at = ? WHERE note_id = ? AND user_id = ?",
		"2026-01-01T16:30:00Z", noteID, "u1")
	if err != nil {
		t.Fatalf("更新 last_reviewed_at 失败: %v", err)
	}
	// streak 按 UTC 日期集合计算：{2026-01-01}，cursor 从本地 01-02 回退到 01-01，得 1
	streak, err := s.calcStreak(today, "u1")
	if err != nil {
		t.Fatalf("calcStreak 失败: %v", err)
	}
	if streak != 1 {
		t.Errorf("期望 streak==1，实际 %d", streak)
	}
}

func TestDigest_空库返回空(t *testing.T) {
	s := newDeepTestStore(t)
	now := time.Now()
	notes, err := s.DigestNotes(now, 10, "u1")
	if err != nil {
		t.Fatalf("DigestNotes 失败: %v", err)
	}
	if len(notes) != 0 {
		t.Errorf("期望空库返回空，实际 len=%d", len(notes))
	}
}

func TestDigest_n非正默认50(t *testing.T) {
	s := newDeepTestStore(t)
	now := time.Now()
	notes, err := s.DigestNotes(now, 0, "u1")
	if err != nil {
		t.Fatalf("DigestNotes(now, 0) 失败: %v", err)
	}
	if len(notes) != 0 {
		t.Errorf("n=0 空库应返回空，实际 len=%d", len(notes))
	}
	notes, err = s.DigestNotes(now, -5, "u1")
	if err != nil {
		t.Fatalf("DigestNotes(now, -5) 失败: %v", err)
	}
	if len(notes) != 0 {
		t.Errorf("n=-5 空库应返回空，实际 len=%d", len(notes))
	}
	seedNote(t, s, "标题1", "内容1")
	seedNote(t, s, "标题2", "内容2")
	seedNote(t, s, "标题3", "内容3")
	notes, err = s.DigestNotes(now, 0, "u1")
	if err != nil {
		t.Fatalf("DigestNotes(now, 0) 失败: %v", err)
	}
	if len(notes) != 3 {
		t.Errorf("n=0 默认 50 应返回 3 篇，实际 len=%d", len(notes))
	}
}

func TestDigest_到期优先排序(t *testing.T) {
	s := newDeepTestStore(t)
	ctx := context.Background()
	id1 := seedNote(t, s, "标题1", "内容1")
	id2 := seedNote(t, s, "标题2", "内容2")
	id3 := seedNote(t, s, "标题3", "内容3")

	// grade 4 首次 interval=1，due=todayUTC+1
	if _, err := s.RecordReview(ctx, id1, 4, time.Date(2026, 1, 4, 0, 0, 0, 0, time.UTC), "u1"); err != nil {
		t.Fatalf("RecordReview id1 失败: %v", err)
	}
	if _, err := s.RecordReview(ctx, id2, 4, time.Date(2026, 1, 2, 0, 0, 0, 0, time.UTC), "u1"); err != nil {
		t.Fatalf("RecordReview id2 失败: %v", err)
	}
	if _, err := s.RecordReview(ctx, id3, 4, time.Date(2026, 1, 3, 0, 0, 0, 0, time.UTC), "u1"); err != nil {
		t.Fatalf("RecordReview id3 失败: %v", err)
	}

	digestToday := time.Date(2026, 1, 6, 0, 0, 0, 0, time.UTC)
	notes, err := s.DigestNotes(digestToday, 10, "u1")
	if err != nil {
		t.Fatalf("DigestNotes 失败: %v", err)
	}
	if len(notes) != 3 {
		t.Fatalf("期望 3 篇，实际 %d", len(notes))
	}
	// 到期优先 ORDER BY due_date ASC：01-03(id2), 01-04(id3), 01-05(id1)
	expectedOrder := []int64{id2, id3, id1}
	for i, n := range notes {
		if n.ID != expectedOrder[i] {
			t.Errorf("位置 %d 期望笔记 %d，实际 %d", i, expectedOrder[i], n.ID)
		}
	}
}

func TestReviewed7d_边界含7天整(t *testing.T) {
	s := newDeepTestStore(t)
	noteID := seedNote(t, s, "标题", "内容")
	now := time.Date(2026, 1, 10, 12, 0, 0, 0, time.UTC)
	ctx := context.Background()
	if _, err := s.RecordReview(ctx, noteID, 4, now, "u1"); err != nil {
		t.Fatalf("RecordReview 失败: %v", err)
	}
	// 把 last_reviewed_at 改为恰好 now-7 天（秒级），验证 >= 边界含端点
	sevenDaysAgo := now.AddDate(0, 0, -7)
	_, err := s.db.Exec("UPDATE reviews SET last_reviewed_at = ? WHERE note_id = ? AND user_id = ?",
		sevenDaysAgo.Format(time.RFC3339), noteID, "u1")
	if err != nil {
		t.Fatalf("更新 last_reviewed_at 失败: %v", err)
	}
	stats, err := s.ReviewStats(now, "u1")
	if err != nil {
		t.Fatalf("ReviewStats 失败: %v", err)
	}
	if stats.Reviewed7d != 1 {
		t.Errorf("期望 Reviewed7d==1，实际 %d", stats.Reviewed7d)
	}
}
