package review

import (
	"math"
	"testing"
	"time"
)

func TestSM2_R3_OldEFUsedForIntervalBeforeUpdate(t *testing.T) {
	today := time.Date(2026, 4, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 2.5, IntervalDays: 6, Repetitions: 2}

	got := Next(s, GradeEasy, today)

	if got.Repetitions != 3 {
		t.Fatalf("Repetitions: want 3, got %d", got.Repetitions)
	}
	if got.IntervalDays != 15 {
		t.Fatalf("IntervalDays: want 15 (round(6*2.5) using old EF), got %d", got.IntervalDays)
	}
	if math.Abs(got.EF-2.6) > 1e-9 {
		t.Fatalf("EF: want ~2.6, got %.12f", got.EF)
	}
	if got.DueDate != "2026-04-16" {
		t.Fatalf("DueDate: want 2026-04-16, got %s", got.DueDate)
	}
}

func TestSM2_R3_LeapDayTwoStepChain(t *testing.T) {
	today1 := time.Date(2024, 2, 28, 0, 0, 0, 0, time.UTC)

	s0 := InitialState(today1)
	if s0.DueDate != "2024-02-29" {
		t.Fatalf("InitialState DueDate: want 2024-02-29, got %s", s0.DueDate)
	}

	s1 := Next(s0, GradeEasy, today1)
	if s1.Repetitions != 1 {
		t.Fatalf("s1 Repetitions: want 1, got %d", s1.Repetitions)
	}
	if s1.IntervalDays != 1 {
		t.Fatalf("s1 IntervalDays: want 1, got %d", s1.IntervalDays)
	}
	if s1.DueDate != "2024-02-29" {
		t.Fatalf("s1 DueDate: want 2024-02-29, got %s", s1.DueDate)
	}

	today2 := time.Date(2024, 2, 29, 0, 0, 0, 0, time.UTC)
	s2 := Next(s1, GradeEasy, today2)
	if s2.Repetitions != 2 {
		t.Fatalf("s2 Repetitions: want 2, got %d", s2.Repetitions)
	}
	if s2.IntervalDays != 6 {
		t.Fatalf("s2 IntervalDays: want 6, got %d", s2.IntervalDays)
	}
	if s2.DueDate != "2024-03-06" {
		t.Fatalf("s2 DueDate: want 2024-03-06, got %s", s2.DueDate)
	}
}