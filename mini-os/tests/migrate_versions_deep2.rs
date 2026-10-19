use std::path::PathBuf;

use mini_os::migrate::{applied_versions, run_migrations};
use rusqlite::Connection;

fn temp_db_path(tag: &str) -> PathBuf {
    std::env::temp_dir().join(format!(
        "minios-mig-deep2-{}-{}.db",
        std::process::id(),
        tag
    ))
}

fn column_names(conn: &Connection, table: &str) -> Vec<String> {
    let sql = format!("PRAGMA table_info({})", table);
    let mut stmt = conn.prepare(&sql).unwrap();
    let mut rows = stmt.query([]).unwrap();
    let mut names = Vec::new();
    while let Some(row) = rows.next().unwrap() {
        let name: String = row.get(1).unwrap();
        names.push(name);
    }
    names
}

#[test]
fn applied_versions_returns_sorted_seven() {
    let conn = mini_os::db::open_db(":memory:").unwrap();
    let versions = applied_versions(&conn).unwrap();
    assert_eq!(
        versions,
        vec![
            "001".to_string(),
            "002".to_string(),
            "003".to_string(),
            "004".to_string(),
            "005".to_string(),
            "006".to_string(),
            "007".to_string()
        ]
    );
}

#[test]
fn applied_versions_empty_before_any_migration() {
    let conn = Connection::open_in_memory().unwrap();
    let versions = applied_versions(&conn).unwrap();
    assert!(versions.is_empty());
    assert_eq!(versions.len(), 0);
}

#[test]
fn run_migrations_repairs_dropped_005() {
    let conn = mini_os::db::open_db(":memory:").unwrap();

    conn.execute("DELETE FROM schema_migrations WHERE version = '005'", [])
        .unwrap();
    conn.execute("ALTER TABLE users DROP COLUMN role", [])
        .unwrap();

    let before = column_names(&conn, "users");
    assert!(!before.iter().any(|n| n == "role"));

    run_migrations(&conn).unwrap();

    let versions = applied_versions(&conn).unwrap();
    assert_eq!(versions.len(), 7);
    assert_eq!(versions[4], "005");
    assert_eq!(versions[5], "006");
    assert_eq!(versions[6], "007");

    let after = column_names(&conn, "users");
    assert!(after.iter().any(|n| n == "role"));

    let role: String = conn
        .query_row(
            "SELECT role FROM users WHERE username = 'legacy'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(role, "viewer");
}

#[test]
fn open_db_migrates_foreign_sqlite_file() {
    let path = temp_db_path("foreign");
    let path_str = path.to_str().unwrap().to_string();

    {
        let conn = Connection::open(&path).unwrap();
        conn.execute("CREATE TABLE foo(a INTEGER)", []).unwrap();
        conn.execute("INSERT INTO foo(a) VALUES (42)", []).unwrap();
    }

    let conn = mini_os::db::open_db(&path_str).unwrap();

    let count: i64 = conn
        .query_row("SELECT COUNT(*) FROM foo", [], |row| row.get(0))
        .unwrap();
    assert_eq!(count, 1);

    let versions = applied_versions(&conn).unwrap();
    assert_eq!(versions.len(), 7);
    assert_eq!(versions[0], "001");
    assert_eq!(versions[4], "005");
    assert_eq!(versions[5], "006");
    assert_eq!(versions[6], "007");

    let _ = std::fs::remove_file(&path);
}

#[test]
fn backup_chain_integrity_ok() {
    let src = temp_db_path("backup-src");
    let dst = temp_db_path("backup-dst");
    let src_str = src.to_str().unwrap().to_string();
    let dst_str = dst.to_str().unwrap().to_string();

    let _ = std::fs::remove_file(&dst);

    let _conn = mini_os::db::open_db(&src_str).unwrap();

    let result = mini_os::db::backup_db(&src_str, &dst_str);
    assert!(result.is_ok());

    let integrity = mini_os::db::check_integrity(&dst_str);
    assert!(integrity.is_ok());

    let _ = std::fs::remove_file(&src);
    let _ = std::fs::remove_file(&dst);
}

#[test]
fn seed_idempotent_across_reopen() {
    let path = temp_db_path("seed-reopen");
    let path_str = path.to_str().unwrap().to_string();

    {
        let state = mini_os::init_state(&path_str, "static");
        drop(state);
    }

    {
        let state = mini_os::init_state(&path_str, "static");
        drop(state);
    }

    let conn = Connection::open(&path_str).unwrap();
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE name = 'Desktop' AND parent_id IS NULL",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 1);

    let _ = std::fs::remove_file(&path);
}

#[test]
fn legacy_user_role_is_viewer_after_fresh_open() {
    let conn = mini_os::db::open_db(":memory:").unwrap();

    let (role, password_hash): (String, Option<String>) = conn
        .query_row(
            "SELECT role, password_hash FROM users WHERE username = 'legacy'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();

    assert_eq!(role, "viewer");
    assert!(password_hash.is_none());
}
