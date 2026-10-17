package push

import (
	"context"
	"errors"
	"math"
	"math/rand"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
)

// ---- 复习调度边界 ----

// reviewDueAt 计算下一次复习时间：now + interval 天，按 UTC 自然日推进。
// 跨天/闰日/时区都通过 UTC 归一化保证结果稳定。
func reviewDueAt(now time.Time, intervalDays int) time.Time {
	if intervalDays < 0 {
		intervalDays = 0
	}
	return now.UTC().AddDate(0, 0, intervalDays)
}

func TestReviewScheduleBoundary(t *testing.T) {
	cases := []struct {
		name         string
		now          time.Time
		intervalDays int
		want         time.Time
	}{
		{
			name:         "跨月边界",
			now:          time.Date(2024, 1, 31, 23, 59, 59, 0, time.UTC),
			intervalDays: 1,
			want:         time.Date(2024, 2, 1, 23, 59, 59, 0, time.UTC),
		},
		{
			name:         "闰日当天加一天到三月",
			now:          time.Date(2024, 2, 29, 8, 0, 0, 0, time.UTC),
			intervalDays: 1,
			want:         time.Date(2024, 3, 1, 8, 0, 0, 0, time.UTC),
		},
		{
			name:         "闰日前一天加一天到闰日",
			now:          time.Date(2024, 2, 28, 0, 0, 0, 0, time.UTC),
			intervalDays: 1,
			want:         time.Date(2024, 2, 29, 0, 0, 0, 0, time.UTC),
		},
		{
			name:         "非闰年二月加一天到三月",
			now:          time.Date(2023, 2, 28, 12, 30, 0, 0, time.UTC),
			intervalDays: 1,
			want:         time.Date(2023, 3, 1, 12, 30, 0, 0, time.UTC),
		},
		{
			name:         "跨年边界",
			now:          time.Date(2024, 12, 31, 23, 59, 59, 0, time.UTC),
			intervalDays: 1,
			want:         time.Date(2025, 1, 1, 23, 59, 59, 0, time.UTC),
		},
		{
			name:         "东八区凌晨归一到UTC前一天",
			now:          time.Date(2024, 3, 1, 0, 30, 0, 0, time.FixedZone("CST", 8*3600)),
			intervalDays: 0,
			want:         time.Date(2024, 2, 29, 16, 30, 0, 0, time.UTC),
		},
		{
			name:         "西五区深夜归一到UTC次日",
			now:          time.Date(2024, 2, 29, 23, 0, 0, 0, time.FixedZone("EST", -5*3600)),
			intervalDays: 0,
			want:         time.Date(2024, 3, 1, 4, 0, 0, 0, time.UTC),
		},
		{
			name:         "负间隔钳制为零",
			now:          time.Date(2024, 2, 29, 10, 0, 0, 0, time.UTC),
			intervalDays: -5,
			want:         time.Date(2024, 2, 29, 10, 0, 0, 0, time.UTC),
		},
		{
			name:         "大间隔跨闰年",
			now:          time.Date(2024, 2, 29, 0, 0, 0, 0, time.UTC),
			intervalDays: 366,
			want:         time.Date(2025, 3, 1, 0, 0, 0, 0, time.UTC),
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := reviewDueAt(tc.now, tc.intervalDays)
			if !got.Equal(tc.want) {
				t.Fatalf("reviewDueAt(%v, %d) = %v, 期望 %v", tc.now, tc.intervalDays, got, tc.want)
			}
			if got.Location() != time.UTC {
				t.Fatalf("结果时区应为 UTC，实际 %v", got.Location())
			}
		})
	}
}

// ---- SM-2 极端 EF 值 ----

// sm2EF 依据 SM-2 算法更新难度因子，质量 q 取值 0..5，EF 下限 1.3。
func sm2EF(ef float64, q int) float64 {
	if ef < 1.3 {
		ef = 1.3
	}
	delta := 0.1 - float64(5-q)*(0.08+float64(5-q)*0.02)
	ef = ef + delta
	if ef < 1.3 {
		ef = 1.3
	}
	return ef
}

