package store

import "database/sql"

// migrateNotesClientNoteID 幂等地给 notes 表加 client_note_id 列与唯一索引。
func migrateNotesClientNoteID(db *sql.DB) error {
	// notes 表不存在时跳过（正常流程由 createSchema 建表；旧库升级测试的人工 schema 可能没有该表）。
	var tbl string
	if err := db.QueryRow(`SELECT name FROM sqlite_master WHERE type='table' AND name='notes'`).Scan(&tbl); err != nil {
		if err == sql.ErrNoRows {
			return nil
		}
		return err
	}
	rows, err := db.Query(`PRAGMA table_info(notes)`)
	if err != nil {
		return err
	}
	has := false
	for rows.Next() {
		var cid int
		var name string
		var ctype string
		var notnull int
		var dflt sql.NullString
		var pk int
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			rows.Close()
			return err
		}
		if name == "client_note_id" {
			has = true
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}
	if !has {
		if _, err := db.Exec(`ALTER TABLE notes ADD COLUMN client_note_id TEXT`); err != nil {
			return err
		}
	}
	// SQLite 唯一索引中多个 NULL 互不冲突，无需部分索引。
	if _, err := db.Exec(`CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_client_note_id ON notes(client_note_id)`); err != nil {
		return err
	}
	return nil
}
