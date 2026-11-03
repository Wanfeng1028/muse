package store

import (
	"fmt"
	"strings"
)

func buildIncidentWhere(monitorID int64, status string) (string, []any, error) {
	var conds []string
	var args []any

	switch status {
	case "":
	case "open":
		conds = append(conds, "i.ended_at IS NULL")
	case "closed":
		conds = append(conds, "i.ended_at IS NOT NULL")
	default:
		return "", nil, fmt.Errorf("invalid status: %s", status)
	}

	if monitorID > 0 {
		conds = append(conds, "i.monitor_id = ?")
		args = append(args, monitorID)
	}

	if len(conds) == 0 {
		return "", args, nil
	}

	return "WHERE " + strings.Join(conds, " AND "), args, nil
}

func (s *Store) CountIncidentsByStatus(monitorID int64, status string) (int, error) {
	where, args, err := buildIncidentWhere(monitorID, status)
	if err != nil {
		return 0, err
	}

	query := "SELECT COUNT(*) FROM incidents i " + where
	var count int
	if err := s.db.QueryRow(query, args...).Scan(&count); err != nil {
		return 0, err
	}
	return count, nil
}

func (s *Store) ListIncidentsPagedByStatus(monitorID int64, status string, offset, limit int) ([]Incident, error) {
	where, args, err := buildIncidentWhere(monitorID, status)
	if err != nil {
		return nil, err
	}

	if offset < 0 {
		offset = 0
	}
	if limit <= 0 {
		limit = 20
	}

	query := "SELECT i.id, i.monitor_id, i.started_at, i.ended_at, i.downtime_sec, i.start_error, m.name FROM incidents i JOIN monitors m ON m.id = i.monitor_id " + where + " ORDER BY i.started_at DESC, i.id DESC LIMIT ? OFFSET ?"
	args = append(args, limit, offset)

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var incidents []Incident
	for rows.Next() {
		var inc Incident
		if err := rows.Scan(&inc.ID, &inc.MonitorID, &inc.StartedAt, &inc.EndedAt, &inc.DowntimeSec, &inc.StartError, &inc.MonitorName); err != nil {
			return nil, err
		}
		incidents = append(incidents, inc)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return incidents, nil
}
