// src/migrate.rs
// 版本化数据库迁移：schema_migrations 记录已应用版本，支持幂等重复调用

use rusqlite::Connection;

/// 迁移 001 的 SQL：建表 vfs_nodes 与 settings（与 db.rs 原始建表语句逐字一致）
const MIGRATION_001_VFS_NODES: &str = "CREATE TABLE IF NOT EXISTS vfs_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES vfs_nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('file','folder')),
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )";

const MIGRATION_001_SETTINGS: &str = "CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )";

/// 确保 schema_migrations 表存在
fn ensure_migrations_table(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )",
        [],
    )?;
    Ok(())
}

/// 查询某版本是否已应用
fn is_applied(conn: &Connection, version: &str) -> rusqlite::Result<bool> {
    let count: i64 = conn.query_row(
        "SELECT COUNT(*) FROM schema_migrations WHERE version = ?1",
        [version],
        |row| row.get(0),
    )?;
    Ok(count > 0)
}

/// 迁移 001：初始建表
fn apply_001(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;
    tx.execute(MIGRATION_001_VFS_NODES, [])?;
    tx.execute(MIGRATION_001_SETTINGS, [])?;
    tx.execute("INSERT INTO schema_migrations(version) VALUES ('001')", [])?;
    tx.commit()?;
    Ok(())
}

/// 迁移 002：vfs_nodes 增加 content_blob / mime_type 列（幂等）
fn apply_002(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;

    let mut has_blob = false;
    let mut has_mime = false;
    {
        let mut stmt = tx.prepare("PRAGMA table_info(vfs_nodes)")?;
        let mut rows = stmt.query([])?;
        while let Some(row) = rows.next()? {
            let name: String = row.get(1)?;
            if name == "content_blob" {
                has_blob = true;
            }
            if name == "mime_type" {
                has_mime = true;
            }
        }
    }

    if !has_blob {
        tx.execute("ALTER TABLE vfs_nodes ADD COLUMN content_blob BLOB", [])?;
    }
    if !has_mime {
        tx.execute("ALTER TABLE vfs_nodes ADD COLUMN mime_type TEXT", [])?;
    }

    tx.execute("INSERT INTO schema_migrations(version) VALUES ('002')", [])?;
    tx.commit()?;
    Ok(())
}

/// 迁移 003：多用户隔离。新增 users / sessions / shares 表，
/// 为 vfs_nodes 增加 user_id 列，并将 settings 重建为 (user_id, key) 联合主键。
fn apply_003(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;

    // a) users 表。password_hash 允许 NULL，代表不可登录的占位用户。
    tx.execute(
        "CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )",
        [],
    )?;

    // b) sessions 表 + 索引
    tx.execute(
        "CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )",
        [],
    )?;
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
        [],
    )?;
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)",
        [],
    )?;

    // c) shares 表 + 索引
    tx.execute(
        "CREATE TABLE IF NOT EXISTS shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            node_id INTEGER NOT NULL REFERENCES vfs_nodes(id) ON DELETE CASCADE,
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )",
        [],
    )?;
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_shares_token ON shares(token)",
        [],
    )?;

    // d) vfs_nodes 增加 user_id 列（SQLite ADD COLUMN 带 NOT NULL 必须提供 DEFAULT）。
    //    先查 PRAGMA 确保幂等。
    let mut has_user_id = false;
    {
        let mut stmt = tx.prepare("PRAGMA table_info(vfs_nodes)")?;
        let mut rows = stmt.query([])?;
        while let Some(row) = rows.next()? {
            let name: String = row.get(1)?;
            if name == "user_id" {
                has_user_id = true;
            }
        }
    }
    if !has_user_id {
        tx.execute(
            "ALTER TABLE vfs_nodes ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            [],
        )?;
    }
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_vfs_user ON vfs_nodes(user_id)",
        [],
    )?;

    // e) settings 重建为 (user_id, key) 联合主键。
    //    001 建的 settings 是 key 单主键；此处 4 步走：
    //    建新表 -> 拷贝老数据（归属 user_id=1）-> 删旧表 -> 重命名。
    //    先查 PRAGMA 判断是否已经是新结构，避免重复重建。
    let mut settings_needs_rebuild = true;
    {
        let mut stmt = tx.prepare("PRAGMA table_info(settings)")?;
        let mut rows = stmt.query([])?;
        let mut has_user_id = false;
        while let Some(row) = rows.next()? {
            let name: String = row.get(1)?;
            if name == "user_id" {
                has_user_id = true;
            }
        }
        if has_user_id {
            settings_needs_rebuild = false;
        }
    }
    if settings_needs_rebuild {
        tx.execute(
            "CREATE TABLE IF NOT EXISTS settings_new (
                user_id INTEGER NOT NULL DEFAULT 1,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY(user_id, key)
            )",
            [],
        )?;
        tx.execute(
            "INSERT INTO settings_new(user_id, key, value) SELECT 1, key, value FROM settings",
            [],
        )?;
        tx.execute("DROP TABLE settings", [])?;
        tx.execute("ALTER TABLE settings_new RENAME TO settings", [])?;
    }

    // f) 占位用户 id=1：003 首次建表时理论上不存在 id=1 的真实用户，
    //    OR IGNORE 兜底（若库中已存在同 id 或同 username 则跳过）。
    tx.execute(
        "INSERT OR IGNORE INTO users(id, username, password_hash, is_admin) VALUES (1, 'legacy', NULL, 0)",
        [],
    )?;

    // g) 防御性：ADD COLUMN DEFAULT 1 已保证非空，此 UPDATE 影响 0 行。
    tx.execute("UPDATE vfs_nodes SET user_id = 1 WHERE user_id IS NULL", [])?;

    // h) 记录版本
    tx.execute("INSERT INTO schema_migrations(version) VALUES ('003')", [])?;

    tx.commit()?;
    Ok(())
}

