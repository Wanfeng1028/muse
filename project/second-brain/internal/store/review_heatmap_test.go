package store

import (
	"context"
	"reflect"
	"testing"
	"time"
)

func TestReviewHeatmapDefaults(t *testing.T) {
	s := newTestStore(t)
	today := time.Now()

	cases := []struct {
		days int
		want int
	}{
		{0, 365},
		{-5, 365},
		{500, 366},
		{366, 366},
	}
	for _, tc := range cases {
		res, err := s.ReviewHeatmap(today, DefaultUser, tc.days)
		if err != nil {
			t.Fatalf("days=%d: %v", tc.days, err)
		}
		if len(res) != tc.want {
			t.Errorf("days=%d: got %d rows, want %d", tc.days, len(res), tc.want)
		}
	}
}

func TestReviewHeatmapData(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now().UTC()

	a, err := s.CreateNote(Note{Title: "A", Body: "a"})
	if err != nil {
		t.Fatal(err)
	}
	b, err := s.CreateNote(Note{Title: "B", Body: "b"})
	if err != nil {
		t.Fatal(err)
	}
	c, err := s.CreateNote(Note{Title: "C", Body: "c"})
	if err != nil {
		t.Fatal(err)
	}

	if _, err := s.RecordReview(ctx, a.ID, 4, today, DefaultUser); err != nil {
		t.Fatal(err)
	}
	if _, err := s.RecordReview(ctx, b.ID, 4, today.AddDate(0, 0, -3), DefaultUser); err != nil {
		t.Fatal(err)
	}
	day6 := today.AddDate(0, 0, -6)
	if _, err := s.db.Exec(`UPDATE notes SET created_at=? WHERE id=?`, day6.Format(time.RFC3339), c.ID); err != nil {
		t.Fatal(err)
	}

	res, err := s.ReviewHeatmap(today, DefaultUser, 7)
	if err != nil {
		t.Fatal(err)
	}
	if len(res) != 7 {
		t.Fatalf("got %d rows, want 7", len(res))
	}
	for i := 1; i < len(res); i++ {
		if res[i].Date <= res[i-1].Date {
			t.Errorf("dates not strictly increasing: %s >= %s", res[i-1].Date, res[i].Date)
		}
	}

	todayStr := dateOnly(today)
	day3Str := dateOnly(today.AddDate(0, 0, -3))
	day6Str := dateOnly(day6)

	for _, d := range res {
		switch d.Date {
		case todayStr:
			if d.Reviewed != 1 || d.Added != 2 {
				t.Errorf("today: got Reviewed=%d Added=%d, want 1 2", d.Reviewed, d.Added)
			}
		case day3Str:
			if d.Reviewed != 1 || d.Added != 0 {
				t.Errorf("3 days ago: got Reviewed=%d Added=%d, want 1 0", d.Reviewed, d.Added)
			}
		case day6Str:
			if d.Reviewed != 0 || d.Added != 1 {
				t.Errorf("6 days ago: got Reviewed=%d Added=%d, want 0 1", d.Reviewed, d.Added)
			}
		default:
			if d.Reviewed != 0 || d.Added != 0 {
				t.Errorf("date %s: got Reviewed=%d Added=%d, want 0 0", d.Date, d.Reviewed, d.Added)
			}
		}
	}
}

func TestReviewHeatmapUserIsolation(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now()

	n, err := s.CreateNote(Note{Title: "U2", Body: "u2"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, "u2"); err != nil {
		t.Fatal(err)
	}

	resDefault, err := s.ReviewHeatmap(today, DefaultUser, 7)
	if err != nil {
		t.Fatal(err)
	}
	todayStr := dateOnly(today)
	for _, d := range resDefault {
		if d.Date == todayStr && d.Reviewed != 0 {
			t.Errorf("default user today Reviewed=%d, want 0", d.Reviewed)
		}
	}

	resU2, err := s.ReviewHeatmap(today, "u2", 7)
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, d := range resU2 {
		if d.Date == todayStr {
			found = true
			if d.Reviewed != 1 {
				t.Errorf("u2 today Reviewed=%d, want 1", d.Reviewed)
			}
		}
	}
	if !found {
		t.Error("u2 heatmap missing today entry")
	}
}

func TestReviewHeatmapConsistentWithTrend(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	today := time.Now()

	n, err := s.CreateNote(Note{Title: "T", Body: "t"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.RecordReview(ctx, n.ID, 4, today, DefaultUser); err != nil {
		t.Fatal(err)
	}

	heatmap, err := s.ReviewHeatmap(today, DefaultUser, 7)
	if err != nil {
		t.Fatal(err)
	}
	trend, err := s.ReviewTrend(today, DefaultUser, 7)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(heatmap, trend) {
		t.Errorf("heatmap != trend\nheatmap: %+v\ntrend: %+v", heatmap, trend)
	}
}
