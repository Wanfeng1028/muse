package store

import (
	"database/sql"
	"fmt"
	"time"
)

// EFBucket EF 分布区间
type EFBucket struct {
	Label string `json:"label"`
	Count int    `json:"count"`
}

// HealthAttention 需要关注的卡片
type HealthAttention struct {
	NoteID        int64   `json:"noteId"`
	Title         string  `json:"title"`
	EF            float64 `json:"ef"`
	DueDate       string  `json:"dueDate"`
	OverdueDays   int     `json:"overdueDays"`
	ReviewedCount int     `json:"reviewedCount"`
	Reason        string  `json:"reason"`
	ReasonText    string  `json:"reasonText"`
}

// ReviewHealth 复习健康度报告
type ReviewHealth struct {
	AsOf          string            `json:"asOf"`
	Total         int               `json:"total"`
	DueNow        int               `json:"dueNow"`
	Overdue7d     int               `json:"overdue7d"`
	NeverReviewed int               `json:"neverReviewed"`
	AvgEF         float64           `json:"avgEf"`
	EFBuckets     []EFBucket        `json:"efBuckets"`
	Attention     []HealthAttention `json:"attention"`
	Advice        []string          `json:"advice"`
}

// ReviewHealth 生成指定用户的复习健康度报告
func (s *Store) ReviewHealth(today time.Time, user string) (ReviewHealth, error) {
	user = NormalizeUser(user)
	todayStr := dateOnly(today)
	var rh ReviewHealth
	rh.AsOf = todayStr

	// ---- 汇总统计 ----

	// 总卡片数
	err := s.db.QueryRow(
		"SELECT COUNT(*) FROM reviews WHERE user_id = ?", user,
	).Scan(&rh.Total)
	if err != nil {
		return rh, err
	}

	// 今日到期数
	err = s.db.QueryRow(
		"SELECT COUNT(*) FROM reviews WHERE user_id = ? AND due_date <= ?", user, todayStr,
	).Scan(&rh.DueNow)
	if err != nil {
		return rh, err
	}

	// 逾期超过7天的数量
	overdue7dDate := dateOnly(today.AddDate(0, 0, -6))
	err = s.db.QueryRow(
		"SELECT COUNT(*) FROM reviews WHERE user_id = ? AND due_date <= ?", user, overdue7dDate,
	).Scan(&rh.Overdue7d)
	if err != nil {
		return rh, err
	}

	// 从未复习过的数量
	err = s.db.QueryRow(
		"SELECT COUNT(*) FROM reviews WHERE user_id = ? AND last_reviewed_at IS NULL", user,
	).Scan(&rh.NeverReviewed)
	if err != nil {
		return rh, err
	}

	// 平均 EF
	var avgEF sql.NullFloat64
	err = s.db.QueryRow(
		"SELECT AVG(ef) FROM reviews WHERE user_id = ?", user,
	).Scan(&avgEF)
	if err != nil {
		return rh, err
	}
	if avgEF.Valid {
		rh.AvgEF = avgEF.Float64
	}

	// ---- EF 分档 ----
	bucketDefs := [4]struct {
		label string
		cond  string
	}{
		{"1.5以下", "ef <= 1.5"},
		{"1.5到2.0", "ef > 1.5 AND ef <= 2.0"},
		{"2.0到2.5", "ef > 2.0 AND ef <= 2.5"},
		{"2.5以上", "ef > 2.5"},
	}
	rh.EFBuckets = make([]EFBucket, 0, 4)
	for _, bd := range bucketDefs {
		var cnt int
		q := fmt.Sprintf("SELECT COUNT(*) FROM reviews WHERE user_id = ? AND %s", bd.cond)
		err = s.db.QueryRow(q, user).Scan(&cnt)
		if err != nil {
			return rh, err
		}
		rh.EFBuckets = append(rh.EFBuckets, EFBucket{Label: bd.label, Count: cnt})
	}

	// ---- 需要关注的卡片 ----
	rows, err := s.db.Query(
		"SELECT n.id, n.title, r.ef, r.due_date, r.reviewed_count, r.last_reviewed_at "+
			"FROM reviews r JOIN notes n ON n.id = r.note_id WHERE r.user_id = ?", user,
	)
	if err != nil {
		return rh, err
	}
	defer rows.Close()

	// 30天前的日期字符串，用于判断 never_reviewed_long
	neverLongDate := dateOnly(today.AddDate(0, 0, -30))

	var candidates []HealthAttention

	for rows.Next() {
		var noteID int64
		var title string
		var ef float64
		var dueDate string
		var reviewedCount int
		var lastReviewedAt sql.NullString

		err = rows.Scan(&noteID, &title, &ef, &dueDate, &reviewedCount, &lastReviewedAt)
		if err != nil {
			return rh, err
		}

		// 解析到期日期，计算逾期天数
		parsedDue, pErr := parseDate(dueDate)
		if pErr != nil {
			continue
		}
		overdueDays := int(today.Sub(parsedDue).Hours() / 24)

		// 三种关注条件，优先级：efFloor > neverLong > overdueLong
		var reason, reasonText string
		matched := false

		efFloor := reviewedCount >= 2 && ef <= 1.35
		overdueLong := dueDate <= overdue7dDate
		neverLong := !lastReviewedAt.Valid && dueDate < neverLongDate

		if efFloor {
			reason = "ef_floor"
			reasonText = fmt.Sprintf("记了%d次还是记不住，EF已经贴到底了", reviewedCount)
			matched = true
		} else if neverLong {
			reason = "never_reviewed_long"
			reasonText = "建好超过30天，一次都没复习过"
			matched = true
		} else if overdueLong {
			reason = "overdue_long"
			reasonText = fmt.Sprintf("已经%d天没复习了", overdueDays)
			matched = true
		}

		if !matched {
			continue
		}

		candidates = append(candidates, HealthAttention{
			NoteID:        noteID,
			Title:         title,
			EF:            ef,
			DueDate:       dueDate,
			OverdueDays:   overdueDays,
			ReviewedCount: reviewedCount,
			Reason:        reason,
			ReasonText:    reasonText,
		})
	}
	if err = rows.Err(); err != nil {
		return rh, err
	}

	// 排序：overdueDays 降序，ef 升序（手动选择排序，避免额外 import）
	for i := 0; i < len(candidates); i++ {
		for j := i + 1; j < len(candidates); j++ {
			swap := false
			if candidates[i].OverdueDays < candidates[j].OverdueDays {
				swap = true
			} else if candidates[i].OverdueDays == candidates[j].OverdueDays &&
				candidates[i].EF > candidates[j].EF {
				swap = true
			}
			if swap {
				candidates[i], candidates[j] = candidates[j], candidates[i]
			}
		}
	}

	// 取前20条，保证非 nil 空切片
	rh.Attention = make([]HealthAttention, 0)
	limit := 20
	if len(candidates) < limit {
		limit = len(candidates)
	}
	for i := 0; i < limit; i++ {
		rh.Attention = append(rh.Attention, candidates[i])
	}

	// ---- 建议大白话 ----
	// 统计 ef_floor 的总数量（从全部候选，而非截断后的前20）
	nFloor := 0
	for _, c := range candidates {
		if c.Reason == "ef_floor" {
			nFloor++
		}
	}

	rh.Advice = make([]string, 0)
	if nFloor > 0 {
		rh.Advice = append(rh.Advice,
			fmt.Sprintf("有%d张卡记了多次还是记不住，建议把内容拆小一点，或者换个问法重写一遍再记", nFloor))
	}
	if rh.Overdue7d > 0 {
		rh.Advice = append(rh.Advice,
			fmt.Sprintf("有%d张卡逾期超过7天了，先把逾期的清完再记新的", rh.Overdue7d))
	}
	if rh.NeverReviewed > 0 {
		rh.Advice = append(rh.Advice,
			fmt.Sprintf("有%d张卡建好后一次都没复习过，顺手过一遍", rh.NeverReviewed))
	}
	if rh.DueNow == 0 && rh.Total > 0 {
		rh.Advice = append(rh.Advice, "今天没有到期的卡，状态不错")
	}
	if rh.Total == 0 {
		rh.Advice = append(rh.Advice, "还没有复习数据，先去记几条笔记")
	}

	return rh, nil
}