/// 迁移 008：TOTP 两步验证。
/// users 新增 totp_secret（AES-256-GCM 加密后的 hex，可空）与 totp_enabled（0/1，默认 0）；
/// 新建 tfa_backup_codes（备用码 argon2 哈希，一次一码）与 tfa_challenges（登录二次验证挑战，5 分钟有效）表。
/// 幂等：列用 PRAGMA table_info 判存在，表用 CREATE TABLE IF NOT EXISTS。
fn apply_008(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;

    for (col, ddl) in [
        (
            "totp_secret",
            "ALTER TABLE users ADD COLUMN totp_secret TEXT NULL",
        ),
        (
            "totp_enabled",
            "ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0",
        ),
    ] {
        let mut has = false;
        {
            let mut stmt = tx.prepare("PRAGMA table_info(users)")?;
            let mut rows = stmt.query([])?;
            while let Some(row) = rows.next()? {
                let name: String = row.get(1)?;
                if name == col {
                    has = true;
                }
            }
        }
        if !has {
            tx.execute(ddl, [])?;
        }
    }

    tx.execute(
        "CREATE TABLE IF NOT EXISTS tfa_backup_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code_hash TEXT NOT NULL,
            used_at TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )",
        [],
    )?;
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_tfa_backup_codes_user ON tfa_backup_codes(user_id)",
        [],
    )?;
    tx.execute(
        "CREATE TABLE IF NOT EXISTS tfa_challenges (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )",
        [],
    )?;

    tx.execute("INSERT INTO schema_migrations(version) VALUES ('008')", [])?;
    tx.commit()?;
    Ok(())
}

/// 单个迁移：版本号 + 应用函数。
pub type Migration = (&'static str, fn(&Connection) -> rusqlite::Result<()>);

/// 迁移注册表：版本号与应用函数的唯一对应。
/// 新增迁移时只改这里；run_migrations 与单测期望都从它派生，避免硬编码版本号漂移。
pub const MIGRATIONS: &[Migration] = &[
    ("001", apply_001),
    ("002", apply_002),
    ("003", apply_003),
    ("004", apply_004),
    ("005", apply_005),
    ("006", apply_006),
    ("007", apply_007),
    ("008", apply_008),
];

/// 运行所有迁移。幂等：对同一文件重复调用不会报错，schema_migrations 行数不变。
pub fn run_migrations(conn: &Connection) -> rusqlite::Result<()> {
    ensure_migrations_table(conn)?;

    for (version, apply) in MIGRATIONS {
        if !is_applied(conn, version)? {
            apply(conn)?;
        }
    }

    Ok(())
}
/// 迁移 007：notes（速记便签）与 events（日程）表。
/// 幂等：CREATE TABLE IF NOT EXISTS + schema_migrations 记账（风格与 006 一致）。
fn apply_007(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;
    tx.execute(
        "CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            pinned INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )",
        [],
    )?;
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)",
        [],
    )?;
    tx.execute(
        "CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT,
            all_day INTEGER NOT NULL DEFAULT 0,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )",
        [],
    )?;
    tx.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_user_start ON events(user_id, starts_at)",
        [],
    )?;
    tx.execute("INSERT INTO schema_migrations(version) VALUES ('007')", [])?;
    tx.commit()?;
    Ok(())
}

