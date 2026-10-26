package store

import (
	"database/sql"
	"errors"
	"fmt"
	"math"
)

type GroupSLAReport struct {
	GroupID          int64               `json:"group_id"`
	GroupName        string              `json:"group_name"`
	Month            string              `json:"month"`
	UptimePct        float64             `json:"uptime_pct"`
	TotalChecks      int                 `json:"total_checks"`
	DownIncidents    int                 `json:"down_incidents"`
	TotalDowntimeSec int64               `json:"total_downtime_sec"`
	Target           float64             `json:"sla_target"`
	Met              bool                `json:"met"`
	MonitorCount     int                 `json:"monitor_count"`
	WorstMonitorID   int64               `json:"worst_monitor_id"`
	WorstMonitorName string              `json:"worst_monitor_name"`
	Attribution      map[string]int      `json:"attribution"`
	AttributionPct   map[string]float64  `json:"attribution_pct"`
	Monitors         []SiteSLAMonitorRow `json:"monitors"`
}

func (s *Store) GroupMonthlySLA(groupID int64, year, month int) (GroupSLAReport, error) {
	rep := GroupSLAReport{
		Month:       fmt.Sprintf("%04d-%02d", year, month),
		Target:      99.9,
		Attribution: map[string]int{},
		Monitors:    []SiteSLAMonitorRow{},
	}
	if month < 1 || month > 12 {
		return rep, fmt.Errorf("非法月份: %d", month)
	}
	var groupName string
	err := s.db.QueryRow("SELECT name FROM monitor_groups WHERE id = ?", groupID).Scan(&groupName)
	if err == sql.ErrNoRows {
		return rep, errors.New("分组不存在")
	}
	if err != nil {
		return rep, err
	}
	rep.GroupID = groupID
	rep.GroupName = groupName
	members, err := s.ListGroupMonitors(groupID)
	if err != nil {
		return rep, err
	}
	rep.MonitorCount = len(members)
	var weightedSum float64
	var weightedChecks int
	for _, m := range members {
		r, err := s.MonthlySLA(m.ID, year, month)
		if err != nil {
			return rep, err
		}
		rep.Monitors = append(rep.Monitors, SiteSLAMonitorRow{
			MonitorID:        m.ID,
			Name:             m.Name,
			Target:           m.Target,
			UptimePct:        r.UptimePct,
			TotalChecks:      r.TotalChecks,
			DownIncidents:    r.DownIncidents,
			TotalDowntimeSec: r.TotalDowntimeSec,
			Met:              r.Met,
		})
		rep.TotalChecks += r.TotalChecks
		rep.DownIncidents += r.DownIncidents
		rep.TotalDowntimeSec += r.TotalDowntimeSec
		if r.TotalChecks > 0 {
			weightedSum += r.UptimePct * float64(r.TotalChecks)
			weightedChecks += r.TotalChecks
		}
		for k, v := range r.Attribution {
			rep.Attribution[k] += v
		}
	}
	if weightedChecks > 0 {
		rep.UptimePct = weightedSum / float64(weightedChecks)
	} else {
		rep.UptimePct = 100
	}
	rep.Met = rep.UptimePct >= rep.Target
	rep.AttributionPct = map[string]float64{}
	if rep.DownIncidents > 0 {
		for k, v := range rep.Attribution {
			rep.AttributionPct[k] = math.Round(float64(v)/float64(rep.DownIncidents)*100*10) / 10
		}
	}
	worst := 101.0
	for _, row := range rep.Monitors {
		if row.UptimePct < worst {
			worst = row.UptimePct
			rep.WorstMonitorID = row.MonitorID
			rep.WorstMonitorName = row.Name
		}
	}
	return rep, nil
}
