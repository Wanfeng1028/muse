package notify

import (
	"strings"
	"testing"
	"time"
)

// assertContains 检查字符串包含子串，用于断言文案片段。
func assertContains(t *testing.T, got, want string) {
	t.Helper()
	if !strings.Contains(got, want) {
		t.Fatalf("期望包含 %q，实际内容：\n%s", want, got)
	}
}

func TestBuildDigestMessageSubjectBoundaries(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}

	cases := []struct {
		name        string
		date        time.Time
		items       []DigestItem
		wantSubject string
		wantDue     int
	}{
		{
			name:        "闰日 2月29日",
			date:        time.Date(2024, time.February, 29, 10, 0, 0, 0, loc),
			items:       []DigestItem{{Title: "闰日笔记"}},
			wantSubject: "第二大脑 · 2月29日复习提醒（1 篇待复习）",
			wantDue:     1,
		},
		{
			name:        "跨天 UTC 深夜换算到上海已是次日",
			date:        time.Date(2024, time.March, 1, 23, 30, 0, 0, time.UTC),
			items:       nil,
			wantSubject: "第二大脑 · 3月2日复习提醒（今日无待复习）",
			wantDue:     0,
		},
		{
			name:        "跨天上海本地 00:00 整",
			date:        time.Date(2024, time.January, 1, 0, 0, 0, 0, loc),
			items:       nil,
			wantSubject: "第二大脑 · 1月1日复习提醒（今日无待复习）",
			wantDue:     0,
		},
		{
			name:        "跨年前一天上海时间 23:59",
			date:        time.Date(2023, time.December, 31, 23, 59, 0, 0, loc),
			items:       []DigestItem{{Title: "a"}, {Title: "b"}, {Title: "c"}},
			wantSubject: "第二大脑 · 12月31日复习提醒（3 篇待复习）",
			wantDue:     3,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			msg := BuildDigestMessage(tc.date, tc.items, DigestStats{}, "user@example.com")
			if msg.Subject != tc.wantSubject {
				t.Fatalf("主题不匹配：期望 %q，实际 %q", tc.wantSubject, msg.Subject)
			}
			if msg.DueCount != tc.wantDue {
				t.Fatalf("DueCount 不匹配：期望 %d，实际 %d", tc.wantDue, msg.DueCount)
			}
			if msg.To != "user@example.com" {
				t.Fatalf("收件人不匹配：期望 user@example.com，实际 %q", msg.To)
			}
		})
	}
}

func TestBuildDigestMessageExtremeEFOverdueDays(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.June, 1, 9, 0, 0, 0, loc)

	items := []DigestItem{
		{Title: "EF 上限边界", OverdueDays: 1},
		{Title: "EF 归零边界", OverdueDays: 36500},
		{Title: "负逾期不显示", OverdueDays: -3},
	}

	msg := BuildDigestMessage(date, items, DigestStats{Streak: 7}, "u@x.com")

	assertContains(t, msg.TextBody, "1. EF 上限边界（逾期 1 天）")
	assertContains(t, msg.TextBody, "2. EF 归零边界（逾期 36500 天）")
	assertContains(t, msg.TextBody, "3. 负逾期不显示")
	if strings.Contains(msg.TextBody, "负逾期不显示（逾期 -3 天）") {
		t.Fatalf("负逾期天数不应显示逾期文案：\n%s", msg.TextBody)
	}
	assertContains(t, msg.TextBody, "你已经连续复习 7 天了。")
	assertContains(t, msg.HTMLBody, "EF 上限边界")
	assertContains(t, msg.HTMLBody, "逾期 36500 天")
	if msg.DueCount != 3 {
		t.Fatalf("DueCount 期望 3，实际 %d", msg.DueCount)
	}
}