func TestSM2ExtremeEF(t *testing.T) {
	cases := []struct {
		name string
		ef   float64
		q    int
		want float64
	}{
		{name: "满分质量EF上升", ef: 2.5, q: 5, want: 2.6},
		{name: "零质量EF下降但未到下限", ef: 2.5, q: 0, want: 1.7},
		{name: "下限EF再被压仍为下限", ef: 1.3, q: 0, want: 1.3},
		{name: "低于下限的EF先被钳制再更新", ef: 0.5, q: 5, want: 1.4},
		{name: "质量3时EF下降", ef: 2.5, q: 3, want: 2.36},
		{name: "质量4时EF微降", ef: 2.5, q: 4, want: 2.5},
		{name: "极大EF满分仍受浮点上界", ef: 1e6, q: 5, want: 1e6 + 0.1},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := sm2EF(tc.ef, tc.q)
			if math.Abs(got-tc.want) > 1e-9 {
				t.Fatalf("sm2EF(%v, %d) = %v, 期望 %v", tc.ef, tc.q, got, tc.want)
			}
			if got < 1.3 {
				t.Fatalf("EF 不得低于下限 1.3，实际 %v", got)
			}
		})
	}
}

// ---- 双链解析边界 ----

// parseWikiLinks 解析文本中的 [[目标]]，返回去重后的顺序列表。
// 只处理最外层配对，嵌套 [[a [[b]] ]] 解析为 "a [[b]]"。
func parseWikiLinks(text string) []string {
	var out []string
	seen := map[string]bool{}
	i := 0
	for i < len(text) {
		start := strings.Index(text[i:], "[[")
		if start < 0 {
			break
		}
		start += i
		depth := 0
		j := start
		end := -1
		for j < len(text)-1 {
			if text[j] == '[' && text[j+1] == '[' {
				depth++
				j += 2
				continue
			}
			if text[j] == ']' && text[j+1] == ']' {
				depth--
				if depth == 0 {
					end = j
					break
				}
				j += 2
				continue
			}
			j++
		}
		if end < 0 {
			break
		}
		inner := text[start+2 : end]
		if inner != "" && !seen[inner] {
			seen[inner] = true
			out = append(out, inner)
		}
		i = end + 2
	}
	return out
}

func TestParseWikiLinksBoundary(t *testing.T) {
	cases := []struct {
		name string
		text string
		want []string
	}{
		{name: "普通单个链接", text: "见 [[笔记]] 结束", want: []string{"笔记"}},
		{name: "多个链接去重保序", text: "[[甲]] 与 [[乙]] 再 [[甲]]", want: []string{"甲", "乙"}},
		{name: "嵌套链接取外层", text: "外层 [[a [[b]] c]] 结束", want: []string{"a [[b]] c"}},
		{name: "中文标题含空格", text: "看 [[ 中文 标题 ]] 完", want: []string{" 中文 标题 "}},
		{name: "空链接忽略", text: "[[]] 与 [[有效]]", want: []string{"有效"}},
		{name: "未闭合链接忽略", text: "开头 [[没有结尾", want: nil},
		{name: "中文标点标题", text: "参考 [[复习：计划（一）]] 结尾", want: []string{"复习：计划（一）"}},
		{name: "相邻链接", text: "[[一]][[二]]", want: []string{"一", "二"}},
		{name: "方括号数量不足", text: "[单] 与 [双", want: nil},
		{name: "链接内含换行", text: "[[第一行\n第二行]]", want: []string{"第一行\n第二行"}},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := parseWikiLinks(tc.text)
			if len(got) != len(tc.want) {
				t.Fatalf("parseWikiLinks(%q) 长度 = %d (%v), 期望 %d (%v)", tc.text, len(got), got, len(tc.want), tc.want)
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Fatalf("parseWikiLinks(%q)[%d] = %q, 期望 %q", tc.text, i, got[i], tc.want[i])
				}
			}
		})
	}
}

// ---- 附件白名单绕过尝试 ----

var allowedAttachmentExts = map[string]bool{
	".png":  true,
	".jpg":  true,
	".jpeg": true,
	".pdf":  true,
	".md":   true,
	".txt":  true,
}

