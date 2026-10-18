package review

import (
	"math"
	"reflect"
	"testing"
	"time"
)

func fixedToday() time.Time {
	return time.Date(2026, 10, 18, 12, 0, 0, 0, time.UTC)
}

func TestSM2_EFClampedAtFloor(t *testing.T) {
	today := fixedToday()
	s := State{EF: 1.4, IntervalDays: 0, Repetitions: 0, DueDate: "2026-10-18"}

	got := Next(s, GradeHard, today)

	if math.Abs(got.EF-1.3) > 1e-9 {
		t.Fatalf("EF = %v, want exactly 1.3 (clamped at floor)", got.EF)
	}
	if got.EF != 1.3 {
		t.Fatalf("EF = %v, want exactly 1.3", got.EF)
	}
}

func TestSM2_EFFloorSticky(t *testing.T) {
	today := fixedToday()
	s := State{EF: 1.3, IntervalDays: 10, Repetitions: 5, DueDate: "2026-10-28"}

	wantReps := 5
	for i := 0; i < 3; i++ {
		s = Next(s, GradeHard, today)
		if s.EF != 1.3 {
			t.Fatalf("iteration %d: EF = %v, want exactly 1.3 (floor sticky)", i, s.EF)
		}
		wantReps++
		if s.Repetitions != wantReps {
			t.Fatalf("iteration %d: Repetitions = %d, want %d", i, s.Repetitions, wantReps)
		}
	}
}

func TestSM2_ForgotResetsProgress(t *testing.T) {
	today := fixedToday()
	s := State{EF: 2.8, IntervalDays: 30, Repetitions: 5, DueDate: "2026-10-01"}

	got := Next(s, GradeForgot, today)

	if got.EF != 2.8 {
		t.Fatalf("EF = %v, want 2.8 (unchanged on forgot)", got.EF)
	}
	if got.IntervalDays != 1 {
		t.Fatalf("IntervalDays = %d, want 1", got.IntervalDays)
	}
	if got.Repetitions != 0 {
		t.Fatalf("Repetitions = %d, want 0", got.Repetitions)
	}
	wantDue := addDays(today, 1)
	if got.DueDate != wantDue {
		t.Fatalf("DueDate = %q, want %q", got.DueDate, wantDue)
	}
	if wantDue != "2026-10-19" {
		t.Fatalf("sanity: addDays(today,1) = %q, want 2026-10-19", wantDue)
	}
}

func TestSM2_IllegalGradeReturnsUnchanged(t *testing.T) {
	today := fixedToday()
	base := State{EF: 2.5, IntervalDays: 6, Repetitions: 2, DueDate: "2026-10-24"}

	for _, g := range []Grade{Grade(-1), Grade(6)} {
		got := Next(base, g, today)
		if !reflect.DeepEqual(got, base) {
			t.Fatalf("grade %d: got %+v, want unchanged %+v", int(g), got, base)
		}
	}
}

func TestSM2_IntervalRoundingAndMinOne(t *testing.T) {
	today := fixedToday()
	s := State{EF: 1.3, IntervalDays: 0, Repetitions: 2, DueDate: "2026-10-18"}

	got := Next(s, GradeGood, today)

	if got.Repetitions != 3 {
		t.Fatalf("Repetitions = %d, want 3", got.Repetitions)
	}
	if got.IntervalDays != 1 {
		t.Fatalf("IntervalDays = %d, want 1 (round(0*1.3)=0 clamped to 1)", got.IntervalDays)
	}
	wantDue := addDays(today, 1)
	if got.DueDate != wantDue {
		t.Fatalf("DueDate = %q, want %q", got.DueDate, wantDue)
	}
	if wantDue != "2026-10-19" {
		t.Fatalf("sanity: wantDue = %q, want 2026-10-19", wantDue)
	}
}

