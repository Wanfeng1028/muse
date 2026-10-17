package review

import (
	"math"
	"testing"
	"time"
)

func mustDate(t *testing.T, s string) time.Time {
	t.Helper()
	d, err := time.Parse(dateLayout, s)
	if err != nil {
		t.Fatalf("解析日期 %q 失败: %v", s, err)
	}
	return d
}

func approxEqual(a, b float64) bool {
	return math.Abs(a-b) < 1e-9
}

// TestNextCrossDayAndLeapDay 验证跨天与闰日调度：到期日必须是 today+IntervalDays。
func TestNextCrossDayAndLeapDay(t *testing.T) {
	cases := []struct {
		name       string
		today      string
		state      State
		grade      Grade
		wantDue    string
		wantInterv int
		wantReps   int
	}{
		{
			name:       "跨月边界_1月31日加一天",
			today:      "2024-01-31",
			state:      State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-02-01"},
			grade:      GradeGood,
			wantDue:    "2024-02-01",
			wantInterv: 1,
			wantReps:   1,
		},
		{
			name:       "跨年边界_12月31日加一天",
			today:      "2023-12-31",
			state:      State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-01-01"},
			grade:      GradeGood,
			wantDue:    "2024-01-01",
			wantInterv: 1,
			wantReps:   1,
		},
		{
			name:       "闰日_2月28日加一天到2月29日",
			today:      "2024-02-28",
			state:      State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-02-29"},
			grade:      GradeGood,
			wantDue:    "2024-02-29",
			wantInterv: 1,
			wantReps:   1,
		},
		{
			name:       "闰日_2月29日加一天到3月1日",
			today:      "2024-02-29",
			state:      State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-03-01"},
			grade:      GradeGood,
			wantDue:    "2024-03-01",
			wantInterv: 1,
			wantReps:   1,
		},
		{
			name:       "非闰年_2月28日加一天到3月1日",
			today:      "2023-02-28",
			state:      State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2023-03-01"},
			grade:      GradeGood,
			wantDue:    "2023-03-01",
			wantInterv: 1,
			wantReps:   1,
		},
		{
			name:       "失败重置_闰日当天失败下次为次日",
			today:      "2024-02-29",
			state:      State{EF: 2.5, IntervalDays: 10, Repetitions: 5, DueDate: "2024-03-10"},
			grade:      GradeForgot,
			wantDue:    "2024-03-01",
			wantInterv: 1,
			wantReps:   0,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			today := mustDate(t, tc.today)
			got := Next(tc.state, tc.grade, today)
			if got.DueDate != tc.wantDue {
				t.Errorf("DueDate = %q, 期望 %q", got.DueDate, tc.wantDue)
			}
			if got.IntervalDays != tc.wantInterv {
				t.Errorf("IntervalDays = %d, 期望 %d", got.IntervalDays, tc.wantInterv)
			}
			if got.Repetitions != tc.wantReps {
				t.Errorf("Repetitions = %d, 期望 %d", got.Repetitions, tc.wantReps)
			}
		})
	}
}

