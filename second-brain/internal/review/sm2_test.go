package review

import (
	"math"
	"testing"
	"time"
)

// 浮点数近似比较的容差。
const efEpsilon = 1e-9

// 辅助函数：判断两个浮点数是否近似相等。
func almostEqual(a, b float64) bool {
	return math.Abs(a-b) < efEpsilon
}

// 测试 1：InitialState 的初始值。
func TestInitialState(t *testing.T) {
	today := time.Date(2026, 10, 13, 0, 0, 0, 0, time.UTC)
	s := InitialState(today)

	if !almostEqual(s.EF, 2.5) {
		t.Errorf("初始 EF 应为 2.5，实际为 %v", s.EF)
	}
	if s.IntervalDays != 0 {
		t.Errorf("初始 IntervalDays 应为 0，实际为 %d", s.IntervalDays)
	}
	if s.Repetitions != 0 {
		t.Errorf("初始 Repetitions 应为 0，实际为 %d", s.Repetitions)
	}
	if s.DueDate != "2026-10-14" {
		t.Errorf("初始 DueDate 应为 2026-10-14，实际为 %s", s.DueDate)
	}
}

// 测试 2：grade=5,5,5 的确定性序列。
func TestNextSequenceGradeEasy(t *testing.T) {
	today := time.Date(2026, 10, 13, 0, 0, 0, 0, time.UTC)
	s := InitialState(today)

	// 第一次评分 5。
	s = Next(s, GradeEasy, today)
	if s.IntervalDays != 1 {
		t.Errorf("第 1 次评分后 IntervalDays 应为 1，实际为 %d", s.IntervalDays)
	}
	if s.Repetitions != 1 {
		t.Errorf("第 1 次评分后 Repetitions 应为 1，实际为 %d", s.Repetitions)
	}
	if !almostEqual(s.EF, 2.6) {
		t.Errorf("第 1 次评分后 EF 应为 2.6，实际为 %v", s.EF)
	}

	// 第二次评分 5。
	s = Next(s, GradeEasy, today)
	if s.IntervalDays != 6 {
		t.Errorf("第 2 次评分后 IntervalDays 应为 6，实际为 %d", s.IntervalDays)
	}
	if s.Repetitions != 2 {
		t.Errorf("第 2 次评分后 Repetitions 应为 2，实际为 %d", s.Repetitions)
	}
	if !almostEqual(s.EF, 2.7) {
		t.Errorf("第 2 次评分后 EF 应为 2.7，实际为 %v", s.EF)
	}

	// 第三次评分 5：round(6 * 2.7) = 16。
	s = Next(s, GradeEasy, today)
	if s.IntervalDays != 16 {
		t.Errorf("第 3 次评分后 IntervalDays 应为 16，实际为 %d", s.IntervalDays)
	}
	if s.Repetitions != 3 {
		t.Errorf("第 3 次评分后 Repetitions 应为 3，实际为 %d", s.Repetitions)
	}
	if !almostEqual(s.EF, 2.8) {
		t.Errorf("第 3 次评分后 EF 应为 2.8，实际为 %v", s.EF)
	}
}

// 测试 3：grade=2（<3）时重新开始，EF 不变。
func TestNextGradeBelowThree(t *testing.T) {
	today := time.Date(2026, 10, 13, 0, 0, 0, 0, time.UTC)
	s := State{
		EF:           2.5,
		IntervalDays: 6,
		Repetitions:  3,
		DueDate:      "2026-10-19",
	}

	s = Next(s, Grade(2), today)
	if s.Repetitions != 0 {
		t.Errorf("评分 <3 时 Repetitions 应归 0，实际为 %d", s.Repetitions)
	}
	if s.IntervalDays != 1 {
		t.Errorf("评分 <3 时 IntervalDays 应回 1，实际为 %d", s.IntervalDays)
	}
	if !almostEqual(s.EF, 2.5) {
		t.Errorf("评分 <3 时 EF 应保持不变为 2.5，实际为 %v", s.EF)
	}
	if s.DueDate != "2026-10-14" {
		t.Errorf("评分 <3 时 DueDate 应为 2026-10-14，实际为 %s", s.DueDate)
	}
}

// 测试 4：EF 下限保护，从 EF=1.3 连续 grade=3 不跌破 1.3。
func TestEFLowerBound(t *testing.T) {
	today := time.Date(2026, 10, 13, 0, 0, 0, 0, time.UTC)
	s := State{
		EF:           1.3,
		IntervalDays: 0,
		Repetitions:  0,
		DueDate:      "2026-10-14",
	}

	for i := 0; i < 5; i++ {
		s = Next(s, GradeHard, today)
		if s.EF < 1.3 {
			t.Fatalf("第 %d 次评分后 EF 跌破下限，实际为 %v", i+1, s.EF)
		}
		if !almostEqual(s.EF, 1.3) {
			t.Errorf("第 %d 次评分后 EF 应保持 1.3，实际为 %v", i+1, s.EF)
		}
	}
}

// 测试 5：非法 grade（-1、6）返回原 State。
func TestInvalidGrade(t *testing.T) {
	today := time.Date(2026, 10, 13, 0, 0, 0, 0, time.UTC)
	original := State{
		EF:           2.5,
		IntervalDays: 6,
		Repetitions:  2,
		DueDate:      "2026-10-19",
	}

	// 非法评分 -1。
	s1 := Next(original, Grade(-1), today)
	if s1 != original {
		t.Errorf("非法 grade=-1 应返回原 State，期望 %+v，实际 %+v", original, s1)
	}

	// 非法评分 6。
	s2 := Next(original, Grade(6), today)
	if s2 != original {
		t.Errorf("非法 grade=6 应返回原 State，期望 %+v，实际 %+v", original, s2)
	}
}

// 测试 6：DueDate 计算，today=2026-10-13、间隔 6 天 → 2026-10-19。
func TestDueDateCalculation(t *testing.T) {
	today := time.Date(2026, 10, 13, 0, 0, 0, 0, time.UTC)

	// 通过序列构造间隔为 6 的状态：初始 -> grade=5（间隔 1）-> grade=5（间隔 6）。
	s := InitialState(today)
	s = Next(s, GradeEasy, today) // 间隔 1
	s = Next(s, GradeEasy, today) // 间隔 6

	if s.IntervalDays != 6 {
		t.Fatalf("构造状态时 IntervalDays 应为 6，实际为 %d", s.IntervalDays)
	}
	if s.DueDate != "2026-10-19" {
		t.Errorf("DueDate 应为 2026-10-19，实际为 %s", s.DueDate)
	}

	// 直接验证 6 天间隔的日期计算。
	expected := today.AddDate(0, 0, 6).Format("2006-01-02")
	if expected != "2026-10-19" {
		t.Errorf("基准日期计算错误：期望 2026-10-19，实际 %s", expected)
	}
}

// 测试 IsValidGrade 的边界行为。
func TestIsValidGrade(t *testing.T) {
	cases := []struct {
		g    int
		want bool
	}{
		{-1, false},
		{0, true},
		{1, true},
		{2, true},
		{3, true},
		{4, true},
		{5, true},
		{6, false},
	}
	for _, c := range cases {
		if got := IsValidGrade(c.g); got != c.want {
			t.Errorf("IsValidGrade(%d) = %v，期望 %v", c.g, got, c.want)
		}
	}
}