/// 迁移 005：users 增加 role 列（RBAC）。
/// 幂等；默认 'editor'，admin 用户回填为 'admin'，legacy 占位回填为 'viewer'。
fn apply_005(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;

    let mut has_role = false;
    {
        let mut stmt = tx.prepare("PRAGMA table_info(users)")?;
        let mut rows = stmt.query([])?;
        while let Some(row) = rows.next()? {
            let name: String = row.get(1)?;
            if name == "role" {
                has_role = true;
            }
        }
    }

    if !has_role {
        tx.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'editor' \
             CHECK(role IN ('admin','editor','viewer'))",
            [],
        )?;
    }

    // 先回填 admin（is_admin = 1 的真实用户）
    tx.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1", [])?;

    // 再把 legacy 占位用户（password_hash IS NULL）覆盖为 viewer。
    // 顺序必须在 admin 回填之后，保证 legacy 最终为 'viewer'。
    tx.execute(
        "UPDATE users SET role = 'viewer' WHERE password_hash IS NULL",
        [],
    )?;

    tx.execute("INSERT INTO schema_migrations(version) VALUES ('005')", [])?;
    tx.commit()?;
    Ok(())
}

/// 迁移 006：shares 增加 expires_at 列（INTEGER NULL，NULL 表示永不过期）。
/// 幂等写法与 apply_004 一致：PRAGMA table_info 判列存在 + ALTER TABLE ADD COLUMN。
fn apply_006(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;

    let mut has_expires_at = false;
    {
        let mut stmt = tx.prepare("PRAGMA table_info(shares)")?;
        let mut rows = stmt.query([])?;
        while let Some(row) = rows.next()? {
            let name: String = row.get(1)?;
            if name == "expires_at" {
                has_expires_at = true;
            }
        }
    }

    if !has_expires_at {
        tx.execute("ALTER TABLE shares ADD COLUMN expires_at INTEGER NULL", [])?;
    }

    tx.execute("INSERT INTO schema_migrations(version) VALUES ('006')", [])?;
    tx.commit()?;
    Ok(())
}

/// 迁移 004：shares 增加 share_type 列（幂等，默认 'file'）
fn apply_004(conn: &Connection) -> rusqlite::Result<()> {
    let tx = conn.unchecked_transaction()?;

    let mut has_share_type = false;
    {
        let mut stmt = tx.prepare("PRAGMA table_info(shares)")?;
        let mut rows = stmt.query([])?;
        while let Some(row) = rows.next()? {
            let name: String = row.get(1)?;
            if name == "share_type" {
                has_share_type = true;
            }
        }
    }

    if !has_share_type {
        tx.execute(
            "ALTER TABLE shares ADD COLUMN share_type TEXT NOT NULL DEFAULT 'file' \
             CHECK(share_type IN ('file','dir'))",
            [],
        )?;
    }

    tx.execute("INSERT INTO schema_migrations(version) VALUES ('004')", [])?;
    tx.commit()?;
    Ok(())
}

