package store

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func TestReviewForecast_EmptyStore(t *testing.T) {
	s := newTestStore(t)
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	got, err := s.ReviewForecast(base, DefaultUser, 7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got.Days != 7 {
		t.Errorf("expected Days=7, got %d", got.Days)
	}
	if len(got.Forecast) != 7 {
		t.Errorf("expected Forecast length 7, got %d", len(got.Forecast))
	}
	if got.Overdue != 0 {
		t.Errorf("expected Overdue=0, got %d", got.Overdue)
	}
	if got.Total != 0 {
		t.Errorf("expected Total=0, got %d", got.Total)
	}
	for i, fd := range got.Forecast {
		wantDate := base.AddDate(0, 0, i).Format("2006-01-02")
		if fd.Date != wantDate {
			t.Errorf("forecast[%d]: expected date %s, got %s", i, wantDate, fd.Date)
		}
		if fd.Due != 0 {
			t.Errorf("forecast[%d]: expected Due=0, got %d", i, fd.Due)
		}
	}
}

func TestReviewForecast_CountAndWindow(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	seq := 0
	createWithDue := func(user string, dueOffset int) {
		seq++
		note, err := s.CreateNote(Note{Title: fmt.Sprintf("note-%d", seq), Body: "body"})
		noteID := note.ID
		if err != nil {
			t.Fatalf("CreateNote: %v", err)
		}
		if _, err := s.RecordReview(ctx, noteID, 3, base, user); err != nil {
			t.Fatalf("RecordReview: %v", err)
		}
		dueStr := base.AddDate(0, 0, dueOffset).Format("2006-01-02")
		if _, err := s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, dueStr, noteID, user); err != nil {
			t.Fatalf("UPDATE reviews: %v", err)
		}
	}

	// base+0: 1 note
	createWithDue(DefaultUser, 0)
	// base+1: 2 notes
	createWithDue(DefaultUser, 1)
	createWithDue(DefaultUser, 1)
	// base+3: 1 note
	createWithDue(DefaultUser, 3)
	// base-1: 1 note (overdue)
	createWithDue(DefaultUser, -1)
	// base+40: 1 note (outside 7-day window)
	createWithDue(DefaultUser, 40)

	got, err := s.ReviewForecast(base, DefaultUser, 7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got.Days != 7 {
		t.Errorf("expected Days=7, got %d", got.Days)
	}
	if len(got.Forecast) != 7 {
		t.Errorf("expected Forecast length 7, got %d", len(got.Forecast))
	}

	wantDue := []int{1, 2, 0, 1, 0, 0, 0}
	for i, fd := range got.Forecast {
		if fd.Due != wantDue[i] {
			t.Errorf("forecast[%d]: expected Due=%d, got %d", i, wantDue[i], fd.Due)
		}
	}
	if got.Overdue != 1 {
		t.Errorf("expected Overdue=1, got %d", got.Overdue)
	}
	if got.Total != 5 {
		t.Errorf("expected Total=5, got %d", got.Total)
	}
}

func TestReviewForecast_UserIsolation(t *testing.T) {
	s := newTestStore(t)
	ctx := context.Background()
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	seq := 0
	createWithDue := func(user string, dueOffset int) {
		seq++
		note, err := s.CreateNote(Note{Title: fmt.Sprintf("note-%d", seq), Body: "body"})
		noteID := note.ID
		if err != nil {
			t.Fatalf("CreateNote: %v", err)
		}
		if _, err := s.RecordReview(ctx, noteID, 3, base, user); err != nil {
			t.Fatalf("RecordReview: %v", err)
		}
		dueStr := base.AddDate(0, 0, dueOffset).Format("2006-01-02")
		if _, err := s.db.Exec(`UPDATE reviews SET due_date=? WHERE note_id=? AND user_id=?`, dueStr, noteID, user); err != nil {
			t.Fatalf("UPDATE reviews: %v", err)
		}
	}

	// DefaultUser data (same layout as case 2)
	createWithDue(DefaultUser, 0)
	createWithDue(DefaultUser, 1)
	createWithDue(DefaultUser, 1)
	createWithDue(DefaultUser, 3)
	createWithDue(DefaultUser, -1)
	createWithDue(DefaultUser, 40)

	// "other" user: 1 note due on base date
	createWithDue("other", 0)

	// Assert DefaultUser forecast is unchanged by "other" user data
	defaultGot, err := s.ReviewForecast(base, DefaultUser, 7)
	if err != nil {
		t.Fatalf("DefaultUser ReviewForecast: %v", err)
	}
	wantDue := []int{1, 2, 0, 1, 0, 0, 0}
	for i, fd := range defaultGot.Forecast {
		if fd.Due != wantDue[i] {
			t.Errorf("DefaultUser forecast[%d]: expected Due=%d, got %d", i, wantDue[i], fd.Due)
		}
	}
	if defaultGot.Overdue != 1 {
		t.Errorf("DefaultUser: expected Overdue=1, got %d", defaultGot.Overdue)
	}
	if defaultGot.Total != 5 {
		t.Errorf("DefaultUser: expected Total=5, got %d", defaultGot.Total)
	}

	// Assert "other" user forecast
	otherGot, err := s.ReviewForecast(base, "other", 7)
	if err != nil {
		t.Fatalf("other ReviewForecast: %v", err)
	}
	if len(otherGot.Forecast) < 1 {
		t.Fatalf("other: Forecast length %d, need at least 1", len(otherGot.Forecast))
	}
	if otherGot.Forecast[0].Due != 1 {
		t.Errorf("other forecast[0]: expected Due=1, got %d", otherGot.Forecast[0].Due)
	}
	if otherGot.Overdue != 0 {
		t.Errorf("other: expected Overdue=0, got %d", otherGot.Overdue)
	}
	if otherGot.Total != 1 {
		t.Errorf("other: expected Total=1, got %d", otherGot.Total)
	}
}

func TestReviewForecast_Clamping(t *testing.T) {
	s := newTestStore(t)
	base := time.Date(2024, 6, 6, 12, 0, 0, 0, time.Local)

	cases := []struct {
		name     string
		days     int
		wantDays int
		wantFLen int
	}{
		{"DaysZeroClampsTo7", 0, 7, 7},
		{"DaysNegativeClampsTo7", -3, 7, 7},
		{"Days31ClampsTo30", 31, 30, 30},
		{"Days100ClampsTo30", 100, 30, 30},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := s.ReviewForecast(base, DefaultUser, tc.days)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got.Days != tc.wantDays {
				t.Errorf("expected Days=%d, got %d", tc.wantDays, got.Days)
			}
			if len(got.Forecast) != tc.wantFLen {
				t.Errorf("expected Forecast length %d, got %d", tc.wantFLen, len(got.Forecast))
			}
		})
	}
}
