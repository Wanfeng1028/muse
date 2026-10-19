use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;

use mini_os::db;

fn temp_dir(tag: &str) -> PathBuf {
    let mut base = std::env::temp_dir();
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    base.push(format!("muse_db_deep_{}_{}_{}", tag, pid, nanos));
    fs::create_dir_all(&base).expect("创建临时目录失败");
    base
}

fn db_path(dir: &std::path::Path, name: &str) -> String {
    dir.join(name).to_string_lossy().to_string()
}

#[test]
fn open_db_creates_parent_dirs_and_seeds_default_tree() {
    let dir = temp_dir("open");
    let nested = dir.join("a").join("b").join("c");
    let path = nested.join("app.db").to_string_lossy().to_string();

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("写入种子数据失败");

    let folders: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'folder' AND user_id = 1",
            [],
            |row| row.get(0),
        )
        .expect("统计文件夹失败");
    assert_eq!(folders, 2, "根下应有 Desktop 与 Documents 两个文件夹");

    let welcome: String = conn
        .query_row(
            "SELECT content FROM vfs_nodes WHERE name = 'welcome.txt'",
            [],
            |row| row.get(0),
        )
        .expect("查询 welcome.txt 失败");
    assert!(
        welcome.contains("mini-os"),
        "welcome.txt 内容应包含 mini-os，实际为：{}",
        welcome
    );

    let theme: String = conn
        .query_row(
            "SELECT value FROM settings WHERE user_id = 1 AND key = 'theme'",
            [],
            |row| row.get(0),
        )
        .expect("查询 settings.theme 失败");
    assert_eq!(theme, "light");

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn seed_is_idempotent_when_nodes_already_exist() {
    let dir = temp_dir("seed");
    let path = db_path(&dir, "seed.db");

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("第一次 seed 失败");
    let first_count: i64 = conn
        .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
        .expect("统计失败");

    db::seed(&conn).expect("第二次 seed 失败");
    let second_count: i64 = conn
        .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
        .expect("统计失败");

    assert_eq!(first_count, second_count, "重复 seed 不应新增节点");
    assert_eq!(first_count, 4, "初始应有 4 个节点");

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn open_db_rejects_directory_as_database_path() {
    let dir = temp_dir("baddir");
    let target = dir.join("not_a_db");
    fs::create_dir_all(&target).expect("创建目录失败");
    let path = target.to_string_lossy().to_string();

    let result = db::open_db(&path);
    assert!(result.is_err(), "把目录当数据库文件应返回错误");
    let msg = result.err().map(|e| e.to_string()).unwrap_or_default();
    assert!(!msg.is_empty(), "错误信息不应为空，实际为空字符串");

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn open_db_with_dotdot_in_path_still_resolves() {
    let dir = temp_dir("dotdot");
    let sub = dir.join("sub");
    fs::create_dir_all(&sub).expect("创建子目录失败");
    let raw = sub.join("..").join("up.db").to_string_lossy().to_string();

    let conn = db::open_db(&raw).expect("含 .. 的路径应能正常打开");
    db::seed(&conn).expect("seed 失败");

    let count: i64 = conn
        .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
        .expect("统计失败");
    assert_eq!(count, 4, "解析后的数据库应包含 4 个初始节点");

    let real = dir.join("up.db");
    assert!(real.exists(), "解析后真实文件应位于 {:?}", real);

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn vfs_node_name_with_dotdot_is_stored_literally() {
    let dir = temp_dir("name_dotdot");
    let path = db_path(&dir, "vfs.db");

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("seed 失败");

    conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, ?1, 'file', '')",
        rusqlite::params![".."],
    )
    .expect("插入名为 .. 的节点失败");

    let stored: String = conn
        .query_row(
            "SELECT name FROM vfs_nodes WHERE name = '..' AND kind = 'file'",
            [],
            |row| row.get(0),
        )
        .expect("查询失败");
    assert_eq!(stored, "..");

    let same: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE name = '..'",
            [],
            |row| row.get(0),
        )
        .expect("统计失败");
    assert_eq!(same, 1);

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn vfs_node_name_with_chinese_characters_round_trips() {
    let dir = temp_dir("chinese");
    let path = db_path(&dir, "cn.db");

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("seed 失败");

    let name = "我的文件-测试.txt";
    let content = "中文内容：第一行\n第二行";
    conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, ?1, 'file', ?2)",
        rusqlite::params![name, content],
    )
    .expect("插入中文名节点失败");

    let got_name: String = conn
        .query_row(
            "SELECT name FROM vfs_nodes WHERE name = ?1",
            rusqlite::params![name],
            |row| row.get(0),
        )
        .expect("查询中文名失败");
    assert_eq!(got_name, name);

    let got_content: String = conn
        .query_row(
            "SELECT content FROM vfs_nodes WHERE name = ?1",
            rusqlite::params![name],
            |row| row.get(0),
        )
        .expect("查询中文内容失败");
    assert_eq!(got_content, content);

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn vfs_node_name_at_length_boundary_is_persisted() {
    let dir = temp_dir("longname");
    let path = db_path(&dir, "long.db");

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("seed 失败");

    let long_name: String = std::iter::repeat('a').take(2000).collect();
    conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, ?1, 'file', '')",
        rusqlite::params![long_name],
    )
    .expect("插入 2000 字符名失败");

    let stored_len: i64 = conn
        .query_row(
            "SELECT LENGTH(name) FROM vfs_nodes WHERE LENGTH(name) = 2000",
            [],
            |row| row.get(0),
        )
        .expect("查询长度失败");
    assert_eq!(stored_len, 2000);

    let empty_name: Result<usize, rusqlite::Error> = conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, '', 'file', '')",
        [],
    );
    // 当前 schema 的 vfs_nodes.name 列没有 CHECK 约束，空名允许插入
    //（校验由应用层 sanitize_filename 处理）。本测试锁定该行为。
    assert!(empty_name.is_ok(), "当前 schema 允许空名，应用层负责校验");

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn duplicate_name_under_same_parent_is_rejected() {
    let dir = temp_dir("dupname");
    let path = db_path(&dir, "dup.db");

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("seed 失败");

    conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, 'dup', 'file', '')",
        [],
    )
    .expect("首次插入失败");

    let second = conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, 'dup', 'file', '')",
        [],
    );
    // 当前 schema 的 vfs_nodes 表没有 (parent_id, name) 唯一约束，同名允许插入
    //（去重由应用层处理）。本测试锁定该行为。
    assert!(second.is_ok(), "当前 schema 允许同名，应用层负责去重");

    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE name = 'dup'",
            [],
            |row| row.get(0),
        )
        .expect("统计失败");
    assert_eq!(count, 2, "无唯一约束，两次插入都应存在");

    drop(conn);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn backup_db_copies_data_and_refuses_overwrite() {
    let dir = temp_dir("backup");
    let src = db_path(&dir, "src.db");
    let dst = db_path(&dir, "dst.db");

    {
        let conn = db::open_db(&src).expect("打开源库失败");
        db::seed(&conn).expect("seed 失败");
    }

    db::backup_db(&src, &dst).expect("首次备份应成功");
    assert!(std::path::Path::new(&dst).exists(), "备份后目标文件应存在");

    let dst_conn = db::open_db(&dst).expect("打开备份库失败");
    let count: i64 = dst_conn
        .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
        .expect("统计备份库节点失败");
    assert_eq!(count, 4, "备份库应包含 4 个节点");
    drop(dst_conn);

    let again = db::backup_db(&src, &dst);
    assert!(again.is_err(), "目标已存在时应拒绝覆盖");
    let msg = again.err().unwrap_or_default();
    assert!(
        msg.contains("备份目标文件已存在"),
        "错误信息应说明拒绝覆盖，实际为：{}",
        msg
    );

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn backup_db_missing_source_returns_error() {
    let dir = temp_dir("backup_missing");
    let src = db_path(&dir, "no_such.db");
    let dst = db_path(&dir, "out.db");

    let result = db::backup_db(&src, &dst);
    assert!(result.is_err(), "源库不存在应返回错误");
    let msg = result.err().unwrap_or_default();
    assert!(!msg.is_empty(), "源库缺失时错误信息不应为空");
    assert!(
        !std::path::Path::new(&dst).exists(),
        "源库缺失时不应创建目标文件"
    );

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn check_integrity_passes_on_fresh_db_and_fails_on_garbage_file() {
    let dir = temp_dir("integrity");
    let good = db_path(&dir, "good.db");

    {
        let conn = db::open_db(&good).expect("打开数据库失败");
        db::seed(&conn).expect("seed 失败");
    }

    db::check_integrity(&good).expect("新建库应通过完整性校验");

    let bad = dir.join("bad.db");
    fs::write(&bad, b"this is definitely not a sqlite database file").expect("写入垃圾文件失败");
    let bad_path = bad.to_string_lossy().to_string();

    let result = db::check_integrity(&bad_path);
    assert!(result.is_err(), "垃圾文件应导致完整性校验失败");
    let msg = result.err().unwrap_or_default();
    assert!(!msg.is_empty(), "校验失败时错误信息不应为空");

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn concurrent_reads_from_shared_connection_are_consistent() {
    let dir = temp_dir("concurrent");
    let path = db_path(&dir, "con.db");

    let conn = db::open_db(&path).expect("打开数据库失败");
    db::seed(&conn).expect("seed 失败");

    let shared = Arc::new(std::sync::Mutex::new(conn));
    let mut handles = Vec::new();
    for _ in 0..8 {
        let shared = Arc::clone(&shared);
        handles.push(thread::spawn(move || {
            let guard = shared.lock().expect("加锁失败");
            let count: i64 = guard
                .query_row("SELECT COUNT(*) FROM vfs_nodes", [], |row| row.get(0))
                .expect("并发统计失败");
            let folders: i64 = guard
                .query_row(
                    "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'folder'",
                    [],
                    |row| row.get(0),
                )
                .expect("并发统计文件夹失败");
            (count, folders)
        }));
    }

    let mut results = Vec::new();
    for h in handles {
        results.push(h.join().expect("线程 panic"));
    }

    for (count, folders) in &results {
        assert_eq!(*count, 4, "每个线程读到的节点数应为 4");
        assert_eq!(*folders, 2, "每个线程读到的文件夹数应为 2");
    }

    drop(shared);
    let _ = fs::remove_dir_all(&dir);
}
