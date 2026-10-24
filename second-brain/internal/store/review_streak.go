package store

import (
	"database/sql"
	"time"
)

// ReviewStreak 复习连续记录
type ReviewStreak struct {
	CurrentStreak    int    `json:"currentStreak"`
	LongestStreak    int    `json:"longestStreak"`
	TotalDays        int    `json:"totalDays"`
	LastReviewedDate string `json:"lastReviewedDate"`
}

// ReviewStreak 获取指定用户的复习连续统计
func (s *Store) ReviewStreak(today time.Time, user string) (ReviewStreak, error) {
	var res ReviewStreak

	// currentStreak 复用 calcStreak 语义
	cs, err := s.calcStreak(today, user)
	if err != nil {
		return res, err
	}
	res.CurrentStreak = cs

	// 查询去重日期集合并按日期升序排列
	var rows *sql.Rows
	rows, err = s.db.Query("SELECT DISTINCT substr(last_reviewed_at, 1, 10) FROM reviews WHERE last_reviewed_at IS NOT NULL AND user_id = ? ORDER BY 1 ASC", NormalizeUser(user))
	if err != nil {
		return res, err
	}
	defer rows.Close()

	var dates []string
	for rows.Next() {
		var d string
		if err = rows.Scan(&d); err != nil {
			return res, err
		}
		dates = append(dates, d)
	}
	if err = rows.Err(); err != nil {
		return res, err
	}

	// totalDays 是集合大小
	res.TotalDays = len(dates)

	if len(dates) == 0 {
		// 无数据时为空字符串，longestStreak 为 0
		res.LastReviewedDate = ""
		res.LongestStreak = 0
		return res, nil
	}

	// lastReviewedDate 是集合最大值
	res.LastReviewedDate = dates[len(dates)-1]

	// longestStreak 按日历连续日计算，相邻两日差恰好1天才连续
	var longest, current int
	var prev time.Time
	for i, d := range dates {
		t, pErr := time.Parse("2006-01-02", d)
		if pErr != nil {
			return res, pErr
		}

		if i == 0 {
			current = 1
		} else {
			if t.Sub(prev) == 24*time.Hour {
				current++
			} else {
				current = 1
			}
		}

		if current > longest {
			longest = current
		}
		prev = t
	}
	res.LongestStreak = longest

	return res, nil
}
