// internal/store/push.go
package store

import (
	"database/sql"
	"time"
)

// PushRecord 表示一条推送记录。
type PushRecord struct {
	ID        int64  `json:"id"`
	Date      string `json:"date"`
	Channel   string `json:"channel"`
	Status    string `json:"status"`
	Detail    string `json:"detail"`
	CreatedAt string `json:"createdAt"`
}

// GetPushSetting 读取一个推送设置项，第二个返回值表示是否存在。
func (s *Store) GetPushSetting(key string) (string, bool) {
	var value string
	err := s.db.QueryRow(`SELECT value FROM push_settings WHERE key = ?`, key).Scan(&value)
	if err != nil {
		return "", false
	}
	return value, true
}

// SetPushSetting 写入或更新一个推送设置项。
func (s *Store) SetPushSetting(key, value string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.db.Exec(
		`INSERT INTO push_settings (key, value, updated_at) VALUES (?, ?, ?)
		 ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
		key, value, now,
	)
	return err
}

// HasPushed 判断指定日期与通道是否已有成功推送记录。
// 查询出错时返回 false，由调用方打日志。
func (s *Store) HasPushed(date, channel string) bool {
	var n int
	err := s.db.QueryRow(
		`SELECT COUNT(1) FROM push_log WHERE date = ? AND channel = ? AND status = 'sent'`,
		date, channel,
	).Scan(&n)
	if err != nil {
		return false
	}
	return n > 0
}

// RecordPush 记录一次推送结果，status 取值 "sent"/"failed"/"skipped"。
func (s *Store) RecordPush(date, channel, status, detail string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.db.Exec(
		`INSERT INTO push_log (date, channel, status, detail, created_at) VALUES (?, ?, ?, ?, ?)
		 ON CONFLICT(date, channel) DO UPDATE SET status = excluded.status, detail = excluded.detail, created_at = excluded.created_at`,
		date, channel, status, detail, now,
	)
	return err
}

// ListPushLog 按 id 倒序返回推送记录，limit<=0 时取 50，上限 200。
func (s *Store) ListPushLog(limit int) ([]PushRecord, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}
	rows, err := s.db.Query(
		`SELECT id, date, channel, status, detail, created_at FROM push_log ORDER BY id DESC LIMIT ?`,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []PushRecord
	for rows.Next() {
		var rec PushRecord
		var detail sql.NullString
		if err := rows.Scan(&rec.ID, &rec.Date, &rec.Channel, &rec.Status, &detail, &rec.CreatedAt); err != nil {
			return nil, err
		}
		if detail.Valid {
			rec.Detail = detail.String
		}
		out = append(out, rec)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