// attachmentAllowed 依据扩展名白名单判定附件是否可上传。
// 先取最后一段扩展名，再做小写归一化，拒绝双扩展名绕过。
func attachmentAllowed(name string) bool {
	if name == "" {
		return false
	}
	lower := strings.ToLower(name)
	idx := strings.LastIndex(lower, ".")
	if idx < 0 {
		return false
	}
	ext := lower[idx:]
	if !allowedAttachmentExts[ext] {
		return false
	}
	// 若在最后一段之前还含有可疑扩展段，视为绕过尝试。
	prefix := lower[:idx]
	if strings.Contains(prefix, ".php") || strings.Contains(prefix, ".sh") || strings.Contains(prefix, ".exe") {
		return false
	}
	return true
}

func TestAttachmentWhitelistBypass(t *testing.T) {
	cases := []struct {
		name string
		file string
		want bool
	}{
		{name: "正常png", file: "photo.png", want: true},
		{name: "大写扩展名归一化", file: "PHOTO.PNG", want: true},
		{name: "双扩展名php绕过拒绝", file: "shell.php.png", want: false},
		{name: "双扩展名sh绕过拒绝", file: "run.sh.jpg", want: false},
		{name: "双扩展名exe绕过拒绝", file: "evil.exe.pdf", want: false},
		{name: "无扩展名拒绝", file: "noext", want: false},
		{name: "空文件名拒绝", file: "", want: false},
		{name: "以点结尾拒绝", file: "file.", want: false},
		{name: "隐藏文件带合法扩展", file: ".config.md", want: true},
		{name: "白名单外扩展名拒绝", file: "script.js", want: false},
		{name: "中文名带合法扩展", file: "文档.pdf", want: true},
		{name: "路径穿越前缀不影响扩展判定", file: "../evil.php.txt", want: false},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := attachmentAllowed(tc.file)
			if got != tc.want {
				t.Fatalf("attachmentAllowed(%q) = %v, 期望 %v", tc.file, got, tc.want)
			}
			if tc.want && got {
				lower := strings.ToLower(tc.file)
				ext := lower[strings.LastIndex(lower, "."):]
				if !allowedAttachmentExts[ext] {
					t.Fatalf("允许的附件扩展名 %q 不在白名单中", ext)
				}
			}
		})
	}
}

// ---- 导出 ZipSlip ----

// safeZipEntry 判定导出条目名是否安全，拒绝绝对路径、上跳、以及盘符前缀。
func safeZipEntry(name string) bool {
	if name == "" {
		return false
	}
	if strings.HasPrefix(name, "/") || strings.HasPrefix(name, "\\") {
		return false
	}
	if len(name) >= 2 && name[1] == ':' {
		return false
	}
	cleaned := strings.ReplaceAll(name, "\\", "/")
	parts := strings.Split(cleaned, "/")
	depth := 0
	for _, p := range parts {
		if p == ".." {
			depth--
			if depth < 0 {
				return false
			}
		} else if p != "." && p != "" {
			depth++
		}
	}
	return true
}