// TestNextTimezoneIndependence 验证调度只按日期（UTC 归一化）计算，不随时区偏移改变。
func TestNextTimezoneIndependence(t *testing.T) {
	utcLoc := time.UTC
	plus8 := time.FixedZone("UTC+8", 8*3600)
	minus5 := time.FixedZone("UTC-5", -5*3600)

	// 同一时刻，用不同时区表示，Next 内部会 UTC() 归一化。
	baseUTC := time.Date(2024, 3, 15, 23, 30, 0, 0, utcLoc)
	sameInstantPlus8 := baseUTC.In(plus8)
	sameInstantMinus5 := baseUTC.In(minus5)

	state := State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-03-16"}

	gotUTC := Next(state, GradeGood, baseUTC)
	gotPlus8 := Next(state, GradeGood, sameInstantPlus8)
	gotMinus5 := Next(state, GradeGood, sameInstantMinus5)

	if gotUTC.DueDate != gotPlus8.DueDate {
		t.Errorf("UTC 与 UTC+8 表示同一时刻结果不同: %q vs %q", gotUTC.DueDate, gotPlus8.DueDate)
	}
	if gotUTC.DueDate != gotMinus5.DueDate {
		t.Errorf("UTC 与 UTC-5 表示同一时刻结果不同: %q vs %q", gotUTC.DueDate, gotMinus5.DueDate)
	}

	// 归一到 UTC 后 today 是 2024-03-15，加 1 天应为 2024-03-16。
	if gotUTC.DueDate != "2024-03-16" {
		t.Errorf("DueDate = %q, 期望 2024-03-16", gotUTC.DueDate)
	}
	if gotUTC.IntervalDays != 1 {
		t.Errorf("IntervalDays = %d, 期望 1", gotUTC.IntervalDays)
	}

	// 构造一个本地日期已是次日的时刻，验证 UTC 归一化行为可预期。
	nextDayLocal := time.Date(2024, 3, 16, 4, 0, 0, 0, plus8) // UTC 为 2024-03-15 20:00
	gotNext := Next(state, GradeGood, nextDayLocal)
	if gotNext.DueDate != "2024-03-16" {
		t.Errorf("UTC 归一化后 DueDate = %q, 期望 2024-03-16", gotNext.DueDate)
	}
}

// TestNextEFExtremes 验证 EF 的极端值：下限夹紧、高分段累加、超界评分不改变状态。
func TestNextEFExtremes(t *testing.T) {
	today := mustDate(t, "2024-06-01")

	t.Run("EF下限夹紧到1.3", func(t *testing.T) {
		// 连续用困难评分，EF 会不断下降，最终被夹到 1.3。
		s := InitialState(today)
		for i := 0; i < 50; i++ {
			s = Next(s, GradeHard, today)
		}
		if !approxEqual(s.EF, minEF) {
			t.Errorf("EF = %v, 期望夹紧到 %v", s.EF, minEF)
		}
		if s.EF < minEF {
			t.Errorf("EF = %v 低于下限 %v", s.EF, minEF)
		}
	})

	t.Run("良好评分EF上升公式", func(t *testing.T) {
		s := State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-06-02"}
		got := Next(s, GradeGood, today)
		// q=4: delta = 0.1 - (5-4)*(0.08+(5-4)*0.02) = 0.1 - 0.10 = 0
		want := 2.5
		if !approxEqual(got.EF, want) {
			t.Errorf("EF = %v, 期望 %v", got.EF, want)
		}
		if got.Repetitions != 1 {
			t.Errorf("Repetitions = %d, 期望 1", got.Repetitions)
		}
	})

	t.Run("简单评分EF上升公式", func(t *testing.T) {
		s := State{EF: 2.5, IntervalDays: 0, Repetitions: 0, DueDate: "2024-06-02"}
		got := Next(s, GradeEasy, today)
		// q=5: delta = 0.1 - 0 = 0.1
		want := 2.6
		if !approxEqual(got.EF, want) {
			t.Errorf("EF = %v, 期望 %v", got.EF, want)
		}
		if got.IntervalDays != 1 {
			t.Errorf("IntervalDays = %d, 期望 1", got.IntervalDays)
		}
	})

	t.Run("初始EF下限状态失败评分保持不变", func(t *testing.T) {
		s := State{EF: 1.3, IntervalDays: 5, Repetitions: 3, DueDate: "2024-06-06"}
		got := Next(s, GradeForgot, today)
		if !approxEqual(got.EF, 1.3) {
			t.Errorf("EF = %v, 期望 1.3", got.EF)
		}
		if got.IntervalDays != 1 {
			t.Errorf("IntervalDays = %d, 期望 1", got.IntervalDays)
		}
		if got.Repetitions != 0 {
			t.Errorf("Repetitions = %d, 期望 0", got.Repetitions)
		}
	})

	t.Run("非法评分返回原状态不变", func(t *testing.T) {
		s := State{EF: 2.5, IntervalDays: 6, Repetitions: 2, DueDate: "2024-06-07"}
		gotNeg := Next(s, Grade(-1), today)
		if gotNeg != s {
			t.Errorf("评分 -1 应返回原状态, 得到 %+v", gotNeg)
		}
		gotHigh := Next(s, Grade(6), today)
		if gotHigh != s {
			t.Errorf("评分 6 应返回原状态, 得到 %+v", gotHigh)
		}
	})
}

