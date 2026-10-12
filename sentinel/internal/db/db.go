package db

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// Open 打开（或创建）SQLite 数据库，完成初始化 PRAGMA 与建表建索引。
// path 为数据库文件路径，若为相对路径则由调用方决定基准目录。
func Open(path string) (*sql.DB, error) {
	// 建父目录
	dir := filepath.Dir(path)
	if dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, fmt.Errorf("创建数据库目录失败: %w", err)
		}
	}

	// 使用 modernc.org/sqlite 纯 Go 驱动
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("打开数据库失败: %w", err)
	}

	// SQLite 写入建议单连接，避免锁竞争
	db.SetMaxOpenConns(1)

	// PRAGMA：WAL 日志模式与外键约束
	if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
		db.Close()
		return nil, fmt.Errorf("设置 journal_mode 失败: %w", err)
	}
	if _, err := db.Exec("PRAGMA foreign_keys=ON"); err != nil {
		db.Close()
		return nil, fmt.Errorf("开启外键约束失败: %w", err)
	}

	// 建表
	if _, err := db.Exec(schemaSQL); err != nil {
		db.Close()
		return nil, fmt.Errorf("建表失败: %w", err)
	}

	// 建索引
	if _, err := db.Exec(indexSQL); err != nil {
		db.Close()
		return nil, fmt.Errorf("建索引失败: %w", err)
	}

	return db, nil
}

// utcNow 返回 UTC 时间的 RFC3339 字符串，用于所有时间字段写入。
func utcNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// schemaSQL 三张表的建表语句（IF NOT EXISTS 幂等）。
const schemaSQL = `
CREATE TABLE IF NOT EXISTS monitors (
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
);

CREATE TABLE IF NOT EXISTS checks (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
	checked_at TEXT NOT NULL,
	ok INTEGER NOT NULL,
	status_code INTEGER,
	latency_ms INTEGER NOT NULL DEFAULT 0,
	error TEXT NOT NULL DEFAULT '',
	cert_days_left INTEGER
);

CREATE TABLE IF NOT EXISTS incidents (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
	started_at TEXT NOT NULL,
	ended_at TEXT,
	downtime_sec INTEGER,
	start_error TEXT NOT NULL DEFAULT ''
);
`

// indexSQL 索引语句（IF NOT EXISTS 幂等）。
const indexSQL = `
CREATE INDEX IF NOT EXISTS idx_checks_monitor_time ON checks(monitor_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_incidents_monitor ON incidents(monitor_id);
`
