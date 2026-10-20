package review

import (
	"testing"
	"time"
)

func TestNextMonthRollover(t *testing.T) {
	today := time.Date(2026, 4, 30, 0, 0, 0, 0, time.UTC)
	s := State{EF: 2.5, IntervalDays: 0, Repetitions: 1}

	got := Next(s, GradeEasy, today)

	if got.Repetitions != 2 {
		t.Fatalf("Repetitions: expected 2, got %d", got.Repetitions)
	}
	if got.IntervalDays != 6 {
		t.Fatalf("IntervalDays: expected 6, got %d", got.IntervalDays)
	}
	if got.DueDate != "2026-05-06" {
		t.Fatalf("DueDate: expected 2026-05-06, got %s", got.DueDate)
	}
}

func TestInitialStateNonLeapFebruary(t *testing.T) {
	today := time.Date(2026, 2, 28, 0, 0, 0, 0, time.UTC)

	s0 := InitialState(today)
	if s0.DueDate != "2026-03-01" {
		t.Fatalf("InitialState DueDate: expected 2026-03-01, got %s", s0.DueDate)
	}

	s1 := Next(s0, GradeEasy, today)
	if s1.IntervalDays != 1 {
		t.Fatalf("Next IntervalDays: expected 1, got %d", s1.IntervalDays)
	}
	if s1.DueDate != "2026-03-01" {
		t.Fatalf("Next DueDate: expected 2026-03-01, got %s", s1.DueDate)
	}
}

func TestDueDateUTCBehindLocalMidnight(t *testing.T) {
	cst := time.FixedZone("CST", 8*3600)
	today := time.Date(2026, 1, 2, 0, 30, 0, 0, cst)

	s0 := InitialState(today)
	if s0.DueDate != "2026-01-02" {
		t.Fatalf("InitialState DueDate: expected 2026-01-02 (UTC 2026-01-01 + 1 day), got %s", s0.DueDate)
	}
}