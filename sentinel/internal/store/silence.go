package store

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
)

// Silence 表示一条静默窗口配置。
type Silence struct {
	ID        int64
	MonitorID int64
	NameMatch string
	StartsAt  string
	EndsAt    string
	Reason    string
	CreatedAt string
}

// CreateSilence 创建一条静默窗口。
func (s *Store) CreateSilence(sl Silence) (int64, error) {
	if _, err := time.Parse(time.RFC3339, sl.StartsAt); err != nil {
		return 0, errors.New("starts_at 不是合法的 RFC3339 时间")
	}
	if _, err := time.Parse(time.RFC3339, sl.EndsAt); err != nil {
		return 0, errors.New("ends_at 不是合法的 RFC3339 时间")
	}
	st, err := time.Parse(time.RFC3339, sl.StartsAt)
	if err != nil {
		return 0, errors.New("starts_at 不是合法的 RFC3339 时间")
	}
	et, err := time.Parse(time.RFC3339, sl.EndsAt)
	if err != nil {
		return 0, errors.New("ends_at 不是合法的 RFC3339 时间")
	}
	if !st.Before(et) {
		return 0, errors.New("starts_at 必须早于 ends_at")
	}
	reason := strings.TrimSpace(sl.Reason)
	if reason == "" {
		return 0, errors.New("reason 不能为空")
	}
	createdAt := sl.CreatedAt
	if createdAt == "" {
		createdAt = time.Now().UTC().Format(time.RFC3339)
	}
	res, err := s.db.Exec(
		`INSERT INTO silences (monitor_id, name_match, starts_at, ends_at, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)`,
		sl.MonitorID, sl.NameMatch, sl.StartsAt, sl.EndsAt, reason, createdAt,
	)
	if err != nil {
		return 0, fmt.Errorf("insert silence: %w", err)
	}
	return res.LastInsertId()
}

// ListSilences 返回全部静默窗口，按 id 倒序。
func (s *Store) ListSilences() ([]Silence, error) {
	rows, err := s.db.Query(
		`SELECT id, monitor_id, name_match, starts_at, ends_at, reason, created_at FROM silences ORDER BY id DESC`,
	)
	if err != nil {
		return nil, fmt.Errorf("list silences: %w", err)
	}
	defer rows.Close()
	var out []Silence
	for rows.Next() {
		var sl Silence
		if err := rows.Scan(&sl.ID, &sl.MonitorID, &sl.NameMatch, &sl.StartsAt, &sl.EndsAt, &sl.Reason, &sl.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan silence: %w", err)
		}
		out = append(out, sl)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate silences: %w", err)
	}
	return out, nil
}

// GetSilence 按 id 获取静默窗口，不存在返回错误。
func (s *Store) GetSilence(id int64) (Silence, error) {
	var sl Silence
	err := s.db.QueryRow(
		`SELECT id, monitor_id, name_match, starts_at, ends_at, reason, created_at FROM silences WHERE id = ?`,
		id,
	).Scan(&sl.ID, &sl.MonitorID, &sl.NameMatch, &sl.StartsAt, &sl.EndsAt, &sl.Reason, &sl.CreatedAt)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Silence{}, fmt.Errorf("silence %d 不存在", id)
		}
		return Silence{}, fmt.Errorf("get silence: %w", err)
	}
	return sl, nil
}

// DeleteSilence 删除指定静默窗口，删不存在的行不报错。
func (s *Store) DeleteSilence(id int64) error {
	if _, err := s.db.Exec(`DELETE FROM silences WHERE id = ?`, id); err != nil {
		return fmt.Errorf("delete silence: %w", err)
	}
	return nil
}

// FindActiveSilence 查找对指定监控目标/名称在 now 时刻生效的静默窗口。
// 多条命中时返回 id 最小的一条。
func (s *Store) FindActiveSilence(monitorID int64, name string, now time.Time) (*Silence, bool, error) {
	rows, err := s.db.Query(
		`SELECT id, monitor_id, name_match, starts_at, ends_at, reason, created_at FROM silences ORDER BY id ASC`,
	)
	if err != nil {
		return nil, false, fmt.Errorf("query silences: %w", err)
	}
	defer rows.Close()
	var found *Silence
	for rows.Next() {
		var sl Silence
		if err := rows.Scan(&sl.ID, &sl.MonitorID, &sl.NameMatch, &sl.StartsAt, &sl.EndsAt, &sl.Reason, &sl.CreatedAt); err != nil {
			return nil, false, fmt.Errorf("scan silence: %w", err)
		}
		st, err := time.Parse(time.RFC3339, sl.StartsAt)
		if err != nil {
			continue
		}
		et, err := time.Parse(time.RFC3339, sl.EndsAt)
		if err != nil {
			continue
		}
		if now.Before(st) || now.After(et) {
			continue
		}
		if sl.MonitorID != 0 && sl.MonitorID != monitorID {
			continue
		}
		if sl.NameMatch != "" && !strings.Contains(name, sl.NameMatch) {
			continue
		}
		if found == nil || sl.ID < found.ID {
			cp := sl
			found = &cp
		}
	}
	if err := rows.Err(); err != nil {
		return nil, false, fmt.Errorf("iterate silences: %w", err)
	}
	if found == nil {
		return nil, false, nil
	}
	return found, true, nil
}
