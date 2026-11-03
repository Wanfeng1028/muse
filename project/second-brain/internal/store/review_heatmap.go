package store

import (
	"time"
)

// ReviewHeatmap 返回最近 days 天（含 today）的每日热力图数据，按日期升序排列。
// days<=0 时默认 365 天，days>366 时钳制为 366 天。
// UTC 日期；复习数按用户过滤去重；新增数全局不按用户过滤。
func (s *Store) ReviewHeatmap(today time.Time, user string, days int) ([]DayTrend, error) {
	if days <= 0 {
		days = 365
	}
	if days > 366 {
		days = 366
	}
	return s.reviewTrendCore(today, NormalizeUser(user), days)
}

func (s *Store) reviewTrendCore(today time.Time, user string, days int) ([]DayTrend, error) {
	user = NormalizeUser(user)

	// 计算日期列表（升序，老→新）
	dates := make([]string, 0, days)
	byDate := make(map[string]*DayTrend, days)
	for i := days - 1; i >= 0; i-- {
		d := dateOnly(today.AddDate(0, 0, -i))
		dates = append(dates, d)
		byDate[d] = &DayTrend{Date: d}
	}
	start := dates[0]

	// 复习数：按用户过滤，substr 取 UTC 日期
	reviewRows, err := s.db.Query(
		`SELECT substr(last_reviewed_at,1,10) AS d, COUNT(DISTINCT note_id)
		 FROM reviews
		 WHERE user_id = ? AND substr(last_reviewed_at,1,10) >= ?
		 GROUP BY d`, user, start)
	if err != nil {
		return nil, err
	}
	defer reviewRows.Close()
	for reviewRows.Next() {
		var d string
		var n int
		if err := reviewRows.Scan(&d, &n); err != nil {
			return nil, err
		}
		if row, ok := byDate[d]; ok {
			row.Reviewed = n
		}
	}
	if err := reviewRows.Err(); err != nil {
		return nil, err
	}

	// 新增数：笔记全局共享，不按用户过滤
	noteRows, err := s.db.Query(
		`SELECT substr(created_at,1,10) AS d, COUNT(*)
		 FROM notes
		 WHERE substr(created_at,1,10) >= ?
		 GROUP BY d`, start)
	if err != nil {
		return nil, err
	}
	defer noteRows.Close()
	for noteRows.Next() {
		var d string
		var n int
		if err := noteRows.Scan(&d, &n); err != nil {
			return nil, err
		}
		if row, ok := byDate[d]; ok {
			row.Added = n
		}
	}
	if err := noteRows.Err(); err != nil {
		return nil, err
	}

	out := make([]DayTrend, 0, days)
	for _, d := range dates {
		out = append(out, *byDate[d])
	}
	return out, nil
}
