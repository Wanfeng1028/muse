package review

import (
	"math"
	"testing"
	"time"
)

func TestSM2FiveDayInterruptChain(t *testing.T) {
	const eps = 1e-9

	day1 := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	day2 := time.Date(2026, 1, 2, 0, 0, 0, 0, time.UTC)
	day3 := time.Date(2026, 1, 8, 0, 0, 0, 0, time.UTC)
	day4 := time.Date(2026, 1, 9, 0, 0, 0, 0, time.UTC)
	day5 := time.Date(2026, 1, 10, 0, 0, 0, 0, time.UTC)

	s0 := InitialState(day1)
	if math.Abs(s0.EF-2.5) > eps {
		t.Fatalf("day1 InitialState EF: want 2.5, got %v", s0.EF)
	}
	if s0.IntervalDays != 0 {
		t.Fatalf("day1 InitialState IntervalDays: want 0, got %d", s0.IntervalDays)
	}
	if s0.Repetitions != 0 {
		t.Fatalf("day1 InitialState Repetitions: want 0, got %d", s0.Repetitions)
	}
	if s0.DueDate != "2026-01-02" {
		t.Fatalf("day1 InitialState DueDate: want 2026-01-02, got %s", s0.DueDate)
	}

	s1 := Next(s0, GradeEasy, day1)
	if s1.Repetitions != 1 {
		t.Fatalf("day1 Next(Easy) Repetitions: want 1, got %d", s1.Repetitions)
	}
	if s1.IntervalDays != 1 {
		t.Fatalf("day1 Next(Easy) IntervalDays: want 1, got %d", s1.IntervalDays)
	}
	if math.Abs(s1.EF-2.6) > eps {
		t.Fatalf("day1 Next(Easy) EF: want 2.6, got %v", s1.EF)
	}
	if s1.DueDate != "2026-01-02" {
		t.Fatalf("day1 Next(Easy) DueDate: want 2026-01-02, got %s", s1.DueDate)
	}

	s2 := Next(s1, GradeEasy, day2)
	if s2.Repetitions != 2 {
		t.Fatalf("day2 Next(Easy) Repetitions: want 2, got %d", s2.Repetitions)
	}
	if s2.IntervalDays != 6 {
		t.Fatalf("day2 Next(Easy) IntervalDays: want 6, got %d", s2.IntervalDays)
	}
	if math.Abs(s2.EF-2.7) > eps {
		t.Fatalf("day2 Next(Easy) EF: want 2.7, got %v", s2.EF)
	}
	if s2.DueDate != "2026-01-08" {
		t.Fatalf("day2 Next(Easy) DueDate: want 2026-01-08, got %s", s2.DueDate)
	}

	s3 := Next(s2, GradeForgot, day3)
	if s3.Repetitions != 0 {
		t.Fatalf("day3 Next(Forgot) Repetitions: want 0, got %d", s3.Repetitions)
	}
	if s3.IntervalDays != 1 {
		t.Fatalf("day3 Next(Forgot) IntervalDays: want 1, got %d", s3.IntervalDays)
	}
	if math.Abs(s3.EF-2.7) > eps {
		t.Fatalf("day3 Next(Forgot) EF: want 2.7 (unchanged), got %v", s3.EF)
	}
	if s3.DueDate != "2026-01-09" {
		t.Fatalf("day3 Next(Forgot) DueDate: want 2026-01-09, got %s", s3.DueDate)
	}

	s4 := Next(s3, GradeEasy, day4)
	if s4.Repetitions != 1 {
		t.Fatalf("day4 Next(Easy) Repetitions: want 1, got %d", s4.Repetitions)
	}
	if s4.IntervalDays != 1 {
		t.Fatalf("day4 Next(Easy) IntervalDays: want 1, got %d", s4.IntervalDays)
	}
	if math.Abs(s4.EF-2.8) > eps {
		t.Fatalf("day4 Next(Easy) EF: want 2.8, got %v", s4.EF)
	}
	if s4.DueDate != "2026-01-10" {
		t.Fatalf("day4 Next(Easy) DueDate: want 2026-01-10, got %s", s4.DueDate)
	}

	s5 := Next(s4, GradeEasy, day5)
	if s5.Repetitions != 2 {
		t.Fatalf("day5 Next(Easy) Repetitions: want 2, got %d", s5.Repetitions)
	}
	if s5.IntervalDays != 6 {
		t.Fatalf("day5 Next(Easy) IntervalDays: want 6, got %d", s5.IntervalDays)
	}
	if math.Abs(s5.EF-2.9) > eps {
		t.Fatalf("day5 Next(Easy) EF: want 2.9, got %v", s5.EF)
	}
	if s5.DueDate != "2026-01-16" {
		t.Fatalf("day5 Next(Easy) DueDate: want 2026-01-16, got %s", s5.DueDate)
	}
}