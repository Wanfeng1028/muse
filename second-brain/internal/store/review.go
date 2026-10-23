package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"

	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
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

// GetReviewState 获取指定用户指定笔记的复习状态，无记录返回 ErrNotFound
func (s *Store) GetReviewState(noteID int64, user string) (review.State, error) {
	user = NormalizeUser(user)
	var st review.State
	// 查询该用户该笔记的复习状态
	err := s.db.QueryRow(
		`SELECT ef, interval_days, repetitions, due_date
		 FROM reviews WHERE note_id = ? AND user_id = ?`, noteID, user,
	).Scan(&st.EF, &st.IntervalDays, &st.Repetitions, &st.DueDate)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return review.State{}, ErrNotFound
		}
		return review.State{}, err
	}
	return st, nil
}

// RecordReview 记录一次复习，使用 review.Next 计算新状态并更新数据库。ctx 用于携带 request_id 做全链路日志。
func (s *Store) RecordReview(ctx context.Context, noteID int64, grade int, today time.Time, user string) (review.State, error) {
	user = NormalizeUser(user)
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

	// 获取当前用户当前状态，无记录则使用初始状态
	cur, err := s.GetReviewState(noteID, user)
	if err != nil && !errors.Is(err, ErrNotFound) {
		return review.State{}, err
	}
	if errors.Is(err, ErrNotFound) {
		cur = review.InitialState(today)
	}

	// 使用纯函数包计算新状态
	next := review.Next(cur, review.Grade(grade), today)

	// 困难卡片联动：已标记困难的卡片打出"困难"(grade=3)时，间隔减半（至少 1 天），
	// 到期日按新间隔重算。GetHardMark 出错时不阻断正常复习流程（降级为无惩罚）。
	if grade == int(review.GradeHard) {
		if hard, herr := s.GetHardMark(noteID, user); herr == nil && hard {
			next.IntervalDays = next.IntervalDays / 2
			if next.IntervalDays < 1 {
				next.IntervalDays = 1
			}
			next.DueDate = today.UTC().AddDate(0, 0, next.IntervalDays).Format("2006-01-02")
		}
	}

	// 更新（或插入）复习记录
	now := today.UTC().Format(time.RFC3339)
	_, err = s.db.Exec(
		`INSERT INTO reviews (note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count, is_hard)
		 VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
		 ON CONFLICT(note_id, user_id) DO UPDATE SET
		   ef = excluded.ef,
		   interval_days = excluded.interval_days,
		   repetitions = excluded.repetitions,
		   due_date = excluded.due_date,
		   last_reviewed_at = excluded.last_reviewed_at,
		   reviewed_count = reviews.reviewed_count + 1`,
		noteID, user, next.EF, next.IntervalDays, next.Repetitions, next.DueDate, now,
	)
	if err != nil {
		return review.State{}, err
	}

	logpkg.RequestLogger(ctx).Info("store.review_recorded",
		"note_id", noteID, "grade", grade, "user", user,
		"interval_days", next.IntervalDays, "due_date", next.DueDate)
	return next, nil
}

