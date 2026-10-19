package store

import "database/sql"

// nullIfEmpty 空字符串转 NULL：无幂等键的笔记在 client_note_id 列存 NULL，
// 多个 NULL 在唯一索引中互不冲突，保持老行为。
func nullIfEmpty(s string) any {
	if s == "" {
		return sql.NullString{}
	}
	return s
}
