// Package store 提供 Sentinel 监控系统所有数据表（monitors/checks/incidents/users/tenants）
// 的持久化访问接口，基于 database/sql 与 SQLite。
package store

import (
	"database/sql"
	"errors"
	"time"
)

// Monitor 对应 monitors 表的一行记录。
type Monitor struct {
	ID             int64
	Name           string
	Kind           string
	Target         string
	Method         string
	ExpectedStatus int
	TimeoutSec     int
	IntervalSec    int
	Enabled        int
	TenantID       int64
	IsPublic       int
	WebhookURL     string
	NotifyChannels string
	// SMSPhones 短信接收号码，逗号分隔；空表示未配置。
	SMSPhones string
	CreatedAt string
	UpdatedAt string
}

// Check 对应 checks 表的一行记录。
type Check struct {
	ID           int64
	MonitorID    int64
	CheckedAt    string
	Ok           int
	StatusCode   sql.NullInt64
	LatencyMs    int64
	Error        string
	CertDaysLeft sql.NullInt64
}

// Incident 对应 incidents 表的一行记录，附带 monitor 名称。
type Incident struct {
	ID          int64
	MonitorID   int64
	StartedAt   string
	EndedAt     sql.NullString
	DowntimeSec sql.NullInt64
	StartError  string
	MonitorName string
}

// User 对应 users 表的一行记录。
type User struct {
	ID        int64
	TenantID  int64
	Name      string
	TokenHash string
	CreatedAt string
}

// Store 封装所有数据库操作。
type Store struct {
	db *sql.DB
}

// New 基于给定的 *sql.DB 构造 Store。
func New(db *sql.DB) *Store {
	return &Store{db: db}
}

// Close 关闭底层数据库连接。
func (s *Store) Close() error {
	return s.db.Close()
}

