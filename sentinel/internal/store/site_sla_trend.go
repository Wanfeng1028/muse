package store

import "fmt"

type SiteSLATrendMonth struct {
	Month            string  `json:"month"`
	UptimePct        float64 `json:"uptime_pct"`
	TotalChecks      int     `json:"total_checks"`
	DownIncidents    int     `json:"down_incidents"`
	TotalDowntimeSec int64   `json:"total_downtime_sec"`
	Met              bool    `json:"met"`
	MonitorCount     int     `json:"monitor_count"`
	WorstMonitorName string  `json:"worst_monitor_name"`
}

type SiteSLATrendReport struct {
	EndMonth string              `json:"end_month"`
	Months   int                 `json:"months"`
	Target   float64             `json:"sla_target"`
	Items    []SiteSLATrendMonth `json:"items"`
}

func shiftMonth(y, m, delta int) (int, int) {
	total := (y*12 + (m - 1)) + delta
	return total / 12, total%12 + 1
}

func (s *Store) SiteSLATrend(endYear, endMonth, months int) (SiteSLATrendReport, error) {
	if months < 1 || months > 12 {
		return SiteSLATrendReport{}, fmt.Errorf("months must be between 1 and 12, got %d", months)
	}
	if endMonth < 1 || endMonth > 12 {
		return SiteSLATrendReport{}, fmt.Errorf("endMonth must be between 1 and 12, got %d", endMonth)
	}
	rep := SiteSLATrendReport{
		EndMonth: fmt.Sprintf("%04d-%02d", endYear, endMonth),
		Months:   months,
		Target:   99.9,
		Items:    []SiteSLATrendMonth{},
	}
	for i := months - 1; i >= 0; i-- {
		y, m := shiftMonth(endYear, endMonth, -i)
		sr, err := s.SiteMonthlySLA(y, m)
		if err != nil {
			return SiteSLATrendReport{}, err
		}
		rep.Items = append(rep.Items, SiteSLATrendMonth{
			Month:            sr.Month,
			UptimePct:        sr.UptimePct,
			TotalChecks:      sr.TotalChecks,
			DownIncidents:    sr.DownIncidents,
			TotalDowntimeSec: sr.TotalDowntimeSec,
			Met:              sr.Met,
			MonitorCount:     sr.MonitorCount,
			WorstMonitorName: sr.WorstMonitorName,
		})
	}
	return rep, nil
}
