package store

import "database/sql"

// migrateReviewsUser 幂等地将 reviews 表迁移到含 user_id 的多用户 schema。
//
// 迁移步骤：
//  1. 若 reviews 表缺少 user_id 列，添加之（默认 'local'）。
//  2. 若 reviews 表主键仍是 note_id 单列（user_id 的 pk 为 0），
//     则重建为 PRIMARY KEY (note_id, user_id)，老数据全部归属 'local'。
//
// 新库（已由 createSchema 建好新 schema）调用本函数时不会做任何改动。
func migrateReviewsUser(db *sql.DB) error {
	hasUserID, userPK, err := reviewsColumnInfo(db)
	if err != nil {
		return err
	}

	if !hasUserID {
		if _, err := db.Exec(
			`ALTER TABLE reviews ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'`,
		); err != nil {
			return err
		}
		// 重新读取 pk 信息：新加列的 pk 必然为 0，需要走重建流程。
		_, userPK, err = reviewsColumnInfo(db)
		if err != nil {
			return err
		}
	}

	if userPK != 0 {
		// 主键已包含 user_id，无需重建。
		return nil
	}

	if _, err := db.Exec(
		`CREATE TABLE reviews_new (
			note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
			user_id TEXT NOT NULL DEFAULT 'local',
			ef REAL NOT NULL DEFAULT 2.5,
			interval_days INTEGER NOT NULL DEFAULT 0,
			repetitions INTEGER NOT NULL DEFAULT 0,
			due_date TEXT NOT NULL,
			last_reviewed_at TEXT,
			reviewed_count INTEGER NOT NULL DEFAULT 0,
			PRIMARY KEY (note_id, user_id)
		)`,
	); err != nil {
		return err
	}
	if _, err := db.Exec(
		`INSERT INTO reviews_new (note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count)
		 SELECT note_id, 'local', ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count FROM reviews`,
	); err != nil {
		return err
	}
	if _, err := db.Exec(`DROP TABLE reviews`); err != nil {
		return err
	}
	if _, err := db.Exec(`ALTER TABLE reviews_new RENAME TO reviews`); err != nil {
		return err
	}
	return nil
}

// reviewsColumnInfo 读取 PRAGMA table_info(reviews)，
// 返回 user_id 列是否存在，以及该列在复合主键中的序号（0 表示不在主键中）。
func reviewsColumnInfo(db *sql.DB) (hasUserID bool, userPK int, err error) {
	rows, err := db.Query(`PRAGMA table_info(reviews)`)
	if err != nil {
		return false, 0, err
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
			return false, 0, err
		}
		if name == "user_id" {
			hasUserID = true
			userPK = pk
		}
	}
	if err := rows.Err(); err != nil {
		return false, 0, err
	}
	return hasUserID, userPK, nil
}