// utcNow 返回当前 UTC 时间的 RFC3339 字符串。
func utcNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// CreateMonitor 插入一条 monitor 记录，自动填充创建/更新时间，返回自增 ID。
func (s *Store) CreateMonitor(m Monitor) (int64, error) {
	now := utcNow()
	res, err := s.db.Exec(
		`INSERT INTO monitors
			(name, kind, target, method, expected_status, timeout_sec, interval_sec, enabled, tenant_id, is_public, webhook_url, notify_channels, sms_phones, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		m.Name, m.Kind, m.Target, m.Method, m.ExpectedStatus, m.TimeoutSec,
		m.IntervalSec, m.Enabled, m.TenantID, m.IsPublic, m.WebhookURL, m.NotifyChannels, m.SMSPhones, now, now,
	)
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// GetMonitor 按 id 查询单条 monitor，无记录返回 sql.ErrNoRows。
func (s *Store) GetMonitor(id int64) (Monitor, error) {
	var m Monitor
	err := s.db.QueryRow(
		`SELECT id, name, kind, target, method, expected_status, timeout_sec, interval_sec, enabled, tenant_id, is_public, webhook_url, notify_channels, sms_phones, created_at, updated_at
		 FROM monitors WHERE id = ?`, id,
	).Scan(&m.ID, &m.Name, &m.Kind, &m.Target, &m.Method, &m.ExpectedStatus,
		&m.TimeoutSec, &m.IntervalSec, &m.Enabled, &m.TenantID, &m.IsPublic,
		&m.WebhookURL, &m.NotifyChannels, &m.SMSPhones, &m.CreatedAt, &m.UpdatedAt)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Monitor{}, sql.ErrNoRows
		}
		return Monitor{}, err
	}
	return m, nil
}

// ListMonitors 按 id 升序返回全部 monitor。
func (s *Store) ListMonitors() ([]Monitor, error) {
	rows, err := s.db.Query(
		`SELECT id, name, kind, target, method, expected_status, timeout_sec, interval_sec, enabled, tenant_id, is_public, webhook_url, notify_channels, sms_phones, created_at, updated_at
		 FROM monitors ORDER BY id ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Monitor
	for rows.Next() {
		var m Monitor
		if err := rows.Scan(&m.ID, &m.Name, &m.Kind, &m.Target, &m.Method, &m.ExpectedStatus,
			&m.TimeoutSec, &m.IntervalSec, &m.Enabled, &m.TenantID, &m.IsPublic,
			&m.WebhookURL, &m.NotifyChannels, &m.SMSPhones, &m.CreatedAt, &m.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// ListMonitorsByTenant 按 id 升序返回指定租户下的全部 monitor。
func (s *Store) ListMonitorsByTenant(tenantID int64) ([]Monitor, error) {
	rows, err := s.db.Query(
		`SELECT id, name, kind, target, method, expected_status, timeout_sec, interval_sec, enabled, tenant_id, is_public, webhook_url, notify_channels, sms_phones, created_at, updated_at
		 FROM monitors WHERE tenant_id = ? ORDER BY id ASC`, tenantID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Monitor
	for rows.Next() {
		var m Monitor
		if err := rows.Scan(&m.ID, &m.Name, &m.Kind, &m.Target, &m.Method, &m.ExpectedStatus,
			&m.TimeoutSec, &m.IntervalSec, &m.Enabled, &m.TenantID, &m.IsPublic,
			&m.WebhookURL, &m.NotifyChannels, &m.SMSPhones, &m.CreatedAt, &m.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// UpdateMonitor 更新指定 monitor 的全部业务字段与 updated_at，无记录返回 sql.ErrNoRows。
func (s *Store) UpdateMonitor(id int64, m Monitor) error {
	res, err := s.db.Exec(
		`UPDATE monitors SET
			name = ?, kind = ?, target = ?, method = ?, expected_status = ?, timeout_sec = ?,
			interval_sec = ?, enabled = ?, tenant_id = ?, is_public = ?, webhook_url = ?, notify_channels = ?, sms_phones = ?, updated_at = ?
		 WHERE id = ?`,
		m.Name, m.Kind, m.Target, m.Method, m.ExpectedStatus, m.TimeoutSec,
		m.IntervalSec, m.Enabled, m.TenantID, m.IsPublic, m.WebhookURL, m.NotifyChannels, m.SMSPhones, utcNow(), id,
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

// DeleteMonitor 删除指定 monitor（级联删除 checks/incidents），无记录返回 sql.ErrNoRows。
func (s *Store) DeleteMonitor(id int64) error {
	res, err := s.db.Exec(`DELETE FROM monitors WHERE id = ?`, id)
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

// InsertCheck 插入一条检查记录，返回自增 ID。
func (s *Store) InsertCheck(c Check) (int64, error) {
	res, err := s.db.Exec(
		`INSERT INTO checks (monitor_id, checked_at, ok, status_code, latency_ms, error, cert_days_left)
		 VALUES (?, ?, ?, ?, ?, ?, ?)`,
		c.MonitorID, c.CheckedAt, c.Ok, c.StatusCode, c.LatencyMs, c.Error, c.CertDaysLeft,
	)
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// LastCheck 返回某 monitor 最近一次检查，无记录返回 (nil, nil)。
func (s *Store) LastCheck(monitorID int64) (*Check, error) {
	var c Check
	err := s.db.QueryRow(
		`SELECT id, monitor_id, checked_at, ok, status_code, latency_ms, error, cert_days_left
		 FROM checks WHERE monitor_id = ? ORDER BY checked_at DESC, id DESC LIMIT 1`, monitorID,
	).Scan(&c.ID, &c.MonitorID, &c.CheckedAt, &c.Ok, &c.StatusCode, &c.LatencyMs, &c.Error, &c.CertDaysLeft)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	return &c, nil
}

// ListChecks 返回某 monitor 的检查记录，按 checked_at 降序。
func (s *Store) ListChecks(monitorID int64, limit int) ([]Check, error) {
	if limit <= 0 {
		limit = 100
	}
	rows, err := s.db.Query(
		`SELECT id, monitor_id, checked_at, ok, status_code, latency_ms, error, cert_days_left
		 FROM checks WHERE monitor_id = ? ORDER BY checked_at DESC, id DESC LIMIT ?`, monitorID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Check
	for rows.Next() {
		var c Check
		if err := rows.Scan(&c.ID, &c.MonitorID, &c.CheckedAt, &c.Ok, &c.StatusCode, &c.LatencyMs, &c.Error, &c.CertDaysLeft); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// MonitorStats 返回某 monitor 在最近 days 天内的统计信息。
// uptimePct = ok 数 / total * 100（total=0 时返回 100.0）；
// avgLatencyMs 为平均延迟（total=0 时返回 0）；
// downIncidents 为 days 天内 started_at 落在区间内的 incidents 数。
func (s *Store) MonitorStats(monitorID int64, days int) (uptimePct float64, avgLatencyMs float64, total int, downIncidents int, err error) {
	if days <= 0 {
		days = 7
	}
	since := time.Now().UTC().Add(-time.Duration(days) * 24 * time.Hour).Format(time.RFC3339)

	// 统计 checks
	var okCount int
	var sumLatency sql.NullInt64
	row := s.db.QueryRow(
		`SELECT COUNT(*), COALESCE(SUM(ok), 0), COALESCE(SUM(latency_ms), 0)
		 FROM checks WHERE monitor_id = ? AND checked_at >= ?`, monitorID, since)
	if err = row.Scan(&total, &okCount, &sumLatency); err != nil {
		return
	}
	if total == 0 {
		uptimePct = 100.0
		avgLatencyMs = 0
	} else {
		uptimePct = float64(okCount) / float64(total) * 100.0
		avgLatencyMs = float64(sumLatency.Int64) / float64(total)
	}

	// 统计事件数
	if err = s.db.QueryRow(
		`SELECT COUNT(*) FROM incidents WHERE monitor_id = ? AND started_at >= ?`, monitorID, since,
	).Scan(&downIncidents); err != nil {
		return
	}
	return
}

// OpenIncident 幂等地为某 monitor 打开一个未关闭 incident。
// 若该 monitor 已存在 ended_at IS NULL 的 incident，直接返回其 id，created=false；
// 否则新建并返回 (id, true, nil)。并发调用由 uq_incidents_open_monitor
// 部分唯一索引在数据库层保证唯一性。
func (s *Store) OpenIncident(monitorID int64, startedAt, startError string) (int64, bool, error) {
	res, err := s.db.Exec(
		`INSERT INTO incidents (monitor_id, started_at, start_error) VALUES (?, ?, ?)
		 ON CONFLICT (monitor_id) WHERE ended_at IS NULL DO NOTHING`,
		monitorID, startedAt, startError,
	)
	if err != nil {
		return 0, false, err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, false, err
	}
	if n > 0 {
		id, err := res.LastInsertId()
		if err != nil {
			return 0, false, err
		}
		return id, true, nil
	}
	var id int64
	if err := s.db.QueryRow(
		`SELECT id FROM incidents WHERE monitor_id = ? AND ended_at IS NULL
		 ORDER BY started_at DESC, id DESC LIMIT 1`,
		monitorID,
	).Scan(&id); err != nil {
		return 0, false, err
	}
	return id, false, nil
}

// CloseOpenIncident 关闭某 monitor 的未关闭 incident（ended_at IS NULL）。
func (s *Store) CloseOpenIncident(monitorID int64, endedAt string, downtimeSec int64) error {
	_, err := s.db.Exec(
		`UPDATE incidents SET ended_at = ?, downtime_sec = ?
		 WHERE monitor_id = ? AND ended_at IS NULL`,
		endedAt, downtimeSec, monitorID,
	)
	return err
}

// ListIncidents 按 started_at 降序返回 incident 列表。
// monitorID <= 0 时返回全部；否则仅返回指定 monitor 的。
// JOIN monitors 表填充 MonitorName。
func (s *Store) ListIncidents(monitorID int64, limit int) ([]Incident, error) {
	if limit <= 0 {
		limit = 100
	}
	var (
		rows *sql.Rows
		err  error
	)
	if monitorID <= 0 {
		rows, err = s.db.Query(
			`SELECT i.id, i.monitor_id, i.started_at, i.ended_at, i.downtime_sec, i.start_error, m.name
			 FROM incidents i JOIN monitors m ON m.id = i.monitor_id
			 ORDER BY i.started_at DESC, i.id DESC LIMIT ?`, limit)
	} else {
		rows, err = s.db.Query(
			`SELECT i.id, i.monitor_id, i.started_at, i.ended_at, i.downtime_sec, i.start_error, m.name
			 FROM incidents i JOIN monitors m ON m.id = i.monitor_id
			 WHERE i.monitor_id = ?
			 ORDER BY i.started_at DESC, i.id DESC LIMIT ?`, monitorID, limit)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Incident
	for rows.Next() {
		var it Incident
		if err := rows.Scan(&it.ID, &it.MonitorID, &it.StartedAt, &it.EndedAt, &it.DowntimeSec, &it.StartError, &it.MonitorName); err != nil {
			return nil, err
		}
		out = append(out, it)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// CountIncidents 统计 incident 总数。
// monitorID <= 0 时统计全部；否则仅统计指定 monitor 的。
func (s *Store) CountIncidents(monitorID int64) (int, error) {
	var (
		n   int
		err error
	)
	if monitorID <= 0 {
		err = s.db.QueryRow(`SELECT COUNT(*) FROM incidents`).Scan(&n)
	} else {
		err = s.db.QueryRow(`SELECT COUNT(*) FROM incidents WHERE monitor_id = ?`, monitorID).Scan(&n)
	}
	if err != nil {
		return 0, err
	}
	return n, nil
}

// ListIncidentsPaged 按 started_at 降序、id 降序分页返回 incident 列表。
// monitorID <= 0 时返回全部；否则仅返回指定 monitor 的。
// offset < 0 按 0 处理；limit <= 0 按 20 处理。
// JOIN monitors 表填充 MonitorName。
func (s *Store) ListIncidentsPaged(monitorID int64, offset, limit int) ([]Incident, error) {
	if offset < 0 {
		offset = 0
	}
	if limit <= 0 {
		limit = 20
	}
	var (
		rows *sql.Rows
		err  error
	)
	if monitorID <= 0 {
		rows, err = s.db.Query(
			`SELECT i.id, i.monitor_id, i.started_at, i.ended_at, i.downtime_sec, i.start_error, m.name
			 FROM incidents i JOIN monitors m ON m.id = i.monitor_id
			 ORDER BY i.started_at DESC, i.id DESC LIMIT ? OFFSET ?`, limit, offset)
	} else {
		rows, err = s.db.Query(
			`SELECT i.id, i.monitor_id, i.started_at, i.ended_at, i.downtime_sec, i.start_error, m.name
			 FROM incidents i JOIN monitors m ON m.id = i.monitor_id
			 WHERE i.monitor_id = ?
			 ORDER BY i.started_at DESC, i.id DESC LIMIT ? OFFSET ?`, monitorID, limit, offset)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Incident
	for rows.Next() {
		var it Incident
		if err := rows.Scan(&it.ID, &it.MonitorID, &it.StartedAt, &it.EndedAt, &it.DowntimeSec, &it.StartError, &it.MonitorName); err != nil {
			return nil, err
		}
		out = append(out, it)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// Overview 返回全局概览统计。
// total=monitors 总数；enabled=enabled=1 数；
// up/down/unknown 按每个 monitor 的 LastCheck 的 ok 值统计（无检查记 unknown）；
// checks24h = checked_at >= now-24h 的 checks 数；
// incidents7d = started_at >= now-7d 的 incidents 数。
func (s *Store) Overview() (total, enabled, up, down, unknown, checks24h, incidents7d int, err error) {
	if err = s.db.QueryRow(`SELECT COUNT(*), COALESCE(SUM(enabled), 0) FROM monitors`).
		Scan(&total, &enabled); err != nil {
		return
	}

	// 逐 monitor 判断 LastCheck
	rows, err := s.db.Query(`SELECT id FROM monitors`)
	if err != nil {
		return
	}
	var ids []int64
	for rows.Next() {
		var id int64
		if err = rows.Scan(&id); err != nil {
			rows.Close()
			return
		}
		ids = append(ids, id)
	}
	if err = rows.Err(); err != nil {
		rows.Close()
		return
	}
	rows.Close()

	for _, id := range ids {
		var ok int
		e := s.db.QueryRow(
			`SELECT ok FROM checks WHERE monitor_id = ? ORDER BY checked_at DESC, id DESC LIMIT 1`, id,
		).Scan(&ok)
		if errors.Is(e, sql.ErrNoRows) {
			unknown++
			continue
		}
		if e != nil {
			err = e
			return
		}
		if ok == 1 {
			up++
		} else {
			down++
		}
	}

	now := time.Now().UTC()
	since24h := now.Add(-24 * time.Hour).Format(time.RFC3339)
	since7d := now.Add(-7 * 24 * time.Hour).Format(time.RFC3339)

	if err = s.db.QueryRow(`SELECT COUNT(*) FROM checks WHERE checked_at >= ?`, since24h).
		Scan(&checks24h); err != nil {
		return
	}
	if err = s.db.QueryRow(`SELECT COUNT(*) FROM incidents WHERE started_at >= ?`, since7d).
		Scan(&incidents7d); err != nil {
		return
	}
	return
}

// OpenIncidentStartedAt 返回该 monitor 未关闭（ended_at IS NULL）incident 的 started_at。
// 无则返回 ("", sql.ErrNoRows)。
func (s *Store) OpenIncidentStartedAt(monitorID int64) (string, error) {
	var startedAt string
	err := s.db.QueryRow(
		`SELECT started_at FROM incidents WHERE monitor_id = ? AND ended_at IS NULL
		 ORDER BY started_at DESC, id DESC LIMIT 1`, monitorID,
	).Scan(&startedAt)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return "", sql.ErrNoRows
		}
		return "", err
	}
	return startedAt, nil
}

// CheckCount 返回该 monitor 的 checks 总数。
func (s *Store) CheckCount(monitorID int64) (int, error) {
	var n int
	err := s.db.QueryRow(`SELECT COUNT(*) FROM checks WHERE monitor_id = ?`, monitorID).Scan(&n)
	if err != nil {
		return 0, err
	}
	return n, nil
}

// CreateUser 插入一条 user 记录，自动填充 created_at，返回自增 ID。
func (s *Store) CreateUser(tenantID int64, name, tokenHash string) (int64, error) {
	res, err := s.db.Exec(
		`INSERT INTO users (tenant_id, name, token_hash, created_at) VALUES (?, ?, ?, ?)`,
		tenantID, name, tokenHash, utcNow(),
	)
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// ListUsers 按 id 升序返回全部 user。
func (s *Store) ListUsers() ([]User, error) {
	rows, err := s.db.Query(
		`SELECT id, tenant_id, name, token_hash, created_at FROM users ORDER BY id ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []User
	for rows.Next() {
		var u User
		if err := rows.Scan(&u.ID, &u.TenantID, &u.Name, &u.TokenHash, &u.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// EnsureDefaultTenant 保证默认租户（id=1, name='default'）存在，幂等。
// tenants 表 COUNT=0 时插入；已存在则不重复插入。
func (s *Store) EnsureDefaultTenant() error {
	var n int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM tenants`).Scan(&n); err != nil {
		return err
	}
	if n > 0 {
		return nil
	}
	_, err := s.db.Exec(`INSERT OR IGNORE INTO tenants (id, name) VALUES (1, 'default')`)
	return err
}
