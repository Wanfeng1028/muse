package review

import (
	"reflect"
	"testing"
	"time"
)

// TestNextExtremeForgotSequence：连续 10 次 GradeForgot，验证忘记不降 EF、
// 间隔恒为 1、重复次数恒为 0、到期日恒为 today+1。
func TestNextExtremeForgotSequence(t *testing.T) {
	today := time.Date(2026, 10, 19, 10, 0, 0, 0, time.UTC)

	s := InitialState(today)
	for i := 0; i < 10; i++ {
		s = Next(s, GradeForgot, today)

		if s.IntervalDays != 1 {
			t.Fatalf("iter %d: IntervalDays = %d, want 1", i, s.IntervalDays)
		}
		if s.Repetitions != 0 {
			t.Fatalf("iter %d: Repetitions = %d, want 0", i, s.Repetitions)
		}
		if s.EF != 2.5 {
			t.Fatalf("iter %d: EF = %v, want 2.5 (忘记不应改变 EF)", i, s.EF)
		}
		if s.DueDate != "2026-10-20" {
			t.Fatalf("iter %d: DueDate = %q, want %q", i, s.DueDate, "2026-10-20")
		}
	}
}

// TestNextEFMinClamp：EF 已在下限 1.3 时，连续 GradeHard 不许把 EF 压到 1.3 以下；
// 之后一次 GradeEasy 应当把 EF 抬升，同时 Repetitions 递增。
func TestNextEFMinClamp(t *testing.T) {
	today := time.Date(2026, 10, 19, 10, 0, 0, 0, time.UTC)

	s := State{EF: 1.3, IntervalDays: 6, Repetitions: 5}

	for i := 0; i < 5; i++ {
		s = Next(s, GradeHard, today)
		if s.EF != 1.3 {
			t.Fatalf("iter %d: EF = %v, want clamp to 1.3", i, s.EF)
		}
		if s.EF < minEF {
			t.Fatalf("iter %d: EF = %v below minEF=%v", i, s.EF, minEF)
		}
	}

	// 连续 5 次 GradeHard 后 Repetitions 应为 5+5=10。
	if s.Repetitions != 10 {
		t.Fatalf("after 5 GradeHard: Repetitions = %d, want 10", s.Repetitions)
	}

	prevEF := s.EF
	s = Next(s, GradeEasy, today)

	if s.EF <= 1.3 {
		t.Fatalf("after GradeEasy: EF = %v, want > 1.3", s.EF)
	}
	if s.EF <= prevEF {
		t.Fatalf("after GradeEasy: EF = %v, want > previous %v", s.EF, prevEF)
	}
	if s.Repetitions != 11 {
		t.Fatalf("after GradeEasy: Repetitions = %d, want 11", s.Repetitions)
	}
}

// TestNextEasyGrowthMonotonic：从 InitialState 起连续 5 次 GradeEasy，
// 断言间隔先 1 后 6 且之后单调非减，EF 单调非减，DueDate 与当日间隔一致。
func TestNextEasyGrowthMonotonic(t *testing.T) {
	today := time.Date(2026, 10, 19, 10, 0, 0, 0, time.UTC)

	s := InitialState(today)

	var prevInterval int = -1
	var prevEF float64 = -1
	var intervals []int

	for i := 0; i < 5; i++ {
		s = Next(s, GradeEasy, today)

		// DueDate 必须等于 today + IntervalDays（按 addDays 的 UTC 语义）。
		expectedDue := today.UTC().AddDate(0, 0, s.IntervalDays).Format("2006-01-02")
		if s.DueDate != expectedDue {
			t.Fatalf("iter %d: DueDate = %q, want %q (interval=%d)",
				i, s.DueDate, expectedDue, s.IntervalDays)
		}

		intervals = append(intervals, s.IntervalDays)

		if i > 0 && s.IntervalDays < prevInterval {
			t.Fatalf("iter %d: IntervalDays = %d decreased from %d (must be monotonic non-decreasing)",
				i, s.IntervalDays, prevInterval)
		}
		if i > 0 && s.EF < prevEF {
			t.Fatalf("iter %d: EF = %v decreased from %v (must be monotonic non-decreasing)",
				i, s.EF, prevEF)
		}

		prevInterval = s.IntervalDays
		prevEF = s.EF
	}

	// 前两次间隔按 SM-2 规范应为 1 与 6。
	if intervals[0] != 1 {
		t.Fatalf("intervals[0] = %d, want 1", intervals[0])
	}
	if intervals[1] != 6 {
		t.Fatalf("intervals[1] = %d, want 6", intervals[1])
	}
}

