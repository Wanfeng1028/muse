package store

import "time"

// ListOverdueReviews 列出指定用户已逾期需要复习的笔记（due_date < today，今天到期不算），附标签
func (s *Store) ListOverdueReviews(today time.Time, limit int, user string) ([]DueReview, error) {
	user = NormalizeUser(user)
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}
	todayStr := dateOnly(today)
	rows, err := s.db.Query(
		`SELECT n.id, n.title, n.body, n.created_at, n.updated_at,
		        r.ef, r.interval_days, r.repetitions, r.due_date
		 FROM reviews r
		 JOIN notes n ON n.id = r.note_id
		 WHERE r.due_date < ? AND r.user_id = ?
		 ORDER BY r.due_date ASC, r.interval_days ASC
		 LIMIT ?`, todayStr, user, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []DueReview{}
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
