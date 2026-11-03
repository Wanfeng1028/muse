package store

import (
	"fmt"
	"math"
)

type SiteYearlySLAMonth struct {
	Month            string  `json:"month"`
	UptimePct        float64 `json:"uptime_pct"`
	TotalChecks      int     `json:"total_checks"`
	DownIncidents    int     `json:"down_incidents"`
	TotalDowntimeSec int64   `json:"total_downtime_sec"`
	Met              bool    `json:"met"`
	MonitorCount     int     `json:"monitor_count"`
	WorstMonitorName string  `json:"worst_monitor_name"`
}

type SiteYearlySLAReport struct {
	Year             int                  `json:"year"`
	Target           float64              `json:"sla_target"`
	UptimePct        float64              `json:"uptime_pct"`
	TotalChecks      int                  `json:"total_checks"`
	DownIncidents    int                  `json:"down_incidents"`
	TotalDowntimeSec int64                `json:"total_downtime_sec"`
	Met              bool                 `json:"met"`
	MonitorCount     int                  `json:"monitor_count"`
	BestMonth        string               `json:"best_month"`
	WorstMonth       string               `json:"worst_month"`
	Attribution      map[string]int       `json:"attribution"`
	AttributionPct   map[string]float64   `json:"attribution_pct"`
	Items            []SiteYearlySLAMonth `json:"items"`
}

func (s *Store) SiteYearlySLA(year int) (SiteYearlySLAReport, error) {
	if year < 1970 || year > 9999 {
		return SiteYearlySLAReport{}, fmt.Errorf("年份非法: %d", year)
	}
	rep := SiteYearlySLAReport{
		Year:        year,
		Target:      99.9,
		Attribution: make(map[string]int),
		Items:       make([]SiteYearlySLAMonth, 0, 12),
	}
	var weightedSum float64
	var weightedChecks int
	bestPct := -1.0
	worstPct := 101.0
	bestMonth := ""
	worstMonth := ""
	for m := 1; m <= 12; m++ {
		sr, err := s.SiteMonthlySLA(year, m)
		if err != nil {
			return SiteYearlySLAReport{}, err
		}
		rep.Items = append(rep.Items, SiteYearlySLAMonth{
			Month:            sr.Month,
			UptimePct:        sr.UptimePct,
			TotalChecks:      sr.TotalChecks,
			DownIncidents:    sr.DownIncidents,
			TotalDowntimeSec: sr.TotalDowntimeSec,
			Met:              sr.Met,
			MonitorCount:     sr.MonitorCount,
			WorstMonitorName: sr.WorstMonitorName,
		})
		rep.TotalChecks += sr.TotalChecks
		rep.DownIncidents += sr.DownIncidents
		rep.TotalDowntimeSec += sr.TotalDowntimeSec
		if sr.TotalChecks > 0 {
			weightedSum += sr.UptimePct * float64(sr.TotalChecks)
			weightedChecks += sr.TotalChecks
		}
		for k, v := range sr.Attribution {
			rep.Attribution[k] += v
		}
		if sr.MonitorCount > rep.MonitorCount {
			rep.MonitorCount = sr.MonitorCount
		}
		if sr.TotalChecks > 0 {
			if sr.UptimePct > bestPct {
				bestPct = sr.UptimePct
				bestMonth = sr.Month
			}
			if sr.UptimePct < worstPct {
				worstPct = sr.UptimePct
				worstMonth = sr.Month
			}
		}
	}
	if bestMonth == "" {
		bestMonth = rep.Items[0].Month
		worstMonth = rep.Items[0].Month
	}
	if weightedChecks > 0 {
		rep.UptimePct = weightedSum / float64(weightedChecks)
	} else {
		rep.UptimePct = 100
	}
	rep.Met = rep.UptimePct >= rep.Target
	rep.BestMonth = bestMonth
	rep.WorstMonth = worstMonth
	rep.AttributionPct = map[string]float64{}
	if rep.DownIncidents > 0 {
		for k, v := range rep.Attribution {
			rep.AttributionPct[k] = math.Round(float64(v)/float64(rep.DownIncidents)*100*10) / 10
		}
	}
	return rep, nil
}
