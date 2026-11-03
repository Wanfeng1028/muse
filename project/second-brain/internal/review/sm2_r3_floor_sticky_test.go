package review

import (
	"testing"
	"time"
)

func TestSM2_HardGradeEFFloorStickyThreeTimes(t *testing.T) {
	today := time.Date(2026, 3, 10, 0, 0, 0, 0, time.UTC)
	const tol = 1e-9

	s := State{EF: 1.3, IntervalDays: 7, Repetitions: 2}

	// 第一次 Grade=3
	s = Next(s, GradeHard, today)
	if diff := s.EF - 1.3; diff > tol || diff < -tol {
		t.Fatalf("第一次 Grade=3 后 EF 期望 1.3，实际 %v", s.EF)
	}
	if s.Repetitions != 3 {
		t.Fatalf("第一次 Grade=3 后 Repetitions 期望 3，实际 %d", s.Repetitions)
	}
	if s.IntervalDays != 9 {
		t.Fatalf("第一次 Grade=3 后 IntervalDays 期望 9 (round(7*1.3)=9)，实际 %d", s.IntervalDays)
	}
	if want := "2026-03-19"; s.DueDate != want {
		t.Fatalf("第一次 Grade=3 后 DueDate 期望 %s，实际 %s", want, s.DueDate)
	}

	// 第二次 Grade=3
	s = Next(s, GradeHard, today)
	if diff := s.EF - 1.3; diff > tol || diff < -tol {
		t.Fatalf("第二次 Grade=3 后 EF 期望 1.3，实际 %v", s.EF)
	}
	if s.Repetitions != 4 {
		t.Fatalf("第二次 Grade=3 后 Repetitions 期望 4，实际 %d", s.Repetitions)
	}
	if s.IntervalDays != 12 {
		t.Fatalf("第二次 Grade=3 后 IntervalDays 期望 12 (round(9*1.3)=12)，实际 %d", s.IntervalDays)
	}
	if want := "2026-03-22"; s.DueDate != want {
		t.Fatalf("第二次 Grade=3 后 DueDate 期望 %s，实际 %s", want, s.DueDate)
	}

	// 第三次 Grade=3
	s = Next(s, GradeHard, today)
	if diff := s.EF - 1.3; diff > tol || diff < -tol {
		t.Fatalf("第三次 Grade=3 后 EF 期望 1.3，实际 %v", s.EF)
	}
	if s.Repetitions != 5 {
		t.Fatalf("第三次 Grade=3 后 Repetitions 期望 5，实际 %d", s.Repetitions)
	}
	if s.IntervalDays != 16 {
		t.Fatalf("第三次 Grade=3 后 IntervalDays 期望 16 (round(12*1.3)=16)，实际 %d", s.IntervalDays)
	}
	if want := "2026-03-26"; s.DueDate != want {
		t.Fatalf("第三次 Grade=3 后 DueDate 期望 %s，实际 %s", want, s.DueDate)
	}
}