package store

import (
	"database/sql"
	"time"
)

// Delivery 对应 webhook_deliveries 表的一行记录。
type Delivery struct {
	ID          int64
	MonitorID   int64
	URL         string
	Event       string
	Payload     string
	Status      string
	Attempt     int
	MaxAttempts int
	NextRetryAt sql.NullString
	LastError   string
	CreatedAt   string
	UpdatedAt   string
}

// EnqueueDelivery 幂等地把一次 webhook 投递任务写入队列。
// 若已存在 (monitor_id, url, event, payload) 相同且 status 为 pending/retrying 的行，
// 直接返回该行 id，不插入新行；否则插入新行并返回其 id。
// maxAttempts <= 0 时按 8 处理。
func (s *Store) EnqueueDelivery(monitorID int64, url, event, payload string, maxAttempts int) (int64, error) {
	if maxAttempts <= 0 {
		maxAttempts = 8
	}

	var existingID int64
	err := s.db.QueryRow(
		`SELECT id FROM webhook_deliveries
WHERE monitor_id = ? AND url = ? AND event = ? AND payload = ?
AND status IN ('pending','retrying')
ORDER BY id DESC LIMIT 1`,
		monitorID, url, event, payload,
	).Scan(&existingID)
	if err == nil {
		return existingID, nil
	}
	if err != sql.ErrNoRows {
		return 0, err
	}

	now := utcNow()
	res, err := s.db.Exec(
		`INSERT INTO webhook_deliveries
(monitor_id, url, event, payload, status, attempt, max_attempts, next_retry_at, last_error, created_at, updated_at)
VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, '', ?, ?)`,
		monitorID, url, event, payload, maxAttempts, now, now, now,
	)
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// GetDelivery 按 id 查询一条投递记录。无行返回 sql.ErrNoRows。
func (s *Store) GetDelivery(id int64) (Delivery, error) {
	row := s.db.QueryRow(
		`SELECT id, monitor_id, url, event, payload, status, attempt, max_attempts,
next_retry_at, last_error, created_at, updated_at
FROM webhook_deliveries WHERE id = ?`, id,
	)
	return scanDelivery(row)
}

// ListDeliveries 列出投递记录。status 非空则按状态过滤；monitorID > 0 则按监控过滤；
// limit 钳制到 1~1000；按 id 降序返回。
func (s *Store) ListDeliveries(status string, monitorID int64, limit int) ([]Delivery, error) {
	if limit <= 0 {
		limit = 1
	}
	if limit > 1000 {
		limit = 1000
	}

	query := `SELECT id, monitor_id, url, event, payload, status, attempt, max_attempts,
next_retry_at, last_error, created_at, updated_at
FROM webhook_deliveries WHERE 1=1`
	args := make([]any, 0, 3)
	if status != "" {
		query += ` AND status = ?`
		args = append(args, status)
	}
	if monitorID > 0 {
		query += ` AND monitor_id = ?`
		args = append(args, monitorID)
	}
	query += ` ORDER BY id DESC LIMIT ?`
	args = append(args, limit)

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]Delivery, 0)
	for rows.Next() {
		d, err := scanDelivery(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// CountDeliveriesByStatus 按状态统计投递记录数量。
func (s *Store) CountDeliveriesByStatus() (map[string]int, error) {
	rows, err := s.db.Query(`SELECT status, COUNT(*) FROM webhook_deliveries GROUP BY status`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make(map[string]int)
	for rows.Next() {
		var status string
		var n int
		if err := rows.Scan(&status, &n); err != nil {
			return nil, err
		}
		out[status] = n
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// ClaimDueDeliveries 捞取所有到期（next_retry_at <= now）且状态为 pending/retrying 的记录，
// 按 next_retry_at 升序返回，limit 钳制到 1~1000。
func (s *Store) ClaimDueDeliveries(now string, limit int) ([]Delivery, error) {
	if limit <= 0 {
		limit = 1
	}
	if limit > 1000 {
		limit = 1000
	}

	rows, err := s.db.Query(
		`SELECT id, monitor_id, url, event, payload, status, attempt, max_attempts,
next_retry_at, last_error, created_at, updated_at
FROM webhook_deliveries
WHERE status IN ('pending','retrying') AND next_retry_at IS NOT NULL AND next_retry_at <= ?
ORDER BY next_retry_at ASC LIMIT ?`,
		now, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]Delivery, 0)
	for rows.Next() {
		d, err := scanDelivery(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// MarkDeliveryDone 把投递记录标记为成功。无行返回 sql.ErrNoRows。
func (s *Store) MarkDeliveryDone(id int64) error {
	res, err := s.db.Exec(
		`UPDATE webhook_deliveries SET status = 'done', updated_at = ? WHERE id = ?`,
		utcNow(), id,
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

// MarkDeliveryAttempt 记录一次投递失败：attempt 自增 1，status 置为 retrying，
// 并更新下一次重试时间与错误信息。
func (s *Store) MarkDeliveryAttempt(id int64, nextRetryAt, lastError string) error {
	res, err := s.db.Exec(
		`UPDATE webhook_deliveries
SET attempt = attempt + 1, status = 'retrying', next_retry_at = ?, last_error = ?, updated_at = ?
WHERE id = ?`,
		nextRetryAt, lastError, utcNow(), id,
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

// MarkDeliveryFailed 把投递记录标记为最终失败，同时把 attempt+1，
// 使 attempt 真实反映已执行的投递次数（最后一次失败也计入）。
func (s *Store) MarkDeliveryFailed(id int64, lastError string) error {
	res, err := s.db.Exec(
		`UPDATE webhook_deliveries SET attempt = attempt + 1, status = 'failed', last_error = ?, updated_at = ? WHERE id = ?`,
		lastError, utcNow(), id,
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

// RetryDelivery 手动重试一条投递记录：只允许 status 为 failed/retrying 的行，
// 重置为 pending、attempt=0、next_retry_at=now。
func (s *Store) RetryDelivery(id int64) error {
	var status string
	err := s.db.QueryRow(`SELECT status FROM webhook_deliveries WHERE id = ?`, id).Scan(&status)
	if err != nil {
		return err
	}
	if status != "failed" && status != "retrying" {
		return errInvalidDeliveryStatus
	}

	now := utcNow()
	res, err := s.db.Exec(
		`UPDATE webhook_deliveries
SET status = 'pending', attempt = 0, next_retry_at = ?, last_error = '', updated_at = ?
WHERE id = ? AND status IN ('failed','retrying')`,
		now, now, id,
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

var errInvalidDeliveryStatus = errDeliveryStatus("只有失败或重试中的投递才能手动重试")

type errDeliveryStatus string

func (e errDeliveryStatus) Error() string { return string(e) }

// scanDelivery 从一行中扫描出 Delivery，避免各方法重复 Scan。
type deliveryScanner interface {
	Scan(dest ...any) error
}

func scanDelivery(row deliveryScanner) (Delivery, error) {
	var d Delivery
	err := row.Scan(
		&d.ID, &d.MonitorID, &d.URL, &d.Event, &d.Payload, &d.Status,
		&d.Attempt, &d.MaxAttempts, &d.NextRetryAt, &d.LastError, &d.CreatedAt, &d.UpdatedAt,
	)
	if err != nil {
		return Delivery{}, err
	}
	return d, nil
}

var _ = time.RFC3339
