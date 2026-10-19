package store

import (
	"context"
	"testing"
	"time"
)

func TestReviewTrend(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()

	// 造 3 篇笔记，均在今天创建
	a, err := s.CreateNote(Note{Title: "A", Body: "a"})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}
	b, err := s.CreateNote(Note{Title: "B", Body: "b"})
	if err != nil {
		t.Fatalf("CreateNote B: %v", err)
	}
	c, err := s.CreateNote(Note{Title: "C", Body: "c"})
	if err != nil {
		t.Fatalf("CreateNote C: %v", err)
	}

	// A 今天复习，B 今天-3 天复习，C 从不复习
	if _, err := s.RecordReview(ctx, a.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("RecordReview A: %v", err)
	}
	if _, err := s.RecordReview(ctx, b.ID, 4, today.AddDate(0, 0, -3), DefaultUser); err != nil {
		t.Fatalf("RecordReview B: %v", err)
	}

	// 把 C 的 created_at 改到 today-6
	oldDate := today.AddDate(0, 0, -6).Format(time.RFC3339)
	if _, err := s.db.Exec(`UPDATE notes SET created_at=? WHERE id=?`, oldDate, c.ID); err != nil {
		t.Fatalf("UPDATE created_at: %v", err)
	}

	trend, err := s.ReviewTrend(today, DefaultUser, 7)
	if err != nil {
		t.Fatalf("ReviewTrend: %v", err)
	}
	if len(trend) != 7 {
		t.Fatalf("len(trend)=%d, want 7", len(trend))
	}
	// 升序校验
	for i := 1; i < len(trend); i++ {
		if trend[i-1].Date >= trend[i].Date {
			t.Fatalf("trend not ascending: %q >= %q", trend[i-1].Date, trend[i].Date)
		}
	}

	wantToday := dateOnly(today)
	wantMinus3 := dateOnly(today.AddDate(0, 0, -3))
	wantMinus6 := dateOnly(today.AddDate(0, 0, -6))

	seenToday, seenMinus3, seenMinus6 := false, false, false
	for _, d := range trend {
		switch d.Date {
		case wantToday:
			seenToday = true
			if d.Reviewed != 1 {
				t.Fatalf("today reviewed=%d, want 1", d.Reviewed)
			}
			// C 的 created_at 被改到 today-6，今天实际新建 2 篇（A、B）
			if d.Added != 2 {
				t.Fatalf("today added=%d, want 2", d.Added)
			}
		case wantMinus3:
			seenMinus3 = true
			if d.Reviewed != 1 {
				t.Fatalf("today-3 reviewed=%d, want 1", d.Reviewed)
			}
			if d.Added != 0 {
				t.Fatalf("today-3 added=%d, want 0", d.Added)
			}
		case wantMinus6:
			seenMinus6 = true
			if d.Reviewed != 0 {
				t.Fatalf("today-6 reviewed=%d, want 0", d.Reviewed)
			}
			if d.Added != 1 {
				t.Fatalf("today-6 added=%d, want 1", d.Added)
			}
		default:
			if d.Reviewed != 0 {
				t.Fatalf("date %s reviewed=%d, want 0", d.Date, d.Reviewed)
			}
			if d.Added != 0 {
				t.Fatalf("date %s added=%d, want 0", d.Date, d.Added)
			}
		}
	}
	if !seenToday || !seenMinus3 || !seenMinus6 {
		t.Fatalf("missing expected dates: today=%v minus3=%v minus6=%v", seenToday, seenMinus3, seenMinus6)
	}

	// days=0 → 默认 7
	trendDefault, err := s.ReviewTrend(today, DefaultUser, 0)
	if err != nil {
		t.Fatalf("ReviewTrend days=0: %v", err)
	}
	if len(trendDefault) != 7 {
		t.Fatalf("days=0 len=%d, want 7", len(trendDefault))
	}

	// days=100 → 钳到 60
	trendClamp, err := s.ReviewTrend(today, DefaultUser, 100)
	if err != nil {
		t.Fatalf("ReviewTrend days=100: %v", err)
	}
	if len(trendClamp) != 60 {
		t.Fatalf("days=100 len=%d, want 60", len(trendClamp))
	}
}

func TestReviewTrendUserIsolation(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()

	a, err := s.CreateNote(Note{Title: "A", Body: "a"})
	if err != nil {
		t.Fatalf("CreateNote A: %v", err)
	}
	if _, err := s.RecordReview(ctx, a.ID, 4, today, DefaultUser); err != nil {
		t.Fatalf("RecordReview A: %v", err)
	}

	other := "other-user"
	trend, err := s.ReviewTrend(today, other, 7)
	if err != nil {
		t.Fatalf("ReviewTrend other: %v", err)
	}
	if len(trend) != 7 {
		t.Fatalf("len(trend)=%d, want 7", len(trend))
	}
	wantToday := dateOnly(today)
	for _, d := range trend {
		if d.Reviewed != 0 {
			t.Fatalf("date %s reviewed=%d, want 0 for other user", d.Date, d.Reviewed)
		}
		if d.Date == wantToday && d.Added != 1 {
			t.Fatalf("today added=%d, want 1 (notes global)", d.Added)
		}
	}
}
