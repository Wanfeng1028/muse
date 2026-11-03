package store

import (
	"fmt"
	"sort"
	"time"
)

type SiteLatencyMonth struct {
	Month              string  `json:"month"`
	P50Ms              float64 `json:"p50_ms"`
	P95Ms              float64 `json:"p95_ms"`
	P99Ms              float64 `json:"p99_ms"`
	AvgMs              float64 `json:"avg_ms"`
	TotalChecks        int     `json:"total_checks"`
	MonitorCount       int     `json:"monitor_count"`
	SlowestMonitorName string  `json:"slowest_monitor_name"`
}

func (s *Store) SiteMonthlyLatency(year, month int) (SiteLatencyMonth, error) {
	result := SiteLatencyMonth{
		Month: fmt.Sprintf("%04d-%02d", year, month),
	}

	if month < 1 || month > 12 {
		return result, fmt.Errorf("非法月份: %d", month)
	}

	monitors, err := s.ListMonitors()
	if err != nil {
		return result, err
	}
	result.MonitorCount = len(monitors)

	start := time.Date(year, time.Month(month), 1, 0, 0, 0, 0, time.UTC)
	end := start.AddDate(0, 1, 0)
	startStr := start.Format(time.RFC3339)
	endStr := end.Format(time.RFC3339)

	var all []float64
	slowestP95 := -1.0

	for _, m := range monitors {
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

type SiteLatencyTrendReport struct {
	EndMonth string             `json:"end_month"`
	Months   int                `json:"months"`
	Items    []SiteLatencyMonth `json:"items"`
}

func (s *Store) SiteLatencyTrend(endYear, endMonth, months int) (SiteLatencyTrendReport, error) {
	if months < 1 || months > 12 {
		return SiteLatencyTrendReport{}, fmt.Errorf("months must be between 1 and 12, got %d", months)
	}
	if endMonth < 1 || endMonth > 12 {
		return SiteLatencyTrendReport{}, fmt.Errorf("endMonth must be between 1 and 12, got %d", endMonth)
	}

	report := SiteLatencyTrendReport{
		EndMonth: fmt.Sprintf("%04d-%02d", endYear, endMonth),
		Months:   months,
		Items:    make([]SiteLatencyMonth, 0, months),
	}

	for i := months - 1; i >= 0; i-- {
		year, month := shiftMonth(endYear, endMonth, -i)
		item, err := s.SiteMonthlyLatency(year, month)
		if err != nil {
			return SiteLatencyTrendReport{}, err
		}
		report.Items = append(report.Items, item)
	}

	return report, nil
}
