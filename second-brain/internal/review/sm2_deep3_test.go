package review

import (
	"math"
	"reflect"
	"testing"
	"time"
)

func TestSM2_EFNoCeiling_RepeatedGrade5(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := InitialState(today)
	cur := today
	for k := 1; k <= 5; k++ {
		cur = cur.AddDate(0, 0, 1)
		s = Next(s, GradeEasy, cur)
		want := 2.5 + 0.1*float64(k)
		if diff := s.EF - want; math.Abs(diff) >= 1e-9 {
			t.Fatalf("k=%d EF=%v want~%v diff=%v", k, s.EF, want, diff)
		}
	}
	// 再连加到 10 次
	s10 := s
	cur10 := cur
	for k := 6; k <= 10; k++ {
		cur10 = cur10.AddDate(0, 0, 1)
		s10 = Next(s10, GradeEasy, cur10)
	}
	want10 := 3.5
	if diff := s10.EF - want10; math.Abs(diff) >= 1e-9 {
		t.Fatalf("10x EF=%v want~%v diff=%v", s10.EF, want10, diff)
	}
	if s10.EF <= 2.5 {
		t.Fatalf("EF 未增长，疑似被上限钳制: %v", s10.EF)
	}
}

func TestSM2_EFFloorExactMath(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 1.35, IntervalDays: 6, Repetitions: 2}
	got := Next(s, GradeHard, today)
	// delta = 0.1 - 2*(0.08+0.04) = -0.14 → 1.35-0.14 = 1.21 < 1.3 → 钳为 1.3
	if got.EF != 1.3 {
		t.Fatalf("EF=%v want exactly 1.3", got.EF)
	}
}

func TestSM2_ConsecutiveGrade4_Intervals(t *testing.T) {
	today := time.Date(2025, 3, 10, 9, 0, 0, 0, time.UTC)
	s1 := Next(InitialState(today), GradeGood, today)
	if s1.Repetitions != 1 || s1.IntervalDays != 1 || s1.DueDate != "2025-03-11" {
		t.Fatalf("s1=(%d,%d,%q) want (1,1,2025-03-11)", s1.Repetitions, s1.IntervalDays, s1.DueDate)
	}
	d2 := today.AddDate(0, 0, 1)
	s2 := Next(s1, GradeGood, d2)
	if s2.Repetitions != 2 || s2.IntervalDays != 6 || s2.DueDate != "2025-03-17" {
		t.Fatalf("s2=(%d,%d,%q) want (2,6,2025-03-17)", s2.Repetitions, s2.IntervalDays, s2.DueDate)
	}
	d3 := today.AddDate(0, 0, 2)
	s3 := Next(s2, GradeGood, d3)
	// interval = round(6*2.5) = 15；due = 2025-03-12 + 15 = 2025-03-27
	if s3.Repetitions != 3 || s3.IntervalDays != 15 || s3.DueDate != "2025-03-27" {
		t.Fatalf("s3=(%d,%d,%q) want (3,15,2025-03-27)", s3.Repetitions, s3.IntervalDays, s3.DueDate)
	}
	for i, st := range []State{s1, s2, s3} {
		if diff := st.EF - 2.5; math.Abs(diff) >= 1e-9 {
			t.Fatalf("step %d EF=%v want~2.5 diff=%v", i+1, st.EF, diff)
		}
	}
}

func TestSM2_LeapDayDueDate(t *testing.T) {
	t1 := time.Date(2024, 2, 28, 12, 0, 0, 0, time.UTC)
	if got := Next(InitialState(t1), GradeGood, t1).DueDate; got != "2024-02-29" {
		t.Fatalf("2024-02-28 due=%q want 2024-02-29", got)
	}
	t2 := time.Date(2023, 2, 28, 12, 0, 0, 0, time.UTC)
	if got := Next(InitialState(t2), GradeGood, t2).DueDate; got != "2023-03-01" {
		t.Fatalf("2023-02-28 due=%q want 2023-03-01", got)
	}
	t3 := time.Date(2024, 2, 29, 12, 0, 0, 0, time.UTC)
	if got := Next(InitialState(t3), GradeGood, t3).DueDate; got != "2024-03-01" {
		t.Fatalf("2024-02-29 due=%q want 2024-03-01", got)
	}
	t4 := time.Date(2024, 2, 27, 12, 0, 0, 0, time.UTC)
	s := State{EF: 2.5, IntervalDays: 1, Repetitions: 1}
	got := Next(s, GradeGood, t4)
	if got.Repetitions != 2 || got.IntervalDays != 6 || got.DueDate != "2024-03-04" {
		t.Fatalf("got=(%d,%d,%q) want (2,6,2024-03-04)", got.Repetitions, got.IntervalDays, got.DueDate)
	}
}

