// src/db.rs
// 数据库打开、迁移、备份与完整性校验

use std::time::Duration;

use rusqlite::{backup::Backup, params, Connection, OpenFlags};

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

    // 运行版本化迁移（建表 + 增量列）
    crate::migrate::run_migrations(&conn)?;

    Ok(conn)
}

/// 种子数据：vfs_nodes 为空时插入初始文件结构（归属 legacy 占位用户 id=1），
/// settings 按用户维度使用 INSERT OR IGNORE。不创建可登录用户。
pub fn seed(conn: &Connection) -> rusqlite::Result<()> {
    // 统计节点数量
    let count: i64 = conn.query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))?;

    if count == 0 {
        // 根下文件夹：Desktop、Documents（显式归属 legacy 占位用户 user_id=1）
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, ?1, 'folder', '')",
            params!["Desktop"],
        )?;
        let desktop_id = conn.last_insert_rowid();

        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, ?1, 'folder', '')",
            params!["Documents"],
        )?;
        let documents_id = conn.last_insert_rowid();

        // Desktop/welcome.txt
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, ?1, ?2, 'file', ?3)",
            params![
                desktop_id,
                "welcome.txt",
                "欢迎使用 mini-os！这是一个运行在浏览器里的迷你操作系统。\n试试打开文件管理器、文本编辑器或终端吧。"
            ],
        )?;

        // Documents/notes.txt
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, ?1, ?2, 'file', ?3)",
            params![
                documents_id,
                "notes.txt",
                "我的第一条笔记：\n- 双击文件夹可以进入\n- 点击图标可以打开应用\n- 在终端里输入 help 查看命令"
            ],
        )?;
    }

    // 默认设置（按用户维度），存在则忽略
    conn.execute(
        "INSERT OR IGNORE INTO settings (user_id, key, value) VALUES (1, 'theme', 'light')",
        [],
    )?;
    conn.execute(
        "INSERT OR IGNORE INTO settings (user_id, key, value) VALUES (1, 'wallpaper', 'ocean')",
        [],
    )?;

    Ok(())
}

/// 在线备份：只读打开源库，写入目标库；目标已存在则拒绝覆盖
pub fn backup_db(src_path: &str, dst_path: &str) -> Result<(), String> {
    if std::path::Path::new(dst_path).exists() {
        return Err(format!("备份目标文件已存在，拒绝覆盖：{}", dst_path));
    }

    let src = Connection::open_with_flags(src_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|e| e.to_string())?;
    let mut dst = Connection::open(dst_path).map_err(|e| e.to_string())?;

    let backup = Backup::new(&src, &mut dst).map_err(|e| e.to_string())?;
    backup
        .run_to_completion(100, Duration::ZERO, None)
        .map_err(|e| e.to_string())?;

    Ok(())
}

/// 完整性校验：只读打开，PRAGMA integrity_check 第一行必须为 ok
pub fn check_integrity(path: &str) -> Result<(), String> {
    let conn = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|e| e.to_string())?;

    let result: String = conn
        .query_row("PRAGMA integrity_check", [], |row| row.get(0))
        .map_err(|e| e.to_string())?;

    if result.trim().eq_ignore_ascii_case("ok") {
        Ok(())
    } else {
        Err(format!("完整性校验失败：{}", result))
    }
}
