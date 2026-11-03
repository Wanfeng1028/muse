package store

import (
	"database/sql"
	"errors"
	"fmt"
	"math"
)

type MonitorYearlySLAMonth struct {
	Month            string  `json:"month"`
	UptimePct        float64 `json:"uptime_pct"`
	TotalChecks      int     `json:"total_checks"`
	DownIncidents    int     `json:"down_incidents"`
	TotalDowntimeSec int64   `json:"total_downtime_sec"`
	Met              bool    `json:"met"`
}

type MonitorYearlySLAReport struct {
	MonitorID        int64                   `json:"monitor_id"`
	MonitorName      string                  `json:"monitor_name"`
	Year             int                     `json:"year"`
	Target           float64                 `json:"sla_target"`
	UptimePct        float64                 `json:"uptime_pct"`
	TotalChecks      int                     `json:"total_checks"`
	DownIncidents    int                     `json:"down_incidents"`
	TotalDowntimeSec int64                   `json:"total_downtime_sec"`
	Met              bool                    `json:"met"`
	BestMonth        string                  `json:"best_month"`
	WorstMonth       string                  `json:"worst_month"`
	Attribution      map[string]int          `json:"attribution"`
	AttributionPct   map[string]float64      `json:"attribution_pct"`
	Items            []MonitorYearlySLAMonth `json:"items"`
}

func (s *Store) MonitorYearlySLA(monitorID int64, year int) (MonitorYearlySLAReport, error) {
	if year < 1970 || year > 9999 {
		return MonitorYearlySLAReport{}, fmt.Errorf("年份非法: %d", year)
	}

	monitor, err := s.GetMonitor(monitorID)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return MonitorYearlySLAReport{}, errors.New("监控不存在")
		}
		return MonitorYearlySLAReport{}, err
	}

	report := MonitorYearlySLAReport{
		MonitorID:   monitorID,
		MonitorName: monitor.Name,
		Year:        year,
		Target:      99.9,
		Attribution: make(map[string]int),
	}

	var totalChecks int
	var downIncidents int
	var totalDowntimeSec int64
	var weightedSum float64
	var weightedChecks int
	var bestPct float64
	var worstPct float64

	for m := 1; m <= 12; m++ {
		monthly, err := s.MonthlySLA(monitorID, year, m)
		if err != nil {
			return MonitorYearlySLAReport{}, err
		}

		report.Items = append(report.Items, MonitorYearlySLAMonth{
			Month:            monthly.Month,
			UptimePct:        monthly.UptimePct,
			TotalChecks:      monthly.TotalChecks,
			DownIncidents:    monthly.DownIncidents,
			TotalDowntimeSec: monthly.TotalDowntimeSec,
			Met:              monthly.Met,
		})

		totalChecks += monthly.TotalChecks
		downIncidents += monthly.DownIncidents
		totalDowntimeSec += monthly.TotalDowntimeSec

		for k, v := range monthly.Attribution {
			report.Attribution[k] += v
		}

		if monthly.TotalChecks > 0 {
			weightedSum += monthly.UptimePct * float64(monthly.TotalChecks)
			weightedChecks += monthly.TotalChecks

			if report.BestMonth == "" || monthly.UptimePct > bestPct {
				bestPct = monthly.UptimePct
				report.BestMonth = monthly.Month
			}
			if report.WorstMonth == "" || monthly.UptimePct < worstPct {
				worstPct = monthly.UptimePct
				report.WorstMonth = monthly.Month
			}
		}
	}

	uptimePct := 100.0
	if weightedChecks > 0 {
		uptimePct = weightedSum / float64(weightedChecks)
	}
	if report.BestMonth == "" {
		report.BestMonth = report.Items[0].Month
	}
	if report.WorstMonth == "" {
		report.WorstMonth = report.Items[0].Month
	}

	report.UptimePct = uptimePct
	report.TotalChecks = totalChecks
	report.DownIncidents = downIncidents
	report.TotalDowntimeSec = totalDowntimeSec
	report.Met = uptimePct >= 99.9

	report.AttributionPct = make(map[string]float64)
	if downIncidents > 0 {
		for k, v := range report.Attribution {
			report.AttributionPct[k] = math.Round(float64(v)/float64(downIncidents)*100*10) / 10
		}
	}

	return report, nil
}