// Package search 提供轻量的关键词分词与相关性打分，用于笔记检索排序。
package search

import (
	"sort"
	"strings"
	"unicode"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// stopWords 英文停用词集合（少量），分词时予以剔除。
var stopWords = map[string]struct{}{
	"a": {}, "an": {}, "and": {}, "are": {}, "as": {}, "at": {},
	"be": {}, "by": {}, "for": {}, "from": {}, "has": {}, "he": {},
	"in": {}, "is": {}, "it": {}, "its": {}, "of": {}, "on": {},
	"that": {}, "the": {}, "to": {}, "was": {}, "were": {}, "will": {},
	"with": {}, "this": {}, "these": {}, "those": {}, "or": {}, "not": {},
}

// isCJK 判断是否为 CJK 表意文字（含扩展区粗略判断），逐字切分用。
func isCJK(r rune) bool {
	return unicode.Is(unicode.Han, r) ||
		(r >= 0x3040 && r <= 0x30FF) || // 日文假名
		(r >= 0xAC00 && r <= 0xD7A3) // 韩文
}

// Tokenize 将输入字符串转为归一化的词元列表：
// 小写、按非字母数字与 CJK 逐字切分、去停用词、去重保序。
func Tokenize(s string) []string {
	s = strings.ToLower(s)
	var tokens []string
	var buf strings.Builder

	flush := func() {
		if buf.Len() > 0 {
			tokens = append(tokens, buf.String())
			buf.Reset()
		}
	}

	for _, r := range s {
		switch {
		case isCJK(r):
			// CJK 逐字切分
			flush()
			tokens = append(tokens, string(r))
		case unicode.IsLetter(r) || unicode.IsDigit(r):
			buf.WriteRune(r)
		default:
			flush()
		}
	}
	flush()

	// 去停用词 + 去重保序
	seen := make(map[string]struct{}, len(tokens))
	result := make([]string, 0, len(tokens))
	for _, t := range tokens {
		if t == "" {
			continue
		}
		if _, ok := stopWords[t]; ok {
			continue
		}
		if _, ok := seen[t]; ok {
			continue
		}
		seen[t] = struct{}{}
		result = append(result, t)
	}
	return result
}

// Score 计算笔记相对于查询的相关性分数：
// 标题命中权重 3、正文命中权重 1，使用简化的词频计数累加。
func Score(title, body, query string) float64 {
	terms := Tokenize(query)
	if len(terms) == 0 {
		return 0
	}

	titleTokens := Tokenize(title)
	bodyTokens := Tokenize(body)

	titleFreq := make(map[string]int, len(titleTokens))
	for _, t := range titleTokens {
		titleFreq[t]++
	}
	bodyFreq := make(map[string]int, len(bodyTokens))
	for _, t := range bodyTokens {
		bodyFreq[t]++
	}

	var score float64
	for _, term := range terms {
		if c := titleFreq[term]; c > 0 {
			score += float64(c) * 3.0
		}
		if c := bodyFreq[term]; c > 0 {
			score += float64(c) * 1.0
		}
	}
	return score
}

// Rank 按相关性对笔记降序排序，过滤掉分数为 0 的笔记。
func Rank(notes []store.Note, query string) []store.Note {
	type scored struct {
		note  store.Note
		score float64
	}

	items := make([]scored, 0, len(notes))
	for _, n := range notes {
		s := Score(n.Title, n.Body, query)
		if s > 0 {
			items = append(items, scored{note: n, score: s})
		}
	}

	sort.SliceStable(items, func(i, j int) bool {
		return items[i].score > items[j].score
	})

	result := make([]store.Note, 0, len(items))
	for _, it := range items {
		result = append(result, it.note)
	}
	return result
}
