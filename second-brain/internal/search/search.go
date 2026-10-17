// Package search 提供轻量的关键词分词与相关性打分，用于笔记检索排序。
package search

import (
	"math"
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

// cjkStopWords 中文单字停用字集合，仅在 ScoreDetailed/QueryTerms 中对单字符词元额外过滤。
var cjkStopWords = map[string]struct{}{
	"的": {}, "了": {}, "是": {}, "在": {}, "和": {}, "有": {}, "不": {},
	"我": {}, "你": {}, "他": {}, "她": {}, "它": {}, "这": {}, "那": {},
	"个": {}, "为": {}, "以": {}, "也": {}, "就": {}, "都": {}, "于": {},
	"而": {}, "及": {}, "或": {}, "之": {}, "其": {}, "所": {}, "把": {},
	"被": {}, "给": {}, "让": {}, "向": {}, "到": {}, "着": {}, "过": {},
	"很": {}, "太": {}, "更": {}, "最": {}, "非": {}, "即": {}, "若": {},
	"如": {}, "但": {}, "可": {}, "能": {}, "会": {},
}

// filterCJKStop 过滤掉单字符中文停用字，多字符词元保留。
func filterCJKStop(terms []string) []string {
	out := make([]string, 0, len(terms))
	for _, t := range terms {
		if len([]rune(t)) == 1 {
			if _, ok := cjkStopWords[t]; ok {
				continue
			}
		}
		out = append(out, t)
	}
	return out
}

// QueryTerms 返回过滤停用词/停用字后实际参与打分查询词，保持原顺序与去重。
func QueryTerms(query string) []string {
	return filterCJKStop(Tokenize(query))
}

// MatchField 命中字段类型。
type MatchField string

const (
	FieldTitle MatchField = "title"
	FieldTag   MatchField = "tag"
	FieldBody  MatchField = "body"
)

// Match 记录单个"查询词×命中字段"的明细。
type Match struct {
	Field MatchField `json:"field"`
	Term  string     `json:"term"`
}

// ScoreDetailed 返回分数与命中明细（可解释）。
func ScoreDetailed(title string, body string, tags []string, query string) (float64, []Match) {
	terms := QueryTerms(query)
	if len(terms) == 0 {
		return 0, nil
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

	// 标签：每个标签单独 Tokenize，命中按标签整体判断。
	tagTokenSets := make([][]string, 0, len(tags))
	for _, tag := range tags {
		tagTokenSets = append(tagTokenSets, Tokenize(tag))
	}
	tagFreq := make(map[string]int, len(tags))
	for _, tts := range tagTokenSets {
		seenInTag := make(map[string]struct{}, len(tts))
		for _, t := range tts {
			if _, ok := seenInTag[t]; ok {
				continue
			}
			seenInTag[t] = struct{}{}
			tagFreq[t]++
		}
	}

	// AND 语义：每个查询词必须在标题/标签/正文至少一处命中。
	for _, term := range terms {
		_, inTitle := titleFreq[term]
		_, inTag := tagFreq[term]
		_, inBody := bodyFreq[term]
		if !inTitle && !inTag && !inBody {
			return 0, nil
		}
	}

	var titleScore, tagScore, bodyScore float64
	matches := make([]Match, 0, len(terms)*3)
	seenMatch := make(map[string]struct{}, len(terms)*3)

	for _, term := range terms {
		if c := titleFreq[term]; c > 0 {
			titleScore += float64(c) * 3.0
			key := string(FieldTitle) + "\x00" + term
			if _, ok := seenMatch[key]; !ok {
				seenMatch[key] = struct{}{}
				matches = append(matches, Match{Field: FieldTitle, Term: term})
			}
		}
		if c := tagFreq[term]; c > 0 {
			tagScore += float64(c) * 2.0
			key := string(FieldTag) + "\x00" + term
			if _, ok := seenMatch[key]; !ok {
				seenMatch[key] = struct{}{}
				matches = append(matches, Match{Field: FieldTag, Term: term})
			}
		}
		if c := bodyFreq[term]; c > 0 {
			bodyScore += float64(c) * 1.0
			key := string(FieldBody) + "\x00" + term
			if _, ok := seenMatch[key]; !ok {
				seenMatch[key] = struct{}{}
				matches = append(matches, Match{Field: FieldBody, Term: term})
			}
		}
	}

	// 词组加成：相邻两 CJK 字组成的二元词组。
	queryRunes := []rune(strings.ToLower(query))
	var bigrams []string
	for i := 0; i+1 < len(queryRunes); i++ {
		a, b := queryRunes[i], queryRunes[i+1]
		if isCJK(a) && isCJK(b) {
			bigrams = append(bigrams, string(a)+string(b))
		}
	}
	titleLower := strings.ToLower(title)
	bodyLower := strings.ToLower(body)
	var phraseBonus float64
	seenBigram := make(map[string]struct{}, len(bigrams))
	for _, bg := range bigrams {
		if _, ok := seenBigram[bg]; ok {
			continue
		}
		seenBigram[bg] = struct{}{}
		hit := false
		if strings.Contains(titleLower, bg) {
			phraseBonus += 2.0
			hit = true
		}
		if !hit {
			for _, tag := range tags {
				if strings.Contains(strings.ToLower(tag), bg) {
					phraseBonus += 1.5
					hit = true
					break
				}
			}
		}
		if !hit && strings.Contains(bodyLower, bg) {
			phraseBonus += 1.0
		}
	}

	// 完全匹配加成。
	var exactBonus float64
	compactQuery := strings.ReplaceAll(strings.ToLower(query), " ", "")
	if len([]rune(compactQuery)) >= 2 {
		if strings.Contains(titleLower, compactQuery) {
			exactBonus += 5.0
		}
		for _, tag := range tags {
			if strings.EqualFold(strings.TrimSpace(tag), strings.TrimSpace(query)) {
				exactBonus += 4.0
				break
			}
		}
	}

	// 正文长度归一化。
	bodyRunes := len([]rune(body))
	normalizer := 1.0 + math.Log10(1.0+float64(bodyRunes)/200.0)
	if normalizer <= 0 {
		normalizer = 1.0
	}
	bodyScore = bodyScore / normalizer

	total := titleScore + tagScore + bodyScore + phraseBonus + exactBonus
	return total, matches
}

// RankedNote 带分数与命中明细的笔记。
type RankedNote struct {
	Note    store.Note
	Score   float64
	Matches []Match
}

// RankDetailed 按 ScoreDetailed 降序稳定排序，过滤 0 分。
func RankDetailed(notes []store.Note, query string) []RankedNote {
	items := make([]RankedNote, 0, len(notes))
	for _, n := range notes {
		s, m := ScoreDetailed(n.Title, n.Body, n.Tags, query)
		if s > 0 {
			items = append(items, RankedNote{Note: n, Score: s, Matches: m})
		}
	}
	sort.SliceStable(items, func(i, j int) bool {
		return items[i].Score > items[j].Score
	})
	return items
}

// orTokenScore 表示单个 token 在一条笔记上的 OR 命中情况。
type orTokenScore struct {
	token     string
	titleHit  bool
	score     float64
	matches   []Match
}

// orScore 对单条笔记按 OR 语义打分：对每个 token 单独调用 ScoreDetailed，
// 命中即计入（分数>0），并累加命中 token 数。标题命中额外加权。
func orScore(title, body string, tags []string, tokens []string) (float64, int, []Match) {
	var total float64
	var hitCount int
	var matches []Match
	for _, tok := range tokens {
		s, m := ScoreDetailed(title, body, tags, tok)
		if s <= 0 {
			continue
		}
		hitCount++
		total += s
		if strings.Contains(strings.ToLower(title), strings.ToLower(tok)) {
			total += 3.0
		}
		matches = append(matches, m...)
	}
	return total, hitCount, matches
}

// SearchWithFallback 先按 AND 语义搜索（Rank）；结果为空且 query 分词后 token 数>=2 时，
// 改用 OR 语义重搜（任一 token 命中即收），并按命中 token 数降序、标题命中加权排序。
func SearchWithFallback(notes []store.Note, query string, limit int) []RankedNote {
	tokens := Tokenize(query)
	if len(tokens) > 0 {
		// 严格 AND：每个 token 都必须出现
		var and []RankedNote
		for _, n := range notes {
			hay := strings.ToLower(n.Title + " " + n.Body + " " + strings.Join(n.Tags, " "))
			ok := true
			for _, tok := range tokens {
				if !strings.Contains(hay, strings.ToLower(tok)) {
					ok = false
					break
				}
			}
			if ok {
				s, m := ScoreDetailed(n.Title, n.Body, n.Tags, query)
				and = append(and, RankedNote{Note: n, Score: s, Matches: m})
			}
		}
		if len(and) > 0 {
			sort.SliceStable(and, func(i, j int) bool { return and[i].Score > and[j].Score })
			if limit > 0 && len(and) > limit {
				and = and[:limit]
			}
			return and
		}
	}
	if len(tokens) < 2 {
		return nil
	}
	items := make([]RankedNote, 0, len(notes))
	hitCounts := make(map[int]int, len(notes))
	for i, n := range notes {
		s, hits, m := orScore(n.Title, n.Body, n.Tags, tokens)
		if s <= 0 {
			continue
		}
		items = append(items, RankedNote{Note: n, Score: s, Matches: m})
		hitCounts[i] = hits
	}
	sort.SliceStable(items, func(i, j int) bool {
		if hitCounts[i] != hitCounts[j] {
			return hitCounts[i] > hitCounts[j]
		}
		return items[i].Score > items[j].Score
	})
	out := make([]RankedNote, 0, len(items))
	for _, it := range items {
		out = append(out, it)
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	return out
}