func TestSM2_Grade2vs3Boundary(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 2.5, IntervalDays: 6, Repetitions: 2}

	g2 := Next(s, Grade(2), today)
	if g2.EF != 2.5 || g2.Repetitions != 0 || g2.IntervalDays != 1 || g2.DueDate != "2025-01-02" {
		t.Fatalf("grade2 got=(%v,%d,%d,%q) want (2.5,0,1,2025-01-02)", g2.EF, g2.Repetitions, g2.IntervalDays, g2.DueDate)
	}

	g3 := Next(s, GradeHard, today)
	if g3.Repetitions != 3 {
		t.Fatalf("grade3 rep=%d want 3", g3.Repetitions)
	}
	if g3.IntervalDays != 15 {
		t.Fatalf("grade3 int=%d want 15", g3.IntervalDays)
	}
	if diff := g3.EF - 2.36; math.Abs(diff) >= 1e-9 {
		t.Fatalf("grade3 EF=%v want~2.36 diff=%v", g3.EF, diff)
	}
	if g3.DueDate != "2025-01-16" {
		t.Fatalf("grade3 due=%q want 2025-01-16", g3.DueDate)
	}
}

func TestSM2_ZeroEF_DefensiveIntervalClamped(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 0, IntervalDays: 6, Repetitions: 2}
	got := Next(s, GradeGood, today)
	if got.IntervalDays != 1 {
		t.Fatalf("interval=%d want 1 (clamped from round(6*0)=0)", got.IntervalDays)
	}
	if got.EF != 1.3 {
		t.Fatalf("EF=%v want exactly 1.3 (clamped from 0)", got.EF)
	}
}

func TestSM2_HugeInterval_NoOverflow(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 2.5, IntervalDays: 1 << 30, Repetitions: 5}
	got := Next(s, GradeGood, today)
	want := int(math.Round(float64(1<<30) * 2.5))
	if got.IntervalDays != want {
		t.Fatalf("interval=%d want %d", got.IntervalDays, want)
	}
	if got.DueDate == "" {
		t.Fatalf("DueDate 为空")
	}
}

func TestSM2_Grade5ThenForgot_KeepsEF(t *testing.T) {
	today := time.Date(2025, 4, 1, 0, 0, 0, 0, time.UTC)
	s1 := Next(InitialState(today), GradeEasy, today)
	if diff := s1.EF - 2.6; math.Abs(diff) >= 1e-9 {
		t.Fatalf("s1 EF=%v want~2.6 diff=%v", s1.EF, diff)
	}
	if s1.Repetitions != 1 {
		t.Fatalf("s1 rep=%d want 1", s1.Repetitions)
	}
	s2 := Next(s1, GradeForgot, today)
	if diff := s2.EF - 2.6; math.Abs(diff) >= 1e-9 {
		t.Fatalf("s2 EF=%v want~2.6 (忘记不扣 EF) diff=%v", s2.EF, diff)
	}
	if s2.Repetitions != 0 || s2.IntervalDays != 1 || s2.DueDate != "2025-04-02" {
		t.Fatalf("s2=(%d,%d,%q) want (0,1,2025-04-02)", s2.Repetitions, s2.IntervalDays, s2.DueDate)
	}
}

func TestSM2_IllegalGrade_ReturnsIdentical(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 1.9, IntervalDays: 6, Repetitions: 2, DueDate: "2025-05-01"}
	if got := Next(s, Grade(-1), today); !reflect.DeepEqual(got, s) {
		t.Fatalf("Grade(-1) got=%+v want %+v", got, s)
	}
	if got := Next(s, Grade(6), today); !reflect.DeepEqual(got, s) {
		t.Fatalf("Grade(6) got=%+v want %+v", got, s)
	}
}

func TestSM2_InitialState_ExactFields(t *testing.T) {
	today := time.Date(2025, 6, 15, 10, 0, 0, 0, time.UTC)
	got := InitialState(today)
	if got.EF != 2.5 {
		t.Fatalf("EF=%v want 2.5", got.EF)
	}
	if got.IntervalDays != 0 {
		t.Fatalf("IntervalDays=%d want 0", got.IntervalDays)
	}
	if got.Repetitions != 0 {
		t.Fatalf("Repetitions=%d want 0", got.Repetitions)
	}
	if got.DueDate != "2025-06-16" {
		t.Fatalf("DueDate=%q want 2025-06-16", got.DueDate)
	}
}

func TestSM2_DueDate_UsesPassedTodayNotWallClock(t *testing.T) {
	today := time.Date(2030, 5, 1, 23, 0, 0, 0, time.UTC)
	got := Next(InitialState(today), GradeGood, today).DueDate
	if got != "2030-05-02" {
		t.Fatalf("DueDate=%q want 2030-05-02 (应基于传入 today)", got)
	}
}

func TestSM2_Grade4_EFExactUnchanged(t *testing.T) {
	today := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	s := State{EF: 1.87, IntervalDays: 6, Repetitions: 2}
	got := Next(s, GradeGood, today)
	// delta = 0.1 - 1*(0.08+0.02) = 0.0 精确
	if got.EF != 1.87 {
		t.Fatalf("EF=%v want exactly 1.87", got.EF)
	}
	got5 := Next(s, GradeEasy, today)
	if diff := got5.EF - 1.97; math.Abs(diff) >= 1e-9 {
		t.Fatalf("grade5 EF=%v want~1.97 diff=%v", got5.EF, diff)
	}
}
