// Package review 实现 SuperMemo SM-2 间隔重复算法。
// 该包提供纯函数、确定性的复习调度计算，便于单元测试。
package review

import (
	"fmt"
	"math"
	"time"
)

// Grade 表示用户对一次复习的评分等级。
// UI 四档映射：忘记=0 / 困难=3 / 良好=4 / 简单=5。
type Grade int

const (
	// GradeForgot 忘记，完全没想起来。
	GradeForgot Grade = 0
	// GradeHard 困难，勉强想起来。
	GradeHard Grade = 3
	// GradeGood 良好，正常想起来。
	GradeGood Grade = 4
	// GradeEasy 简单，毫不费力。
	GradeEasy Grade = 5
)

// State 表示一个复习项在 SM-2 算法中的状态。
type State struct {
	// EF 为难度因子（Easiness Factor），初始 2.5，下限 1.3。
	EF float64 `json:"ef"`
	// IntervalDays 为当前复习间隔（天）。
	IntervalDays int `json:"intervalDays"`
	// Repetitions 为连续成功复习次数。
	Repetitions int `json:"repetitions"`
	// DueDate 为下次到期日期，格式 YYYY-MM-DD。
	DueDate string `json:"dueDate"`
}

// dateLayout 为日期字符串格式。
const dateLayout = "2006-01-02"

// minEF 为难度因子的下限。
const minEF = 1.3

// IsValidGrade 判断评分是否合法（0..5 之间）。
func IsValidGrade(g int) bool {
	return g >= 0 && g <= 5
}

// TodayUTC 返回当前 UTC 日期，格式 YYYY-MM-DD。
func TodayUTC() string {
	return time.Now().UTC().Format(dateLayout)
}

// formatDate 将时间格式化为 YYYY-MM-DD。
func formatDate(t time.Time) string {
	return t.Format(dateLayout)
}

// addDays 返回在给定日期基础上加 n 天后的日期字符串（按 UTC 处理）。
func addDays(today time.Time, days int) string {
	base := today.UTC()
	return base.AddDate(0, 0, days).Format(dateLayout)
}

// InitialState 返回一个初始状态：
// EF=2.5, IntervalDays=0, Repetitions=0, DueDate=today+1 天。
func InitialState(today time.Time) State {
	return State{
		EF:           2.5,
		IntervalDays: 0,
		Repetitions:  0,
		DueDate:      addDays(today, 1),
	}
}

// Next 根据当前状态与评分计算下一次复习状态。
// 标准 SM-2 行为：
//   - grade < 3：Repetitions=0，IntervalDays=1，EF 不变（重新开始）。
//   - grade >= 3：Repetitions+1；
//     IntervalDays = 1(n=1) / 6(n=2) / round(上一间隔*EF)(n>2)；
//     EF = EF + (0.1-(5-grade)*(0.08+(5-grade)*0.02))，下限 1.3。
//   - DueDate = today + IntervalDays 天（YYYY-MM-DD）。
//
// grade 非法（<0 或 >5）时返回原 State 不变。
func Next(s State, grade Grade, today time.Time) State {
	g := int(grade)
	if !IsValidGrade(g) {
		return s
	}

	// 评分低于 3，视为失败，重新开始。
	if g < 3 {
		return State{
			EF:           s.EF,
			IntervalDays: 1,
			Repetitions:  0,
			DueDate:      addDays(today, 1),
		}
	}

	// 评分 >= 3，视为成功。
	repetitions := s.Repetitions + 1

	var intervalDays int
	switch repetitions {
	case 1:
		intervalDays = 1
	case 2:
		intervalDays = 6
	default:
		// n > 2：round(上一间隔 * EF)
		intervalDays = int(math.Round(float64(s.IntervalDays) * s.EF))
		// 防御性处理：间隔至少为 1 天，避免出现非正数。
		if intervalDays < 1 {
			intervalDays = 1
		}
	}

	// 更新难度因子 EF。
	q := float64(g)
	ef := s.EF + (0.1 - (5-q)*(0.08+(5-q)*0.02))
	if ef < minEF {
		ef = minEF
	}

	return State{
		EF:           ef,
		IntervalDays: intervalDays,
		Repetitions:  repetitions,
		DueDate:      addDays(today, intervalDays),
	}
}

// 确保 fmt 被使用（用于潜在的调试/错误信息格式化）。
var _ = fmt.Sprintf
