package store

import (
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/review"
)

// DueReview 待复习条目，包含笔记与复习状态信息
type DueReview struct {
	Note         Note    `json:"note"`
	EF           float64 `json:"ef"`
	IntervalDays int     `json:"intervalDays"`
	Repetitions  int     `json:"repetitions"`
	DueDate      string  `json:"dueDate"`
	OverdueDays  int     `json:"overdueDays"`
}

// ReviewStats 复习统计信息
type ReviewStats struct {
	DueToday   int     `json:"dueToday"`
	TotalNotes int     `json:"totalNotes"`
	Reviewed7d int     `json:"reviewed7d"`
	AvgEF      float64 `json:"avgEf"`
	StreakDays int     `json:"streakDays"`
}

// dateOnly 将 time.Time 格式化为 YYYY-MM-DD 文本，用于日期比较
func dateOnly(t time.Time) string {
	return t.Format("2006-01-02")
}

// parseDate 解析 YYYY-MM-DD 文本为 time.Time（UTC 零点）
func parseDate(s string) (time.Time, error) {
	return time.Parse("2006-01-02", s)
}

// GetReviewState 获取指定笔记的复习状态，无记录返回 ErrNotFound
func (s *Store) GetReviewState(noteID int64) (review.State, error) {
	var st review.State
	// 查询该笔记的复习状态
	err := s.db.QueryRow(
		`SELECT ef, interval_days, repetitions, due_date
		 FROM reviews WHERE note_id = ?`, noteID,
	).Scan(&st.EF, &st.IntervalDays, &st.Repetitions, &st.DueDate)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return review.State{}, ErrNotFound
		}
		return review.State{}, err
	}
	return st, nil
}

// RecordReview 记录一次复习，使用 review.Next 计算新状态并更新数据库
func (s *Store) RecordReview(noteID int64, grade int, today time.Time) (review.State, error) {
	// 校验 grade 合法性
	if grade < 0 || grade > 5 {
		return review.State{}, fmt.Errorf("无效的评分等级: %d", grade)
	}

	// 检查笔记是否存在
	var exists int
	err := s.db.QueryRow(`SELECT 1 FROM notes WHERE id = ?`, noteID).Scan(&exists)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return review.State{}, ErrNotFound
		}
		return review.State{}, err
	}

	// 获取当前状态，无记录则使用初始状态
	cur, err := s.GetReviewState(noteID)
	if err != nil && !errors.Is(err, ErrNotFound) {
		return review.State{}, err
	}
	if errors.Is(err, ErrNotFound) {
		cur = review.InitialState(today)
	}

	// 使用纯函数包计算新状态
	next := review.Next(cur, review.Grade(grade), today)

	// 更新（或插入）复习记录
	now := today.UTC().Format(time.RFC3339)
	_, err = s.db.Exec(
		`INSERT INTO reviews (note_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count)
		 VALUES (?, ?, ?, ?, ?, ?, 1)
		 ON CONFLICT(note_id) DO UPDATE SET
		   ef = excluded.ef,
		   interval_days = excluded.interval_days,
		   repetitions = excluded.repetitions,
		   due_date = excluded.due_date,
		   last_reviewed_at = excluded.last_reviewed_at,
		   reviewed_count = reviews.reviewed_count + 1`,
		noteID, next.EF, next.IntervalDays, next.Repetitions, next.DueDate, now,
	)
	if err != nil {
		return review.State{}, err
	}

	return next, nil
}

