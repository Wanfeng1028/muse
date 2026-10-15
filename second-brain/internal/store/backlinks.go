package store

import (
	"strings"
)

// Backlink 一条反向链接：哪篇笔记引用了目标笔记。
type Backlink struct {
	ID          int64  `json:"id"`          // 引用者笔记 id
	Title       string `json:"title"`       // 引用者标题
	TargetTitle string `json:"targetTitle"` // 当时写的 [[...]] 里原文（大小写可能与目标标题不同）
	Snippet     string `json:"snippet"`     // 引用者正文里链接出现处的上下文
	CreatedAt   string `json:"createdAt"`   // 引用者创建时间
}

const snippetContextRunes = 40
const snippetFallbackRunes = 120

// Backlinks 返回所有引用了 noteID 的笔记（links.target_id = noteID），按引用者 id 倒序（新的在前）。
// 目标笔记不存在时不报错，返回空切片（存在性由 API 层校验）。
// 返回的切片永不为 nil。
func (s *Store) Backlinks(noteID int64) ([]Backlink, error) {
	rows, err := s.db.Query(
		`SELECT l.target_title, n.id, n.title, n.body, n.created_at
FROM links l JOIN notes n ON n.id = l.source_id
WHERE l.target_id = ?
ORDER BY n.id DESC`,
		noteID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := make([]Backlink, 0)
	for rows.Next() {
		var (
			targetTitle string
			id          int64
			title       string
			body        string
			createdAt   string
		)
		if err := rows.Scan(&targetTitle, &id, &title, &body, &createdAt); err != nil {
			return nil, err
		}
		result = append(result, Backlink{
			ID:          id,
			Title:       title,
			TargetTitle: targetTitle,
			Snippet:     buildSnippet(body, targetTitle),
			CreatedAt:   createdAt,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return result, nil
}

// buildSnippet 在 body 中定位第一处 [[targetTitle]] 字面出现，返回该行的上下文片段。
// 按 rune 切分，避免破坏 UTF-8。找不到时回退到 body 前 snippetFallbackRunes 个 rune。
func buildSnippet(body, targetTitle string) string {
	needle := "[[" + targetTitle + "]]"
	idx := strings.Index(body, needle)
	if idx < 0 {
		return headRunes(body, snippetFallbackRunes)
	}

	// 计算匹配所在的整行范围（以字节索引表示，但只用于定位换行边界）。
	lineStart := strings.LastIndexByte(body[:idx], '\n') + 1
	lineEnd := len(body)
	if nl := strings.IndexByte(body[idx:], '\n'); nl >= 0 {
		lineEnd = idx + nl
	}

	line := body[lineStart:lineEnd]
	// 匹配点在行内的相对字节偏移。
	rel := idx - lineStart

	// 转成 rune 切片，按 rune 切分前后文。
	// 计算匹配点之前的 rune 数。
	beforeRunes := []rune(line[:rel])
	matchRunes := []rune(needle)
	afterStartByte := rel + len(needle)
	if afterStartByte > len(line) {
		afterStartByte = len(line)
	}
	afterRunes := []rune(line[afterStartByte:])

	var b strings.Builder

	beforeLen := len(beforeRunes)
	if beforeLen > snippetContextRunes {
		b.WriteString("…")
		b.WriteString(string(beforeRunes[beforeLen-snippetContextRunes:]))
	} else {
		b.WriteString(string(beforeRunes))
	}

	b.WriteString(string(matchRunes))

	afterLen := len(afterRunes)
	if afterLen > snippetContextRunes {
		b.WriteString(string(afterRunes[:snippetContextRunes]))
		b.WriteString("…")
	} else {
		b.WriteString(string(afterRunes))
	}

	return b.String()
}

// headRunes 返回 s 的前 n 个 rune（不足则原样返回）。
func headRunes(s string, n int) string {
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n])
}
