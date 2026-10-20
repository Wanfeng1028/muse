package review

import (
	"math"
	"testing"
	"time"
)

func TestSM2_Grade1ResetsProgressKeepsEF(t *testing.T) {
	today := time.Date(2026, 2, 10, 0, 0, 0, 0, time.UTC)

	s := State{EF: 2.9, IntervalDays: 16, Repetitions: 4}
	got := Next(s, Grade(1), today)

	if got.Repetitions != 0 {
		t.Fatalf("grade=1 失败后 Repetitions 期望 0，实际 %d", got.Repetitions)
	}
	if got.IntervalDays != 1 {
		t.Fatalf("grade=1 失败后 IntervalDays 期望 1，实际 %d", got.IntervalDays)
	}
	if got.DueDate != "2026-02-11" {
		t.Fatalf("grade=1 失败后 DueDate 期望 2026-02-11，实际 %q", got.DueDate)
	}
	if math.Abs(got.EF-2.9) > 1e-9 {
		t.Fatalf("grade=1 失败只重置进度不应惩罚 EF，期望 EF≈2.9，实际 %.12f", got.EF)
	}
}

func TestSM2_Grade1FromInitialState(t *testing.T) {
	today := time.Date(2026, 2, 10, 0, 0, 0, 0, time.UTC)

	got := Next(InitialState(today), Grade(1), today)

	if got.Repetitions != 0 {
		t.Fatalf("初始状态 grade=1 后 Repetitions 期望 0，实际 %d", got.Repetitions)
	}
	if got.IntervalDays != 1 {
		t.Fatalf("初始状态 grade=1 后 IntervalDays 期望 1，实际 %d", got.IntervalDays)
	}
	if math.Abs(got.EF-2.5) > 1e-9 {
		t.Fatalf("初始状态 grade=1 后 EF 期望保持 2.5，实际 %.12f", got.EF)
	}
	if got.DueDate != "2026-02-11" {
		t.Fatalf("初始状态 grade=1 后 DueDate 期望 2026-02-11，实际 %q", got.DueDate)
	}
}

func TestSM2_IsValidGradeAcceptsOne(t *testing.T) {
	if !IsValidGrade(1) {
		t.Fatalf("IsValidGrade(1) 期望 true（1 是合法评分，只是 <3 视为失败），实际 false")
	}
}