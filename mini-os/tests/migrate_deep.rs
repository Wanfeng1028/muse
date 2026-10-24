//! migrate 模块深度测试：迁移幂等、schema 结构、错误传播与并发。
//!
//! 被测模块源码见 src/migrate.rs。此处只使用源码中逐字出现的
//! 函数名 run_migrations，以及迁移建立的表/列名。

use rusqlite::Connection;
use std::sync::{Arc, Mutex};
use std::thread;

/// 打开一个内存库并跑完所有迁移。
fn migrated_conn() -> Connection {
    let conn = Connection::open_in_memory().expect("open in-memory db");
    run_migrations_for_test(&conn);
    conn
}

/// 通过被测 crate 暴露的迁移入口执行迁移。
/// 集成测试里直接调用被测库的公开函数。
use mini_os::migrate::run_migrations;

fn run_migrations_for_test(conn: &Connection) {
    run_migrations(conn).expect("run_migrations should succeed");
}

/// 读取 vfs_nodes 表的列名集合。
fn vfs_columns(conn: &Connection) -> Vec<String> {
    let mut stmt = conn
        .prepare("PRAGMA table_info(vfs_nodes)")
        .expect("prepare table_info vfs_nodes");
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .expect("query table_info vfs_nodes");
    rows.map(|r| r.expect("column name")).collect()
}

/// 读取 settings 表的列名集合。
fn settings_columns(conn: &Connection) -> Vec<String> {
    let mut stmt = conn
        .prepare("PRAGMA table_info(settings)")
        .expect("prepare table_info settings");
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .expect("query table_info settings");
    rows.map(|r| r.expect("column name")).collect()
}

/// 读取 users 表的列名集合。
fn users_columns(conn: &Connection) -> Vec<String> {
    let mut stmt = conn
        .prepare("PRAGMA table_info(users)")
        .expect("prepare table_info users");
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .expect("query table_info users");
    rows.map(|r| r.expect("column name")).collect()
}

/// 统计 schema_migrations 中某个版本的记录条数。
fn migration_count(conn: &Connection, version: &str) -> i64 {
    conn.query_row(
        "SELECT COUNT(*) FROM schema_migrations WHERE version = ?1",
        [version],
        |row| row.get(0),
    )
    .expect("count schema_migrations")
}

// ---------------------------------------------------------------------------
// 1. 首次迁移建全所有表，且每个版本只记录一次
// ---------------------------------------------------------------------------
#[test]
fn first_run_creates_all_tables_and_records_versions_once() {
    let conn = migrated_conn();

    // 断言点 1：schema_migrations 里有 001/002/003 三条，各恰好一次。
    assert_eq!(migration_count(&conn, "001"), 1);
    assert_eq!(migration_count(&conn, "002"), 1);
    assert_eq!(migration_count(&conn, "003"), 1);

    // 断言点 2：核心业务表都可查询到。
    let vfs_nodes_exists: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vfs_nodes'",
            [],
            |row| row.get(0),
        )
        .expect("count vfs_nodes table");
    assert_eq!(vfs_nodes_exists, 1);

    let settings_exists: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='settings'",
            [],
            |row| row.get(0),
        )
        .expect("count settings table");
    assert_eq!(settings_exists, 1);

    let users_exists: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'",
            [],
            |row| row.get(0),
        )
        .expect("count users table");
    assert_eq!(users_exists, 1);
}

// ---------------------------------------------------------------------------
// 2. 幂等：重复调用不报错，版本记录不增加
// ---------------------------------------------------------------------------
#[test]
fn run_migrations_is_idempotent_on_repeat_calls() {
    let conn = migrated_conn();

    // 再跑两次，必须都成功。
    run_migrations(&conn).expect("second run_migrations");
    run_migrations(&conn).expect("third run_migrations");

    // 断言点 1：版本记录没有重复插入（从 MIGRATIONS 注册表派生，不硬编码版本号）。
    for (v, _) in mini_os::migrate::MIGRATIONS {
        assert_eq!(migration_count(&conn, v), 1, "版本 {v} 应恰好一条记录");
    }

    // 断言点 2：总行数就是注册表版本数，没有多余记录。
    let total: i64 = conn
        .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
            row.get(0)
        })
        .expect("count all migrations");
    assert_eq!(total, mini_os::migrate::MIGRATIONS.len() as i64);
}

// ---------------------------------------------------------------------------
// 3. 迁移 002 给 vfs_nodes 补上 content_blob / mime_type 列
// ---------------------------------------------------------------------------
#[test]
fn migration_002_adds_blob_and_mime_columns() {
    let conn = migrated_conn();
    let cols = vfs_columns(&conn);

    // 断言点 1：两个新列都在。
    assert!(
        cols.iter().any(|c| c == "content_blob"),
        "content_blob 应存在"
    );
    assert!(cols.iter().any(|c| c == "mime_type"), "mime_type 应存在");

    // 断言点 2：原有列没被破坏。
    assert!(cols.iter().any(|c| c == "name"));
    assert!(cols.iter().any(|c| c == "kind"));
    assert!(cols.iter().any(|c| c == "content"));
}

