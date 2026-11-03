package store

import (
	"time"
)

type ForecastDay struct {
	Date string `json:"date"`
	Due  int    `json:"due"`
}

type ReviewForecast struct {
	Days     int           `json:"days"`
	Overdue  int           `json:"overdue"`
	Total    int           `json:"total"`
	Forecast []ForecastDay `json:"forecast"`
}

func (s *Store) ReviewForecast(today time.Time, user string, days int) (ReviewForecast, error) {
	if days <= 0 {
		days = 7
	}
	if days > 30 {
		days = 30
	}

	u := NormalizeUser(user)

	baseStr := dateOnly(today)
	base, err := parseDate(baseStr)
	if err != nil {
		return ReviewForecast{}, err
	}

	var overdue int
	err = s.db.QueryRow(
		"SELECT COUNT(*) FROM reviews WHERE due_date < ? AND user_id = ?",
		baseStr, u,
	).Scan(&overdue)
	if err != nil {
		return ReviewForecast{}, err
	}

	endExclusive := base.AddDate(0, 0, days)
	endStr := dateOnly(endExclusive)

	rows, err := s.db.Query(
		"SELECT due_date, COUNT(*) FROM reviews WHERE user_id = ? AND due_date >= ? AND due_date < ? GROUP BY due_date",
		u, baseStr, endStr,
	)
	if err != nil {
		return ReviewForecast{}, err
	}
	defer rows.Close()

	countMap := make(map[string]int)
	for rows.Next() {
		var d string
		var c int
		if err := rows.Scan(&d, &c); err != nil {
			return ReviewForecast{}, err
		}
		countMap[d] = c
	}
	if err := rows.Err(); err != nil {
		return ReviewForecast{}, err
	}

	forecast := make([]ForecastDay, days)
	var dueSum int
	for i := 0; i < days; i++ {
		d := base.AddDate(0, 0, i)
		ds := dateOnly(d)
		cnt := countMap[ds]
		forecast[i] = ForecastDay{Date: ds, Due: cnt}
		dueSum += cnt
	}

	return ReviewForecast{
		Days:     days,
		Overdue:  overdue,
		Total:    overdue + dueSum,
		Forecast: forecast,
	}, nil
}
