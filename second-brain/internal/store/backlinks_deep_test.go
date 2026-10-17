package store

import (
	"testing"
)

func TestBuildSnippet(t *testing.T) {
	cases := []struct {
		name        string
		body        string
		targetTitle string
		want        string
	}{
		{
			name:        "普通中文标题命中",
			body:        "前面的话 [[目标笔记]] 后面的话",
			targetTitle: "目标笔记",
			want:        "前面的话 [[目标笔记]] 后面的话",
		},
		{
			name:        "匹配不到时回退前120rune",
			body:        "没有任何链接的正文",
			targetTitle: "不存在的标题",
			want:        "没有任何链接的正文",
		},
		{
			name:        "超过120rune时截断到120rune",
			body:        "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十尾巴",
			targetTitle: "无",
			want:        "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十",
		},
		{
			name:        "前文超过40rune加省略号",
			body:        "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三[[标题]]后",
			targetTitle: "标题",
			want:        "…四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三[[标题]]后",
		},
		{
			name:        "后文超过40rune加省略号",
			body:        "前[[标题]]一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三",
			targetTitle: "标题",
			want:        "前[[标题]]一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十…",
		},
		{
			name:        "只匹配当前行不含其他行",
			body:        "上一行内容\n本行有 [[标题]] 命中\n下一行内容",
			targetTitle: "标题",
			want:        "本行有 [[标题]] 命中",
		},
		{
			name:        "匹配标题大小写不同则回退",
			body:        "正文里写的是 [[Title]]",
			targetTitle: "title",
			want:        "正文里写的是 [[Title]]",
		},
		{
			name:        "嵌套双方括号只匹配外层字面",
			body:        "文本 [[外层 [[内层]] 结束]] 尾巴",
			targetTitle: "外层 [[内层",
			want:        "文本 [[外层 [[内层]] 结束]] 尾巴",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := buildSnippet(tc.body, tc.targetTitle)
			if got != tc.want {
				t.Fatalf("buildSnippet 结果不对\nbody=%q\ntarget=%q\ngot =%q\nwant=%q", tc.body, tc.targetTitle, got, tc.want)
			}
			if tc.targetTitle != "不存在的标题" && tc.targetTitle != "无" && tc.targetTitle != "title" {
				if len([]rune(got)) == 0 {
					t.Fatalf("命中场景不应返回空串")
				}
			}
		})
	}
}

func TestHeadRunes(t *testing.T) {
	cases := []struct {
		name string
		in   string
		n    int
		want string
	}{
		{
			name: "不足n原样返回",
			in:   "短",
			n:    5,
			want: "短",
		},
		{
			name: "超过n按rune截断",
			in:   "一二三四五六",
			n:    3,
			want: "一二三",
		},
		{
			name: "恰好n个rune",
			in:   "一二三",
			n:    3,
			want: "一二三",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := headRunes(tc.in, tc.n)
			if got != tc.want {
				t.Fatalf("headRunes(%q,%d)=%q want %q", tc.in, tc.n, got, tc.want)
			}
			if len([]rune(got)) > tc.n {
				t.Fatalf("结果 rune 数超过 n: got %d rune", len([]rune(got)))
			}
		})
	}
}

func TestBuildSnippetExactRuneBoundary(t *testing.T) {
	before := ""
	for i := 0; i < snippetContextRunes; i++ {
		before += "前"
	}
	after := ""
	for i := 0; i < snippetContextRunes; i++ {
		after += "后"
	}
	body := before + "[[标题]]" + after
	got := buildSnippet(body, "标题")
	want := before + "[[标题]]" + after
	if got != want {
		t.Fatalf("边界等于40rune时不应加省略号\ngot =%q\nwant=%q", got, want)
	}
	if len([]rune(got)) != snippetContextRunes*2+len([]rune("[[标题]]")) {
		t.Fatalf("边界场景 rune 长度不符: got %d", len([]rune(got)))
	}
}

func TestBuildSnippetJustOverBoundary(t *testing.T) {
	before := ""
	for i := 0; i < snippetContextRunes+1; i++ {
		before += "前"
	}
	after := ""
	for i := 0; i < snippetContextRunes+1; i++ {
		after += "后"
	}
	body := before + "[[标题]]" + after
	got := buildSnippet(body, "标题")
	runes := []rune(got)
	if runes[0] != '…' {
		t.Fatalf("前文超1个rune应加前省略号, got 开头=%q", string(runes[0]))
	}
	if runes[len(runes)-1] != '…' {
		t.Fatalf("后文超1个rune应加后省略号, got 结尾=%q", string(runes[len(runes)-1]))
	}
	if !containsSub(got, "[[标题]]") {
		t.Fatalf("结果应保留匹配片段, got=%q", got)
	}
}

func TestBuildSnippetMultiLinePosition(t *testing.T) {
	body := "第一行\n第二行 [[目标]] 中间\n第三行\n第四行"
	got := buildSnippet(body, "目标")
	want := "第二行 [[目标]] 中间"
	if got != want {
		t.Fatalf("多行场景应只取命中行\ngot =%q\nwant=%q", got, want)
	}
	if containsSub(got, "第一行") || containsSub(got, "第三行") {
		t.Fatalf("结果不应包含其他行, got=%q", got)
	}
}

func TestBuildSnippetNestedBrackets(t *testing.T) {
	body := "开头 [[外层 [[内层]] 尾巴]] 结尾"
	got := buildSnippet(body, "外层 [[内层")
	want := "开头 [[外层 [[内层]] 尾巴]] 结尾"
	if got != want {
		t.Fatalf("嵌套方括号字面匹配结果不对\ngot =%q\nwant=%q", got, want)
	}
	if len([]rune(got)) == 0 {
		t.Fatalf("嵌套场景不应返回空串")
	}
}

func TestBuildSnippetUnicodeSnippet(t *testing.T) {
	body := "普通段落 [[中文标题]] 后续文字"
	got := buildSnippet(body, "中文标题")
	if !containsSub(got, "[[中文标题]]") {
		t.Fatalf("中文标题应完整保留在结果中, got=%q", got)
	}
	for _, r := range got {
		if r == '\uFFFD' {
			t.Fatalf("结果中不应出现 UTF-8 替换字符, got=%q", got)
		}
	}
}

func TestBacklinkStructFields(t *testing.T) {
	b := Backlink{
		ID:          7,
		Title:       "来源笔记",
		TargetTitle: "目标笔记",
		Snippet:     "包含 [[目标笔记]] 的片段",
		CreatedAt:   "2024-02-29T00:00:00Z",
	}
	if b.ID != 7 {
		t.Fatalf("ID 字段未正确赋值: %d", b.ID)
	}
	if b.TargetTitle != "目标笔记" {
		t.Fatalf("TargetTitle 字段未正确赋值: %q", b.TargetTitle)
	}
	if b.CreatedAt != "2024-02-29T00:00:00Z" {
		t.Fatalf("CreatedAt 字段未正确赋值: %q", b.CreatedAt)
	}
}

func containsSub(s, sub string) bool {
	return len(sub) == 0 || indexOf(s, sub) >= 0
}

func indexOf(s, sub string) int {
	n := len(sub)
	if n == 0 {
		return 0
	}
	for i := 0; i+n <= len(s); i++ {
		if s[i:i+n] == sub {
			return i
		}
	}
	return -1
}
