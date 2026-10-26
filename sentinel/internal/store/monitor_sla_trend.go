package store

import (
	"database/sql"
	"errors"
	"fmt"
)

type MonitorSLATrendMonth struct {
	Month            string  `json:"month"`
	UptimePct        float64 `json:"uptime_pct"`
	TotalChecks      int     `json:"total_checks"`
	DownIncidents    int     `json:"down_incidents"`
	TotalDowntimeSec int64   `json:"total_downtime_sec"`
	Met              bool    `json:"met"`
}

type MonitorSLATrendReport struct {
	MonitorID   int64                  `json:"monitor_id"`
	MonitorName string                 `json:"monitor_name"`
	Target      string                 `json:"target"`
	EndMonth    string                 `json:"end_month"`
	Months      int                    `json:"months"`
	SLATarget   float64                `json:"sla_target"`
	Items       []MonitorSLATrendMonth `json:"items"`
}

func (s *Store) MonitorSLATrend(monitorID int64, endYear, endMonth, months int) (MonitorSLATrendReport, error) {
	if months < 1 || months > 12 {
		return MonitorSLATrendReport{}, errors.New("months 必须在 1~12 之间")
	}
	if endMonth < 1 || endMonth > 12 {
		return MonitorSLATrendReport{}, errors.New("endMonth 必须在 1~12 之间")
	}

	monitor, err := s.GetMonitor(monitorID)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return MonitorSLATrendReport{}, errors.New("监控不存在")
		}
		return MonitorSLATrendReport{}, err
	}

	report := MonitorSLATrendReport{
		MonitorID:   monitor.ID,
		MonitorName: monitor.Name,
		Target:      monitor.Target,
		EndMonth:    fmt.Sprintf("%04d-%02d", endYear, endMonth),
		Months:      months,
		SLATarget:   99.9,
		Items:       make([]MonitorSLATrendMonth, 0, months),
	}

	startYear, startMonth := shiftMonth(endYear, endMonth, -(months - 1))
	for i := 0; i < months; i++ {
		y, m := shiftMonth(startYear, startMonth, i)
		sla, err := s.MonthlySLA(monitorID, y, m)
		if err != nil {
			return MonitorSLATrendReport{}, err
		}
		report.Items = append(report.Items, MonitorSLATrendMonth{
			Month:            sla.Month,
			UptimePct:        sla.UptimePct,
			TotalChecks:      sla.TotalChecks,
			DownIncidents:    sla.DownIncidents,
			TotalDowntimeSec: sla.TotalDowntimeSec,
			Met:              sla.Met,
		})
	}

	return report, nil
}