// TestNextIntervalGrowthAndDefensiveClamp 验证间隔增长公式与防御性夹紧。
func TestNextIntervalGrowthAndDefensiveClamp(t *testing.T) {
	today := mustDate(t, "2024-01-01")

	t.Run("第一次与第二次固定间隔", func(t *testing.T) {
		s := InitialState(today)
		s1 := Next(s, GradeGood, today)
		if s1.IntervalDays != 1 {
			t.Errorf("第一次成功 IntervalDays = %d, 期望 1", s1.IntervalDays)
		}
		if s1.Repetitions != 1 {
			t.Errorf("第一次成功 Repetitions = %d, 期望 1", s1.Repetitions)
		}
		s2 := Next(s1, GradeGood, today)
		if s2.IntervalDays != 6 {
			t.Errorf("第二次成功 IntervalDays = %d, 期望 6", s2.IntervalDays)
		}
		if s2.Repetitions != 2 {
			t.Errorf("第二次成功 Repetitions = %d, 期望 2", s2.Repetitions)
		}
	})

	t.Run("第三次按上一间隔乘EF四舍五入", func(t *testing.T) {
		s := State{EF: 2.5, IntervalDays: 6, Repetitions: 2, DueDate: "2024-01-07"}
		got := Next(s, GradeGood, today)
		// 6 * 2.5 = 15
		if got.IntervalDays != 15 {
			t.Errorf("IntervalDays = %d, 期望 15", got.IntervalDays)
		}
		if got.Repetitions != 3 {
			t.Errorf("Repetitions = %d, 期望 3", got.Repetitions)
		}
		if got.DueDate != "2024-01-16" {
			t.Errorf("DueDate = %q, 期望 2024-01-16", got.DueDate)
		}
	})

	t.Run("间隔乘EF后非正数被夹到1", func(t *testing.T) {
		// 上一间隔为 0，EF 为正，乘积为 0，防御性夹到 1。
		s := State{EF: 2.5, IntervalDays: 0, Repetitions: 5, DueDate: "2024-01-01"}
		got := Next(s, GradeGood, today)
		if got.IntervalDays != 1 {
			t.Errorf("IntervalDays = %d, 期望夹到 1", got.IntervalDays)
		}
		if got.DueDate != "2024-01-02" {
			t.Errorf("DueDate = %q, 期望 2024-01-02", got.DueDate)
		}
	})
}

// TestIsValidGradeDeep 验证评分合法性边界。
func TestIsValidGradeDeep(t *testing.T) {
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
		{100, false},
	}
	for _, tc := range cases {
		got := IsValidGrade(tc.g)
		if got != tc.want {
			t.Errorf("IsValidGrade(%d) = %v, 期望 %v", tc.g, got, tc.want)
		}
	}
}

// TestInitialStateDeep 验证初始状态字段。
func TestInitialStateDeep(t *testing.T) {
	today := mustDate(t, "2024-05-20")
	s := InitialState(today)
	if !approxEqual(s.EF, 2.5) {
		t.Errorf("EF = %v, 期望 2.5", s.EF)
	}
	if s.IntervalDays != 0 {
		t.Errorf("IntervalDays = %d, 期望 0", s.IntervalDays)
	}
	if s.Repetitions != 0 {
		t.Errorf("Repetitions = %d, 期望 0", s.Repetitions)
	}
	if s.DueDate != "2024-05-21" {
		t.Errorf("DueDate = %q, 期望 2024-05-21", s.DueDate)
	}
}

