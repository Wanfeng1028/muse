package store

import (
	"context"
	"testing"
	"time"
)

// contains 字节级子串搜索，仅依赖允许的 import
func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

// TestReviewHealthEmpty 空库场景
func TestReviewHealthEmpty(t *testing.T) {
	s := newTestStore(t)
	today := time.Date(2024, 6, 1, 12, 0, 0, 0, time.Local)

	h, err := s.ReviewHealth(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewHealth 失败: %v", err)
	}

	if h.Total != 0 {
		t.Errorf("Total 得到 %d, 期望 0", h.Total)
	}
	if h.DueNow != 0 {
		t.Errorf("DueNow 得到 %d, 期望 0", h.DueNow)
	}
	if h.Overdue7d != 0 {
		t.Errorf("Overdue7d 得到 %d, 期望 0", h.Overdue7d)
	}
	if h.NeverReviewed != 0 {
		t.Errorf("NeverReviewed 得到 %d, 期望 0", h.NeverReviewed)
	}
	if h.AvgEF != 0 {
		t.Errorf("AvgEF 得到 %f, 期望 0", h.AvgEF)
	}

	// EFBuckets 长度 4，四档 Label 顺序正确，Count 全 0
	if len(h.EFBuckets) != 4 {
		t.Fatalf("EFBuckets 长度得到 %d, 期望 4", len(h.EFBuckets))
	}
	wantLabels := [4]string{"1.5以下", "1.5到2.0", "2.0到2.5", "2.5以上"}
	for i, want := range wantLabels {
		if h.EFBuckets[i].Label != want {
			t.Errorf("EFBuckets[%d].Label 得到 %q, 期望 %q", i, h.EFBuckets[i].Label, want)
		}
		if h.EFBuckets[i].Count != 0 {
			t.Errorf("EFBuckets[%d].Count 得到 %d, 期望 0", i, h.EFBuckets[i].Count)
		}
	}

	if h.Attention == nil {
		t.Error("Attention 为 nil, 期望非 nil")
	}
	if len(h.Attention) != 0 {
		t.Errorf("Attention 长度得到 %d, 期望 0", len(h.Attention))
	}

	if len(h.Advice) < 1 {
		t.Fatalf("Advice 长度得到 %d, 期望至少 1", len(h.Advice))
	}
	foundEmpty := false
	for _, a := range h.Advice {
		if contains(a, "还没有复习数据") {
			foundEmpty = true
			break
		}
	}
	if !foundEmpty {
		t.Errorf("Advice 缺少 '还没有复习数据', 得到 %v", h.Advice)
	}
}

// TestReviewHealthSummary 汇总场景
func TestReviewHealthSummary(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Date(2024, 6, 1, 12, 0, 0, 0, time.Local)

	// noteA: RecordReview 一次，due=次日，不逾期
	noteA, err := s.CreateNote(Note{Title: "A", Body: "a"})
	if err != nil {
		t.Fatal(err)
	}
	s.RecordReview(ctx, noteA.ID, 4, today, DefaultUser)

	// noteB: RecordReview 一次后 UPDATE due_date 为 10 天前
	noteB, err := s.CreateNote(Note{Title: "B", Body: "b"})
	if err != nil {
		t.Fatal(err)
	}
	s.RecordReview(ctx, noteB.ID, 4, today, DefaultUser)
	due10dAgo := today.AddDate(0, 0, -10).Format("2006-01-02")
	s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, due10dAgo, noteB.ID, DefaultUser)

	// noteC: 不复习，due=次日，last_reviewed_at=NULL
	if _, err := s.CreateNote(Note{Title: "C", Body: "c"}); err != nil {
		t.Fatal(err)
	}

	h, err := s.ReviewHealth(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewHealth 失败: %v", err)
	}

	if h.Total != 3 {
		t.Errorf("Total 得到 %d, 期望 3", h.Total)
	}
	if h.DueNow != 1 {
		t.Errorf("DueNow 得到 %d, 期望 1", h.DueNow)
	}
	if h.Overdue7d != 1 {
		t.Errorf("Overdue7d 得到 %d, 期望 1", h.Overdue7d)
	}
	if h.NeverReviewed != 1 {
		t.Errorf("NeverReviewed 得到 %d, 期望 1", h.NeverReviewed)
	}
	if h.AvgEF <= 0 {
		t.Errorf("AvgEF 得到 %f, 期望 > 0", h.AvgEF)
	}
}

