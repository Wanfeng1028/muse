// internal/store/incident_detail.go
package store

import "database/sql"

// GetIncidentByID 按 id 查询单个 incident，附带 monitor 名称。
func (s *Store) GetIncidentByID(id int64) (Incident, error) {
	query := `SELECT i.id, i.monitor_id, i.started_at, i.ended_at, i.downtime_sec, i.start_error, m.name
FROM incidents i JOIN monitors m ON m.id = i.monitor_id
WHERE i.id = ?`

	var inc Incident
	err := s.db.QueryRow(query, id).Scan(
		&inc.ID, &inc.MonitorID, &inc.StartedAt, &inc.EndedAt, &inc.DowntimeSec, &inc.StartError, &inc.MonitorName,
	)
	if err != nil {
		return Incident{}, err
	}
	return inc, nil
}

// FirstRecoveryCheck 返回 incident 开始之后最早的一次成功检查；不存在则返回 nil, nil。
func (s *Store) FirstRecoveryCheck(inc Incident) (*Check, error) {
	query := `SELECT id, monitor_id, checked_at, ok, status_code, latency_ms, error, cert_days_left
FROM checks
WHERE monitor_id = ? AND checked_at >= ? AND ok = 1
ORDER BY checked_at ASC, id ASC
LIMIT 1`

	var c Check
	err := s.db.QueryRow(query, inc.MonitorID, inc.StartedAt).Scan(
		&c.ID, &c.MonitorID, &c.CheckedAt, &c.Ok, &c.StatusCode, &c.LatencyMs, &c.Error, &c.CertDaysLeft,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &c, nil
}

// ListIncidentDeliveries 返回 incident 时间窗口内（含恢复前）与 down/recovered 相关的 webhook 投递记录。
func (s *Store) ListIncidentDeliveries(inc Incident) ([]Delivery, error) {
	query := `SELECT id, monitor_id, url, event, payload, status, attempt, max_attempts, next_retry_at, last_error, created_at, updated_at
FROM webhook_deliveries
WHERE monitor_id = ? AND event IN ('down', 'recovered') AND created_at >= ?`
	args := []any{inc.MonitorID, inc.StartedAt}

	if inc.EndedAt.Valid {
		query += " AND created_at <= ?"
		args = append(args, inc.EndedAt.String)
	}

	query += " ORDER BY id ASC LIMIT 200"

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	deliveries := make([]Delivery, 0, 200)
	for rows.Next() {
		d, err := scanDelivery(rows)
		if err != nil {
			return nil, err
		}
		deliveries = append(deliveries, d)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	return deliveries, nil
}
