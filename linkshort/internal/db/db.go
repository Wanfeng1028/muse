package db

import (
	"database/sql"
	"fmt"

	// 注册纯 Go 的 sqlite 驱动，驱动名为 "sqlite"。
	_ "modernc.org/sqlite"
)

// schema 是建表与建索引语句，全部使用 IF NOT EXISTS，可重复执行。
const schema = `
CREATE TABLE IF NOT EXISTS links (
	id INTEGER PRIMARY KEY,
	slug TEXT UNIQUE NOT NULL,
	url TEXT NOT NULL,
	title TEXT NOT NULL DEFAULT "",
	clicks INTEGER NOT NULL DEFAULT 0,
	enabled INTEGER NOT NULL DEFAULT 1,
	expires_at TEXT,
	created_at TEXT NOT NULL,
	updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visits (
	id INTEGER PRIMARY KEY,
	link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
	ts TEXT NOT NULL,
	ip_hash TEXT NOT NULL DEFAULT "",
	ua TEXT NOT NULL DEFAULT "",
	referer TEXT NOT NULL DEFAULT ""
);

CREATE INDEX IF NOT EXISTS idx_visits_link_ts ON visits(link_id, ts);
CREATE INDEX IF NOT EXISTS idx_links_slug ON links(slug);
`

// Open 打开指定路径的 sqlite 数据库，并完成建表与 PRAGMA 设置。
// path 为文件路径（如 ./data/linkshort.db），如需内存库可传 ":memory:"。
func Open(path string) (*sql.DB, error) {
	// 开启 WAL 与 foreign_keys，使用 _pragma 查询参数随连接初始化。
	dsn := fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(ON)", path)
	database, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	// 单连接串行化写入，避免 sqlite 锁竞争。
	database.SetMaxOpenConns(1)

	if err := database.Ping(); err != nil {
		// Ping 失败时关闭已打开的资源，避免连接泄漏。
		if cerr := database.Close(); cerr != nil {
			return nil, fmt.Errorf("ping sqlite: %w; close: %v", err, cerr)
		}
		return nil, fmt.Errorf("ping sqlite: %w", err)
	}

	// 额外显式执行一次 PRAGMA，确保在连接层生效。
	if _, err := database.Exec("PRAGMA journal_mode=WAL;"); err != nil {
		if cerr := database.Close(); cerr != nil {
			return nil, fmt.Errorf("pragma journal_mode: %w; close: %v", err, cerr)
		}
		return nil, fmt.Errorf("pragma journal_mode: %w", err)
	}
	if _, err := database.Exec("PRAGMA foreign_keys=ON;"); err != nil {
		if cerr := database.Close(); cerr != nil {
			return nil, fmt.Errorf("pragma foreign_keys: %w; close: %v", err, cerr)
		}
		return nil, fmt.Errorf("pragma foreign_keys: %w", err)
	}

	if _, err := database.Exec(schema); err != nil {
		if cerr := database.Close(); cerr != nil {
			return nil, fmt.Errorf("init schema: %w; close: %v", err, cerr)
		}
		return nil, fmt.Errorf("init schema: %w", err)
	}

	return database, nil
}
