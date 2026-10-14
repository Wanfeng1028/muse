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
	max_visits INTEGER,
	burn INTEGER NOT NULL DEFAULT 0,
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

	if err := migrate(database); err != nil {
		if cerr := database.Close(); cerr != nil {
			return nil, fmt.Errorf("migrate: %w; close: %v", err, cerr)
		}
		return nil, fmt.Errorf("migrate: %w", err)
	}

	return database, nil
}

// migrate 负责把老库结构升级到当前版本。
// v1 -> v2：links 表新增 max_visits（NULL=不限次数）与 burn（0/1，默认0）。
func migrate(db *sql.DB) error {
	var v int
	if err := db.QueryRow("PRAGMA user_version;").Scan(&v); err != nil {
		return fmt.Errorf("read user_version: %w", err)
	}
	if v >= 2 {
		return nil
	}

	// 检查 max_visits 是否已存在，避免重复 ALTER 导致报错。
	rows, err := db.Query("PRAGMA table_info(links);")
	if err != nil {
		return fmt.Errorf("table_info links: %w", err)
	}
	hasMaxVisits := false
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
			if cerr := rows.Close(); cerr != nil {
				return fmt.Errorf("scan table_info: %w; close: %v", err, cerr)
			}
			return fmt.Errorf("scan table_info: %w", err)
		}
		if name == "max_visits" {
			hasMaxVisits = true
		}
	}
	if err := rows.Err(); err != nil {
		if cerr := rows.Close(); cerr != nil {
			return fmt.Errorf("iterate table_info: %w; close: %v", err, cerr)
		}
		return fmt.Errorf("iterate table_info: %w", err)
	}
	if err := rows.Close(); err != nil {
		return fmt.Errorf("close table_info: %w", err)
	}

	if !hasMaxVisits {
		if _, err := db.Exec("ALTER TABLE links ADD COLUMN max_visits INTEGER;"); err != nil {
			return fmt.Errorf("add column max_visits: %w", err)
		}
		if _, err := db.Exec("ALTER TABLE links ADD COLUMN burn INTEGER NOT NULL DEFAULT 0;"); err != nil {
			return fmt.Errorf("add column burn: %w", err)
		}
	}

	if _, err := db.Exec("PRAGMA user_version = 2;"); err != nil {
		return fmt.Errorf("set user_version: %w", err)
	}
	return nil
}