// TestNextForgotThenRecover：忘记之后一次 GradeGood 应重置到 n=1, interval=1。
func TestNextForgotThenRecover(t *testing.T) {
	today := time.Date(2026, 10, 19, 10, 0, 0, 0, time.UTC)

	s := State{EF: 2.5, IntervalDays: 30, Repetitions: 8}
	s = Next(s, GradeForgot, today)

	if s.IntervalDays != 1 || s.Repetitions != 0 {
		t.Fatalf("after Forgot: interval=%d reps=%d, want 1/0", s.IntervalDays, s.Repetitions)
	}

	s = Next(s, GradeGood, today)

	if s.Repetitions != 1 {
		t.Fatalf("after Good: Repetitions = %d, want 1", s.Repetitions)
	}
	if s.IntervalDays != 1 {
		t.Fatalf("after Good: IntervalDays = %d, want 1", s.IntervalDays)
	}
}

// TestNextInvalidGradeUnchanged：非法 grade 必须原样返回，逐字段相等。
func TestNextInvalidGradeUnchanged(t *testing.T) {
	today := time.Date(2026, 10, 19, 10, 0, 0, 0, time.UTC)

	s := State{
		EF:           1.75,
		IntervalDays: 42,
		Repetitions:  7,
		DueDate:      "2026-12-01",
	}

	invalid := []Grade{Grade(-1), Grade(6), Grade(100)}
	for _, g := range invalid {
		got := Next(s, g, today)
		if !reflect.DeepEqual(got, s) {
			t.Fatalf("grade=%d: got %+v, want unchanged %+v", int(g), got, s)
		}
	}
}

// TestNextLeapDayBoundary：闰年边界 + 普通推进跨越闰日。
func TestNextLeapDayBoundary(t *testing.T) {
	// 2028-02-28 → 次日应为闰日 2028-02-29。
	initA := InitialState(time.Date(2028, 2, 28, 12, 0, 0, 0, time.UTC))
	if initA.DueDate != "2028-02-29" {
		t.Fatalf("InitialState(2028-02-28): DueDate = %q, want %q", initA.DueDate, "2028-02-29")
	}

	// 2028-02-29 → 次日应为 2028-03-01。
	initB := InitialState(time.Date(2028, 2, 29, 12, 0, 0, 0, time.UTC))
	if initB.DueDate != "2028-03-01" {
		t.Fatalf("InitialState(2028-02-29): DueDate = %q, want %q", initB.DueDate, "2028-03-01")
	}

	// n=3 从 2028-02-27 出发：interval = round(6*2.5) = 15 → 2028-03-13。
	got := Next(
		State{EF: 2.5, IntervalDays: 6, Repetitions: 2},
		GradeGood,
		time.Date(2028, 2, 27, 12, 0, 0, 0, time.UTC),
	)
	if got.Repetitions != 3 {
		t.Fatalf("Repetitions = %d, want 3", got.Repetitions)
	}
	if got.IntervalDays != 15 {
		t.Fatalf("IntervalDays = %d, want 15 (round(6*2.5))", got.IntervalDays)
	}
	if got.DueDate != "2028-03-13" {
		t.Fatalf("DueDate = %q, want %q", got.DueDate, "2028-03-13")
	}
}

// TestNextTimezoneBoundary：无论传入的 today 时区如何，DueDate 都按 UTC 语义计算。
func TestNextTimezoneBoundary(t *testing.T) {
	cst, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("LoadLocation(Asia/Shanghai): %v", err)
	}

	// 2028-02-29 20:00 CST == 2028-02-29 12:00 UTC → +1 天 = 2028-03-01。
	localTime := time.Date(2028, 2, 29, 20, 0, 0, 0, cst)
	if got := localTime.UTC().Format("2006-01-02"); got != "2028-02-29" {
		t.Fatalf("precondition: localTime UTC date = %q, want %q", got, "2028-02-29")
	}
	got := Next(InitialState(localTime), GradeGood, localTime)
	if got.DueDate != "2028-03-01" {
		t.Fatalf("DueDate = %q, want %q", got.DueDate, "2028-03-01")
	}

	// 2028-03-01 06:00 CST == 2028-02-29 22:00 UTC → +1 天 = 2028-03-01。
	localTime2 := time.Date(2028, 3, 1, 6, 0, 0, 0, cst)
	if got := localTime2.UTC().Format("2006-01-02"); got != "2028-02-29" {
		t.Fatalf("precondition: localTime2 UTC date = %q, want %q", got, "2028-02-29")
	}
	init := InitialState(localTime2)
	if init.DueDate != "2028-03-01" {
		t.Fatalf("InitialState(localTime2).DueDate = %q, want %q", init.DueDate, "2028-03-01")
	}
}
