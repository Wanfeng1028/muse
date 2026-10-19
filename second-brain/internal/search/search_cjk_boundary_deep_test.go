package search

import (
	"reflect"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// TestTokenizeCJKBoundary 检查分词边界相关的真实行为。
// 依据：cjkDict 词典里有 "量子" 也有 "计算"，窗口最长 4 字，未命中回退逐字，
// 所以 Tokenize("量子计算") 切出 ["量子","计算"]。
// CJK 缓冲和拉丁缓冲是分开攒的，遇到 CJK 先 flush 拉丁缓冲，遇到字母数字先 flush CJK 缓冲，
// 所以 "量子 computing" 是 ["量子","computing"]。
// Tokenize 只去英文停用词，不去中文单字停用字，所以 "the and" 被剔成空，而 "的" 原样留着。
// cjkStopWords 只在 QueryTerms 里过滤，所以 QueryTerms("的") 是空，QueryTerms("量子") 保留。
func TestTokenizeCJKBoundary(t *testing.T) {
	if got := Tokenize("量子计算"); !reflect.DeepEqual(got, []string{"量子", "计算"}) {
		t.Fatalf("Tokenize(量子计算) = %#v, 想要 [量子 计算]", got)
	}
	if got := Tokenize("量子 computing"); !reflect.DeepEqual(got, []string{"量子", "computing"}) {
		t.Fatalf("Tokenize(量子 computing) = %#v, 想要 [量子 computing]", got)
	}
	if got := Tokenize("the and"); !reflect.DeepEqual(got, []string{}) {
		t.Fatalf("Tokenize(the and) = %#v, 想要空切片", got)
	}
	if got := Tokenize("的"); !reflect.DeepEqual(got, []string{"的"}) {
		t.Fatalf("Tokenize(的) = %#v, 想要 [的]", got)
	}
	if got := QueryTerms("的"); !reflect.DeepEqual(got, []string{}) {
		t.Fatalf("QueryTerms(的) = %#v, 想要空切片", got)
	}
	if got := QueryTerms("量子"); !reflect.DeepEqual(got, []string{"量子"}) {
		t.Fatalf("QueryTerms(量子) = %#v, 想要 [量子]", got)
	}
}

// TestFallbackTriggeredByPartialMatch 检查 OR 回退会被部分命中触发。
// 依据：AND 门用的是原始子串包含判断 hay 里 strings.Contains(hay, tok)，
// 查 "量子计算" 分出的 token 是 ["量子","计算"]，两个都得是子串才算通过。
// 笔记 A 含 "量子" 但正文和标题里都没有 "计算"，AND 门失败；
// 笔记 B 两个都没有，AND 门也失败。AND 结果为空且 token 数为 2，走 OR 回退，
// 任一 token 命中即收，所以 A 被捞回来，B 还是进不来。
func TestFallbackTriggeredByPartialMatch(t *testing.T) {
	notes := []store.Note{
		{Title: "量子物理入门", Body: "介绍量子力学基础"},
		{Title: "深度学习笔记", Body: "神经网络入门"},
	}
	got := SearchWithFallback(notes, "量子计算", 0)
	if len(got) == 0 {
		t.Fatalf("结果为空，想要回退后至少捞回笔记 A")
	}
	var hasA, hasB bool
	for _, r := range got {
		switch r.Note.Title {
		case "量子物理入门":
			hasA = true
		case "深度学习笔记":
			hasB = true
		}
	}
	if !hasA {
		t.Fatalf("结果里没有笔记 A，回退没把 A 捞回来：%#v", got)
	}
	if hasB {
		t.Fatalf("结果里不该有笔记 B，它两个 token 都不含：%#v", got)
	}
}

// TestANDPrecedenceNoFallback 检查 AND 成功就不走回退。
// 依据：SearchWithFallback 先严格 AND，每个 token 都得在 hay 里作为子串出现。
// 笔记 B 同时含 "量子" 和 "计算"，AND 门通过；笔记 C 只含 "量子"，AND 门不通过。
// 只要 and 切片非空就直接排序返回，不会再走下面的 OR 回退，
// 所以 C 即使 OR 语义能命中也不会出现在结果里。
func TestANDPrecedenceNoFallback(t *testing.T) {
	notes := []store.Note{
		{Title: "量子计算导论", Body: "量子计算是未来方向"},
		{Title: "量子物理", Body: "只讲量子"},
	}
	got := SearchWithFallback(notes, "量子计算", 0)
	var hasB, hasC bool
	for _, r := range got {
		switch r.Note.Title {
		case "量子计算导论":
			hasB = true
		case "量子物理":
			hasC = true
		}
	}
	if !hasB {
		t.Fatalf("结果里没有笔记 B，AND 路径应该收到它：%#v", got)
	}
	if hasC {
		t.Fatalf("结果里不该有笔记 C，AND 成功就不走回退：%#v", got)
	}
}

// TestSingleCharQuery 检查单字非停用字查询的真实路径。
// 依据：查 "量" 分词后是 ["量"]，len 为 1 不满足回退条件 len(tokens) < 2 的取反，所以不走 OR。
// AND 门是子串判断，"量子力学" 里含 "量" 这个子串，通过。
// ScoreDetailed 里 QueryTerms("量") 是 ["量"]，因为 "量" 不在 cjkStopWords 里，
// cjkTermHitCount 对 CJK 词还会做包含匹配，所以能拿到正分。
func TestSingleCharQuery(t *testing.T) {
	notes := []store.Note{
		{Title: "量子力学", Body: "研究微观世界"},
	}
	got := SearchWithFallback(notes, "量", 0)
	if len(got) == 0 {
		t.Fatalf("结果为空，单字查询应该走 AND 门拿到结果")
	}
	if got[0].Score <= 0 {
		t.Fatalf("第一条 Score = %v, 想要 > 0", got[0].Score)
	}
}

// TestAllStopWordQuery 检查纯停用字查询的真实行为。
// 依据：查 "的" 分词是 ["的"]，len 为 1 不触发回退。
// AND 门是子串判断，正文里含 "的" 就通过，然后调 ScoreDetailed。
// ScoreDetailed 内部用 QueryTerms，而 QueryTerms 会用 cjkStopWords 滤掉单字停用字，
// QueryTerms("的") 为空，ScoreDetailed 返回 (0, nil)，
// 但 AND 分支不管分数是否为 0 都直接塞进结果，所以结果是非空的 0 分条目。
// 查 "the and" 分词为空，tokens 长度为 0，直接返回 nil，AND 和 OR 都不走。
func TestAllStopWordQuery(t *testing.T) {
	notes := []store.Note{
		{Title: "这是测试", Body: "的确如此"},
	}
	got := SearchWithFallback(notes, "的", 0)
	if len(got) == 0 {
		t.Fatalf("结果为空，真实行为是返回 0 分条目")
	}
	for i, r := range got {
		if r.Score != 0 {
			t.Fatalf("第 %d 条 Score = %v, 想要 0", i, r.Score)
		}
		if len(r.Matches) != 0 {
			t.Fatalf("第 %d 条 Matches = %#v, 想要空", i, r.Matches)
		}
	}
	if nilGot := SearchWithFallback(notes, "the and", 0); nilGot != nil {
		t.Fatalf("查 the and 结果 = %#v, 想要 nil", nilGot)
	}
}

// TestMixedCJKAsciiQuery 检查中英混合查询走 OR 回退。
// 依据："量子 computing" 分词是 ["量子","computing"]，AND 门要求两个子串都在 hay 里。
// 笔记只含 "量子"，缺 "computing"，AND 门失败。
// token 数为 2，满足回退条件，走 OR 语义，命中 "量子" 就收进来。
func TestMixedCJKAsciiQuery(t *testing.T) {
	notes := []store.Note{
		{Title: "量子科普", Body: "讲量子的文章"},
	}
	got := SearchWithFallback(notes, "量子 computing", 0)
	if len(got) == 0 {
		t.Fatalf("结果为空，中英混合部分命中应该触发 OR 回退")
	}
	var hasNote bool
	for _, r := range got {
		if r.Note.Title == "量子科普" {
			hasNote = true
		}
	}
	if !hasNote {
		t.Fatalf("结果里没有目标笔记：%#v", got)
	}
}

// TestFallbackOrderStable 检查回退路径同样输入两次调用顺序一致。
// 依据：回退排序里 hitCounts 的 key 是 notes 循环下标 i，
// 而比较函数里用的下标是结果切片 items 的下标，两者不对齐，
// 所以这里只断言两次调用顺序完全一致，不编造按命中数降序这种理想顺序。
func TestFallbackOrderStable(t *testing.T) {
	notes := []store.Note{
		{Title: "量子物理入门", Body: "介绍量子力学基础"},
		{Title: "深度学习笔记", Body: "神经网络入门"},
	}
	first := SearchWithFallback(notes, "量子计算", 0)
	second := SearchWithFallback(notes, "量子计算", 0)
	if len(first) != len(second) {
		t.Fatalf("两次调用长度不同：%d vs %d", len(first), len(second))
	}
	for i := range first {
		if first[i].Note.Title != second[i].Note.Title {
			t.Fatalf("第 %d 条两次顺序不同：%q vs %q", i, first[i].Note.Title, second[i].Note.Title)
		}
	}
}

// TestLimitTruncationAND 检查 AND 成功路径上的 limit 截断。
// 依据：and 分支里先按 Score 降序排序，然后 limit > 0 且长度超过 limit 就切到 limit。
// 两条笔记标题正文都含 "量子" 和 "计算"，AND 门都通过，limit=1 应该只返回 1 条。
func TestLimitTruncationAND(t *testing.T) {
	notes := []store.Note{
		{Title: "量子计算一", Body: "量子计算内容一"},
		{Title: "量子计算二", Body: "量子计算内容二"},
	}
	got := SearchWithFallback(notes, "量子计算", 1)
	if len(got) != 1 {
		t.Fatalf("结果长度 = %d, 想要 1", len(got))
	}
}
