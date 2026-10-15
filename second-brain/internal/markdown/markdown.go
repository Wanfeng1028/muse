// Package markdown 提供 Markdown 子集到安全 HTML 的渲染。
package markdown

import (
	"fmt"
	"html"
	"regexp"
	"strings"
)

// fence 表示 Markdown 代码围栏（三个反引号）。
var fence = strings.Repeat("`", 3)

var (
	reHeading    = regexp.MustCompile(`^(#{1,6})\s+(.*)$`)
	reULItem     = regexp.MustCompile(`^[-*+]\s+(.*)$`)
	reOLItem     = regexp.MustCompile(`^\d+\.\s+(.*)$`)
	reBlockquote = regexp.MustCompile(`^>\s?(.*)$`)
	reHR         = regexp.MustCompile(`^(-{3,}|\*{3,}|_{3,})\s*$`)
	reLink       = regexp.MustCompile(`\[([^\]]+)\]\(([^)\s]+)\)`)
	reWiki       = regexp.MustCompile(`\[\[([^\]]+)\]\]`)
	reBold       = regexp.MustCompile(`\*\*([^*]+)\*\*`)
	reItalic     = regexp.MustCompile(`\*([^*]+)\*`)
	reCodeSpan   = regexp.MustCompile("`([^`]+)`")
	reAttachImg  = regexp.MustCompile(`!\[([^\]]*)\]\(attachment:(\d+)\)`)
	reAttachLink = regexp.MustCompile(`\[([^\]]+)\]\(attachment:(\d+)\)`)
)

// Render 将 Markdown 子集渲染为安全 HTML。
func Render(src string) string {
	src = strings.ReplaceAll(src, "\r\n", "\n")
	src = strings.ReplaceAll(src, "\r", "\n")
	lines := strings.Split(src, "\n")

	var out strings.Builder
	i := 0
	for i < len(lines) {
		line := lines[i]

		// 代码块围栏
		if strings.HasPrefix(strings.TrimSpace(line), fence) {
			i++
			var code strings.Builder
			for i < len(lines) && !strings.HasPrefix(strings.TrimSpace(lines[i]), fence) {
				if code.Len() > 0 {
					code.WriteString("\n")
				}
				code.WriteString(lines[i])
				i++
			}
			if i < len(lines) {
				i++ // 跳过结束围栏
			}
			out.WriteString("<pre><code>")
			out.WriteString(html.EscapeString(code.String()))
			out.WriteString("</code></pre>\n")
			continue
		}

		trimmed := strings.TrimSpace(line)

		// 空行
		if trimmed == "" {
			i++
			continue
		}

		// 分隔线
		if reHR.MatchString(trimmed) {
			out.WriteString("<hr>\n")
			i++
			continue
		}

		// 标题
		if m := reHeading.FindStringSubmatch(trimmed); m != nil {
			level := len(m[1])
			out.WriteString(fmt.Sprintf("<h%d>%s</h%d>\n", level, renderInline(m[2]), level))
			i++
			continue
		}

		// 无序列表
		if reULItem.MatchString(trimmed) {
			out.WriteString("<ul>\n")
			for i < len(lines) {
				m := reULItem.FindStringSubmatch(strings.TrimSpace(lines[i]))
				if m == nil {
					break
				}
				out.WriteString("<li>" + renderInline(m[1]) + "</li>\n")
				i++
			}
			out.WriteString("</ul>\n")
			continue
		}

		// 有序列表
		if reOLItem.MatchString(trimmed) {
			out.WriteString("<ol>\n")
			for i < len(lines) {
				m := reOLItem.FindStringSubmatch(strings.TrimSpace(lines[i]))
				if m == nil {
					break
				}
				out.WriteString("<li>" + renderInline(m[1]) + "</li>\n")
				i++
			}
			out.WriteString("</ol>\n")
			continue
		}

		// 引用
		if reBlockquote.MatchString(trimmed) {
			var parts []string
			for i < len(lines) {
				m := reBlockquote.FindStringSubmatch(strings.TrimSpace(lines[i]))
				if m == nil {
					break
				}
				parts = append(parts, m[1])
				i++
			}
			out.WriteString("<blockquote>" + renderInline(strings.Join(parts, " ")) + "</blockquote>\n")
			continue
		}

		// 段落：聚合连续普通行
		var para []string
		for i < len(lines) {
			t := strings.TrimSpace(lines[i])
			if t == "" || reHR.MatchString(t) ||
				reHeading.MatchString(t) ||
				reULItem.MatchString(t) ||
				reOLItem.MatchString(t) ||
				reBlockquote.MatchString(t) ||
				strings.HasPrefix(t, fence) {
				break
			}
			para = append(para, t)
			i++
		}
		if len(para) > 0 {
			out.WriteString("<p>" + renderInline(strings.Join(para, " ")) + "</p>\n")
		}
	}

	return out.String()
}

// renderInline 处理行内元素。先转义，再替换标记。
func renderInline(s string) string {
	// 保护行内代码，避免其中的标记被处理。
	var codes []string
	s = reCodeSpan.ReplaceAllStringFunc(s, func(m string) string {
		inner := m[1 : len(m)-1]
		codes = append(codes, "<code>"+html.EscapeString(inner)+"</code>")
		return "\x00CODE" + fmt.Sprint(len(codes)-1) + "\x00"
	})

	// 转义其余内容
	s = html.EscapeString(s)

	// 附件引用：必须在普通链接之前处理，因为 reLink 也会匹配 attachment: 形式。
	// ![alt](attachment:123) 渲染为内联图片
	s = reAttachImg.ReplaceAllStringFunc(s, func(m string) string {
		g := reAttachImg.FindStringSubmatch(m)
		if g == nil {
			return m
		}
		return `<img src="/api/attachments/` + g[2] + `" alt="` + g[1] + `" loading="lazy" class="attachment-image">`
	})
	// [label](attachment:123) 渲染为下载链接
	s = reAttachLink.ReplaceAllStringFunc(s, func(m string) string {
		g := reAttachLink.FindStringSubmatch(m)
		if g == nil {
			return m
		}
		return `<a href="/api/attachments/` + g[2] + `">` + g[1] + `</a>`
	})

	// 链接 [文本](url) 仅 http/https
	s = reLink.ReplaceAllStringFunc(s, func(m string) string {
		g := reLink.FindStringSubmatch(m)
		if g == nil {
			return m
		}
		text := g[1]
		url := g[2]
		if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") {
			return m
		}
		return `<a href="` + url + `" rel="noopener noreferrer">` + text + `</a>`
	})

	// 双链 [[标题]]
	s = reWiki.ReplaceAllStringFunc(s, func(m string) string {
		g := reWiki.FindStringSubmatch(m)
		if g == nil {
			return m
		}
		title := g[1]
		return `<a href="#" data-wiki="` + title + `">` + title + `</a>`
	})

	// 粗体
	s = reBold.ReplaceAllString(s, "<strong>$1</strong>")
	// 斜体
	s = reItalic.ReplaceAllString(s, "<em>$1</em>")

	// 还原行内代码
	for idx, code := range codes {
		s = strings.ReplaceAll(s, "\x00CODE"+fmt.Sprint(idx)+"\x00", code)
	}

	return s
}
