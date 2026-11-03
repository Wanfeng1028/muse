package store

import (
	"database/sql"
	"errors"
	"fmt"
	"sort"
	"time"
)

type GroupLatencyMonth struct {
	GroupID            int64   `json:"group_id"`
	GroupName          string  `json:"group_name"`
	Month              string  `json:"month"`
	P50Ms              float64 `json:"p50_ms"`
	P95Ms              float64 `json:"p95_ms"`
	P99Ms              float64 `json:"p99_ms"`
	AvgMs              float64 `json:"avg_ms"`
	TotalChecks        int     `json:"total_checks"`
	MonitorCount       int     `json:"monitor_count"`
	SlowestMonitorName string  `json:"slowest_monitor_name"`
}

func (s *Store) GroupMonthlyLatency(groupID int64, year, month int) (GroupLatencyMonth, error) {
	result := GroupLatencyMonth{Month: fmt.Sprintf("%04d-%02d", year, month)}
	if month < 1 || month > 12 {
		return result, fmt.Errorf("非法月份: %d", month)
	}
	var groupName string
	err := s.db.QueryRow("SELECT name FROM monitor_groups WHERE id = ?", groupID).Scan(&groupName)
	if err == sql.ErrNoRows {
		return result, errors.New("分组不存在")
	}
	if err != nil {
		return result, err
	}
	result.GroupID = groupID
	result.GroupName = groupName
	members, err := s.ListGroupMonitors(groupID)
	if err != nil {
		return result, err
	}
	result.MonitorCount = len(members)
	start := time.Date(year, time.Month(month), 1, 0, 0, 0, 0, time.UTC)
	end := start.AddDate(0, 1, 0)
	startStr := start.Format(time.RFC3339)
	endStr := end.Format(time.RFC3339)
	var all []float64
	slowestP95 := -1.0
	for _, m := range members {
		rows, err := s.db.Query("SELECT latency_ms FROM checks WHERE monitor_id = ? AND ok = 1 AND checked_at >= ? AND checked_at < ? ORDER BY latency_ms ASC", m.ID, startStr, endStr)
		if err != nil {
			return result, err
		}
		var latencies []float64
		for rows.Next() {
			var latency float64
			if err := rows.Scan(&latency); err != nil {
				rows.Close()
				return result, err
			}
			latencies = append(latencies, latency)
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return result, err
		}
		rows.Close()
		if len(latencies) == 0 {
			continue
		}
		p95 := percentileLinear(latencies, 95)
		if p95 > slowestP95 {
			slowestP95 = p95
			result.SlowestMonitorName = m.Name
		}
		all = append(all, latencies...)
	}
	result.TotalChecks = len(all)
	if len(all) > 0 {
		sort.Float64s(all)
		result.P50Ms = percentileLinear(all, 50)
		result.P95Ms = percentileLinear(all, 95)
		result.P99Ms = percentileLinear(all, 99)
		var sum float64
		for _, v := range all {
			sum += v
		}
		result.AvgMs = sum / float64(len(all))
	}
	return result, nil
}

type GroupLatencyTrendReport struct {
	GroupID   int64               `json:"group_id"`
	GroupName string              `json:"group_name"`
	EndMonth  string              `json:"end_month"`
	Months    int                 `json:"months"`
	Items     []GroupLatencyMonth `json:"items"`
}

func (s *Store) GroupLatencyTrend(groupID int64, endYear, endMonth, months int) (GroupLatencyTrendReport, error) {
	if months < 1 || months > 12 {
		return GroupLatencyTrendReport{}, fmt.Errorf("months must be between 1 and 12, got %d", months)
	}
	if endMonth < 1 || endMonth > 12 {
		return GroupLatencyTrendReport{}, fmt.Errorf("endMonth must be between 1 and 12, got %d", endMonth)
	}
	report := GroupLatencyTrendReport{
		EndMonth: fmt.Sprintf("%04d-%02d", endYear, endMonth),
		Months:   months,
		Items:    make([]GroupLatencyMonth, 0, months),
	}
	for i := months - 1; i >= 0; i-- {
		y, m := shiftMonth(endYear, endMonth, -i)
		item, err := s.GroupMonthlyLatency(groupID, y, m)
		if err != nil {
			return GroupLatencyTrendReport{}, err
		}
		report.GroupID = item.GroupID
		report.GroupName = item.GroupName
		report.Items = append(report.Items, item)
	}
	return report, nil
}
