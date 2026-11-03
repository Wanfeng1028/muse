// internal/store/push_migrate.go
package store

import "database/sql"

// migratePushLogUser 幂等地将 push_log 表迁移到含 user_id 的多用户 schema。
//
// 迁移步骤：
// 1. 若 push_log 表缺少 user_id 列，添加之（默认 'local'）。
// 2. 删除旧的 (date, channel) 唯一索引，创建新的 (date, channel, user_id) 唯一索引。
//
// 新库（已由 createSchema 建好新 schema）调用本函数时不会做任何改动。
func migratePushLogUser(db *sql.DB) error {
	hasUserID, err := pushLogColumnInfo(db)
	if err != nil {
		return err
	}

	if !hasUserID {
		if _, err := db.Exec(
			`ALTER TABLE push_log ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'`,
		); err != nil {
			return err
		}
	}

	if _, err := db.Exec(`DROP INDEX IF EXISTS idx_push_log_date_channel`); err != nil {
		return err
	}
	if _, err := db.Exec(
		`CREATE UNIQUE INDEX IF NOT EXISTS idx_push_log_date_channel_user ON push_log(date, channel, user_id)`,
	); err != nil {
		return err
	}
	return nil
}

// pushLogColumnInfo 读取 PRAGMA table_info(push_log)，返回 user_id 列是否存在。
func pushLogColumnInfo(db *sql.DB) (hasUserID bool, err error) {
	rows, err := db.Query(`PRAGMA table_info(push_log)`)
	if err != nil {
		return false, err
	}
	defer rows.Close()

	for rows.Next() {
		var (
			cid     int
			name    string
			ctype   string
			notnull int
			dflt    sql.NullString
			pk      int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			return false, err
		}
		if name == "user_id" {
			hasUserID = true
		}
	}
	if err := rows.Err(); err != nil {
		return false, err
	}
	return hasUserID, nil
}
