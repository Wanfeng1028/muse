package push

// 深测补强：NextPushTime 调度边界。模型生成 + 编排手工落盘（原文照搬，无修改）。

import (
	"testing"
	"time"
)

func TestNextPushTime_恰好相等推次日(t *testing.T) {
	loc := time.UTC
	now := time.Date(2026, 1, 2, 8, 30, 0, 0, loc)
	result, err := NextPushTime(now, "08:30", loc)
	if err != nil {
		t.Fatalf("NextPushTime 失败: %v", err)
	}
	expected := time.Date(2026, 1, 3, 8, 30, 0, 0, loc)
	if !result.Equal(expected) {
		t.Errorf("期望 %v，实际 %v", expected, result)
	}
}

func TestNextPushTime_一秒前算当天(t *testing.T) {
	loc := time.UTC
	now := time.Date(2026, 1, 2, 8, 29, 59, 0, loc)
	result, err := NextPushTime(now, "08:30", loc)
	if err != nil {
		t.Fatalf("NextPushTime 失败: %v", err)
	}
	expected := time.Date(2026, 1, 2, 8, 30, 0, 0, loc)
	if !result.Equal(expected) {
		t.Errorf("期望 %v，实际 %v", expected, result)
	}
}

func TestNextPushTime_非法格式(t *testing.T) {
	loc := time.UTC
	now := time.Date(2026, 1, 2, 8, 0, 0, 0, loc)
	invalidTimes := []string{"24:00", "8:60", "0830", "8:3x"}
	for _, ct := range invalidTimes {
		if _, err := NextPushTime(now, ct, loc); err == nil {
			t.Errorf("clockTime %q 应返回错误", ct)
		}
	}
}

func TestNextPushTime_不存在时刻归一化(t *testing.T) {
	loc, err := time.LoadLocation("America/New_York")
	if err != nil {
		t.Fatalf("LoadLocation 失败: %v", err)
	}
	now := time.Date(2026, 3, 8, 0, 0, 0, 0, loc)
	result, err := NextPushTime(now, "02:30", loc)
	if err != nil {
		t.Fatalf("NextPushTime 失败: %v", err)
	}
	// Go time.Date 对夏令时切换日不存在的 02:30 向后归一化到 01:30 EST（实测），
	// 而非向前到 03:30——这是 Go 标准库行为，测试只做行为锁定。
	// 诚实记录：这意味着 SB_PUSH_TIME 配成 02:30 的用户，在夏令时切换日会提前到 01:30 推送。
	if result.Hour() != 1 {
		t.Errorf("期望 Hour()==1，实际 %d", result.Hour())
	}
}
