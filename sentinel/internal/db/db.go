// Package db 负责打开 SQLite 数据库、设置 PRAGMA 并执行版本化迁移。
// 迁移通过 schema_migrations 表跟踪，每个迁移在独立事务中执行。
package db

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// migration 描述一个版本化迁移。
type migration struct {
	version int
	stmts   []string
}

// migrations 按版本升序排列的迁移列表。
var migrations = []migration{
	{
		version: 1,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS monitors (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				name TEXT NOT NULL,
				kind TEXT NOT NULL DEFAULT 'http',
				target TEXT NOT NULL,
				method TEXT NOT NULL DEFAULT 'GET',
				expected_status INTEGER NOT NULL DEFAULT 200,
				timeout_sec INTEGER NOT NULL DEFAULT 10,
				interval_sec INTEGER NOT NULL DEFAULT 60,
				enabled INTEGER NOT NULL DEFAULT 1,
				webhook_url TEXT NOT NULL DEFAULT '',
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL
			)`,
			`CREATE TABLE IF NOT EXISTS checks (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
				checked_at TEXT NOT NULL,
				ok INTEGER NOT NULL,
				status_code INTEGER,
				latency_ms INTEGER NOT NULL DEFAULT 0,
				error TEXT NOT NULL DEFAULT '',
				cert_days_left INTEGER
			)`,
			`CREATE TABLE IF NOT EXISTS incidents (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
				started_at TEXT NOT NULL,
				ended_at TEXT,
				downtime_sec INTEGER,
				start_error TEXT NOT NULL DEFAULT ''
			)`,
			`CREATE INDEX IF NOT EXISTS idx_checks_monitor_time ON checks(monitor_id, checked_at)`,
			`CREATE INDEX IF NOT EXISTS idx_incidents_monitor ON incidents(monitor_id)`,
		},
	},
	{
		version: 2,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS tenants (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				name TEXT NOT NULL,
				created_at TEXT NOT NULL
			)`,
			`INSERT OR IGNORE INTO tenants(id, name, created_at) VALUES(1, 'default', ` + quoteNow() + `)`,
			`CREATE TABLE IF NOT EXISTS users (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				tenant_id INTEGER NOT NULL DEFAULT 1 REFERENCES tenants(id),
				name TEXT NOT NULL,
				token_hash TEXT NOT NULL UNIQUE,
				created_at TEXT NOT NULL
			)`,
			`CREATE TABLE IF NOT EXISTS status_pages (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				tenant_id INTEGER NOT NULL DEFAULT 1 REFERENCES tenants(id),
				slug TEXT NOT NULL UNIQUE,
				title TEXT NOT NULL,
				created_at TEXT NOT NULL
			)`,
			`CREATE TABLE IF NOT EXISTS status_page_monitors (
				page_id INTEGER NOT NULL REFERENCES status_pages(id) ON DELETE CASCADE,
				monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
				PRIMARY KEY(page_id, monitor_id)
			)`,
		},
	},
	{
		version: 3,
		stmts: []string{
			`ALTER TABLE status_pages ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'`,
			`ALTER TABLE status_pages ADD COLUMN accent_color TEXT NOT NULL DEFAULT ''`,
		},
	},
	{
		version: 4,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS status_subscriptions (
id INTEGER PRIMARY KEY AUTOINCREMENT,
page_id INTEGER NOT NULL REFERENCES status_pages(id) ON DELETE CASCADE,
email TEXT NOT NULL,
token TEXT NOT NULL UNIQUE,
confirmed INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL,
confirmed_at TEXT
)`,
			`CREATE UNIQUE INDEX IF NOT EXISTS idx_status_subscriptions_page_email ON status_subscriptions(page_id, email)`,
			`CREATE INDEX IF NOT EXISTS idx_status_subscriptions_token ON status_subscriptions(token)`,
		},
	},
	{
		version: 5,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS webhook_deliveries (
id INTEGER PRIMARY KEY AUTOINCREMENT,
monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
url TEXT NOT NULL,
event TEXT NOT NULL,
payload TEXT NOT NULL,
status TEXT NOT NULL DEFAULT 'pending',
attempt INTEGER NOT NULL DEFAULT 0,
max_attempts INTEGER NOT NULL DEFAULT 8,
next_retry_at TEXT,
last_error TEXT NOT NULL DEFAULT '',
created_at TEXT NOT NULL,
updated_at TEXT NOT NULL
)`,
			`CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_due ON webhook_deliveries(status, next_retry_at)`,
			`CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_monitor ON webhook_deliveries(monitor_id)`,
		},
	},
	{
		version: 6,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS silences (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				monitor_id INTEGER NOT NULL DEFAULT 0,
				name_match TEXT NOT NULL DEFAULT '',
				starts_at TEXT NOT NULL,
				ends_at TEXT NOT NULL,
				reason TEXT NOT NULL DEFAULT '',
				created_at TEXT NOT NULL
			)`,
			`CREATE INDEX IF NOT EXISTS idx_silences_window ON silences(monitor_id, starts_at, ends_at)`,
		},
	},
	{
		version: 7,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS incident_escalations (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
				level_minutes INTEGER NOT NULL,
				sent_at TEXT NOT NULL,
				UNIQUE(incident_id, level_minutes)
			)`,
			`CREATE INDEX IF NOT EXISTS idx_incident_escalations_incident ON incident_escalations(incident_id)`,
		},
	},
	{
		version: 8,
		stmts: []string{
			`ALTER TABLE monitors ADD COLUMN sms_phones TEXT NOT NULL DEFAULT ''`,
		},
	},
	{
		version: 9,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS sms_log (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				phone TEXT NOT NULL DEFAULT '',
				message TEXT NOT NULL DEFAULT '',
				provider TEXT NOT NULL DEFAULT '',
				status TEXT NOT NULL DEFAULT '',
				error TEXT NOT NULL DEFAULT '',
				created_at TEXT NOT NULL
			)`,
			`CREATE INDEX IF NOT EXISTS idx_sms_log_phone ON sms_log(phone)`,
			`CREATE INDEX IF NOT EXISTS idx_sms_log_status ON sms_log(status)`,
			`CREATE INDEX IF NOT EXISTS idx_sms_log_created ON sms_log(created_at)`,
		},
	},
	{
		version: 10,
		stmts: []string{
			`UPDATE incidents SET ended_at = started_at, downtime_sec = 0
			 WHERE ended_at IS NULL
			   AND id NOT IN (
			     SELECT id FROM (
			       SELECT id,
			              ROW_NUMBER() OVER (
			                PARTITION BY monitor_id
			                ORDER BY started_at DESC, id DESC
			              ) AS rn
			       FROM incidents
			       WHERE ended_at IS NULL
			     ) ranked
			     WHERE rn = 1
			   )`,
			`CREATE UNIQUE INDEX IF NOT EXISTS uq_incidents_open_monitor ON incidents(monitor_id) WHERE ended_at IS NULL`,
		},
	},
	{
		version: 11,
		stmts: []string{
			`CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_deliveries_dedup ON webhook_deliveries(monitor_id, url, event, payload) WHERE status IN ('pending','retrying')`,
		},
	},
	{
		version: 12,
		stmts: []string{
			`ALTER TABLE monitors ADD COLUMN cert_warn_days INTEGER NOT NULL DEFAULT 0`,
			`ALTER TABLE monitors ADD COLUMN keyword TEXT NOT NULL DEFAULT ''`,
			`ALTER TABLE monitors ADD COLUMN keyword_mode TEXT NOT NULL DEFAULT ''`,
		},
	},
	{
		version: 13,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS status_snapshots (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				page_id INTEGER NOT NULL REFERENCES status_pages(id) ON DELETE CASCADE,
				created_at TEXT NOT NULL,
				generator TEXT NOT NULL DEFAULT 'manual',
				theme TEXT NOT NULL DEFAULT 'light',
				size_bytes INTEGER NOT NULL DEFAULT 0,
				html TEXT NOT NULL DEFAULT ''
			)`,
			`CREATE INDEX IF NOT EXISTS idx_status_snapshots_page_time ON status_snapshots(page_id, created_at)`,
			`ALTER TABLE status_pages ADD COLUMN snapshot_schedule TEXT NOT NULL DEFAULT 'off'`,
		},
	},
	{
		version: 14,
		stmts: []string{
			`ALTER TABLE sms_log ADD COLUMN monitor_id INTEGER NOT NULL DEFAULT 0`,
			`CREATE INDEX IF NOT EXISTS idx_sms_log_monitor ON sms_log(monitor_id)`,
		},
	},
	{
		version: 15,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS maintenance_windows (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				monitor_id INTEGER NOT NULL DEFAULT 0,
				title TEXT NOT NULL DEFAULT '',
				starts_at TEXT NOT NULL,
				ends_at TEXT NOT NULL,
				created_at TEXT NOT NULL
			)`,
			`CREATE INDEX IF NOT EXISTS idx_maintenance_windows_monitor_time ON maintenance_windows(monitor_id, starts_at, ends_at)`,
		},
	},
	{
		version: 16,
		stmts: []string{
			`CREATE TABLE IF NOT EXISTS monitor_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )`,
			`CREATE TABLE IF NOT EXISTS monitor_group_members (
            group_id INTEGER NOT NULL REFERENCES monitor_groups(id) ON DELETE CASCADE,
            monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, monitor_id)
        )`,
			`CREATE INDEX IF NOT EXISTS idx_monitor_group_members_monitor ON monitor_group_members(monitor_id)`,
		},
	},
}

// quoteNow 返回一个包含当前 UTC 时间的 SQL 字符串字面量（带引号）。
func quoteNow() string {
	return "'" + utcNow() + "'"
}

// utcNow 返回当前 UTC 时间的 RFC3339 字符串。
func utcNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// Open 打开数据库，设置 PRAGMA 并执行未应用的迁移。
func Open(path string) (*sql.DB, error) {
	if path == "" {
		return nil, fmt.Errorf("数据库路径为空")
	}
	dir := filepath.Dir(path)
	if dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, fmt.Errorf("创建数据库目录失败：%w", err)
		}
	}

	dsn := fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)", path)
	conn, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("打开数据库失败：%w", err)
	}
	conn.SetMaxOpenConns(1)

	pragmas := []string{
		`PRAGMA journal_mode=WAL`,
		`PRAGMA foreign_keys=ON`,
		`PRAGMA busy_timeout=5000`,
	}
	for _, p := range pragmas {
		if _, err := conn.Exec(p); err != nil {
			_ = conn.Close()
			return nil, fmt.Errorf("执行 PRAGMA 失败 (%s)：%w", p, err)
		}
	}

	if err := ensureMigrationsTable(conn); err != nil {
		_ = conn.Close()
		return nil, err
	}

	applied, err := AppliedVersions(conn)
	if err != nil {
		_ = conn.Close()
		return nil, err
	}
	appliedSet := make(map[int]struct{}, len(applied))
	for _, v := range applied {
		appliedSet[v] = struct{}{}
	}

	for _, m := range migrations {
		if _, ok := appliedSet[m.version]; ok {
			continue
		}
		if err := applyMigration(conn, m); err != nil {
			_ = conn.Close()
			return nil, err
		}
	}

	// v2 中 monitors 需要新增列：使用 PRAGMA 检查后按需 ALTER。
	if err := ensureMonitorColumns(conn); err != nil {
		_ = conn.Close()
		return nil, err
	}

	return conn, nil
}

// ensureMigrationsTable 创建 schema_migrations 表（幂等）。
func ensureMigrationsTable(conn *sql.DB) error {
	_, err := conn.Exec(`CREATE TABLE IF NOT EXISTS schema_migrations (
		version INTEGER PRIMARY KEY,
		applied_at TEXT NOT NULL
	)`)
	if err != nil {
		return fmt.Errorf("创建 schema_migrations 表失败：%w", err)
	}
	return nil
}

// applyMigration 在单个事务中执行迁移语句并记录版本。
func applyMigration(conn *sql.DB, m migration) error {
	tx, err := conn.Begin()
	if err != nil {
		return fmt.Errorf("开始迁移 v%d 事务失败：%w", m.version, err)
	}
	for _, stmt := range m.stmts {
		if _, err := tx.Exec(stmt); err != nil {
			_ = tx.Rollback()
			return fmt.Errorf("执行迁移 v%d 语句失败：%w", m.version, err)
		}
	}
	if _, err := tx.Exec(`INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)`, m.version, utcNow()); err != nil {
		_ = tx.Rollback()
		return fmt.Errorf("记录迁移 v%d 失败：%w", m.version, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("提交迁移 v%d 失败：%w", m.version, err)
	}
	return nil
}

// ensureMonitorColumns 检查并新增 monitors 表在 v2 中引入的列。
func ensureMonitorColumns(conn *sql.DB) error {
	has, err := columnExists(conn, "monitors", "tenant_id")
	if err != nil {
		return err
	}
	if !has {
		if _, err := conn.Exec(`ALTER TABLE monitors ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1`); err != nil {
			return fmt.Errorf("为 monitors 添加 tenant_id 列失败：%w", err)
		}
	}

	has, err = columnExists(conn, "monitors", "is_public")
	if err != nil {
		return err
	}
	if !has {
		if _, err := conn.Exec(`ALTER TABLE monitors ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0`); err != nil {
			return fmt.Errorf("为 monitors 添加 is_public 列失败：%w", err)
		}
	}

	has, err = columnExists(conn, "monitors", "notify_channels")
	if err != nil {
		return err
	}
	if !has {
		if _, err := conn.Exec(`ALTER TABLE monitors ADD COLUMN notify_channels TEXT NOT NULL DEFAULT ''`); err != nil {
			return fmt.Errorf("为 monitors 添加 notify_channels 列失败：%w", err)
		}
	}
	return nil
}

// columnExists 通过 PRAGMA table_info 判断某表是否包含指定列。
func columnExists(conn *sql.DB, table, column string) (bool, error) {
	rows, err := conn.Query(fmt.Sprintf("PRAGMA table_info(%s)", table))
	if err != nil {
		return false, fmt.Errorf("查询表 %s 结构失败：%w", table, err)
	}
	defer rows.Close()

	for rows.Next() {
		var (
			cid       int
			name      string
			ctype     string
			notnull   int
			dfltValue sql.NullString
			pk        int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dfltValue, &pk); err != nil {
			return false, fmt.Errorf("扫描表 %s 结构失败：%w", table, err)
		}
		if name == column {
			return true, nil
		}
	}
	if err := rows.Err(); err != nil {
		return false, fmt.Errorf("读取表 %s 结构失败：%w", table, err)
	}
	return false, nil
}

// AppliedVersions 返回已应用的迁移版本列表（升序）。
func AppliedVersions(conn *sql.DB) ([]int, error) {
	rows, err := conn.Query(`SELECT version FROM schema_migrations ORDER BY version ASC`)
	if err != nil {
		return nil, fmt.Errorf("查询已应用迁移失败：%w", err)
	}
	defer rows.Close()

	var versions []int
	for rows.Next() {
		var v int
		if err := rows.Scan(&v); err != nil {
			return nil, fmt.Errorf("扫描迁移版本失败：%w", err)
		}
		versions = append(versions, v)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("读取迁移版本失败：%w", err)
	}
	return versions, nil
}
