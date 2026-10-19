// guard.go 提供只读 SQL 白名单校验。
package pgsource

import (
	"errors"
	"regexp"
	"strings"
)

var readOnlyPattern = regexp.MustCompile(`(?is)^\s*(select|with)\b`)

// dangerousFuncPattern 匹配危险函数调用：单词 + 可选空白 + '('。
// 在剥离字面量/注释后的文本上匹配，大小写不敏感。
var dangerousFuncPattern = regexp.MustCompile(`(?is)\b(pg_sleep|pg_terminate_backend|pg_cancel_backend|dblink_exec|dblink_connect)\s*\(`)

// writeKeywordPattern 匹配独立写操作关键字。
var writeKeywordPattern = regexp.MustCompile(`(?is)\b(insert|update|delete|merge)\b`)

// intoKeywordPattern 匹配独立 INTO 关键字（SELECT INTO 建表）。
var intoKeywordPattern = regexp.MustCompile(`(?is)\binto\b`)

// stripLiteralsAndComments 从左到右扫描 SQL，把字符串字面量、引用标识符、
// dollar-quoted 串、行注释、块注释全部替换为空格（保持词边界不断裂）。
// 处理：单引号串（” 转义）、双引号标识符（"" 转义）、dollar-quoted
// （$$...$$ 与 $tag$...$tag$，tag 为字母数字下划线）、行注释（-- 到换行）、
// 块注释（/*...*/，不支持嵌套，遇 */ 即结束）。
func stripLiteralsAndComments(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	i := 0
	n := len(s)
	for i < n {
		c := s[i]
		switch {
		case c == '\'':
			// 单引号字符串，'' 为转义。
			b.WriteByte(' ')
			i++
			for i < n {
				if s[i] == '\'' {
					if i+1 < n && s[i+1] == '\'' {
						b.WriteByte(' ')
						b.WriteByte(' ')
						i += 2
						continue
					}
					b.WriteByte(' ')
					i++
					break
				}
				b.WriteByte(' ')
				i++
			}
		case c == '"':
			// 双引号标识符，"" 为转义。
			b.WriteByte(' ')
			i++
			for i < n {
				if s[i] == '"' {
					if i+1 < n && s[i+1] == '"' {
						b.WriteByte(' ')
						b.WriteByte(' ')
						i += 2
						continue
					}
					b.WriteByte(' ')
					i++
					break
				}
				b.WriteByte(' ')
				i++
			}
		case c == '-' && i+1 < n && s[i+1] == '-':
			// 行注释到换行（换行本身保留以维持行边界）。
			b.WriteByte(' ')
			b.WriteByte(' ')
			i += 2
			for i < n && s[i] != '\n' {
				b.WriteByte(' ')
				i++
			}
		case c == '/' && i+1 < n && s[i+1] == '*':
			// 块注释，不支持嵌套，遇 */ 即结束。
			b.WriteByte(' ')
			b.WriteByte(' ')
			i += 2
			for i < n {
				if s[i] == '*' && i+1 < n && s[i+1] == '/' {
					b.WriteByte(' ')
					b.WriteByte(' ')
					i += 2
					break
				}
				b.WriteByte(' ')
				i++
			}
		case c == '$':
			// dollar-quoted：$$...$$ 或 $tag$...$tag$，tag 为字母数字下划线。
			tagEnd := i + 1
			for tagEnd < n {
				ch := s[tagEnd]
				if ch == '$' {
					break
				}
				if (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
					(ch >= '0' && ch <= '9') || ch == '_' {
					tagEnd++
					continue
				}
				tagEnd = -1
				break
			}
			if tagEnd < 0 || tagEnd >= n || s[tagEnd] != '$' {
				// 不是合法的 dollar-quote 起始，按普通字符处理。
				b.WriteByte(c)
				i++
				continue
			}
			tag := s[i : tagEnd+1] // 含两端 $ 的完整 tag，如 "$$" 或 "$body$"
			// 找到下一个相同 tag。
			searchFrom := tagEnd + 1
			closeIdx := strings.Index(s[searchFrom:], tag)
			if closeIdx < 0 {
				// 未闭合，全部按字面量剥离。
				for j := i; j < n; j++ {
					b.WriteByte(' ')
				}
				i = n
				continue
			}
			end := searchFrom + closeIdx + len(tag)
			for j := i; j < end; j++ {
				b.WriteByte(' ')
			}
			i = end
		default:
			b.WriteByte(c)
			i++
		}
	}
	return b.String()
}

// AssertReadOnlySQL 校验 query 是否为允许的只读语句。
//
// 三层只读保障的第一层，做字面量/注释感知的词法扫描，零数据库往返即可
// 拒绝常见绕过（WITH 体内 DML、SELECT INTO、pg_sleep 类资源耗尽）。
//
// 分工与误伤面：
//   - 第二层 default_transaction_read_only=on 的只读事务本就能挡住 DML，
//     第三层只读账号权限做最终兜底；第一层的价值是零往返快速拒绝，
//     并额外挡住只读事务拦不住的资源耗尽调用（如 pg_sleep）。
//   - 字符串/注释里的关键字不误杀（先剥离再匹配）。
//   - 误伤面：裸列名/标识符恰好叫 update、into 等关键字的病态查询会被误拒
//     （见设计文档第 4 节声明）。带引号的 "update" 不会被误拒。
func AssertReadOnlySQL(query string) error {
	stripped := stripLiteralsAndComments(query)
	trimmed := strings.TrimSpace(stripped)
	if !readOnlyPattern.MatchString(trimmed) {
		return errors.New("只读校验失败：SQL 必须以 SELECT 或 WITH 开头")
	}
	if strings.Contains(stripped, ";") {
		return errors.New("只读校验失败：SQL 中不允许包含分号，禁止多语句")
	}
	if writeKeywordPattern.MatchString(stripped) {
		return errors.New("只读校验失败：不允许 INSERT/UPDATE/DELETE/MERGE 写操作")
	}
	if intoKeywordPattern.MatchString(stripped) {
		return errors.New("只读校验失败：不允许 SELECT INTO 建表")
	}
	if m := dangerousFuncPattern.FindStringSubmatch(stripped); m != nil {
		return errors.New("只读校验失败：不允许调用危险函数 " + strings.ToLower(m[1]))
	}
	return nil
}
