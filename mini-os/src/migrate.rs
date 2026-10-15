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
    tx.execute(
        "INSERT INTO schema_migrations(version) VALUES ('001')",
        [],
    )?;
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

    tx.execute(
        "INSERT INTO schema_migrations(version) VALUES ('002')",
        [],
    )?;
    tx.commit()?;
    Ok(())
}

/// 运行所有迁移。幂等：对同一文件重复调用不会报错，schema_migrations 行数不变。
pub fn run_migrations(conn: &Connection) -> rusqlite::Result<()> {
    ensure_migrations_table(conn)?;

    if !is_applied(conn, "001")? {
        apply_001(conn)?;
    }

    if !is_applied(conn, "002")? {
        apply_002(conn)?;
    }

    Ok(())
}

/// 返回已应用的迁移版本，按 version 排序
pub fn applied_versions(conn: &Connection) -> rusqlite::Result<Vec<String>> {
    ensure_migrations_table(conn)?;
    let mut stmt =
        conn.prepare("SELECT version FROM schema_migrations ORDER BY version ASC")?;
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
        assert_eq!(versions, vec!["001".to_string(), "002".to_string()]);

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| row.get(0))
            .expect("count");
        assert_eq!(count, 2);

        let blob_cols: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('vfs_nodes') WHERE name IN ('content_blob','mime_type')",
                [],
                |row| row.get(0),
            )
            .expect("pragma");
        assert_eq!(blob_cols, 2);
    }
}
