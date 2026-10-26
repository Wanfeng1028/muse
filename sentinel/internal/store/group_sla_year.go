package store

import (
	"fmt"
	"math"
)

type GroupYearlySLAMonth struct {
	Month            string  `json:"month"`
	UptimePct        float64 `json:"uptime_pct"`
	TotalChecks      int     `json:"total_checks"`
	DownIncidents    int     `json:"down_incidents"`
	TotalDowntimeSec int64   `json:"total_downtime_sec"`
	Met              bool    `json:"met"`
	MonitorCount     int     `json:"monitor_count"`
	WorstMonitorName string  `json:"worst_monitor_name"`
}

type GroupYearlySLAReport struct {
	GroupID          int64                 `json:"group_id"`
	GroupName        string                `json:"group_name"`
	Year             int                   `json:"year"`
	Target           float64               `json:"sla_target"`
	UptimePct        float64               `json:"uptime_pct"`
	TotalChecks      int                   `json:"total_checks"`
	DownIncidents    int                   `json:"down_incidents"`
	TotalDowntimeSec int64                 `json:"total_downtime_sec"`
	Met              bool                  `json:"met"`
	MonitorCount     int                   `json:"monitor_count"`
	BestMonth        string                `json:"best_month"`
	WorstMonth       string                `json:"worst_month"`
	Attribution      map[string]int        `json:"attribution"`
	AttributionPct   map[string]float64    `json:"attribution_pct"`
	Items            []GroupYearlySLAMonth `json:"items"`
}

func (s *Store) GroupYearlySLA(groupID int64, year int) (GroupYearlySLAReport, error) {
	if year < 1970 || year > 9999 {
		return GroupYearlySLAReport{}, fmt.Errorf("年份非法: %d", year)
	}
	rep := GroupYearlySLAReport{
		Year:        year,
		Target:      99.9,
		Attribution: make(map[string]int),
		Items:       make([]GroupYearlySLAMonth, 0, 12),
	}
	var weightedSum float64
	var weightedChecks int
	bestPct, worstPct := -1.0, 101.0
	bestMonth, worstMonth := "", ""
	for m := 1; m <= 12; m++ {
		mr, err := s.GroupMonthlySLA(groupID, year, m)
		if err != nil {
			return GroupYearlySLAReport{}, err
		}
		rep.Items = append(rep.Items, GroupYearlySLAMonth{
			Month:            mr.Month,
			UptimePct:        mr.UptimePct,
			TotalChecks:      mr.TotalChecks,
			DownIncidents:    mr.DownIncidents,
			TotalDowntimeSec: mr.TotalDowntimeSec,
			Met:              mr.Met,
			MonitorCount:     mr.MonitorCount,
			WorstMonitorName: mr.WorstMonitorName,
		})
		rep.GroupID = mr.GroupID
		rep.GroupName = mr.GroupName
		rep.TotalChecks += mr.TotalChecks
		rep.DownIncidents += mr.DownIncidents
		rep.TotalDowntimeSec += mr.TotalDowntimeSec
		if mr.TotalChecks > 0 {
			weightedSum += mr.UptimePct * float64(mr.TotalChecks)
			weightedChecks += mr.TotalChecks
		}
		for k, v := range mr.Attribution {
			rep.Attribution[k] += v
		}
		if mr.MonitorCount > rep.MonitorCount {
			rep.MonitorCount = mr.MonitorCount
		}
		if mr.TotalChecks > 0 && mr.UptimePct > bestPct {
			bestPct, bestMonth = mr.UptimePct, mr.Month
		}
		if mr.TotalChecks > 0 && mr.UptimePct < worstPct {
			worstPct, worstMonth = mr.UptimePct, mr.Month
		}
	}
	if bestMonth == "" {
		bestMonth, worstMonth = rep.Items[0].Month, rep.Items[0].Month
	}
	if weightedChecks > 0 {
		rep.UptimePct = weightedSum / float64(weightedChecks)
	} else {
		rep.UptimePct = 100
	}
	rep.Met = rep.UptimePct >= rep.Target
	rep.BestMonth, rep.WorstMonth = bestMonth, worstMonth
	rep.AttributionPct = map[string]float64{}
	if rep.DownIncidents > 0 {
		for k, v := range rep.Attribution {
			rep.AttributionPct[k] = math.Round(float64(v)/float64(rep.DownIncidents)*100*10) / 10
		}
	}
	return rep, nil
}
