// internal/store/push_user.go
package store

import (
	"database/sql"
	"time"
)

// ListUsersWithDueReviews 返回今天（含）之前有到期复习的去重用户列表，
// 按 user_id ASC 排序；无数据时返回空 slice（非 nil）。
func (s *Store) ListUsersWithDueReviews(today time.Time) ([]string, error) {
	date := today.Format("2006-01-02")
	rows, err := s.db.Query(
		`SELECT DISTINCT user_id FROM reviews WHERE due_date <= ? ORDER BY user_id ASC`,
		date,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []string{}
	for rows.Next() {
		var u string
		if err := rows.Scan(&u); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// HasPushedFor 判断指定日期、通道与用户是否已有成功推送记录。
// 查询出错时返回 false，由调用方打日志。
func (s *Store) HasPushedFor(date, channel, user string) bool {
	user = NormalizeUser(user)
	var n int
	err := s.db.QueryRow(
		`SELECT COUNT(1) FROM push_log WHERE date = ? AND channel = ? AND user_id = ? AND status = 'sent'`,
		date, channel, user,
	).Scan(&n)
	if err != nil {
		return false
	}
	return n > 0
}

// RecordPushFor 记录一次指定用户的推送结果，status 取值 "sent"/"failed"/"skipped"。
func (s *Store) RecordPushFor(date, channel, user, status, detail string) error {
	user = NormalizeUser(user)
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.db.Exec(
		`INSERT INTO push_log (date, channel, user_id, status, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(date, channel, user_id) DO UPDATE SET status = excluded.status, detail = excluded.detail, created_at = excluded.created_at`,
		date, channel, user, status, detail, now,
	)
	return err
}

// ListPushLogFor 按 id 倒序返回推送记录，limit<=0 时取 50，上限 200。
// user 为空时不过滤；否则按归一化后的 user_id 过滤。
func (s *Store) ListPushLogFor(limit int, user string) ([]PushRecord, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}

	var (
		rows *sql.Rows
		err  error
	)
	if user == "" {
		rows, err = s.db.Query(
			`SELECT id, date, channel, user_id, status, detail, created_at FROM push_log ORDER BY id DESC LIMIT ?`,
			limit,
		)
	} else {
		rows, err = s.db.Query(
			`SELECT id, date, channel, user_id, status, detail, created_at FROM push_log WHERE user_id = ? ORDER BY id DESC LIMIT ?`,
			NormalizeUser(user), limit,
		)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []PushRecord
	for rows.Next() {
		var rec PushRecord
		var detail sql.NullString
		if err := rows.Scan(&rec.ID, &rec.Date, &rec.Channel, &rec.User, &rec.Status, &detail, &rec.CreatedAt); err != nil {
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