// ---------------------------------------------------------------------------
// 4. 迁移 003 给 vfs_nodes 加 user_id，默认值为 1
// ---------------------------------------------------------------------------
#[test]
fn migration_003_adds_user_id_with_default_one() {
    let conn = migrated_conn();
    let cols = vfs_columns(&conn);

    // 断言点 1：user_id 列存在。
    assert!(cols.iter().any(|c| c == "user_id"), "user_id 应存在");

    // 断言点 2：插入一行不带 user_id 的节点，默认落到 1。
    conn.execute(
        "INSERT INTO vfs_nodes(parent_id, name, kind) VALUES (NULL, 'a.txt', 'file')",
        [],
    )
    .expect("insert vfs node");
    let user_id: i64 = conn
        .query_row(
            "SELECT user_id FROM vfs_nodes WHERE name = 'a.txt'",
            [],
            |row| row.get(0),
        )
        .expect("read user_id");
    assert_eq!(user_id, 1);
}

// ---------------------------------------------------------------------------
// 5. 迁移 003 把 settings 重建为 (user_id, key) 联合主键
// ---------------------------------------------------------------------------
#[test]
fn migration_003_rebuilds_settings_with_composite_primary_key() {
    let conn = migrated_conn();
    let cols = settings_columns(&conn);

    // 断言点 1：settings 现在有 user_id / key / value 三列。
    assert!(
        cols.iter().any(|c| c == "user_id"),
        "settings.user_id 应存在"
    );
    assert!(cols.iter().any(|c| c == "key"));
    assert!(cols.iter().any(|c| c == "value"));

    // 断言点 2：不同 user_id 下同 key 可以共存。
    conn.execute(
        "INSERT INTO settings(user_id, key, value) VALUES (1, 'theme', 'dark')",
        [],
    )
    .expect("insert settings user 1");
    conn.execute(
        "INSERT INTO settings(user_id, key, value) VALUES (2, 'theme', 'light')",
        [],
    )
    .expect("insert settings user 2");
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM settings WHERE key = 'theme'",
            [],
            |row| row.get(0),
        )
        .expect("count settings theme");
    assert_eq!(count, 2);
}

// ---------------------------------------------------------------------------
// 6. 迁移 003 建 users 表并插入 legacy 占位用户
// ---------------------------------------------------------------------------
#[test]
fn migration_003_creates_legacy_placeholder_user() {
    let conn = migrated_conn();

    // 断言点 1：legacy 用户存在，id 为 1。
    let (id, username, hash_null): (i64, String, i64) = conn
        .query_row(
            "SELECT id, username, (password_hash IS NULL) FROM users WHERE id = 1",
            [],
            |row| {
                let id: i64 = row.get(0)?;
                let username: String = row.get(1)?;
                let hash_null: i64 = row.get(2)?;
                Ok((id, username, hash_null))
            },
        )
        .expect("read legacy user");
    assert_eq!(id, 1);
    assert_eq!(username, "legacy");

    // 断言点 2：占位用户不可登录，password_hash 为 NULL。
    assert_eq!(hash_null, 1, "legacy 用户 password_hash 应为 NULL");
}

// ---------------------------------------------------------------------------
// 7. 迁移 003 建 sessions / shares 表及其索引
// ---------------------------------------------------------------------------
#[test]
fn migration_003_creates_sessions_and_shares_with_indexes() {
    let conn = migrated_conn();

    // 断言点 1：sessions 与 shares 表存在。
    let sessions: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sessions'",
            [],
            |row| row.get(0),
        )
        .expect("count sessions");
    assert_eq!(sessions, 1);

    let shares: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='shares'",
            [],
            |row| row.get(0),
        )
        .expect("count shares");
    assert_eq!(shares, 1);

    // 断言点 2：三个索引都建了。
    let idx_sessions_user: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='idx_sessions_user'",
            [],
            |row| row.get(0),
        )
        .expect("count idx_sessions_user");
    assert_eq!(idx_sessions_user, 1);

    let idx_sessions_expires: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='idx_sessions_expires'",
            [],
            |row| row.get(0),
        )
        .expect("count idx_sessions_expires");
    assert_eq!(idx_sessions_expires, 1);

    let idx_shares_token: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='idx_shares_token'",
            [],
            |row| row.get(0),
        )
        .expect("count idx_shares_token");
    assert_eq!(idx_shares_token, 1);
}

