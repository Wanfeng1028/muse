package store

import (
	"database/sql"
	"math"
	"time"
)

// TimelineEvent 描述一次故障事件的起止。
type TimelineEvent struct {
	ID          int64  `json:"id"`
	StartedAt   string `json:"started_at"`
	EndedAt     any    `json:"ended_at"`
	DowntimeSec any    `json:"downtime_sec"`
	StartError  string `json:"start_error"`
	Open        bool   `json:"open"`
}

// IncidentTimeline 返回指定监控最近 days 天的故障时间线，按 started_at 倒序，最多 limit 条。
// days<=0 时取 30，limit<=0 时取 50，limit 上限 200。
func (s *Store) IncidentTimeline(monitorID int64, days int, limit int) ([]TimelineEvent, error) {
	if days <= 0 {
		days = 30
	}
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}
	since := time.Now().UTC().AddDate(0, 0, -days).Format(time.RFC3339)
	rows, err := s.db.Query(
		`SELECT id, started_at, ended_at, downtime_sec, start_error
		 FROM incidents
		 WHERE monitor_id = ? AND started_at >= ?
		 ORDER BY started_at DESC
		 LIMIT ?`,
		monitorID, since, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	events := []TimelineEvent{}
	for rows.Next() {
		var (
			ev      TimelineEvent
			endedAt sql.NullString
			downSec sql.NullInt64
		)
		if err := rows.Scan(&ev.ID, &ev.StartedAt, &endedAt, &downSec, &ev.StartError); err != nil {
			return nil, err
		}
		if endedAt.Valid {
			ev.EndedAt = endedAt.String
		}
		if downSec.Valid {
			ev.DowntimeSec = downSec.Int64
		}
		ev.Open = !endedAt.Valid
		events = append(events, ev)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return events, nil
}

// JitterScore 计算抖动评分：衡量单位时间内站点 up/down 翻转频率。
// 口径：相邻两次检查 ok 值发生一次变化记 1 次翻转；100 次检查内翻转 1 次以下视为稳定。
// 返回 score（0-100，保留 2 位小数）与 level。
func (s *Store) JitterScore(monitorID int64, days int) (score float64, level string, err error) {
	if days <= 0 {
		days = 7
	}
	since := time.Now().UTC().AddDate(0, 0, -days).Format(time.RFC3339)
	rows, err := s.db.Query(
		`SELECT ok FROM checks
		 WHERE monitor_id = ? AND checked_at >= ?
		 ORDER BY checked_at ASC
		 LIMIT 100000`,
		monitorID, since,
	)
	if err != nil {
		return 0, "", err
	}
	defer rows.Close()

	var prev sql.NullBool
	n := 0
	flaps := 0
	for rows.Next() {
		var ok bool
		if err := rows.Scan(&ok); err != nil {
			return 0, "", err
		}
		if prev.Valid && prev.Bool != ok {
			flaps++
		}
		prev = sql.NullBool{Bool: ok, Valid: true}
		n++
	}
	if err := rows.Err(); err != nil {
		return 0, "", err
	}
	if n < 2 {
		return 0, "数据不足", nil
	}
	raw := float64(flaps) / float64(n-1) * 100
	raw = math.Round(raw*100) / 100
	if raw > 100 {
		raw = 100
	}
	score = raw
	switch {
	case score < 1:
		level = "稳定"
	case score < 5:
		level = "轻微波动"
	case score < 20:
		level = "波动明显"
	default:
		level = "频繁抖动"
	}
	return score, level, nil
}

// MonitorPortrait 站点可用性画像 v1。
type MonitorPortrait struct {
	Uptime7d     float64         `json:"uptime_7d"`
	Uptime30d    float64         `json:"uptime_30d"`
	LatencyP50   float64         `json:"latency_p50"`
	LatencyP95   float64         `json:"latency_p95"`
	LatencyP99   float64         `json:"latency_p99"`
	JitterScore  float64         `json:"jitter_score"`
	JitterLevel  string          `json:"jitter_level"`
	Timeline     []TimelineEvent `json:"timeline"`
	Daily        []DayStat       `json:"daily"`
	Incidents30d int             `json:"incidents_30d"`
}

// MonitorPortrait 组装画像。MonitorStats/LatencyPercentiles/DailyBreakdown 的 err 忽略按零值处理；
// IncidentTimeline/JitterScore 的 err 向上传播。
func (s *Store) MonitorPortrait(monitorID int64) (MonitorPortrait, error) {
	var p MonitorPortrait

	up7, _, _, _, _ := s.MonitorStats(monitorID, 7)
	up30, _, _, inc30, _ := s.MonitorStats(monitorID, 30)
	p.Uptime7d = up7
	p.Uptime30d = up30
	p.Incidents30d = inc30

	p50, p95, p99, _ := s.LatencyPercentiles(monitorID, 30)
	p.LatencyP50 = p50
	p.LatencyP95 = p95
	p.LatencyP99 = p99

	js, jl, err := s.JitterScore(monitorID, 7)
	if err != nil {
		return MonitorPortrait{}, err
	}
	p.JitterScore = js
	p.JitterLevel = jl

	tl, err := s.IncidentTimeline(monitorID, 30, 50)
	if err != nil {
		return MonitorPortrait{}, err
	}
	p.Timeline = tl

	daily, _ := s.DailyBreakdown(monitorID, 30)
	if daily == nil {
		daily = []DayStat{}
	}
	p.Daily = daily

	return p, nil
}