/// 返回已应用的迁移版本，按 version 排序
pub fn applied_versions(conn: &Connection) -> rusqlite::Result<Vec<String>> {
    ensure_migrations_table(conn)?;
    let mut stmt = conn.prepare("SELECT version FROM schema_migrations ORDER BY version ASC")?;
    let mut rows = stmt.query([])?;
    let mut out = Vec::new();
    while let Some(row) = rows.next()? {
        out.push(row.get::<_, String>(0)?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrations_are_idempotent() {
        let conn = Connection::open_in_memory().expect("open in-memory");
        run_migrations(&conn).expect("first run");
        run_migrations(&conn).expect("second run");

        let versions = applied_versions(&conn).expect("applied versions");
        assert_eq!(
            versions,
            MIGRATIONS
                .iter()
                .map(|(v, _)| (*v).to_string())
                .collect::<Vec<String>>()
        );

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
                row.get(0)
            })
            .expect("count");
        assert_eq!(count, MIGRATIONS.len() as i64);

        let blob_cols: i64 = conn

            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('vfs_nodes') WHERE name IN ('content_blob','mime_type')",
                [],
                |row| row.get(0),
            )
            .expect("pragma");
        assert_eq!(blob_cols, 2);
    }

    #[test]
    fn migration_003_preserves_legacy_data() {
        let conn = Connection::open_in_memory().expect("open in-memory");

        // 手工构造 001/002 之后的旧库结构。
        ensure_migrations_table(&conn).expect("migrations table");
        conn.execute(MIGRATION_001_VFS_NODES, [])
            .expect("vfs_nodes");
        conn.execute(MIGRATION_001_SETTINGS, []).expect("settings");
        conn.execute("INSERT INTO schema_migrations(version) VALUES ('001')", [])
            .expect("mark 001");
        conn.execute("ALTER TABLE vfs_nodes ADD COLUMN content_blob BLOB", [])
            .expect("add content_blob");
        conn.execute("ALTER TABLE vfs_nodes ADD COLUMN mime_type TEXT", [])
            .expect("add mime_type");
        conn.execute("INSERT INTO schema_migrations(version) VALUES ('002')", [])
            .expect("mark 002");

        // 老数据
        conn.execute(
            "INSERT INTO vfs_nodes(parent_id, name, kind, content) VALUES (NULL, 'doc.txt', 'file', 'hello')",
            [],
        )
        .expect("insert node");
        conn.execute(
            "INSERT INTO settings(key, value) VALUES ('theme', 'dark')",
            [],
        )
        .expect("insert setting");
        conn.execute("INSERT INTO settings(key, value) VALUES ('lang', 'zh')", [])
            .expect("insert setting 2");

        // 跑迁移升级到 003
        run_migrations(&conn).expect("migrate to 003");

        // users 含 legacy 占位
        let legacy_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM users WHERE id = 1 AND username = 'legacy' AND password_hash IS NULL",
                [],
                |row| row.get(0),
            )
            .expect("legacy user");
        assert_eq!(legacy_count, 1);

        // vfs_nodes 行保留且 user_id = 1
        let (name, user_id): (String, i64) = conn
            .query_row(
                "SELECT name, user_id FROM vfs_nodes WHERE name = 'doc.txt'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .expect("node row");
        assert_eq!(name, "doc.txt");
        assert_eq!(user_id, 1);

        // settings 数据保留，且可按 (user_id, key) 查询
        let theme: String = conn
            .query_row(
                "SELECT value FROM settings WHERE user_id = 1 AND key = 'theme'",
                [],
                |row| row.get(0),
            )
            .expect("theme setting");
        assert_eq!(theme, "dark");
        let lang: String = conn
            .query_row(
                "SELECT value FROM settings WHERE user_id = 1 AND key = 'lang'",
                [],
                |row| row.get(0),
            )
            .expect("lang setting");
        assert_eq!(lang, "zh");

        // 重复 run 幂等
        run_migrations(&conn).expect("second run");
        let versions = applied_versions(&conn).expect("versions");
        assert_eq!(
            versions,
            MIGRATIONS
                .iter()
                .map(|(v, _)| (*v).to_string())
                .collect::<Vec<String>>()
        );
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
                row.get(0)
            })
            .expect("count");
        assert_eq!(count, MIGRATIONS.len() as i64);
    }

    #[test]
    fn migration_004_share_type_defaults_file() {
        let conn = Connection::open_in_memory().expect("open in-memory");
        ensure_migrations_table(&conn).expect("migrations table");
        apply_001(&conn).expect("apply 001");
        apply_002(&conn).expect("apply 002");
        apply_003(&conn).expect("apply 003");

        // 003 时代：shares 表无 share_type 列
        let cols: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('shares') WHERE name = 'share_type'",
                [],
                |row| row.get(0),
            )
            .expect("pragma");
        assert_eq!(cols, 0);

        // 手工搭出 003 时代的库内容：一个 file 节点 + 一条老分享行
        conn.execute(
            "INSERT INTO vfs_nodes (id, user_id, parent_id, name, kind, content, content_blob, mime_type) \
             VALUES (1, 1, NULL, 'legacy.txt', 'file', 'hello', NULL, NULL)",
            [],
        )
        .expect("insert node");
        conn.execute(
            "INSERT INTO shares (token, node_id, owner_id) VALUES ('legacy-token', 1, 1)",
            [],
        )
        .expect("insert legacy share");

        // 升级
        run_migrations(&conn).expect("run migrations");

        // 老数据默认 'file'
        let legacy_type: String = conn
            .query_row(
                "SELECT share_type FROM shares WHERE token = 'legacy-token'",
                [],
                |row| row.get(0),
            )
            .expect("legacy share_type");
        assert_eq!(legacy_type, "file");

        // 新插入行默认 'file'
        conn.execute(
            "INSERT INTO shares (token, node_id, owner_id) VALUES ('new-token', 1, 1)",
            [],
        )
        .expect("insert new share");
        let new_type: String = conn
            .query_row(
                "SELECT share_type FROM shares WHERE token = 'new-token'",
                [],
                |row| row.get(0),
            )
            .expect("new share_type");
        assert_eq!(new_type, "file");

        // CHECK 约束拒绝非法值
        let bad = conn.execute(
            "INSERT INTO shares (token, node_id, owner_id, share_type) \
             VALUES ('bad-token', 1, 1, 'x')",
            [],
        );
        assert!(bad.is_err(), "share_type='x' 应被 CHECK 约束拒绝");

        // 重复 run 幂等
        run_migrations(&conn).expect("second run");
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
                row.get(0)
            })
            .expect("count");
        assert_eq!(count, MIGRATIONS.len() as i64);
    }

    #[test]
    fn migration_005_role_backfill() {
        let conn = Connection::open_in_memory().expect("open in-memory");
        ensure_migrations_table(&conn).expect("migrations table");
        apply_001(&conn).expect("apply 001");
        apply_002(&conn).expect("apply 002");
        apply_003(&conn).expect("apply 003");
        apply_004(&conn).expect("apply 004");

        // 003 已自动插入 legacy 占位（id=1, password_hash IS NULL）。
        // 再插入 admin 用户与普通用户。
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES ('admin', 'hash-admin', 1)",
            [],
        )
        .expect("insert admin user");
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES ('alice', 'hash-alice', 0)",
            [],
        )
        .expect("insert normal user");

        // 升级到 005
        run_migrations(&conn).expect("run migrations");

        // admin 用户 -> 'admin'
        let admin_role: String = conn
            .query_row(
                "SELECT role FROM users WHERE username = 'admin'",
                [],
                |row| row.get(0),
            )
            .expect("admin role");
        assert_eq!(admin_role, "admin");

        // 普通用户 -> 'editor'
        let alice_role: String = conn
            .query_row(
                "SELECT role FROM users WHERE username = 'alice'",
                [],
                |row| row.get(0),
            )
            .expect("alice role");
        assert_eq!(alice_role, "editor");

        // legacy 占位 -> 'viewer'
        let legacy_role: String = conn
            .query_row(
                "SELECT role FROM users WHERE username = 'legacy'",
                [],
                |row| row.get(0),
            )
            .expect("legacy role");
        assert_eq!(legacy_role, "viewer");

        // CHECK 约束拒绝非法值
        let bad = conn.execute("UPDATE users SET role = 'x' WHERE username = 'alice'", []);
        assert!(bad.is_err(), "role='x' 应被 CHECK 约束拒绝");

        // 重复 run 幂等
        run_migrations(&conn).expect("second run");
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
                row.get(0)
            })
            .expect("count");
        assert_eq!(count, MIGRATIONS.len() as i64);
    }
}