func TestBuildDigestMessageStreakZeroSuppressed(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.July, 15, 12, 0, 0, 0, loc)

	msg := BuildDigestMessage(date, nil, DigestStats{Streak: 0}, "u@x.com")

	if strings.Contains(msg.TextBody, "你已经连续复习") {
		t.Fatalf("Streak 为 0 时不应出现连续复习文案：\n%s", msg.TextBody)
	}
	if strings.Contains(msg.HTMLBody, "你已经连续复习") {
		t.Fatalf("Streak 为 0 时 HTML 不应出现连续复习文案：\n%s", msg.HTMLBody)
	}
	assertContains(t, msg.TextBody, "今天没有到期的笔记，好好休息。")
	assertContains(t, msg.HTMLBody, "今天没有到期的笔记，好好休息")
	assertContains(t, msg.TextBody, "打开第二大脑开始复习。")
	assertContains(t, msg.HTMLBody, "打开第二大脑开始复习。")
}

func TestBuildDigestMessageDoubleBracketParsing(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.August, 8, 8, 0, 0, 0, loc)

	items := []DigestItem{
		{Title: "嵌套 [[外层 [[内层]] 结束]] 标题", Snippet: "片段含 [[链接]]", Tags: []string{"双链"}},
		{Title: "未闭合 [[草稿", Snippet: "[[", Tags: nil},
		{Title: "空双链 [[]]", Snippet: "[[ ]]", Tags: []string{}},
	}

	msg := BuildDigestMessage(date, items, DigestStats{}, "u@x.com")

	assertContains(t, msg.TextBody, "1. 嵌套 [[外层 [[内层]] 结束]] 标题")
	assertContains(t, msg.TextBody, "2. 未闭合 [[草稿")
	assertContains(t, msg.TextBody, "3. 空双链 [[]]")
	assertContains(t, msg.TextBody, "   片段含 [[链接]]")
	assertContains(t, msg.TextBody, "标签：双链")
	if strings.Count(msg.TextBody, "标签：") != 1 {
		t.Fatalf("只有第一条应显示标签，实际标签行数=%d\n%s", strings.Count(msg.TextBody, "标签："), msg.TextBody)
	}
	assertContains(t, msg.HTMLBody, "[[内层]]")
	assertContains(t, msg.HTMLBody, "[[链接]]")
}

func TestBuildDigestMessageChineseTitleEscaping(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.September, 9, 9, 9, 0, 0, loc)

	items := []DigestItem{
		{Title: "中文标题 <script>alert('x')</script> & \"引号\"", Snippet: "片段 & <b>粗体</b>", Tags: []string{"标签&<>"}},
	}

	msg := BuildDigestMessage(date, items, DigestStats{Streak: 3}, "u@x.com")

	if strings.Contains(msg.HTMLBody, "<script>") {
		t.Fatalf("HTML 未转义 script 标签：\n%s", msg.HTMLBody)
	}
	assertContains(t, msg.HTMLBody, "&lt;script&gt;")
	assertContains(t, msg.HTMLBody, "&amp;")
	assertContains(t, msg.HTMLBody, "&lt;b&gt;粗体&lt;/b&gt;")
	assertContains(t, msg.HTMLBody, "标签&amp;&lt;&gt;")
	assertContains(t, msg.TextBody, "中文标题 <script>alert('x')</script> & \"引号\"")
	assertContains(t, msg.TextBody, "标签：标签&<>")
}

func TestBuildDigestMessageSnippetTrim(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.October, 10, 10, 0, 0, 0, loc)

	items := []DigestItem{
		{Title: "空白片段", Snippet: "   \t\n  "},
		{Title: "正常片段", Snippet: "  内容  "},
	}

	msg := BuildDigestMessage(date, items, DigestStats{}, "u@x.com")

	if strings.Contains(msg.TextBody, "1. 空白片段\n   \n") {
		t.Fatalf("纯空白片段不应输出缩进行：\n%q", msg.TextBody)
	}
	assertContains(t, msg.TextBody, "   内容")
	if strings.Contains(msg.TextBody, "   内容  ") {
		t.Fatalf("片段应被 TrimSpace：\n%q", msg.TextBody)
	}
	if strings.Contains(msg.HTMLBody, "padding-top:4px;\">   ") {
		t.Fatalf("HTML 片段应被 TrimSpace：\n%s", msg.HTMLBody)
	}
	assertContains(t, msg.HTMLBody, "内容")
}