func TestSM2_Grade5EFIncrease(t *testing.T) {
	today := fixedToday()
	s := State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2026-10-18"}

	got := Next(s, GradeEasy, today)

	wantEF := 2.5 + (0.1 - (5-5.0)*(0.08+(5-5.0)*0.02))
	if math.Abs(got.EF-wantEF) > 1e-9 {
		t.Fatalf("EF = %v, want %v", got.EF, wantEF)
	}
	if math.Abs(got.EF-2.6) > 1e-9 {
		t.Fatalf("EF = %v, want 2.6", got.EF)
	}
	if got.Repetitions != 1 {
		t.Fatalf("Repetitions = %d, want 1", got.Repetitions)
	}
	if got.IntervalDays != 1 {
		t.Fatalf("IntervalDays = %d, want 1", got.IntervalDays)
	}
}

func TestSM2_ThirdSuccessUsesEFProduct(t *testing.T) {
	today := fixedToday()
	s := State{EF: 2.7, IntervalDays: 6, Repetitions: 2, DueDate: "2026-10-24"}

	got := Next(s, GradeEasy, today)

	if got.Repetitions != 3 {
		t.Fatalf("Repetitions = %d, want 3", got.Repetitions)
	}
	if got.IntervalDays != 16 {
		t.Fatalf("IntervalDays = %d, want 16 (round(6*2.7)=round(16.2)=16)", got.IntervalDays)
	}
	wantDue := addDays(today, 16)
	if got.DueDate != wantDue {
		t.Fatalf("DueDate = %q, want %q", got.DueDate, wantDue)
	}
	if wantDue != "2026-11-03" {
		t.Fatalf("sanity: addDays(today,16) = %q, want 2026-11-03", wantDue)
	}
}

func TestSM2_DueDateCrossesYearBoundary(t *testing.T) {
	today := time.Date(2026, 12, 31, 12, 0, 0, 0, time.UTC)
	s := InitialState(today)

	if s.DueDate != "2027-01-01" {
		t.Fatalf("InitialState DueDate = %q, want 2027-01-01", s.DueDate)
	}

	got := Next(s, GradeGood, today)
	if got.DueDate != "2027-01-01" {
		t.Fatalf("Next DueDate = %q, want 2027-01-01", got.DueDate)
	}
}

func TestSM2_IsValidGradeBoundaries(t *testing.T) {
	if !IsValidGrade(0) {
		t.Fatalf("IsValidGrade(0) = false, want true")
	}
	if !IsValidGrade(5) {
		t.Fatalf("IsValidGrade(5) = false, want true")
	}
	if IsValidGrade(-1) {
		t.Fatalf("IsValidGrade(-1) = true, want false")
	}
	if IsValidGrade(6) {
		t.Fatalf("IsValidGrade(6) = true, want false")
	}
}

func TestSM2_DueDateMatchesInterval(t *testing.T) {
	today := fixedToday()
	s := State{EF: 2.5, IntervalDays: 6, Repetitions: 2, DueDate: "2026-10-24"}

	got := Next(s, GradeGood, today)

	wantInterval := int(math.Round(float64(s.IntervalDays) * s.EF))
	if wantInterval < 1 {
		wantInterval = 1
	}
	if got.IntervalDays != wantInterval {
		t.Fatalf("IntervalDays = %d, want %d", got.IntervalDays, wantInterval)
	}
	if wantInterval != 15 {
		t.Fatalf("sanity: round(6*2.5) = %d, want 15", wantInterval)
	}

	due, err := time.Parse(dateLayout, got.DueDate)
	if err != nil {
		t.Fatalf("parse DueDate %q: %v", got.DueDate, err)
	}
	todayDate, err := time.Parse(dateLayout, today.Format(dateLayout))
	if err != nil {
		t.Fatalf("parse today: %v", err)
	}
	diff := int(due.Sub(todayDate).Hours() / 24)
	if diff != got.IntervalDays {
		t.Fatalf("DueDate-today diff = %d days, want %d", diff, got.IntervalDays)
	}
	if got.DueDate != "2026-11-02" {
		t.Fatalf("DueDate = %q, want 2026-11-02", got.DueDate)
	}
}
