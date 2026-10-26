package store

import "fmt"

type GroupSLATrendMonth struct {
	Month            string  `json:"month"`
	UptimePct        float64 `json:"uptime_pct"`
	TotalChecks      int     `json:"total_checks"`
	DownIncidents    int     `json:"down_incidents"`
	TotalDowntimeSec int64   `json:"total_downtime_sec"`
	Met              bool    `json:"met"`
	MonitorCount     int     `json:"monitor_count"`
	WorstMonitorName string  `json:"worst_monitor_name"`
}

type GroupSLATrendReport struct {
	GroupID   int64                `json:"group_id"`
	GroupName string               `json:"group_name"`
	EndMonth  string               `json:"end_month"`
	Months    int                  `json:"months"`
	Target    float64              `json:"sla_target"`
	Items     []GroupSLATrendMonth `json:"items"`
}

func (s *Store) GroupSLATrend(groupID int64, endYear, endMonth, months int) (GroupSLATrendReport, error) {
	if months < 1 || months > 12 {
		return GroupSLATrendReport{}, fmt.Errorf("months must be between 1 and 12, got %d", months)
	}
	if endMonth < 1 || endMonth > 12 {
		return GroupSLATrendReport{}, fmt.Errorf("endMonth must be between 1 and 12, got %d", endMonth)
	}
	rep := GroupSLATrendReport{
		EndMonth: fmt.Sprintf("%04d-%02d", endYear, endMonth),
		Months:   months,
		Target:   99.9,
		Items:    []GroupSLATrendMonth{},
	}
	for i := months - 1; i >= 0; i-- {
		y, m := shiftMonth(endYear, endMonth, -i)
		sr, err := s.GroupMonthlySLA(groupID, y, m)
		if err != nil {
			return GroupSLATrendReport{}, err
		}
		rep.Items = append(rep.Items, GroupSLATrendMonth{
			Month:            sr.Month,
			UptimePct:        sr.UptimePct,
			TotalChecks:      sr.TotalChecks,
			DownIncidents:    sr.DownIncidents,
			TotalDowntimeSec: sr.TotalDowntimeSec,
			Met:              sr.Met,
			MonitorCount:     sr.MonitorCount,
			WorstMonitorName: sr.WorstMonitorName,
		})
		rep.GroupID = sr.GroupID
		rep.GroupName = sr.GroupName
	}
	return rep, nil
}
