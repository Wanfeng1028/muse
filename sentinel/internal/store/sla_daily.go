package store

import (
	"fmt"
	"time"
)

// DailySLAPoint 单日 SLA 明细。
type DailySLAPoint struct {
	Date         string  `json:"date"`
	UptimePct    float64 `json:"uptime_pct"`
	P95LatencyMs float64 `json:"p95_latency_ms"`
	TotalChecks  int     `json:"total_checks"`
	DowntimeSec  int64   `json:"downtime_sec"`
}

// DailySLA 按日聚合某监控某月的可用性与延迟。返回当月每天一条，按日期升序。
func (s *Store) DailySLA(monitorID int64, year, month int) ([]DailySLAPoint, error) {
	if month < 1 || month > 12 {
		return nil, fmt.Errorf("invalid month: %d", month)
	}

	monthStart := time.Date(year, time.Month(month), 1, 0, 0, 0, 0, time.UTC)
	nextMonth := monthStart.AddDate(0, 1, 0)

	var points []DailySLAPoint

	for day := monthStart; day.Before(nextMonth); day = day.AddDate(0, 0, 1) {
		dayStart := day
		dayEnd := day.AddDate(0, 0, 1)
		startStr := dayStart.Format(time.RFC3339)
		endStr := dayEnd.Format(time.RFC3339)

		var totalChecks, okChecks int
		err := s.db.QueryRow(
			`SELECT COUNT(*), COALESCE(SUM(ok), 0) FROM checks WHERE monitor_id = ? AND checked_at >= ? AND checked_at < ?`,
			monitorID, startStr, endStr,
		).Scan(&totalChecks, &okChecks)
		if err != nil {
			return nil, err
		}

		uptimePct := 100.0
		if totalChecks > 0 {
			uptimePct = float64(okChecks) / float64(totalChecks) * 100
		}

		var p95LatencyMs float64
		if totalChecks > 0 {
			rows, err := s.db.Query(
				`SELECT latency_ms FROM checks WHERE monitor_id = ? AND checked_at >= ? AND checked_at < ? ORDER BY latency_ms`,
				monitorID, startStr, endStr,
			)
			if err != nil {
				return nil, err
			}
			var latencies []int
			for rows.Next() {
				var l int
				if err := rows.Scan(&l); err != nil {
					rows.Close()
					return nil, err
				}
				latencies = append(latencies, l)
			}
			rows.Close()
			if err := rows.Err(); err != nil {
				return nil, err
			}
			if len(latencies) > 0 {
				idx := int(float64(len(latencies)) * 0.95)
				if idx >= len(latencies) {
					idx = len(latencies) - 1
				}
				if idx < 0 {
					idx = 0
				}
				p95LatencyMs = float64(latencies[idx])
			}
		}

		var downtimeSec int64
		err = s.db.QueryRow(
			`SELECT COALESCE(SUM(downtime_sec), 0) FROM incidents WHERE monitor_id = ? AND started_at >= ? AND started_at < ?`,
			monitorID, startStr, endStr,
		).Scan(&downtimeSec)
		if err != nil {
			return nil, err
		}

		points = append(points, DailySLAPoint{
			Date:         dayStart.Format("2006-01-02"),
			UptimePct:    uptimePct,
			P95LatencyMs: p95LatencyMs,
			TotalChecks:  totalChecks,
			DowntimeSec:  downtimeSec,
		})
	}

	return points, nil
}
