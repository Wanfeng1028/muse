package store

import (
	"database/sql"
	"fmt"
	"time"
)

// StatusSnapshot 状态页快照归档记录。List 时不返回 HTML 正文（HTML 字段置空）。
type StatusSnapshot struct {
	ID        int64  `json:"id"`
	PageID    int64  `json:"page_id"`
	CreatedAt string `json:"created_at"`
	Generator string `json:"generator"`
	Theme     string `json:"theme"`
	SizeBytes int64  `json:"size_bytes"`
	HTML      string `json:"html,omitempty"`
}

// ValidSnapshotSchedule 校验快照定时计划取值合法。
func ValidSnapshotSchedule(s string) bool {
	return s == "off" || s == "daily" || s == "hourly"
}

// CreateStatusSnapshot 生成一条快照归档，返回新记录 id。html 为空时返回错误。
func (s *Store) CreateStatusSnapshot(pageID int64, generator, theme, html string) (int64, error) {
	if html == "" {
		return 0, fmt.Errorf("html 不能为空")
	}
	if generator != "manual" && generator != "schedule" {
		return 0, fmt.Errorf("generator 非法取值: %s", generator)
	}
	effectiveTheme := theme
	if effectiveTheme == "" {
		effectiveTheme = "light"
	}
	sizeBytes := len(html)
	now := time.Now().UTC().Format(time.RFC3339)

	res, err := s.db.Exec(
		"INSERT INTO status_snapshots (page_id, created_at, generator, theme, size_bytes, html) VALUES (?, ?, ?, ?, ?, ?)",
		pageID, now, generator, effectiveTheme, sizeBytes, html,
	)
	if err != nil {
		return 0, fmt.Errorf("插入快照失败: %w", err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("获取快照 id 失败: %w", err)
	}
	return id, nil
}

// ListStatusSnapshots 按 page 列出快照（id 倒序，不含 html 正文）。limit<=0 默认 50，上限 200。
func (s *Store) ListStatusSnapshots(pageID int64, limit int) ([]StatusSnapshot, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}

	rows, err := s.db.Query(
		"SELECT id, page_id, created_at, generator, theme, size_bytes FROM status_snapshots WHERE page_id=? ORDER BY id DESC LIMIT ?",
		pageID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("查询快照列表失败: %w", err)
	}
	defer rows.Close()

	var list []StatusSnapshot
	for rows.Next() {
		var sn StatusSnapshot
		if err := rows.Scan(&sn.ID, &sn.PageID, &sn.CreatedAt, &sn.Generator, &sn.Theme, &sn.SizeBytes); err != nil {
			return nil, fmt.Errorf("扫描快照记录失败: %w", err)
		}
		list = append(list, sn)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历快照列表失败: %w", err)
	}
	return list, nil
}

// GetStatusSnapshot 按 id 取快照（含 html 正文）。不存在返回 sql.ErrNoRows。
func (s *Store) GetStatusSnapshot(id int64) (StatusSnapshot, error) {
	var sn StatusSnapshot
	err := s.db.QueryRow(
		"SELECT id, page_id, created_at, generator, theme, size_bytes, html FROM status_snapshots WHERE id=?",
		id,
	).Scan(&sn.ID, &sn.PageID, &sn.CreatedAt, &sn.Generator, &sn.Theme, &sn.SizeBytes, &sn.HTML)
	if err != nil {
		if err == sql.ErrNoRows {
			return StatusSnapshot{}, fmt.Errorf("快照不存在: %w", sql.ErrNoRows)
		}
		return StatusSnapshot{}, fmt.Errorf("查询快照失败: %w", err)
	}
	return sn, nil
}

// DeleteStatusSnapshot 删除一条快照。不存在也返回 nil（幂等）。
func (s *Store) DeleteStatusSnapshot(id int64) error {
	_, err := s.db.Exec("DELETE FROM status_snapshots WHERE id=?", id)
	if err != nil {
		return fmt.Errorf("删除快照失败: %w", err)
	}
	return nil
}

// PruneStatusSnapshots 按 page 只保留最新 keep 条，删除更旧的，返回删除条数。keep<=0 时不删除返回 0。
func (s *Store) PruneStatusSnapshots(pageID int64, keep int) (int64, error) {
	if keep <= 0 {
		return 0, nil
	}
	res, err := s.db.Exec(
		"DELETE FROM status_snapshots WHERE page_id=? AND id NOT IN (SELECT id FROM status_snapshots WHERE page_id=? ORDER BY id DESC LIMIT ?)",
		pageID, pageID, keep,
	)
	if err != nil {
		return 0, fmt.Errorf("清理快照失败: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("获取删除条数失败: %w", err)
	}
	return affected, nil
}

// LatestStatusSnapshotAt 返回某页面最新快照的 created_at；无快照时 found=false。
func (s *Store) LatestStatusSnapshotAt(pageID int64) (at string, found bool, err error) {
	err = s.db.QueryRow(
		"SELECT created_at FROM status_snapshots WHERE page_id=? ORDER BY id DESC LIMIT 1",
		pageID,
	).Scan(&at)
	if err != nil {
		if err == sql.ErrNoRows {
			return "", false, nil
		}
		return "", false, fmt.Errorf("查询最新快照时间失败: %w", err)
	}
	return at, true, nil
}

// UpdateStatusPageSnapshotSchedule 更新状态页的快照定时计划，非法取值返回错误（错误信息含 "snapshot_schedule"）。
func (s *Store) UpdateStatusPageSnapshotSchedule(pageID int64, schedule string) error {
	if !ValidSnapshotSchedule(schedule) {
		return fmt.Errorf("snapshot_schedule 非法取值: %s", schedule)
	}
	_, err := s.db.Exec(
		"UPDATE status_pages SET snapshot_schedule=? WHERE id=?",
		schedule, pageID,
	)
	if err != nil {
		return fmt.Errorf("更新快照定时计划失败: %w", err)
	}
	return nil
}