func TestBuildDigestMessageAttachmentWhitelistBypass(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.November, 11, 11, 0, 0, 0, loc)

	bypassAttempts := []string{
		"../../etc/passwd",
		"..%2f..%2fetc%2fpasswd",
		"notes.exe",
		"notes.EXE",
		"notes.png.exe",
		"notes\u0000.png",
		"notes.png ",
		" notes.png",
		"notes.png\n",
		"notes.PnG.exe",
	}

	items := make([]DigestItem, 0, len(bypassAttempts))
	for _, name := range bypassAttempts {
		items = append(items, DigestItem{Title: name})
	}

	msg := BuildDigestMessage(date, items, DigestStats{}, "u@x.com")

	for i, name := range bypassAttempts {
		prefix := ""
		if i == 0 {
			prefix = "1. "
		}
		_ = prefix
		if !strings.Contains(msg.TextBody, name) {
			t.Fatalf("第 %d 条尝试 %q 未被原样输出，可能被静默篡改：\n%s", i+1, name, msg.TextBody)
		}
	}
	if msg.DueCount != len(bypassAttempts) {
		t.Fatalf("DueCount 期望 %d，实际 %d", len(bypassAttempts), msg.DueCount)
	}
	assertContains(t, msg.TextBody, "10. notes.PnG.exe")
	assertContains(t, msg.HTMLBody, "notes.PnG.exe")
}

func TestBuildDigestMessageHTMLStructure(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.December, 25, 9, 0, 0, 0, loc)

	msg := BuildDigestMessage(date, nil, DigestStats{}, "u@x.com")

	assertContains(t, msg.HTMLBody, "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body")
	assertContains(t, msg.HTMLBody, "width=\"600\"")
	assertContains(t, msg.HTMLBody, "第二大脑 · 复习提醒")
	if !strings.HasSuffix(msg.HTMLBody, "</table></td></tr></table></body></html>") {
		t.Fatalf("HTML 结尾结构不匹配：\n%s", msg.HTMLBody)
	}
	if msg.Subject != "第二大脑 · 12月25日复习提醒（今日无待复习）" {
		t.Fatalf("主题不匹配：%q", msg.Subject)
	}
	if msg.DueCount != 0 {
		t.Fatalf("DueCount 期望 0，实际 %d", msg.DueCount)
	}
}

func TestBuildDigestMessageItemsPreserved(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.May, 20, 20, 0, 0, 0, loc)

	items := []DigestItem{
		{Title: "一", Snippet: "s1", Tags: []string{"t1", "t2"}, DueDate: "2024-05-20", OverdueDays: 0},
		{Title: "二", Snippet: "s2", Tags: nil, DueDate: "2024-05-18", OverdueDays: 2},
	}

	msg := BuildDigestMessage(date, items, DigestStats{Streak: 1}, "owner@example.com")

	if len(msg.Items) != 2 {
		t.Fatalf("Items 长度期望 2，实际 %d", len(msg.Items))
	}
	if msg.Items[0].Title != "一" || msg.Items[1].Title != "二" {
		t.Fatalf("Items 顺序被改动：%+v", msg.Items)
	}
	if msg.Items[1].OverdueDays != 2 {
		t.Fatalf("Items[1].OverdueDays 期望 2，实际 %d", msg.Items[1].OverdueDays)
	}
	if msg.Items[0].DueDate != "2024-05-20" {
		t.Fatalf("Items[0].DueDate 期望 2024-05-20，实际 %q", msg.Items[0].DueDate)
	}
	assertContains(t, msg.TextBody, "今天有 2 篇笔记到期了：")
	assertContains(t, msg.TextBody, "标签：t1、t2")
}

