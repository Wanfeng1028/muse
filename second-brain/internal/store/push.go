// internal/store/push.go
package store

import "time"

// PushRecord 表示一条推送记录。
type PushRecord struct {
	ID        int64  `json:"id"`
	Date      string `json:"date"`
	Channel   string `json:"channel"`
	User      string `json:"user"`
	Status    string `json:"status"`
	Detail    string `json:"detail"`
	CreatedAt string `json:"createdAt"`
}

// GetPushSetting 读取一个推送设置项，第二个返回值表示是否存在。
func (s *Store) GetPushSetting(key string) (string, bool) {
	var value string
	err := s.db.QueryRow(`SELECT value FROM push_settings WHERE key = ?`, key).Scan(&value)
	if err != nil {
		return "", false
	}
	return value, true
}

// SetPushSetting 写入或更新一个推送设置项。
func (s *Store) SetPushSetting(key, value string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := s.db.Exec(
		`INSERT INTO push_settings (key, value, updated_at) VALUES (?, ?, ?)
		 ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
		key, value, now,
	)
	return err
}

// HasPushed 判断指定日期与通道是否已有成功推送记录（默认用户）。
// 查询出错时返回 false，由调用方打日志。
func (s *Store) HasPushed(date, channel string) bool {
	return s.HasPushedFor(date, channel, DefaultUser)
}

// RecordPush 记录一次推送结果（默认用户），status 取值 "sent"/"failed"/"skipped"。
func (s *Store) RecordPush(date, channel, status, detail string) error {
	return s.RecordPushFor(date, channel, DefaultUser, status, detail)
}

// ListPushLog 按 id 倒序返回推送记录（不过滤用户），limit<=0 时取 50，上限 200。
func (s *Store) ListPushLog(limit int) ([]PushRecord, error) {
	return s.ListPushLogFor(limit, "")
}
