package store

import (
	"database/sql"
	"fmt"
	"strings"
)

// PushSubscription 表示一条 Web Push 订阅记录。
// p256dh 与 auth 为客户端密钥，store 层原样存取，脱敏由 API 层负责。
type PushSubscription struct {
	ID        int64  `json:"id"`
	User      string `json:"user"`
	Endpoint  string `json:"endpoint"`
	P256DH    string `json:"p256dh"`
	Auth      string `json:"auth"`
	CreatedAt string `json:"createdAt"`
}

// UpsertSubscription 写入或更新一条订阅。
// user 会经 NormalizeUser 归一化；endpoint 必须以 https:// 开头且长度不超过 2048；
// p256dh、auth 非空且分别不超过 256、128。任一校验失败返回中文错误。
// endpoint 全局唯一：若同一 endpoint 被另一用户重新订阅，则归属新用户。
func (s *Store) UpsertSubscription(user, endpoint, p256dh, auth string) (PushSubscription, error) {
	user = NormalizeUser(user)
	if !strings.HasPrefix(endpoint, "https://") {
		return PushSubscription{}, fmt.Errorf("endpoint 必须以 https:// 开头")
	}
	if len(endpoint) > 2048 {
		return PushSubscription{}, fmt.Errorf("endpoint 长度不能超过 2048")
	}
	if p256dh == "" {
		return PushSubscription{}, fmt.Errorf("p256dh 不能为空")
	}
	if len(p256dh) > 256 {
		return PushSubscription{}, fmt.Errorf("p256dh 长度不能超过 256")
	}
	if auth == "" {
		return PushSubscription{}, fmt.Errorf("auth 不能为空")
	}
	if len(auth) > 128 {
		return PushSubscription{}, fmt.Errorf("auth 长度不能超过 128")
	}

	createdAt := nowRFC3339()
	_, err := s.db.Exec(
		`INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at)
		 VALUES (?, ?, ?, ?, ?)
		 ON CONFLICT(endpoint) DO UPDATE SET
		   user_id = excluded.user_id,
		   p256dh = excluded.p256dh,
		   auth = excluded.auth,
		   created_at = excluded.created_at`,
		user, endpoint, p256dh, auth, createdAt,
	)
	if err != nil {
		return PushSubscription{}, err
	}

	return s.getSubscriptionByEndpoint(endpoint)
}

// getSubscriptionByEndpoint 按 endpoint 读取单条订阅，仅内部使用。
func (s *Store) getSubscriptionByEndpoint(endpoint string) (PushSubscription, error) {
	row := s.db.QueryRow(
		`SELECT id, user_id, endpoint, p256dh, auth, created_at
		 FROM push_subscriptions WHERE endpoint = ?`,
		endpoint,
	)
	var sub PushSubscription
	if err := row.Scan(&sub.ID, &sub.User, &sub.Endpoint, &sub.P256DH, &sub.Auth, &sub.CreatedAt); err != nil {
		if err == sql.ErrNoRows {
			return PushSubscription{}, fmt.Errorf("订阅不存在")
		}
		return PushSubscription{}, err
	}
	return sub, nil
}

// DeleteSubscriptionForUser 删除归属指定用户且 endpoint 匹配的订阅。
// user 会经 NormalizeUser 归一化；只删除 user_id 匹配的行，返回是否删到记录。
func (s *Store) DeleteSubscriptionForUser(user, endpoint string) (bool, error) {
	user = NormalizeUser(user)
	res, err := s.db.Exec(
		`DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?`,
		user, endpoint,
	)
	if err != nil {
		return false, err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return false, err
	}
	return n > 0, nil
}

// ListSubscriptionsForUser 列出指定用户的全部订阅，按 created_at 倒序。
// user 会经 NormalizeUser 归一化。
func (s *Store) ListSubscriptionsForUser(user string) ([]PushSubscription, error) {
	user = NormalizeUser(user)
	rows, err := s.db.Query(
		`SELECT id, user_id, endpoint, p256dh, auth, created_at
		 FROM push_subscriptions
		 WHERE user_id = ?
		 ORDER BY created_at DESC, id DESC`,
		user,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var subs []PushSubscription
	for rows.Next() {
		var sub PushSubscription
		if err := rows.Scan(&sub.ID, &sub.User, &sub.Endpoint, &sub.P256DH, &sub.Auth, &sub.CreatedAt); err != nil {
			return nil, err
		}
		subs = append(subs, sub)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return subs, nil
}

// CountSubscriptionsForUser 统计指定用户的订阅数量。
// user 会经 NormalizeUser 归一化。
func (s *Store) CountSubscriptionsForUser(user string) (int, error) {
	user = NormalizeUser(user)
	var n int
	if err := s.db.QueryRow(
		`SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?`,
		user,
	).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}
