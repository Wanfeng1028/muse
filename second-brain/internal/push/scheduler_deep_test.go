package push

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
)

// ---------- 复习调度边界：NextPushTime ----------

func TestNextPushTimeBoundaries(t *testing.T) {
	shanghai, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败: %v", err)
	}
	utc := time.UTC

	cases := []struct {
		name      string
		now       time.Time
		clock     string
		loc       *time.Location
		wantErr   bool
		wantYear  int
		wantMonth time.Month
		wantDay   int
		wantHour  int
		wantMin   int
	}{
		{
			name:      "当天时刻未到返回当天",
			now:       time.Date(2024, 3, 10, 6, 0, 0, 0, shanghai),
			clock:     "08:30",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   10,
			wantHour:  8,
			wantMin:   30,
		},
		{
			name:      "当天时刻已过返回次日",
			now:       time.Date(2024, 3, 10, 9, 0, 0, 0, shanghai),
			clock:     "08:30",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   11,
			wantHour:  8,
			wantMin:   30,
		},
		{
			name:      "恰好等于当前时刻则算已过进次日",
			now:       time.Date(2024, 3, 10, 8, 30, 0, 0, shanghai),
			clock:     "08:30",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   11,
			wantHour:  8,
			wantMin:   30,
		},
		{
			name:      "跨天边界深夜23:59推进到次日00:00",
			now:       time.Date(2024, 3, 10, 23, 59, 0, 0, shanghai),
			clock:     "00:00",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   11,
			wantHour:  0,
			wantMin:   0,
		},
		{
			name:      "闰日当天时刻未到返回闰日当天",
			now:       time.Date(2024, 2, 29, 1, 0, 0, 0, shanghai),
			clock:     "07:15",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.February,
			wantDay:   29,
			wantHour:  7,
			wantMin:   15,
		},
		{
			name:      "闰日时刻已过推进到3月1日",
			now:       time.Date(2024, 2, 29, 20, 0, 0, 0, shanghai),
			clock:     "07:15",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   1,
			wantHour:  7,
			wantMin:   15,
		},
		{
			name:      "跨时区utc输入在shanghai计算",
			now:       time.Date(2024, 3, 10, 23, 30, 0, 0, utc),
			clock:     "08:00",
			loc:       shanghai,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   11,
			wantHour:  8,
			wantMin:   0,
		},
		{
			name:      "loc为nil退回本地时区",
			now:       time.Date(2024, 3, 10, 6, 0, 0, 0, time.Local),
			clock:     "08:30",
			loc:       nil,
			wantYear:  2024,
			wantMonth: time.March,
			wantDay:   10,
			wantHour:  8,
			wantMin:   30,
		},
		{
			name:    "非法格式缺少冒号",
			now:     time.Date(2024, 3, 10, 6, 0, 0, 0, shanghai),
			clock:   "0830",
			loc:     shanghai,
			wantErr: true,
		},
		{
			name:    "非法小时非数字",
			now:     time.Date(2024, 3, 10, 6, 0, 0, 0, shanghai),
			clock:   "ab:30",
			loc:     shanghai,
			wantErr: true,
		},
		{
			name:    "小时越界24",
			now:     time.Date(2024, 3, 10, 6, 0, 0, 0, shanghai),
			clock:   "24:00",
			loc:     shanghai,
			wantErr: true,
		},
		{
			name:    "分钟越界60",
			now:     time.Date(2024, 3, 10, 6, 0, 0, 0, shanghai),
			clock:   "08:60",
			loc:     shanghai,
			wantErr: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := NextPushTime(tc.now, tc.clock, tc.loc)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("期望报错，实际返回 %v", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("不期望报错: %v", err)
			}
			if got.Year() != tc.wantYear || got.Month() != tc.wantMonth || got.Day() != tc.wantDay {
				t.Fatalf("日期不符 期望 %d-%02d-%02d 实际 %d-%02d-%02d",
					tc.wantYear, tc.wantMonth, tc.wantDay, got.Year(), got.Month(), got.Day())
			}
			if got.Hour() != tc.wantHour || got.Minute() != tc.wantMin {
				t.Fatalf("时刻不符 期望 %02d:%02d 实际 %02d:%02d",
					tc.wantHour, tc.wantMin, got.Hour(), got.Minute())
			}
			if !got.After(tc.now) && tc.loc != nil {
				t.Fatalf("返回时刻未晚于输入 now: %v <= %v", got, tc.now)
			}
		})
	}
}