func TestExportZipSlip(t *testing.T) {
	cases := []struct {
		name  string
		entry string
		want  bool
	}{
		{name: "普通相对路径", entry: "notes/a.md", want: true},
		{name: "根级上跳拒绝", entry: "../etc/passwd", want: false},
		{name: "深层上跳拒绝", entry: "a/b/../../../etc/passwd", want: false},
		{name: "绝对路径拒绝", entry: "/etc/passwd", want: false},
		{name: "反斜杠绝对路径拒绝", entry: "\\windows\\system32", want: false},
		{name: "Windows盘符拒绝", entry: "C:/windows/win.ini", want: false},
		{name: "反斜杠上跳拒绝", entry: "..\\..\\secret.txt", want: false},
		{name: "中间上跳后回到根内", entry: "a/../b.md", want: true},
		{name: "当前目录前缀安全", entry: "./notes/b.md", want: true},
		{name: "空条目拒绝", entry: "", want: false},
		{name: "中文目录安全", entry: "笔记/复习.md", want: true},
		{name: "混合斜杠上跳拒绝", entry: "a/..\\../secret", want: false},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := safeZipEntry(tc.entry)
			if got != tc.want {
				t.Fatalf("safeZipEntry(%q) = %v, 期望 %v", tc.entry, got, tc.want)
			}
			if !got {
				return
			}
			normalized := strings.ReplaceAll(tc.entry, "\\", "/")
			if strings.HasPrefix(normalized, "/") {
				t.Fatalf("被判定安全的条目 %q 却是绝对路径", tc.entry)
			}
			if strings.Contains(normalized, "..") {
				depth := 0
				for _, p := range strings.Split(normalized, "/") {
					if p == ".." {
						depth--
						if depth < 0 {
							t.Fatalf("被判定安全的条目 %q 实际会逃逸根目录", tc.entry)
						}
					} else if p != "." && p != "" {
						depth++
					}
				}
			}
		})
	}
}

// ---- 多用户隔离 ----

// userNoteKey 生成用户维度的存储键，保证不同用户互不可见。
func userNoteKey(userID, noteID string) string {
	return userID + "::" + noteID
}

func TestMultiUserIsolation(t *testing.T) {
	cases := []struct {
		name   string
		userA  string
		userB  string
		noteID string
	}{
		{name: "不同用户同笔记ID键不同", userA: "u1", userB: "u2", noteID: "n1"},
		{name: "空用户名区分", userA: "", userB: "u2", noteID: "n1"},
		{name: "相同前缀用户区分", userA: "user", userB: "user2", noteID: "n1"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			keyA := userNoteKey(tc.userA, tc.noteID)
			keyB := userNoteKey(tc.userB, tc.noteID)
			if keyA == keyB {
				t.Fatalf("不同用户的键不应相同: %q", keyA)
			}
			if !strings.HasPrefix(keyA, tc.userA+"::") {
				t.Fatalf("键 %q 未以用户 %q 前缀", keyA, tc.userA)
			}
			if !strings.HasSuffix(keyA, "::"+tc.noteID) {
				t.Fatalf("键 %q 未以笔记 %q 结尾", keyA, tc.noteID)
			}
		})
	}
}

// ---- 重试策略与退避 ----

func TestBackoffForAttemptBoundary(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  5,
		BaseBackoff: 100 * time.Millisecond,
		MaxBackoff:  800 * time.Millisecond,
		JitterRatio: 0,
	}
	cases := []struct {
		name    string
		attempt int
		want    time.Duration
	}{
		{name: "第零次为基础值", attempt: 0, want: 100 * time.Millisecond},
		{name: "第一次翻倍", attempt: 1, want: 200 * time.Millisecond},
		{name: "第二次翻倍", attempt: 2, want: 400 * time.Millisecond},
		{name: "第三次触及上限", attempt: 3, want: 800 * time.Millisecond},
		{name: "第四次被上限钳制", attempt: 4, want: 800 * time.Millisecond},
		{name: "负attempt钳为零", attempt: -3, want: 100 * time.Millisecond},
		{name: "超大attempt直接上限", attempt: 100, want: 800 * time.Millisecond},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := backoffForAttempt(policy, tc.attempt, nil)
			if got != tc.want {
				t.Fatalf("backoffForAttempt(attempt=%d) = %v, 期望 %v", tc.attempt, got, tc.want)
			}
			if got > policy.MaxBackoff {
				t.Fatalf("退避 %v 超过上限 %v", got, policy.MaxBackoff)
			}
		})
	}
}

func TestBackoffWithJitterStaysWithinRange(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  3,
		BaseBackoff: 1000 * time.Millisecond,
		MaxBackoff:  3000 * time.Millisecond,
		JitterRatio: 0.25,
	}
	rng := rand.New(rand.NewSource(20240301))
	for attempt := 0; attempt < 8; attempt++ {
		for i := 0; i < 50; i++ {
			got := backoffForAttempt(policy, attempt, rng)
			if got < 0 {
				t.Fatalf("attempt=%d 第%d次抖动结果为负: %v", attempt, i, got)
			}
			if got > policy.MaxBackoff {
				t.Fatalf("attempt=%d 第%d次抖动 %v 超过上限 %v", attempt, i, got, policy.MaxBackoff)
			}
		}
	}
}

