package store

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
)

type MonitorGroup struct {
	ID           int64
	Name         string
	CreatedAt    string
	MonitorCount int
}

func (s *Store) ListGroups() ([]MonitorGroup, error) {
	groups := make([]MonitorGroup, 0)

	rows, err := s.db.Query("SELECT g.id, g.name, g.created_at, COUNT(m.monitor_id) FROM monitor_groups g LEFT JOIN monitor_group_members m ON m.group_id = g.id GROUP BY g.id ORDER BY g.id ASC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var g MonitorGroup
		if err := rows.Scan(&g.ID, &g.Name, &g.CreatedAt, &g.MonitorCount); err != nil {
			return nil, err
		}
		groups = append(groups, g)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	return groups, nil
}

func (s *Store) CreateGroup(name string) (int64, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return 0, errors.New("name 不能为空")
	}

	var id int64
	err := s.db.QueryRow("SELECT id FROM monitor_groups WHERE name = ?", name).Scan(&id)
	if err == nil {
		return 0, errors.New("分组名已存在")
	}
	if err != sql.ErrNoRows {
		return 0, err
	}

	res, err := s.db.Exec("INSERT INTO monitor_groups (name, created_at) VALUES (?, ?)", name, time.Now().UTC().Format(time.RFC3339))
	if err != nil {
		return 0, fmt.Errorf("insert monitor group: %w", err)
	}
	id, err = res.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("insert monitor group: %w", err)
	}
	return id, nil
}

func (s *Store) AddMonitorToGroup(groupID, monitorID int64) error {
	var id int64
	err := s.db.QueryRow("SELECT id FROM monitor_groups WHERE id = ?", groupID).Scan(&id)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return errors.New("分组不存在")
		}
		return err
	}

	if _, err := s.GetMonitor(monitorID); err != nil {
		return errors.New("监控不存在")
	}

	_, err = s.db.Exec("INSERT OR IGNORE INTO monitor_group_members (group_id, monitor_id) VALUES (?, ?)", groupID, monitorID)
	return err
}

func (s *Store) RemoveMonitorFromGroup(groupID, monitorID int64) error {
	_, err := s.db.Exec("DELETE FROM monitor_group_members WHERE group_id = ? AND monitor_id = ?", groupID, monitorID)
	return err
}

func (s *Store) DeleteGroup(id int64) error {
	if _, err := s.db.Exec("DELETE FROM monitor_group_members WHERE group_id = ?", id); err != nil {
		return err
	}
	_, err := s.db.Exec("DELETE FROM monitor_groups WHERE id = ?", id)
	return err
}

func (s *Store) ListGroupMonitors(groupID int64) ([]Monitor, error) {
	out := make([]Monitor, 0)
	rows, err := s.db.Query("SELECT m.id, m.name, m.kind, m.target, m.method, m.expected_status, m.timeout_sec, m.interval_sec, m.enabled, m.tenant_id, m.is_public, m.webhook_url, m.notify_channels, m.sms_phones, m.cert_warn_days, m.keyword, m.keyword_mode, m.created_at, m.updated_at FROM monitors m JOIN monitor_group_members gm ON gm.monitor_id = m.id WHERE gm.group_id = ? ORDER BY m.id ASC", groupID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var m Monitor
		if err := rows.Scan(&m.ID, &m.Name, &m.Kind, &m.Target, &m.Method, &m.ExpectedStatus, &m.TimeoutSec, &m.IntervalSec, &m.Enabled, &m.TenantID, &m.IsPublic, &m.WebhookURL, &m.NotifyChannels, &m.SMSPhones, &m.CertWarnDays, &m.Keyword, &m.KeywordMode, &m.CreatedAt, &m.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