// TestReviewHealthEfFloor EF触底场景
func TestReviewHealthEfFloor(t *testing.T) {
	s := newTestStore(t)
	today := time.Date(2024, 6, 1, 12, 0, 0, 0, time.Local)

	note, err := s.CreateNote(Note{Title: "EF", Body: "ef"})
	if err != nil {
		t.Fatal(err)
	}
	// 直接造数：EF 贴底 1.3、已复习 2 次（SM-2 里 grade<3 时 EF 不变，真实评分打不到贴底，测聚合逻辑直接写库）
	if _, err := s.db.Exec(`UPDATE reviews SET ef=1.3, reviewed_count=2, last_reviewed_at=?, due_date=? WHERE note_id=? AND user_id=?`,
		today.Format(time.RFC3339), dateOnly(today.AddDate(0, 0, 1)), note.ID, DefaultUser); err != nil {
		t.Fatal(err)
	}

	h, err := s.ReviewHealth(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewHealth 失败: %v", err)
	}

	if len(h.Attention) != 1 {
		t.Fatalf("Attention 长度得到 %d, 期望 1", len(h.Attention))
	}
	a := h.Attention[0]
	if a.Reason != "ef_floor" {
		t.Errorf("Reason 得到 %q, 期望 'ef_floor'", a.Reason)
	}
	if !contains(a.ReasonText, "贴到底") {
		t.Errorf("ReasonText 得到 %q, 期望包含 '贴到底'", a.ReasonText)
	}
	if a.ReviewedCount != 2 {
		t.Errorf("ReviewedCount 得到 %d, 期望 2", a.ReviewedCount)
	}
	if a.EF > 1.35 {
		t.Errorf("EF 得到 %f, 期望 <= 1.35", a.EF)
	}

	// Advice 中有含"拆小"的条目
	found := false
	for _, adv := range h.Advice {
		if contains(adv, "拆小") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("Advice 缺少 '拆小', 得到 %v", h.Advice)
	}
}

// TestReviewHealthOverdueLong 长期逾期场景
func TestReviewHealthOverdueLong(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Date(2024, 6, 1, 12, 0, 0, 0, time.Local)

	note, err := s.CreateNote(Note{Title: "Overdue", Body: "o"})
	if err != nil {
		t.Fatal(err)
	}
	s.RecordReview(ctx, note.ID, 4, today, DefaultUser)
	// UPDATE due_date 为 10 天前，last_reviewed_at 保持非空
	due10dAgo := today.AddDate(0, 0, -10).Format("2006-01-02")
	s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, due10dAgo, note.ID, DefaultUser)

	h, err := s.ReviewHealth(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewHealth 失败: %v", err)
	}

	if h.Overdue7d != 1 {
		t.Errorf("Overdue7d 得到 %d, 期望 1", h.Overdue7d)
	}
	if len(h.Attention) != 1 {
		t.Fatalf("Attention 长度得到 %d, 期望 1", len(h.Attention))
	}
	a := h.Attention[0]
	if a.Reason != "overdue_long" {
		t.Errorf("Reason 得到 %q, 期望 'overdue_long'", a.Reason)
	}
	if a.OverdueDays != 10 {
		t.Errorf("OverdueDays 得到 %d, 期望 10", a.OverdueDays)
	}
	if a.Title != "Overdue" {
		t.Errorf("Title 得到 %q, 期望 'Overdue'", a.Title)
	}

	// Advice 中有含"逾期的清完"的条目
	found := false
	for _, adv := range h.Advice {
		if contains(adv, "逾期的清完") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("Advice 缺少 '逾期的清完', 得到 %v", h.Advice)
	}
}

// TestReviewHealthNeverReviewedLong 从未复习且长期逾期场景
func TestReviewHealthNeverReviewedLong(t *testing.T) {
	s := newTestStore(t)
	today := time.Date(2024, 6, 1, 12, 0, 0, 0, time.Local)

	note, err := s.CreateNote(Note{Title: "Never", Body: "n"})
	if err != nil {
		t.Fatal(err)
	}
	// 不复习，UPDATE due_date 为 40 天前
	due40dAgo := today.AddDate(0, 0, -40).Format("2006-01-02")
	s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, due40dAgo, note.ID, DefaultUser)

	h, err := s.ReviewHealth(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewHealth 失败: %v", err)
	}

	if h.NeverReviewed != 1 {
		t.Errorf("NeverReviewed 得到 %d, 期望 1", h.NeverReviewed)
	}

	// Attention 中有 Reason=="never_reviewed_long" 的条目
	foundAtt := false
	for _, a := range h.Attention {
		if a.Reason == "never_reviewed_long" {
			foundAtt = true
			break
		}
	}
	if !foundAtt {
		t.Errorf("Attention 缺少 'never_reviewed_long', 得到 %v", h.Attention)
	}

	// Advice 中有含"一次都没复习过"的条目
	foundAdv := false
	for _, adv := range h.Advice {
		if contains(adv, "一次都没复习过") {
			foundAdv = true
			break
		}
	}
	if !foundAdv {
		t.Errorf("Advice 缺少 '一次都没复习过', 得到 %v", h.Advice)
	}
}

// TestReviewHealthUserIsolation 用户隔离场景
func TestReviewHealthUserIsolation(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Date(2024, 6, 1, 12, 0, 0, 0, time.Local)

	note, err := s.CreateNoteFor(ctx, Note{Title: "UA", Body: "u"}, "alice")
	if err != nil {
		t.Fatal(err)
	}
	s.RecordReview(ctx, note.ID, 4, today, "alice")

	hAlice, err := s.ReviewHealth(today, "alice")
	if err != nil {
		t.Fatalf("ReviewHealth alice 失败: %v", err)
	}
	if hAlice.Total != 1 {
		t.Errorf("alice Total 得到 %d, 期望 1", hAlice.Total)
	}

	hLocal, err := s.ReviewHealth(today, DefaultUser)
	if err != nil {
		t.Fatalf("ReviewHealth local 失败: %v", err)
	}
	if hLocal.Total != 0 {
		t.Errorf("local Total 得到 %d, 期望 0", hLocal.Total)
	}
	found := false
	for _, adv := range hLocal.Advice {
		if contains(adv, "还没有复习数据") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("local Advice 缺少 '还没有复习数据', 得到 %v", hLocal.Advice)
	}
}
