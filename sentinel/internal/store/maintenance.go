package store

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
)

// MaintenanceWindow 表示一条维护窗口：窗口内调度检查跳过，不产生检查记录与新事件。
type MaintenanceWindow struct {
	ID        int64
	MonitorID int64
	Title     string
	StartsAt  string
	EndsAt    string
	CreatedAt string
}

func (s *Store) CreateMaintenanceWindow(w MaintenanceWindow) (int64, error) {
	title := strings.TrimSpace(w.Title)
	if title == "" {
		return 0, errors.New("title 不能为空")
	}

	startsAt, err := time.Parse(time.RFC3339, w.StartsAt)
	if err != nil {
		return 0, errors.New("starts_at 不是合法的 RFC3339 时间")
	}

	endsAt, err := time.Parse(time.RFC3339, w.EndsAt)
	if err != nil {
		return 0, errors.New("ends_at 不是合法的 RFC3339 时间")
	}

	if !startsAt.Before(endsAt) {
		return 0, errors.New("starts_at 必须早于 ends_at")
	}

	if w.MonitorID < 0 {
		return 0, errors.New("monitor_id 非法")
	}

	if w.MonitorID != 0 {
		if _, err := s.GetMonitor(w.MonitorID); err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				return 0, errors.New("监控不存在")
			}
			return 0, err
		}
	}

	createdAt := w.CreatedAt
	if createdAt == "" {
		createdAt = time.Now().UTC().Format(time.RFC3339)
	}

	res, err := s.db.Exec(
		`INSERT INTO maintenance_windows (monitor_id, title, starts_at, ends_at, created_at) VALUES (?, ?, ?, ?, ?)`,
		w.MonitorID, title, w.StartsAt, w.EndsAt, createdAt,
	)
	if err != nil {
		return 0, fmt.Errorf("insert maintenance window: %w", err)
	}

	id, err := res.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("insert maintenance window: %w", err)
	}

	return id, nil
}

func (s *Store) ListMaintenanceWindows() ([]MaintenanceWindow, error) {
	rows, err := s.db.Query(`SELECT id, monitor_id, title, starts_at, ends_at, created_at FROM maintenance_windows ORDER BY id DESC`)
	if err != nil {
		return nil, fmt.Errorf("list maintenance windows: %w", err)
	}
	defer rows.Close()

	out := make([]MaintenanceWindow, 0)
	for rows.Next() {
		var mw MaintenanceWindow
		if err := rows.Scan(&mw.ID, &mw.MonitorID, &mw.Title, &mw.StartsAt, &mw.EndsAt, &mw.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan maintenance window: %w", err)
		}
		out = append(out, mw)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate maintenance windows: %w", err)
	}
	return out, nil
}

func (s *Store) DeleteMaintenanceWindow(id int64) error {
	if _, err := s.db.Exec(`DELETE FROM maintenance_windows WHERE id = ?`, id); err != nil {
		return fmt.Errorf("delete maintenance window: %w", err)
	}
	return nil
}

func (s *Store) ActiveMaintenanceWindow(monitorID int64, now time.Time) (bool, *MaintenanceWindow, error) {
	rows, err := s.db.Query(`SELECT id, monitor_id, title, starts_at, ends_at, created_at FROM maintenance_windows ORDER BY id ASC`)
	if err != nil {
		return false, nil, fmt.Errorf("query maintenance windows: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var (
			id         int64
			monID      int64
			title      string
			startsRaw  string
			endsRaw    string
			createdRaw string
		)
		if err := rows.Scan(&id, &monID, &title, &startsRaw, &endsRaw, &createdRaw); err != nil {
			return false, nil, fmt.Errorf("scan maintenance window: %w", err)
		}
		st, err := time.Parse(time.RFC3339, startsRaw)
		if err != nil {
			continue
		}
		et, err := time.Parse(time.RFC3339, endsRaw)
		if err != nil {
			continue
		}
		if now.Before(st) || now.After(et) {
			continue
		}
		if monID != 0 && monID != monitorID {
			continue
		}
		return true, &MaintenanceWindow{
			ID:        id,
			MonitorID: monID,
			Title:     title,
			StartsAt:  startsRaw,
			EndsAt:    endsRaw,
			CreatedAt: createdRaw,
		}, nil
	}
	if err := rows.Err(); err != nil {
		return false, nil, fmt.Errorf("iterate maintenance windows: %w", err)
	}
	return false, nil, nil
}