func TestBuildDigestMessageMultiUserIsolation(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.April, 1, 9, 0, 0, 0, loc)

	aliceItems := []DigestItem{{Title: "Alice 的笔记"}}
	bobItems := []DigestItem{{Title: "Bob 的笔记"}, {Title: "Bob 的另一条"}}

	aliceMsg := BuildDigestMessage(date, aliceItems, DigestStats{Streak: 5}, "alice@example.com")
	bobMsg := BuildDigestMessage(date, bobItems, DigestStats{Streak: 2}, "bob@example.com")

	if aliceMsg.To != "alice@example.com" {
		t.Fatalf("Alice 收件人不匹配：%q", aliceMsg.To)
	}
	if bobMsg.To != "bob@example.com" {
		t.Fatalf("Bob 收件人不匹配：%q", bobMsg.To)
	}
	if strings.Contains(aliceMsg.TextBody, "Bob 的笔记") {
		t.Fatalf("Alice 的正文泄露了 Bob 的笔记：\n%s", aliceMsg.TextBody)
	}
	if strings.Contains(aliceMsg.HTMLBody, "Bob 的笔记") {
		t.Fatalf("Alice 的 HTML 泄露了 Bob 的笔记：\n%s", aliceMsg.HTMLBody)
	}
	if strings.Contains(bobMsg.TextBody, "Alice 的笔记") {
		t.Fatalf("Bob 的正文泄露了 Alice 的笔记：\n%s", bobMsg.TextBody)
	}
	assertContains(t, aliceMsg.TextBody, "你已经连续复习 5 天了。")
	assertContains(t, bobMsg.TextBody, "你已经连续复习 2 天了。")
	if aliceMsg.DueCount != 1 || bobMsg.DueCount != 2 {
		t.Fatalf("DueCount 隔离失败：alice=%d bob=%d", aliceMsg.DueCount, bobMsg.DueCount)
	}
}

func TestBuildDigestMessageZipSlipTitle(t *testing.T) {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		t.Fatalf("加载 Asia/Shanghai 失败：%v", err)
	}
	date := time.Date(2024, time.February, 1, 9, 0, 0, 0, loc)

	zipSlipTitles := []string{
		"../../../../etc/passwd",
		"..\\..\\Windows\\System32\\config",
		"/absolute/path",
		"C:\\Windows\\win.ini",
		"foo/../../../bar",
	}

	items := make([]DigestItem, 0, len(zipSlipTitles))
	for _, title := range zipSlipTitles {
		items = append(items, DigestItem{Title: title})
	}

	msg := BuildDigestMessage(date, items, DigestStats{}, "u@x.com")

	for _, title := range zipSlipTitles {
		if !strings.Contains(msg.TextBody, title) {
			t.Fatalf("ZipSlip 标题 %q 未原样保留在正文：\n%s", title, msg.TextBody)
		}
		if !strings.Contains(msg.HTMLBody, title) && !strings.Contains(msg.HTMLBody, htmlEscapeTitle(title)) {
			t.Fatalf("ZipSlip 标题 %q 未出现在 HTML：\n%s", title, msg.HTMLBody)
		}
	}
	assertContains(t, msg.TextBody, "5. foo/../../../bar")
	if msg.DueCount != 5 {
		t.Fatalf("DueCount 期望 5，实际 %d", msg.DueCount)
	}
}

// htmlEscapeTitle 复刻 html.EscapeString 的关键字符替换，仅用于测试断言对比。
func htmlEscapeTitle(s string) string {
	replacer := strings.NewReplacer(
		"&", "&amp;",
		"<", "&lt;",
		">", "&gt;",
		`"`, "&#34;",
		"'", "&#39;",
	)
	return replacer.Replace(s)
}
