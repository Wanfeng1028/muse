package store

import (
	"database/sql"
)

// reviewsHasIsHardColumn 检查 reviews 表是否已有 is_hard 列。
func reviewsHasIsHardColumn(db *sql.DB) (bool, error) {
	rows, err := db.Query(`PRAGMA table_info(reviews)`)
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
		if name == "is_hard" {
			return true, nil
		}
	}
	if err := rows.Err(); err != nil {
		return false, err
	}
	return false, nil
}

// migrateReviewsIsHard 为 reviews 表添加 is_hard 列（幂等）。
func migrateReviewsIsHard(db *sql.DB) error {
	has, err := reviewsHasIsHardColumn(db)
	if err != nil {
		return err
	}
	if has {
		return nil
	}
	_, err = db.Exec(`ALTER TABLE reviews ADD COLUMN is_hard INTEGER NOT NULL DEFAULT 0`)
	return err
}
