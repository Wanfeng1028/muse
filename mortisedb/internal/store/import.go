package store

import (
	"database/sql"
	"time"
)

// RecordImport 记录一次成功导入的幂等键与统计。
func (s *Store) RecordImport(source, fileHash, filename string, total, inserted, updated, errRows int) error {
	_, err := s.DB.Exec(
		`INSERT INTO "_m_imports" ("source","file_hash","filename","rows_total","inserted","updated","error_rows","created_at")
		 VALUES (?,?,?,?,?,?,?,?)`,
		source, fileHash, filename, total, inserted, updated, errRows, time.Now().UTC().Format(time.RFC3339),
	)
	return err
}

// FindImport 查询同 source+file_hash 的上次成功导入统计。
func (s *Store) FindImport(source, fileHash string) (bool, map[string]any, error) {
	row := s.DB.QueryRow(
		`SELECT "filename","rows_total","inserted","updated","error_rows","created_at"
		 FROM "_m_imports" WHERE "source" = ? AND "file_hash" = ?`,
		source, fileHash,
	)
	var (
		filename  string
		total     int
		inserted  int
		updated   int
		errRows   int
		createdAt string
	)
	if err := row.Scan(&filename, &total, &inserted, &updated, &errRows, &createdAt); err != nil {
		if err == sql.ErrNoRows {
			return false, nil, nil
		}
		return false, nil, err
	}
	summary := map[string]any{
		"filename":   filename,
		"rows_total": total,
		"inserted":   inserted,
		"updated":    updated,
		"error_rows": errRows,
		"created_at": createdAt,
	}
	return true, summary, nil
}