// ---------------------------------------------------------------------------
// 8. 约束生效：vfs_nodes.kind 只允许 file / folder
// ---------------------------------------------------------------------------
#[test]
fn vfs_nodes_kind_check_constraint_rejects_invalid_kind() {
    let conn = migrated_conn();

    // 断言点 1：非法 kind 被 CHECK 约束拒绝。
    let bad = conn.execute(
        "INSERT INTO vfs_nodes(parent_id, name, kind) VALUES (NULL, 'x', 'symlink')",
        [],
    );
    assert!(bad.is_err(), "非法 kind 应触发 CHECK 约束错误");

    // 断言点 2：合法 kind 能插入。
    conn.execute(
        "INSERT INTO vfs_nodes(parent_id, name, kind) VALUES (NULL, 'ok', 'folder')",
        [],
    )
    .expect("insert folder node");
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE name = 'ok'",
            [],
            |row| row.get(0),
        )
        .expect("count folder node");
    assert_eq!(count, 1);
}

// ---------------------------------------------------------------------------
// 9. 外键级联：删除父节点连带删除子节点
// ---------------------------------------------------------------------------
#[test]
fn vfs_nodes_parent_cascade_deletes_children() {
    let conn = migrated_conn();
    conn.execute("PRAGMA foreign_keys = ON", [])
        .expect("enable foreign keys");

    // 断言点 1：建父子节点。
    conn.execute(
        "INSERT INTO vfs_nodes(id, parent_id, name, kind) VALUES (10, NULL, 'parent', 'folder')",
        [],
    )
    .expect("insert parent");
    conn.execute(
        "INSERT INTO vfs_nodes(parent_id, name, kind) VALUES (10, 'child', 'file')",
        [],
    )
    .expect("insert child");

    let before: i64 = conn
        .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
        .expect("count before delete");
    assert_eq!(before, 2);

    // 断言点 2：删父后子也没了。
    conn.execute("DELETE FROM vfs_nodes WHERE id = 10", [])
        .expect("delete parent");
    let after: i64 = conn
        .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
        .expect("count after delete");
    assert_eq!(after, 0);
}

// ---------------------------------------------------------------------------
// 10. users.username 唯一约束触发错误传播
// ---------------------------------------------------------------------------
#[test]
fn users_username_unique_constraint_propagates_error() {
    let conn = migrated_conn();

    // 断言点 1：重复 username 插入返回 Err。
    conn.execute(
        "INSERT INTO users(username, password_hash, is_admin) VALUES ('alice', NULL, 0)",
        [],
    )
    .expect("insert alice");
    let dup = conn.execute(
        "INSERT INTO users(username, password_hash, is_admin) VALUES ('alice', NULL, 0)",
        [],
    );
    assert!(dup.is_err(), "重复 username 应触发 UNIQUE 约束错误");

    // 断言点 2：alice 只存了一条。
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM users WHERE username = 'alice'",
            [],
            |row| row.get(0),
        )
        .expect("count alice");
    assert_eq!(count, 1);
}

// ---------------------------------------------------------------------------
// 11. 并发：多线程同时对同一个内存库跑迁移，只应用一次
// ---------------------------------------------------------------------------
#[test]
fn concurrent_run_migrations_applies_each_version_once() {
    let conn = Connection::open_in_memory().expect("open in-memory db");
    let shared = Arc::new(Mutex::new(conn));

    let mut handles = Vec::new();
    for _ in 0..8 {
        let shared = Arc::clone(&shared);
        handles.push(thread::spawn(move || {
            let guard = shared.lock().expect("lock db");
            run_migrations(&guard).expect("concurrent run_migrations");
        }));
    }
    for h in handles {
        h.join().expect("thread join");
    }

    let guard = shared.lock().expect("lock db");

    // 断言点 1：每个版本恰好一条记录（从 MIGRATIONS 注册表派生，不硬编码版本号）。
    for (v, _) in mini_os::migrate::MIGRATIONS {
        assert_eq!(migration_count(&guard, v), 1, "版本 {v} 应恰好一条记录");
    }

    // 断言点 2：总记录数就是注册表版本数。
    let total: i64 = guard
        .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
            row.get(0)
        })
        .expect("count all migrations");
    assert_eq!(total, mini_os::migrate::MIGRATIONS.len() as i64);
}

// ---------------------------------------------------------------------------
// 12. 未迁移库：查询 schema_migrations 前先跑迁移不报错
// ---------------------------------------------------------------------------
#[test]
fn fresh_database_migrates_without_prior_tables() {
    let conn = Connection::open_in_memory().expect("open in-memory db");

    // 断言点 1：迁移前 schema_migrations 不存在。
    let before: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'",
            [],
            |row| row.get(0),
        )
        .expect("count schema_migrations before");
    assert_eq!(before, 0);

    // 断言点 2：跑完后表出现，且版本齐了。
    run_migrations(&conn).expect("run_migrations on fresh db");
    let after: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'",
            [],
            |row| row.get(0),
        )
        .expect("count schema_migrations after");
    assert_eq!(after, 1);
    assert_eq!(migration_count(&conn, "001"), 1);
    assert_eq!(migration_count(&conn, "002"), 1);
    assert_eq!(migration_count(&conn, "003"), 1);
}
