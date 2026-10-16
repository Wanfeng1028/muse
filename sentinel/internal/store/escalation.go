package store

import (
"database/sql"
)

// ListOpenIncidents 返回所有未关闭（ended_at IS NULL）的 incident，按 started_at 升序。
func (s *Store) ListOpenIncidents() ([]Incident, error) {
rows, err := s.db.Query(
`SELECT id, monitor_id, started_at, ended_at, downtime_sec, start_error
FROM incidents WHERE ended_at IS NULL ORDER BY started_at`,
)
if err != nil {
return nil, err
}
defer rows.Close()

var out []Incident
for rows.Next() {
var inc Incident
if err := rows.Scan(&inc.ID, &inc.MonitorID, &inc.StartedAt, &inc.EndedAt, &inc.DowntimeSec, &inc.StartError); err != nil {
return nil, err
}
out = append(out, inc)
}
return out, rows.Err()
}

// SentEscalationLevels 返回某 incident 已发送过升级通知的级别分钟数列表。
func (s *Store) SentEscalationLevels(incidentID int64) ([]int, error) {
rows, err := s.db.Query(
`SELECT level_minutes FROM incident_escalations WHERE incident_id = ?`,
incidentID,
)
if err != nil {
return nil, err
}
defer rows.Close()

var out []int
for rows.Next() {
var lv int
if err := rows.Scan(&lv); err != nil {
return nil, err
}
out = append(out, lv)
}
return out, rows.Err()
}

// MarkEscalationSent 幂等记录某 incident 的某级别升级通知已发送。
func (s *Store) MarkEscalationSent(incidentID int64, levelMinutes int) error {
_, err := s.db.Exec(
`INSERT OR IGNORE INTO incident_escalations (incident_id, level_minutes, sent_at) VALUES (?, ?, ?)`,
incidentID, levelMinutes, sql.NullString{}.String,
)
return err
}