// ---------- SM-2 极端 EF 值 ----------

// ---------- RunPushForUser 单通道失败不影响其他通道 ----------

type deepStubSender struct {
	name    string
	failErr error
	calls   int
}

func (s *deepStubSender) Name() string { return s.name }

func (s *deepStubSender) Send(ctx context.Context, msg notify.Message) error {
	s.calls++
	return s.failErr
}

// ---------- snippetOf 边界 ----------

func TestSnippetOfBoundaries(t *testing.T) {
	cases := []struct {
		name   string
		body   string
		max    int
		want   string
	}{
		{name: "短文本原样", body: "简短正文", max: 120, want: "简短正文"},
		{name: "空文本返回空", body: "", max: 120, want: ""},
		{name: "恰好等于上限不截断", body: strings.Repeat("a", 120), max: 120, want: strings.Repeat("a", 120)},
		{name: "超长按上限截断", body: strings.Repeat("a", 200), max: 120, want: strings.Repeat("a", 120)},
		{name: "中文按字符截断不切多字节", body: strings.Repeat("中", 200), max: 120, want: strings.Repeat("中", 120)},
		{name: "换行保留原样", body: "第一行\\n第二行", max: 120, want: "第一行\\n第二行"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := snippetOf(tc.body, tc.max)
			if got != tc.want {
				t.Fatalf("内容不符 期望 %q 实际 %q", tc.want, got)
			}
			if len([]rune(got)) > tc.max {
				t.Fatalf("结果超出上限 %d 实际 %d", tc.max, len([]rune(got)))
			}
			if strings.Contains(got, "\n") {
				t.Fatalf("结果不应含换行: %q", got)
			}
		})
	}
}

// ---------- truncateRunes 边界 ----------

func TestTruncateRunesBoundaries(t *testing.T) {
	cases := []struct {
		name string
		in   string
		max  int
		want string
	}{
		{name: "短串原样", in: "abc", max: 5, want: "abc"},
		{name: "恰好上限原样", in: "abcde", max: 5, want: "abcde"},
		{name: "超限截断", in: "abcdefg", max: 5, want: "abcde"},
		{name: "中文按rune截断", in: "中文测试内容", max: 3, want: "中文测"},
		{name: "空串原样", in: "", max: 5, want: ""},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := truncateRunes(tc.in, tc.max)
			if got != tc.want {
				t.Fatalf("内容不符 期望 %q 实际 %q", tc.want, got)
			}
			if len([]rune(got)) > tc.max {
				t.Fatalf("结果超出上限 %d 实际 %d", tc.max, len([]rune(got)))
			}
		})
	}
}

// ---------- channelEntries 稳定顺序 ----------

func TestChannelEntriesOrder(t *testing.T) {
	wp := &notify.WebPushSender{}
	senders := SenderSet{
		SMTP:    &deepStubSender{name: "smtp"},
		Webhook: &deepStubSender{name: "webhook"},
		WebPush: wp,
	}
	entries := channelEntries(senders)
	if len(entries) != 2 {
		t.Fatalf("应有2个通道 实际 %d", len(entries))
	}
	if entries[0].sender == nil || entries[0].sender.Name() != "smtp" {
		t.Fatalf("第0个应为 smtp 实际 %v", entries[0].sender)
	}
	if entries[1].sender == nil || entries[1].sender.Name() != "webhook" {
		t.Fatalf("第1个应为 webhook 实际 %v", entries[1].sender)
	}
}