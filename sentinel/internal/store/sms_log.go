package store

import (
	"strings"
	"time"
)

// SMSLog 短信发送记录。
type SMSLog struct {
	ID        int64  `json:"id"`
	Phone     string `json:"phone"`
	Message   string `json:"message"`
	Provider  string `json:"provider"`
	Status    string `json:"status"`
	Error     string `json:"error"`
	CreatedAt string `json:"created_at"`
}

// RecordSMSLog 记录一条短信发送记录。
func (s *Store) RecordSMSLog(phone, message, provider, status, errMsg string) error {
	_, err := s.db.Exec(
		`INSERT INTO sms_log (phone, message, provider, status, error, created_at)
		 VALUES (?,?,?,?,?,?)`,
		phone, message, provider, status, errMsg,
		time.Now().UTC().Format(time.RFC3339),
	)
	return err
}

// ListSMSLog 按条件分页查询短信记录（id 倒序），返回记录列表与总数。
func (s *Store) ListSMSLog(phone, status string, limit, offset int) ([]SMSLog, int, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	if offset < 0 {
		offset = 0
	}

	var conds []string
	var args []any
	if phone != "" {
		conds = append(conds, "phone = ?")
		args = append(args, phone)
	}
	if status != "" {
		conds = append(conds, "status = ?")
		args = append(args, status)
	}
	where := ""
	if len(conds) > 0 {
		where = "WHERE " + strings.Join(conds, " AND ")
	}

	var total int
	countQ := "SELECT COUNT(*) FROM sms_log " + where
	if err := s.db.QueryRow(countQ, args...).Scan(&total); err != nil {
		return nil, 0, err
	}

	q := `SELECT id, phone, message, provider, status, error, created_at
	      FROM sms_log ` + where + ` ORDER BY id DESC LIMIT ? OFFSET ?`
	args = append(args, limit, offset)
	rows, err := s.db.Query(q, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var out []SMSLog
	for rows.Next() {
		var e SMSLog
		if err := rows.Scan(&e.ID, &e.Phone, &e.Message, &e.Provider, &e.Status, &e.Error, &e.CreatedAt); err != nil {
			return nil, 0, err
		}
		out = append(out, e)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	if out == nil {
		out = []SMSLog{}
	}
	return out, total, nil
}
