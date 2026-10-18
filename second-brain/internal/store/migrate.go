package store

import (
	"database/sql"
	"fmt"
)

// Migration 描述一次数据库结构迁移。
//
// Version 必须严格递增且全局唯一，Migrations 切片必须按 Version 升序排列。
// Up 必须幂等：在旧库上执行一次达到目标结构；在新库（结构已是目标）上执行
// 也不得报错，以便重复调用 Migrate 时安全跳过或重放。
type Migration struct {
	Version int
	Name    string
	Up      func(db *sql.DB) error
}

// Migrations 是所有迁移的有序集合，按 Version 升序排列。
var Migrations = []Migration{
	{Version: 1, Name: "reviews_user_id", Up: migrateReviewsUser},
	{Version: 2, Name: "push_log_user_id", Up: migratePushLogUser},
}

// CurrentSchemaVersion 是当前代码期望的数据库 schema 版本。
const CurrentSchemaVersion = 2

// GetSchemaVersion 返回当前数据库的 schema 版本号。
// 若 schema_version 表不存在则创建；表为空时视为版本 0 并写入一行 0。
func GetSchemaVersion(db *sql.DB) (int, error) {
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS schema_version (
		version INTEGER NOT NULL
	)`); err != nil {
		return 0, fmt.Errorf("create schema_version table: %w", err)
	}

	var v int
	err := db.QueryRow(`SELECT version FROM schema_version LIMIT 1`).Scan(&v)
	if err == sql.ErrNoRows {
		if _, err := db.Exec(`INSERT INTO schema_version (version) VALUES (0)`); err != nil {
			return 0, fmt.Errorf("insert initial schema version: %w", err)
		}
		return 0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("read schema version: %w", err)
	}
	return v, nil
}

// SetSchemaVersion 将数据库的 schema 版本号写为 v。
func SetSchemaVersion(db *sql.DB, v int) error {
	if _, err := db.Exec(`UPDATE schema_version SET version = ?`, v); err != nil {
		return fmt.Errorf("set schema version %d: %w", v, err)
	}
	return nil
}

// Migrate 将数据库升级到 CurrentSchemaVersion。
// 读取当前版本后，按 Version 升序执行所有 Version 大于当前版本的迁移，
// 每成功一个立即持久化版本号。全部成功返回 nil。重复调用为 noop。
func Migrate(db *sql.DB) error {
	current, err := GetSchemaVersion(db)
	if err != nil {
		return err
	}

	for _, m := range Migrations {
		if m.Version <= current {
			continue
		}
		if err := m.Up(db); err != nil {
			return fmt.Errorf("migration %d (%s): %w", m.Version, m.Name, err)
		}
		if err := SetSchemaVersion(db, m.Version); err != nil {
			return err
		}
		current = m.Version
	}
	return nil
}
