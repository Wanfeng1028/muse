package store

import (
	"errors"
	"fmt"
)

// SetLinkPassword 设置指定短链的密码哈希。
// hash 为空字符串时返回错误。
func (s *Store) SetLinkPassword(id int64, hash string) error {
	if hash == "" {
		return errors.New("password hash 不能为空")
	}
	res, err := s.db.Exec(
		`UPDATE links SET password_hash = ?, updated_at = ? WHERE id = ?`,
		hash, formatTime(nowUTC()), id,
	)
	if err != nil {
		return fmt.Errorf("set link password: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// ClearLinkPassword 清除指定短链的密码哈希。
func (s *Store) ClearLinkPassword(id int64) error {
	res, err := s.db.Exec(
		`UPDATE links SET password_hash = NULL, updated_at = ? WHERE id = ?`,
		formatTime(nowUTC()), id,
	)
	if err != nil {
		return fmt.Errorf("clear link password: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}
