// src/db.rs
// 数据库打开与种子数据初始化

use rusqlite::{params, Connection};

/// 打开数据库连接，必要时创建父目录并建表
pub fn open_db(path: &str) -> rusqlite::Result<Connection> {
    // 非内存库时确保父目录存在
    if path != ":memory:" {
        if let Some(parent) = std::path::Path::new(path).parent() {
            if !parent.as_os_str().is_empty() {
                let _ = std::fs::create_dir_all(parent);
            }
        }
    }

    let conn = Connection::open(path)?;

    // 开启外键约束
    conn.execute("PRAGMA foreign_keys = ON", [])?;

    // 建表：虚拟文件系统节点
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vfs_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES vfs_nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('file','folder')),
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )",
        [],
    )?;

    // 建表：设置键值
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )",
        [],
    )?;

    // 幂等迁移：vfs_nodes 增加 content_blob / mime_type 列
    {
        let mut stmt = conn.prepare("PRAGMA table_info(vfs_nodes)")?;
        let mut has_blob = false;
        let mut has_mime = false;
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
        drop(rows);
        drop(stmt);

        if !has_blob {
            conn.execute("ALTER TABLE vfs_nodes ADD COLUMN content_blob BLOB", [])?;
        }
        if !has_mime {
            conn.execute("ALTER TABLE vfs_nodes ADD COLUMN mime_type TEXT", [])?;
        }
    }

    Ok(conn)
}

/// 种子数据：vfs_nodes 为空时插入初始文件结构，settings 用 INSERT OR IGNORE
pub fn seed(conn: &Connection) -> rusqlite::Result<()> {
    // 统计节点数量
    let count: i64 = conn.query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))?;

    if count == 0 {
        // 根下文件夹：Desktop、Documents
        conn.execute(
            "INSERT INTO vfs_nodes (parent_id, name, kind, content) VALUES (NULL, ?1, 'folder', '')",
            params!["Desktop"],
        )?;
        let desktop_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO vfs_nodes (parent_id, name, kind, content) VALUES (NULL, ?1, 'folder', '')",
            params!["Documents"],
        )?;
        let documents_id = conn.last_insert_rowid();

        // Desktop/welcome.txt
        conn.execute(
            "INSERT INTO vfs_nodes (parent_id, name, kind, content) VALUES (?1, ?2, 'file', ?3)",
            params![
                desktop_id,
                "welcome.txt",
                "欢迎使用 mini-os！这是一个运行在浏览器里的迷你操作系统。\n试试打开文件管理器、文本编辑器或终端吧。"
            ],
        )?;

        // Documents/notes.txt
        conn.execute(
            "INSERT INTO vfs_nodes (parent_id, name, kind, content) VALUES (?1, ?2, 'file', ?3)",
            params![
                documents_id,
                "notes.txt",
                "我的第一条笔记：\n- 双击文件夹可以进入\n- 点击图标可以打开应用\n- 在终端里输入 help 查看命令"
            ],
        )?;
    }

    // 默认设置，存在则忽略
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('theme', 'light')",
        [],
    )?;
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('wallpaper', 'ocean')",
        [],
    )?;

    Ok(())
}