func TestIsRetryableCategories(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want bool
	}{
		{name: "nil不重试", err: nil, want: false},
		{name: "context取消不重试", err: context.Canceled, want: false},
		{name: "context超时不重试", err: context.DeadlineExceeded, want: false},
		{name: "鉴权失败不重试", err: notify.ErrAuth, want: false},
		{name: "订阅失效不重试", err: notify.ErrSubscriptionGone, want: false},
		{name: "连接错误重试", err: notify.ErrConn, want: true},
		{name: "中文429重试", err: errors.New("请求失败 状态码 429 太频繁"), want: true},
		{name: "中文500重试", err: errors.New("服务端 状态码 500 崩溃"), want: true},
		{name: "中文200不重试", err: errors.New("状态 200 正常"), want: false},
		{name: "中文404不重试", err: errors.New("状态码 404 找不到"), want: false},
		{name: "英文429重试", err: errors.New("http status: 429"), want: true},
		{name: "英文503重试", err: errors.New("HTTP 503 unavailable"), want: true},
		{name: "英文400不重试", err: errors.New("status 400 bad request"), want: false},
		{name: "长数字串不误判为状态码", err: errors.New("状态码 2000 内部码"), want: true},
		{name: "未知错误fail-open重试", err: errors.New("神秘的错误"), want: true},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			got := IsRetryable(tc.err)
			if got != tc.want {
				t.Fatalf("IsRetryable(%v) = %v, 期望 %v", tc.err, got, tc.want)
			}
			if tc.err == nil && got {
				t.Fatalf("nil 错误不应被判定为可重试")
			}
		})
	}
}

func TestWithRetryImmediateFailure(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  3,
		BaseBackoff: time.Second,
		MaxBackoff:  10 * time.Second,
		JitterRatio: 0.25,
	}
	var sleeps []time.Duration
	sleep := func(ctx context.Context, d time.Duration) error {
		sleeps = append(sleeps, d)
		return nil
	}
	calls := 0
	err := withRetry(context.Background(), policy, sleep, "test", func() error {
		calls++
		return notify.ErrAuth
	})
	if calls != 1 {
		t.Fatalf("不可重试错误应只尝试一次，实际 %d 次", calls)
	}
	if len(sleeps) != 0 {
		t.Fatalf("不可重试错误不应睡眠，实际睡眠 %d 次", len(sleeps))
	}
	var exhausted *RetryExhaustedError
	if !errors.As(err, &exhausted) {
		t.Fatalf("期望 RetryExhaustedError，实际 %v", err)
	}
	if !exhausted.Immediate {
		t.Fatalf("期望 Immediate=true，实际 %v", exhausted.Immediate)
	}
	if exhausted.Attempts != 1 {
		t.Fatalf("期望 Attempts=1，实际 %d", exhausted.Attempts)
	}
	if !errors.Is(err, notify.ErrAuth) {
		t.Fatalf("Unwrap 应暴露 ErrAuth")
	}
}

func TestWithRetryExhaustsAndSucceeds(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  4,
		BaseBackoff: time.Millisecond,
		MaxBackoff:  time.Millisecond,
		JitterRatio: 0,
	}
	var slept int
	sleep := func(ctx context.Context, d time.Duration) error {
		slept++
		return nil
	}

	// 前两次可重试失败，第三次成功。
	calls := 0
	err := withRetry(context.Background(), policy, sleep, "test", func() error {
		calls++
		if calls < 3 {
			return notify.ErrConn
		}
		return nil
	})
	if err != nil {
		t.Fatalf("最终应成功，实际错误 %v", err)
	}
	if calls != 3 {
		t.Fatalf("期望尝试 3 次，实际 %d 次", calls)
	}
	if slept != 2 {
		t.Fatalf("期望睡眠 2 次，实际 %d 次", slept)
	}

	// 全部失败应耗尽并返回 RetryExhaustedError。
	calls = 0
	err = withRetry(context.Background(), policy, sleep, "test", func() error {
		calls++
		return notify.ErrConn
	})
	if calls != policy.MaxRetries+1 {
		t.Fatalf("耗尽时尝试次数应为 %d，实际 %d", policy.MaxRetries+1, calls)
	}
	var exhausted *RetryExhaustedError
	if !errors.As(err, &exhausted) {
		t.Fatalf("期望 RetryExhaustedError，实际 %v", err)
	}
	if exhausted.Immediate {
		t.Fatalf("耗尽错误不应标记 Immediate")
	}
	if exhausted.Attempts != policy.MaxRetries+1 {
		t.Fatalf("期望 Attempts=%d，实际 %d", policy.MaxRetries+1, exhausted.Attempts)
	}
}

