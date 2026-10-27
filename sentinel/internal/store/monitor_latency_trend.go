package store

import (
	"database/sql"
	"errors"
	"fmt"
	"sort"
	"time"
)

type MonitorLatencyMonth struct {
	MonitorID   int64   `json:"monitor_id"`
	MonitorName string  `json:"monitor_name"`
	Month       string  `json:"month"`
	P50Ms       float64 `json:"p50_ms"`
	P95Ms       float64 `json:"p95_ms"`
	P99Ms       float64 `json:"p99_ms"`
	AvgMs       float64 `json:"avg_ms"`
	TotalChecks int     `json:"total_checks"`
}

func (s *Store) MonitorMonthlyLatency(monitorID int64, year, month int) (MonitorLatencyMonth, error) {
	result := MonitorLatencyMonth{Month: fmt.Sprintf("%04d-%02d", year, month)}
	if month < 1 || month > 12 {
		return result, fmt.Errorf("非法月份: %d", month)
	}
	monitor, err := s.GetMonitor(monitorID)
	if err == sql.ErrNoRows {
		return result, errors.New("监控不存在")
	}
	if err != nil {
		return result, err
	}
	result.MonitorID = monitorID
	result.MonitorName = monitor.Name
	start := time.Date(year, time.Month(month), 1, 0, 0, 0, 0, time.UTC)
	end := start.AddDate(0, 1, 0)
	startStr := start.Format(time.RFC3339)
	endStr := end.Format(time.RFC3339)
	rows, err := s.db.Query("SELECT latency_ms FROM checks WHERE monitor_id = ? AND ok = 1 AND checked_at >= ? AND checked_at < ? ORDER BY latency_ms ASC", monitorID, startStr, endStr)
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
	result.TotalChecks = len(latencies)
	if len(latencies) > 0 {
		sort.Float64s(latencies)
		result.P50Ms = percentileLinear(latencies, 50)
		result.P95Ms = percentileLinear(latencies, 95)
		result.P99Ms = percentileLinear(latencies, 99)
		var sum float64
		for _, v := range latencies {
			sum += v
		}
		result.AvgMs = sum / float64(len(latencies))
	}
	return result, nil
}

type MonitorLatencyTrendReport struct {
	MonitorID   int64                 `json:"monitor_id"`
	MonitorName string                `json:"monitor_name"`
	EndMonth    string                `json:"end_month"`
	Months      int                   `json:"months"`
	Items       []MonitorLatencyMonth `json:"items"`
}

func (s *Store) MonitorLatencyTrend(monitorID int64, endYear, endMonth, months int) (MonitorLatencyTrendReport, error) {
	if months < 1 || months > 12 {
		return MonitorLatencyTrendReport{}, fmt.Errorf("months must be between 1 and 12, got %d", months)
	}
	if endMonth < 1 || endMonth > 12 {
		return MonitorLatencyTrendReport{}, fmt.Errorf("endMonth must be between 1 and 12, got %d", endMonth)
	}
	report := MonitorLatencyTrendReport{
		EndMonth: fmt.Sprintf("%04d-%02d", endYear, endMonth),
		Months:   months,
		Items:    make([]MonitorLatencyMonth, 0, months),
	}
	for i := months - 1; i >= 0; i-- {
		y, m := shiftMonth(endYear, endMonth, -i)
		item, err := s.MonitorMonthlyLatency(monitorID, y, m)
		if err != nil {
			return MonitorLatencyTrendReport{}, err
		}
		report.MonitorID = item.MonitorID
		report.MonitorName = item.MonitorName
		report.Items = append(report.Items, item)
	}
	return report, nil
}