// ListDueReviews 列出到期需要复习的笔记（due_date <= today），附标签
func (s *Store) ListDueReviews(today time.Time, limit int) ([]DueReview, error) {
	if limit <= 0 {
		limit = 50
	}
	todayStr := dateOnly(today)

	// 查询到期复习记录并 JOIN 笔记
	rows, err := s.db.Query(
		`SELECT n.id, n.title, n.body, n.created_at, n.updated_at,
		        r.ef, r.interval_days, r.repetitions, r.due_date
		 FROM reviews r
		 JOIN notes n ON n.id = r.note_id
		 WHERE r.due_date <= ?
		 ORDER BY r.due_date ASC, r.interval_days ASC
		 LIMIT ?`, todayStr, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []DueReview
	type tmpRow struct {
		note Note
		dr   DueReview
	}
	var tmps []tmpRow
	for rows.Next() {
		var t tmpRow
		if err := rows.Scan(
			&t.note.ID, &t.note.Title, &t.note.Body, &t.note.CreatedAt, &t.note.UpdatedAt,
			&t.dr.EF, &t.dr.IntervalDays, &t.dr.Repetitions, &t.dr.DueDate,
		); err != nil {
			rows.Close()
			return nil, err
		}
		// 计算逾期天数（纯计算，不碰 DB）
		if due, perr := parseDate(t.dr.DueDate); perr == nil {
			days := int(today.Sub(due).Hours() / 24)
			if days < 0 {
				days = 0
			}
			t.dr.OverdueDays = days
		}
		tmps = append(tmps, t)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	// 第二阶段：rows 已关闭后再查标签（:memory: 下嵌套查询会换连接导致表不存在）
	ids := make([]int64, len(tmps))
	for i := range tmps {
		ids[i] = tmps[i].note.ID
	}
	tagMap, err := s.tagsForNotes(ids)
	if err != nil {
		return nil, err
	}
	for _, t := range tmps {
		if tags, ok := tagMap[t.note.ID]; ok {
			t.note.Tags = tags
		} else {
			t.note.Tags = []string{}
		}
		t.dr.Note = t.note
		result = append(result, t.dr)
	}
	return result, nil
}

// ReviewStats 计算复习统计数据
func (s *Store) ReviewStats(today time.Time) (ReviewStats, error) {
	var stats ReviewStats
	todayStr := dateOnly(today)

	// DueToday：到期（due <= today）计数
	if err := s.db.QueryRow(
		`SELECT COUNT(*) FROM reviews WHERE due_date <= ?`, todayStr,
	).Scan(&stats.DueToday); err != nil {
		return stats, err
	}

	// TotalNotes：笔记总数
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM notes`).Scan(&stats.TotalNotes); err != nil {
		return stats, err
	}

	// Reviewed7d：过去 7 天内复习过的去重笔记数
	sevenDaysAgo := today.AddDate(0, 0, -7).UTC().Format(time.RFC3339)
	if err := s.db.QueryRow(
		`SELECT COUNT(DISTINCT note_id) FROM reviews
		 WHERE last_reviewed_at IS NOT NULL AND last_reviewed_at >= ?`, sevenDaysAgo,
	).Scan(&stats.Reviewed7d); err != nil {
		return stats, err
	}

	// AvgEF：平均 EF 值，无数据为 0
	var avgEF sql.NullFloat64
	if err := s.db.QueryRow(`SELECT AVG(ef) FROM reviews`).Scan(&avgEF); err != nil {
		return stats, err
	}
	if avgEF.Valid {
		stats.AvgEF = avgEF.Float64
	}

	// StreakDays：连续复习天数
	streak, err := s.calcStreak(today)
	if err != nil {
		return stats, err
	}
	stats.StreakDays = streak

	return stats, nil
}

// calcStreak 计算从 today 起算的连续复习天数（含 today，未复习则从昨天起算）
func (s *Store) calcStreak(today time.Time) (int, error) {
	// 取出所有复习日期的去重集合（按日期倒序）
	rows, err := s.db.Query(
		`SELECT DISTINCT substr(last_reviewed_at, 1, 10) AS d
		 FROM reviews
		 WHERE last_reviewed_at IS NOT NULL
		 ORDER BY d DESC`,
	)
	if err != nil {
		return 0, err
	}
	defer rows.Close()

	dateSet := make(map[string]bool)
	for rows.Next() {
		var d string
		if err := rows.Scan(&d); err != nil {
			return 0, err
		}
		dateSet[d] = true
	}
	if err := rows.Err(); err != nil {
		return 0, err
	}

	// 从 today 开始，若 today 无复习则从昨天起算
	cursor := today
	if !dateSet[dateOnly(cursor)] {
		cursor = cursor.AddDate(0, 0, -1)
	}

	streak := 0
	for dateSet[dateOnly(cursor)] {
		streak++
		cursor = cursor.AddDate(0, 0, -1)
	}
	return streak, nil
}

// DigestNotes 摘要笔记：优先取到期笔记，不足则用从未复习/最久未复习的笔记补足
func (s *Store) DigestNotes(today time.Time, n int) ([]Note, error) {
	if n <= 0 {
		n = 50
	}
	todayStr := dateOnly(today)

	var result []Note

	// 1. 到期优先（due_date ASC）
	rows, err := s.db.Query(
		`SELECT n.id, n.title, n.body, n.created_at, n.updated_at
		 FROM reviews r
		 JOIN notes n ON n.id = r.note_id
		 WHERE r.due_date <= ?
		 ORDER BY r.due_date ASC
		 LIMIT ?`, todayStr, n,
	)
	if err != nil {
		return nil, err
	}
	seen := make(map[int64]bool)
	var dueNotes []Note
	for rows.Next() {
		var note Note
		if err := rows.Scan(&note.ID, &note.Title, &note.Body, &note.CreatedAt, &note.UpdatedAt); err != nil {
			rows.Close()
			return nil, err
		}
		dueNotes = append(dueNotes, note)
		seen[note.ID] = true
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	// rows 已关闭后再批量查标签（:memory: 下嵌套查询会换连接）
	dueNotes, err = s.fillTags(dueNotes)
	if err != nil {
		return nil, err
	}
	result = append(result, dueNotes...)

	// 2. 若不足，补足未在结果中的笔记，按 last_reviewed_at ASC NULLS FIRST
	remaining := n - len(result)
	if remaining > 0 {
		rows2, err := s.db.Query(
			`SELECT n.id, n.title, n.body, n.created_at, n.updated_at
			 FROM notes n
			 LEFT JOIN reviews r ON r.note_id = n.id
			 ORDER BY r.last_reviewed_at IS NOT NULL ASC, r.last_reviewed_at ASC
			 LIMIT ?`, remaining+len(seen),
		)
		if err != nil {
			return nil, err
		}

		var extra []Note
		for rows2.Next() && len(result)+len(extra) < n {
			var note Note
			if err := rows2.Scan(&note.ID, &note.Title, &note.Body, &note.CreatedAt, &note.UpdatedAt); err != nil {
				rows2.Close()
				return nil, err
			}
			if seen[note.ID] {
				continue
			}
			seen[note.ID] = true
			extra = append(extra, note)
		}
		if err := rows2.Err(); err != nil {
			rows2.Close()
			return nil, err
		}
		rows2.Close()

		extra, err = s.fillTags(extra)
		if err != nil {
			return nil, err
		}
		result = append(result, extra...)
	}

	return result, nil
}

// fillTags 批量填充笔记的标签（复用 store.go 的 tagsForNotes，避免 N+1 查询）。
func (s *Store) fillTags(notes []Note) ([]Note, error) {
	if len(notes) == 0 {
		return notes, nil
	}
	ids := make([]int64, len(notes))
	for i := range notes {
		ids[i] = notes[i].ID
	}
	tagMap, err := s.tagsForNotes(ids)
	if err != nil {
		return nil, err
	}
	for i := range notes {
		if tags, ok := tagMap[notes[i].ID]; ok {
			notes[i].Tags = tags
		} else {
			notes[i].Tags = []string{}
		}
	}
	return notes, nil
}