func TestDefaultRetryPolicyClampsEnv(t *testing.T) {
	cases := []struct {
		name        string
		maxRetries  string
		baseMS      string
		wantRetries int
		wantBase    time.Duration
	}{
		{name: "缺省值", maxRetries: "", baseMS: "", wantRetries: 3, wantBase: 1000 * time.Millisecond},
		{name: "超大重试被钳到10", maxRetries: "100", baseMS: "", wantRetries: 10, wantBase: 1000 * time.Millisecond},
		{name: "负数重试回落默认", maxRetries: "-1", baseMS: "", wantRetries: 3, wantBase: 1000 * time.Millisecond},
		{name: "非数字重试回落默认", maxRetries: "abc", baseMS: "", wantRetries: 3, wantBase: 1000 * time.Millisecond},
		{name: "超大基础被钳到60秒", maxRetries: "", baseMS: "1000000", wantRetries: 3, wantBase: 60000 * time.Millisecond},
		{name: "零基础回落默认", maxRetries: "", baseMS: "0", wantRetries: 3, wantBase: 1000 * time.Millisecond},
		{name: "合法自定义生效", maxRetries: "5", baseMS: "200", wantRetries: 5, wantBase: 200 * time.Millisecond},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			if tc.maxRetries == "" {
				os.Unsetenv("SB_PUSH_MAX_RETRIES")
			} else {
				os.Setenv("SB_PUSH_MAX_RETRIES", tc.maxRetries)
			}
			if tc.baseMS == "" {
				os.Unsetenv("SB_PUSH_RETRY_BASE_MS")
			} else {
				os.Setenv("SB_PUSH_RETRY_BASE_MS", tc.baseMS)
			}
			defer os.Unsetenv("SB_PUSH_MAX_RETRIES")
			defer os.Unsetenv("SB_PUSH_RETRY_BASE_MS")

			p := DefaultRetryPolicy()
			if p.MaxRetries != tc.wantRetries {
				t.Fatalf("MaxRetries = %d, 期望 %d", p.MaxRetries, tc.wantRetries)
			}
			if p.BaseBackoff != tc.wantBase {
				t.Fatalf("BaseBackoff = %v, 期望 %v", p.BaseBackoff, tc.wantBase)
			}
			if p.MaxBackoff != 30*time.Second {
				t.Fatalf("MaxBackoff = %v, 期望 30s", p.MaxBackoff)
			}
			if p.JitterRatio != 0.25 {
				t.Fatalf("JitterRatio = %v, 期望 0.25", p.JitterRatio)
			}
		})
	}
}

func TestWithRetryContextCanceled(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  5,
		BaseBackoff: time.Hour,
		MaxBackoff:  time.Hour,
		JitterRatio: 0,
	}
	ctx, cancel := context.WithCancel(context.Background())
	sleep := func(ctx context.Context, d time.Duration) error {
		cancel()
		return ctx.Err()
	}
	err := withRetry(ctx, policy, sleep, "test", func() error {
		return notify.ErrConn
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("期望 context.Canceled，实际 %v", err)
	}
	var exhausted *RetryExhaustedError
	if errors.As(err, &exhausted) {
		t.Fatalf("取消不应被包装为 RetryExhaustedError")
	}
}