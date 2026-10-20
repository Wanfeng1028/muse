package review

import (
	"math"
	"testing"
	"time"
)

func TestSM2_R3_RoundHalfAwayFromZeroInterval(t *testing.T) {
	today := time.Date(2026, 1, 5, 0, 0, 0, 0, time.UTC)

	// Case 1: round(5*2.5)=round(12.5)=13 (half-away-from-zero, not banker's 12)
	s1 := State{EF: 2.5, IntervalDays: 5, Repetitions: 2}
	got1 := Next(s1, GradeEasy, today)
	if got1.Repetitions != 3 {
		t.Fatalf("case1: expected Repetitions=3, got %d", got1.Repetitions)
	}
	if got1.IntervalDays != 13 {
		t.Fatalf("case1: expected IntervalDays=13 (round(5*2.5)=round(12.5)), got %d", got1.IntervalDays)
	}
	if got1.DueDate != "2026-01-18" {
		t.Fatalf("case1: expected DueDate=2026-01-18 (today+13), got %q", got1.DueDate)
	}

	// Case 2: round(3*2.5)=round(7.5)=8
	s2 := State{EF: 2.5, IntervalDays: 3, Repetitions: 2}
	got2 := Next(s2, GradeGood, today)
	if got2.Repetitions != 3 {
		t.Fatalf("case2: expected Repetitions=3, got %d", got2.Repetitions)
	}
	if got2.IntervalDays != 8 {
		t.Fatalf("case2: expected IntervalDays=8 (round(3*2.5)=round(7.5)), got %d", got2.IntervalDays)
	}
	if got2.DueDate != "2026-01-13" {
		t.Fatalf("case2: expected DueDate=2026-01-13 (today+8), got %q", got2.DueDate)
	}
}

func TestSM2_R3_EFDeltaFromInitialState(t *testing.T) {
	today := time.Date(2026, 1, 5, 0, 0, 0, 0, time.UTC)
	init := InitialState(today)

	// Grade=3 (hard): EF = 2.5 + (0.1 - 2*(0.08+2*0.02)) = 2.5 + (0.1 - 2*0.12) = 2.5 - 0.14 = 2.36
	hard := Next(init, GradeHard, today)
	wantHardEF := 2.5 + (0.1 - (5-3.0)*(0.08+(5-3.0)*0.02))
	if math.Abs(hard.EF-wantHardEF) > 1e-9 {
		t.Fatalf("GradeHard: expected EF≈%.10f, got %.10f (diff %.3e)", wantHardEF, hard.EF, math.Abs(hard.EF-wantHardEF))
	}
	if math.Abs(hard.EF-2.36) > 1e-9 {
		t.Fatalf("GradeHard: expected EF≈2.36, got %.10f", hard.EF)
	}
	if hard.Repetitions != 1 {
		t.Fatalf("GradeHard: expected Repetitions=1, got %d", hard.Repetitions)
	}
	if hard.IntervalDays != 1 {
		t.Fatalf("GradeHard: expected IntervalDays=1, got %d", hard.IntervalDays)
	}
	if hard.DueDate != "2026-01-06" {
		t.Fatalf("GradeHard: expected DueDate=2026-01-06, got %q", hard.DueDate)
	}

	// Grade=5 (easy): EF = 2.5 + 0.1 = 2.6
	easy := Next(init, GradeEasy, today)
	wantEasyEF := 2.5 + 0.1
	if math.Abs(easy.EF-wantEasyEF) > 1e-9 {
		t.Fatalf("GradeEasy: expected EF≈%.10f, got %.10f (diff %.3e)", wantEasyEF, easy.EF, math.Abs(easy.EF-wantEasyEF))
	}
	if math.Abs(easy.EF-2.6) > 1e-9 {
		t.Fatalf("GradeEasy: expected EF≈2.6, got %.10f", easy.EF)
	}
	if easy.Repetitions != 1 {
		t.Fatalf("GradeEasy: expected Repetitions=1, got %d", easy.Repetitions)
	}
	if easy.IntervalDays != 1 {
		t.Fatalf("GradeEasy: expected IntervalDays=1, got %d", easy.IntervalDays)
	}
	if easy.DueDate != "2026-01-06" {
		t.Fatalf("GradeEasy: expected DueDate=2026-01-06, got %q", easy.DueDate)
	}
}