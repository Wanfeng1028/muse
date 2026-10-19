package pgsource

import (
	"strings"
	"testing"
)

// slitEq 断言 got 与 want 完全相等，并额外断言长度恒等。
func slitEq(t *testing.T, name, in, got, want string) {
	t.Helper()
	if len(got) != len(in) {
		t.Fatalf("%s: 长度不守恒 len(in)=%d len(got)=%d (in=%q got=%q)", name, len(in), len(got), in, got)
	}
	if got != want {
		t.Fatalf("%s: 输出不匹配\n in   =%q\n got  =%q\n want =%q", name, in, got, want)
	}
}

// slitCase 表驱动用例结构。
type slitCase struct {
	name string
	in   string
	want string
}

// TestSlitSingleQuote 覆盖 A. 单引号字面量。
func TestSlitSingleQuote(t *testing.T) {
	slitCases := []slitCase{
		{
			name: "普通单引号串",
			in:   "select 'abc'",
			want: "select      ",
		},
		{
			name: "双单引号转义",
			in:   "select 'a''b'",
			want: "select       ",
		},
		{
			name: "空串",
			in:   "''",
			want: "  ",
		},
		{
			name: "未闭合单引号",
			in:   "select 'abc",
			want: "select     ",
		},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}

// TestSlitDoubleQuote 覆盖 B. 双引号引用标识符。
func TestSlitDoubleQuote(t *testing.T) {
	slitCases := []slitCase{
		{
			name: "普通引用标识符",
			in:   `select "col" from t`,
			want: `select       from t`,
		},
		{
			name: "双引号转义",
			in:   `select "a""b" from t`,
			want: `select        from t`,
		},
		{
			name: "未闭合双引号",
			in:   `select "col`,
			want: `select     `,
		},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}

// TestSlitDollarQuote 覆盖 C. dollar-quoted。
func TestSlitDollarQuote(t *testing.T) {
	slitCases := []slitCase{
		{
			name: "空 tag",
			in:   "select $$hello$$ from t",
			want: "select           from t",
		},
		{
			name: "自定义 tag",
			in:   "select $body$hi$body$ from t",
			want: "select                from t",
		},
		{
			name: "未闭合 dollar quote",
			in:   "select $$hello from t",
			want: "select               ",
		},
		{
			name: "tag 含数字下划线",
			in:   "select $t1_x$z$t1_x$ from t",
			want: "select               from t",
		},
		{
			name: "纯数字 tag",
			in:   "select $1$z$1$ from t",
			want: "select         from t",
		},
		{
			name: "dollar 后跟空格按普通字符",
			in:   "select $ x",
			want: "select $ x",
		},
		{
			name: "dollar 后跟左括号按普通字符",
			in:   "select $(",
			want: "select $(",
		},
		{
			name: "tag 嵌在其它文本中",
			in:   "$body$x$body$y$body$",
			want: "             y      ",
		},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}

// TestSlitLineComment 覆盖 D. 行注释。
func TestSlitLineComment(t *testing.T) {
	slitCases := []slitCase{
		{
			name: "行注释到末尾",
			in:   "select 1 -- comment",
			want: "select 1           ",
		},
		{
			name: "行注释到换行换行保留",
			in:   "select 1 -- c\nselect 2",
			want: "select 1     \nselect 2",
		},
		{
			name: "单个减号不是注释",
			in:   "select 1-2",
			want: "select 1-2",
		},
		{
			name: "注释标记在单引号串内",
			in:   "select '--x'",
			want: "select      ",
		},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}

// TestSlitBlockComment 覆盖 E. 块注释。
func TestSlitBlockComment(t *testing.T) {
	slitCases := []slitCase{
		{
			name: "普通块注释",
			in:   "select /* c */ 1",
			want: "select         1",
		},
		{
			name: "块注释不支持嵌套",
			in:   "select /* a /* b */ 1",
			want: "select              1",
		},
		{
			name: "跨行块注释",
			in:   "select /* a\nb */ 1",
			want: "select           1",
		},
		{
			name: "未闭合块注释",
			in:   "select /* abc",
			want: "select       ",
		},
		{
			name: "单个斜杠不是注释",
			in:   "select 1/2",
			want: "select 1/2",
		},
		{
			name: "单个星号不是注释",
			in:   "select 1*2",
			want: "select 1*2",
		},
		{
			name: "空块注释",
			in:   "/**/",
			want: "    ",
		},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}

// TestSlitLengthInvariant 覆盖 F. 位置对齐与长度恒等。
func TestSlitLengthInvariant(t *testing.T) {
	slitCases := []slitCase{
		{"单引号", "select 'abc'", "select      "},
		{"双引号", `select "col"`, "select      "},
		{"dollar", "select $$x$$", "select      "},
		{"行注释", "select -- x", "select     "},
		{"块注释", "select /* x */", "select        "},
		{"混合", "select 'a', \"b\", $$c$$ -- d\nfrom t", "select    ,    ,           \nfrom t"},
		{"无特殊字符", "select * from t where a = 1", "select * from t where a = 1"},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}

// TestSlitWordBoundary 覆盖 F.2/F.3 词边界与字面量内关键字剥离。
func TestSlitWordBoundary(t *testing.T) {
	// select'abc'from -> "select" 保留，'abc' 变空格，"from" 保留且为完整词。
	in := "select'abc'from"
	got := stripLiteralsAndComments(in)
	want := "select     from"
	slitEq(t, "字面量紧贴标识符", in, got, want)

	// 剥离后 from 必须是独立词：前后相邻字符应为空格或字符串边界。
	idx := strings.Index(got, "from")
	if idx < 0 {
		t.Fatalf("字面量紧贴标识符: 输出中未找到 from 词: %q", got)
	}
	if idx > 0 {
		prev := got[idx-1]
		if prev != ' ' {
			t.Fatalf("字面量紧贴标识符: from 前一个字符 %q 不是空格，词边界断裂: %q", prev, got)
		}
	}
	if idx+len("from") < len(got) {
		next := got[idx+len("from")]
		if next != ' ' {
			t.Fatalf("字面量紧贴标识符: from 后一个字符 %q 不是空格，词边界断裂: %q", next, got)
		}
	}

	// 关键字隐藏在字面量里，被整体剥离。
	in2 := "select 'insert' from t"
	got2 := stripLiteralsAndComments(in2)
	want2 := "select          from t"
	slitEq(t, "字面量内关键字剥离", in2, got2, want2)
	if strings.Contains(got2, "insert") {
		t.Fatalf("字面量内关键字剥离: 输出仍含 insert: %q", got2)
	}
}

// TestSlitBoundary 覆盖 G. 边界。
func TestSlitBoundary(t *testing.T) {
	slitCases := []slitCase{
		{"空输入", "", ""},
		{"纯行注释", "-- only comment", "               "},
		{"纯块注释", "/* x */", "       "},
		{"纯字面量", "'x'", "   "},
		{"纯空白", "   ", "   "},
	}
	for _, sc := range slitCases {
		got := stripLiteralsAndComments(sc.in)
		slitEq(t, sc.name, sc.in, got, sc.want)
	}
}