// ListDueReviews 列出指定用户到期需要复习的笔记（due_date <= today），附标签
func (s *Store) ListDueReviews(today time.Time, limit int, user string) ([]DueReview, error) {
	user = NormalizeUser(user)
	if limit <= 0 {
		limit = 50
	}
	todayStr := dateOnly(today)

	// 查询该用户到期复习记录并 JOIN 笔记
	rows, err := s.db.Query(
		`SELECT n.id, n.title, n.body, n.created_at, n.updated_at,
		        r.ef, r.interval_days, r.repetitions, r.due_date
		 FROM reviews r
		 JOIN notes n ON n.id = r.note_id
		 WHERE r.due_date <= ? AND r.user_id = ?
		 ORDER BY r.due_date ASC, r.interval_days ASC
		 LIMIT ?`, todayStr, user, limit,
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

// ReviewStats 计算指定用户的复习统计数据
func (s *Store) ReviewStats(today time.Time, user string) (ReviewStats, error) {
	user = NormalizeUser(user)
	var stats ReviewStats
	todayStr := dateOnly(today)

	// DueToday：该用户到期（due <= today）计数
	if err := s.db.QueryRow(
		`SELECT COUNT(*) FROM reviews WHERE due_date <= ? AND user_id = ?`, todayStr, user,
	).Scan(&stats.DueToday); err != nil {
		return stats, err
	}

	// TotalNotes：笔记总数（笔记全局共享，不按用户过滤）
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM notes`).Scan(&stats.TotalNotes); err != nil {
		return stats, err
	}

	// Reviewed7d：该用户过去 7 天内复习过的去重笔记数
	sevenDaysAgo := today.AddDate(0, 0, -7).UTC().Format(time.RFC3339)
	if err := s.db.QueryRow(
		`SELECT COUNT(DISTINCT note_id) FROM reviews
		 WHERE last_reviewed_at IS NOT NULL AND last_reviewed_at >= ? AND user_id = ?`, sevenDaysAgo, user,
	).Scan(&stats.Reviewed7d); err != nil {
		return stats, err
	}

	// AvgEF：该用户平均 EF 值，无数据为 0
	var avgEF sql.NullFloat64
	if err := s.db.QueryRow(`SELECT AVG(ef) FROM reviews WHERE user_id = ?`, user).Scan(&avgEF); err != nil {
		return stats, err
	}
	if avgEF.Valid {
		stats.AvgEF = avgEF.Float64
	}

	// StreakDays：连续复习天数
	streak, err := s.calcStreak(today, user)
	if err != nil {
		return stats, err
	}
	stats.StreakDays = streak

	return stats, nil
}

// calcStreak 计算指定用户从 today 起算的连续复习天数（含 today，未复习则从昨天起算）
func (s *Store) calcStreak(today time.Time, user string) (int, error) {
	user = NormalizeUser(user)
	// 取出该用户所有复习日期的去重集合（按日期倒序）
	rows, err := s.db.Query(
		`SELECT DISTINCT substr(last_reviewed_at, 1, 10) AS d
		 FROM reviews
		 WHERE last_reviewed_at IS NOT NULL AND user_id = ?
		 ORDER BY d DESC`, user,
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

// DayTrend 单日复习趋势
type DayTrend struct {
	Date     string `json:"date"`
	Reviewed int    `json:"reviewed"`
	Added    int    `json:"added"`
}

// ReviewTrend 返回最近 days 天（含 today）的每日复习趋势，按日期升序排列。
// days<=0 时默认 7 天，days>60 时钳制为 60 天。
// 日期口径统一按 UTC 计算（与 dateOnly 一致，不做时区转换）。
// Reviewed 为该用户在指定 UTC 日期复习过的去重笔记数；
// Added 为指定 UTC 日期创建的笔记数（笔记全局共享，不按用户过滤）。
func (s *Store) ReviewTrend(today time.Time, user string, days int) ([]DayTrend, error) {
	if days <= 0 {
		days = 7
	}
	if days > 60 {
		days = 60
	}
	return s.reviewTrendCore(today, NormalizeUser(user), days)
}

// DigestNotes 摘要指定用户的笔记：优先取到期笔记，不足则用从未复习/最久未复习的笔记补足
func (s *Store) DigestNotes(today time.Time, n int, user string) ([]Note, error) {
	user = NormalizeUser(user)
	if n <= 0 {
		n = 50
	}
	todayStr := dateOnly(today)

	var result []Note

	// 1. 该用户到期优先（due_date ASC）
	rows, err := s.db.Query(
		`SELECT n.id, n.title, n.body, n.created_at, n.updated_at
		 FROM reviews r
		 JOIN notes n ON n.id = r.note_id
		 WHERE r.due_date <= ? AND r.user_id = ?
		 ORDER BY r.due_date ASC
		 LIMIT ?`, todayStr, user, n,
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

	// 2. 若不足，补足未在结果中的笔记，按该用户 last_reviewed_at ASC NULLS FIRST
	remaining := n - len(result)
	if remaining > 0 {
		rows2, err := s.db.Query(
			`SELECT n.id, n.title, n.body, n.created_at, n.updated_at
			 FROM notes n
			 LEFT JOIN reviews r ON r.note_id = n.id AND r.user_id = ?
			 ORDER BY r.last_reviewed_at IS NOT NULL ASC, r.last_reviewed_at ASC
			 LIMIT ?`, user, remaining+len(seen),
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

// SetHardMark 设置或取消某条笔记的"困难卡片"标记。
// 笔记不存在返回 ErrNotFound。无复习记录时先插入初始状态行再置标记，
// 不调用 RecordReview，避免推进 SM-2 状态。
func (s *Store) SetHardMark(noteID int64, user string, hard bool) error {
	user = NormalizeUser(user)

	var exists int
	err := s.db.QueryRow(`SELECT 1 FROM notes WHERE id = ?`, noteID).Scan(&exists)
	if err == sql.ErrNoRows {
		return ErrNotFound
	}
	if err != nil {
		return err
	}

	hardVal := 0
	if hard {
		hardVal = 1
	}

	now := time.Now().UTC()
	dueDate := now.AddDate(0, 0, 1).Format("2006-01-02")

	_, err = s.db.Exec(
		`INSERT INTO reviews (note_id, user_id, ef, interval_days, repetitions, due_date, last_reviewed_at, reviewed_count, is_hard)
		 VALUES (?, ?, 2.5, 0, 0, ?, NULL, 0, ?)
		 ON CONFLICT(note_id, user_id) DO UPDATE SET
		   is_hard = excluded.is_hard`,
		noteID, user, dueDate, hardVal,
	)
	if err != nil {
		return err
	}
	return nil
}

// GetHardMark 返回某条笔记的"困难卡片"标记。
// 无复习记录时返回 (false, nil)，不返回 ErrNotFound。
func (s *Store) GetHardMark(noteID int64, user string) (bool, error) {
	user = NormalizeUser(user)

	var isHard int
	err := s.db.QueryRow(
		`SELECT is_hard FROM reviews WHERE note_id = ? AND user_id = ?`,
		noteID, user,
	).Scan(&isHard)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return isHard != 0, nil
}

// ListHardNotes 返回被标记为困难的笔记，按 last_reviewed_at ASC 排序（NULL 最前）。
// limit <= 0 时默认 50。
func (s *Store) ListHardNotes(user string, limit int) ([]Note, error) {
	user = NormalizeUser(user)
	if limit <= 0 {
		limit = 50
	}

	rows, err := s.db.Query(
		`SELECT n.id, n.title, n.body, n.created_at, n.updated_at
		 FROM reviews r
		 JOIN notes n ON n.id = r.note_id
		 WHERE r.user_id = ? AND r.is_hard = 1
		 ORDER BY r.last_reviewed_at ASC
		 LIMIT ?`,
		user, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var notes []Note
	for rows.Next() {
		var n Note
		if err := rows.Scan(&n.ID, &n.Title, &n.Body, &n.CreatedAt, &n.UpdatedAt); err != nil {
			return nil, err
		}
		notes = append(notes, n)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(notes) == 0 {
		return []Note{}, nil
	}
	return s.fillTags(notes)
}

// HardMarkMap 批量查询指定笔记在当前用户下是否被标记为困难。
// ids 为空时直接返回空 map，不查库。返回 map 中仅包含 is_hard=1 的 note_id。
func (s *Store) HardMarkMap(ids []int64, user string) (map[int64]bool, error) {
	out := make(map[int64]bool)
	if len(ids) == 0 {
		return out, nil
	}
	u := NormalizeUser(user)
	placeholders := make([]string, 0, len(ids))
	args := make([]interface{}, 0, len(ids)+1)
	args = append(args, u)
	for _, id := range ids {
		placeholders = append(placeholders, "?")
		args = append(args, id)
	}
	query := "SELECT note_id FROM reviews WHERE user_id=? AND is_hard=1 AND note_id IN (" +
		strings.Join(placeholders, ",") + ")"
	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out[id] = true
	}
	return out, rows.Err()
}

// TagMastery 表示某标签下的复习掌握度统计。
type TagMastery struct {
	Tag   string  `json:"tag"`
	Total int     `json:"total"`
	AvgEF float64 `json:"avgEf"`
	Hard  int     `json:"hard"`
	Due   int     `json:"due"`
}

// ReviewMastery 按标签聚合当前用户的复习掌握度。
// 口径：INNER JOIN reviews，只统计该用户有复习记录的卡片；无标签笔记不计入；
// Total=0 的标签不出现。按 Total DESC 排序。
func (s *Store) ReviewMastery(today time.Time, user string) ([]TagMastery, error) {
	u := NormalizeUser(user)
	todayStr := dateOnly(today)
	rows, err := s.db.Query(`
SELECT t.name,
       COUNT(DISTINCT r.note_id) AS total,
       AVG(r.ef) AS avg_ef,
       SUM(r.is_hard) AS hard,
       SUM(CASE WHEN r.due_date <= ? THEN 1 ELSE 0 END) AS due
FROM tags t
JOIN note_tags nt ON nt.tag_id = t.id
JOIN notes n ON n.id = nt.note_id
JOIN reviews r ON r.note_id = n.id AND r.user_id = ?
GROUP BY t.id, t.name
HAVING COUNT(DISTINCT r.note_id) > 0
ORDER BY total DESC, t.name ASC
`, todayStr, u)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []TagMastery{}
	for rows.Next() {
		var m TagMastery
		if err := rows.Scan(&m.Tag, &m.Total, &m.AvgEF, &m.Hard, &m.Due); err != nil {
			return nil, err
		}
		m.AvgEF = math.Round(m.AvgEF*100) / 100
		out = append(out, m)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
