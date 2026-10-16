package store

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"errors"
	"strings"
)

// ErrDuplicateSubscription 该邮箱已订阅此状态页。
var ErrDuplicateSubscription = errors.New("该邮箱已订阅此状态页")

// Subscription 对应 status_subscriptions 表的一行。
type Subscription struct {
	ID          int64
	PageID      int64
	Email       string
	Token       string
	Confirmed   int
	CreatedAt   string
	ConfirmedAt sql.NullString
}

// Subscriber 已确认订阅者（供通知扇出，含退订 token 与页面信息）。
type Subscriber struct {
	Email     string
	Token     string
	PageTitle string
	PageSlug  string
}

// NewSubscriptionToken 生成 32 字节随机 hex token。
func NewSubscriptionToken() (string, error) {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(b[:]), nil
}

// NormalizeEmail 规整邮箱：去首尾空格、转小写。
func NormalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

// ValidEmail 粗略校验邮箱格式：长度 3~254、恰含一个 @、@ 后有 dot、无空格。
func ValidEmail(email string) bool {
	if len(email) < 3 || len(email) > 254 {
		return false
	}
	if strings.Contains(email, " ") {
		return false
	}
	parts := strings.Split(email, "@")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return false
	}
	if !strings.Contains(parts[1], ".") {
		return false
	}
	return true
}

// CreateSubscription 创建待确认订阅。email 应先经 NormalizeEmail 处理。
// 同一 (page_id, email) 重复订阅返回 ErrDuplicateSubscription。
func (s *Store) CreateSubscription(pageID int64, email, token string) (int64, error) {
	res, err := s.db.Exec(
		`INSERT INTO status_subscriptions(page_id, email, token, confirmed, created_at) VALUES(?,?,?,?,?)`,
		pageID, email, token, 0, utcNow(),
	)
	if err != nil {
		if strings.Contains(err.Error(), "UNIQUE constraint failed") {
			return 0, ErrDuplicateSubscription
		}
		return 0, err
	}
	return res.LastInsertId()
}

// GetSubscriptionByToken 按 token 查询订阅，无记录返回 sql.ErrNoRows。
func (s *Store) GetSubscriptionByToken(token string) (Subscription, error) {
	var sub Subscription
	err := s.db.QueryRow(
		`SELECT id, page_id, email, token, confirmed, created_at, confirmed_at
		 FROM status_subscriptions WHERE token = ?`, token,
	).Scan(&sub.ID, &sub.PageID, &sub.Email, &sub.Token, &sub.Confirmed, &sub.CreatedAt, &sub.ConfirmedAt)
	if err != nil {
		return Subscription{}, err
	}
	return sub, nil
}

// GetSubscriptionByPageEmail 按 (page_id, email) 查询订阅，无记录返回 sql.ErrNoRows。
func (s *Store) GetSubscriptionByPageEmail(pageID int64, email string) (Subscription, error) {
	var sub Subscription
	err := s.db.QueryRow(
		`SELECT id, page_id, email, token, confirmed, created_at, confirmed_at
		 FROM status_subscriptions WHERE page_id = ? AND email = ?`, pageID, email,
	).Scan(&sub.ID, &sub.PageID, &sub.Email, &sub.Token, &sub.Confirmed, &sub.CreatedAt, &sub.ConfirmedAt)
	if err != nil {
		return Subscription{}, err
	}
	return sub, nil
}

// ConfirmSubscription 将待确认订阅置为已确认（幂等：已确认行不受影响但返回 sql.ErrNoRows）。
// token 无匹配返回 sql.ErrNoRows。
func (s *Store) ConfirmSubscription(token string) error {
	res, err := s.db.Exec(
		`UPDATE status_subscriptions SET confirmed = 1, confirmed_at = ? WHERE token = ? AND confirmed = 0`,
		utcNow(), token,
	)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// DeleteSubscriptionByToken 删除订阅（退订），无匹配返回 sql.ErrNoRows。
func (s *Store) DeleteSubscriptionByToken(token string) error {
	res, err := s.db.Exec(`DELETE FROM status_subscriptions WHERE token = ?`, token)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// ListPageIDsForMonitor 返回包含该 monitor 的状态页 ID 列表（升序）。
func (s *Store) ListPageIDsForMonitor(monitorID int64) ([]int64, error) {
	rows, err := s.db.Query(
		`SELECT page_id FROM status_page_monitors WHERE monitor_id = ? ORDER BY page_id ASC`, monitorID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, id)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// ListConfirmedSubscribers 返回某页所有已确认订阅者（含 token 与页面标题/slug），按 id 升序。
func (s *Store) ListConfirmedSubscribers(pageID int64) ([]Subscriber, error) {
	rows, err := s.db.Query(
		`SELECT s.email, s.token, p.title, p.slug
		 FROM status_subscriptions s JOIN status_pages p ON p.id = s.page_id
		 WHERE s.page_id = ? AND s.confirmed = 1 ORDER BY s.id ASC`, pageID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Subscriber
	for rows.Next() {
		var sub Subscriber
		if err := rows.Scan(&sub.Email, &sub.Token, &sub.PageTitle, &sub.PageSlug); err != nil {
			return nil, err
		}
		out = append(out, sub)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