// TestGradeConstants 验证四档评分的具体数值。
func TestGradeConstants(t *testing.T) {
	if int(GradeForgot) != 0 {
		t.Errorf("GradeForgot = %d, 期望 0", int(GradeForgot))
	}
	if int(GradeHard) != 3 {
		t.Errorf("GradeHard = %d, 期望 3", int(GradeHard))
	}
	if int(GradeGood) != 4 {
		t.Errorf("GradeGood = %d, 期望 4", int(GradeGood))
	}
	if int(GradeEasy) != 5 {
		t.Errorf("GradeEasy = %d, 期望 5", int(GradeEasy))
	}
}

// TestTodayUTC 验证 TodayUTC 返回合法日期格式。
func TestTodayUTC(t *testing.T) {
	got := TodayUTC()
	if len(got) != 10 {
		t.Fatalf("TodayUTC 长度 = %d, 期望 10, 值 = %q", len(got), got)
	}
	parsed, err := time.Parse(dateLayout, got)
	if err != nil {
		t.Fatalf("TodayUTC 返回 %q 不是合法日期: %v", got, err)
	}
	// 与当前 UTC 日期一致。
	want := time.Now().UTC().Format(dateLayout)
	if parsed.Format(dateLayout) != want {
		t.Errorf("TodayUTC = %q, 期望 %q", parsed.Format(dateLayout), want)
	}
}

// TestAddDays 验证日期加天数边界，含闰年与月长差异。
func TestAddDays(t *testing.T) {
	cases := []struct {
		name string
		base string
		days int
		want string
	}{
		{"加0天", "2024-03-10", 0, "2024-03-10"},
		{"跨月", "2024-01-31", 1, "2024-02-01"},
		{"跨闰日", "2024-02-28", 1, "2024-02-29"},
		{"闰日加一天", "2024-02-29", 1, "2024-03-01"},
		{"非闰年2月末", "2023-02-28", 1, "2023-03-01"},
		{"跨年", "2023-12-31", 1, "2024-01-01"},
		{"加30天", "2024-01-01", 30, "2024-01-31"},
		{"负数减一天", "2024-03-01", -1, "2024-02-29"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			base := mustDate(t, tc.base)
			got := addDays(base, tc.days)
			if got != tc.want {
				t.Errorf("addDays(%q, %d) = %q, 期望 %q", tc.base, tc.days, got, tc.want)
			}
			// 断言加 0 天等于自身格式。
			if tc.days == 0 && got != base.Format(dateLayout) {
				t.Errorf("加0天 = %q, 期望 %q", got, base.Format(dateLayout))
			}
		})
	}
}

// TestNextFullProgression 验证连续成功复习下间隔序列符合 SM-2 预期。
func TestNextFullProgression(t *testing.T) {
	today := mustDate(t, "2024-01-01")
	s := InitialState(today)

	type step struct {
		grade      Grade
		wantInterv int
		wantReps   int
		wantEF     float64
	}
	steps := []step{
		{GradeGood, 1, 1, 2.5},
		{GradeGood, 6, 2, 2.5},
		{GradeGood, 15, 3, 2.5},
		{GradeEasy, 38, 4, 2.6},
	}

	for i, st := range steps {
		s = Next(s, st.grade, today)
		if s.IntervalDays != st.wantInterv {
			t.Errorf("第 %d 步 IntervalDays = %d, 期望 %d", i+1, s.IntervalDays, st.wantInterv)
		}
		if s.Repetitions != st.wantReps {
			t.Errorf("第 %d 步 Repetitions = %d, 期望 %d", i+1, s.Repetitions, st.wantReps)
		}
		if !approxEqual(s.EF, st.wantEF) {
			t.Errorf("第 %d 步 EF = %v, 期望 %v", i+1, s.EF, st.wantEF)
		}
	}
}
