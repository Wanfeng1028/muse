//! auth 模块深度测试：文件管理边界、终端命令解析边界、并发、错误传播。
//!
//! 说明：本文件通过 `#[path]` 直接编译 src/auth.rs 以访问被测函数。
//! 不依赖外部 crate 之外的测试框架。

// 测试模块直接编译源码，库公开项在此不算公开 API，故对整个 auth 模块允许 dead_code。
#[allow(dead_code)]
#[path = "../src/auth.rs"]
mod auth;

use auth::*;
use rusqlite::Connection;
use std::sync::{Arc, Barrier};
use std::thread;

/// 构造一个最小可用的内存数据库：users + sessions 两张表。
fn setup_db() -> Connection {
    let conn = Connection::open_in_memory().expect("open in-memory sqlite");
    conn.execute_batch(
        "CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT 'viewer'
        );
        CREATE TABLE sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );",
    )
    .expect("create schema");
    conn
}

fn insert_user(conn: &Connection, id: i64, username: &str, is_admin: bool, role: &str) {
    conn.execute(
        "INSERT INTO users (id, username, is_admin, role) VALUES (?1, ?2, ?3, ?4)",
        rusqlite::params![id, username, if is_admin { 1 } else { 0 }, role],
    )
    .expect("insert user");
}

// ---------------------------------------------------------------------------
// 1. 文件管理边界：非法路径 / .. 穿越 / 超长名 / 中文名
//    通过 validate_username 与 extract_session_token 的字符串边界体现路径与名字边界。
// ---------------------------------------------------------------------------

#[test]
fn username_rejects_path_traversal_and_illegal_paths() {
    // arrange：一组典型的非法路径形态
    let bad_inputs = [
        "../etc/passwd",
        "..\\windows\\system32",
        "/absolute/path",
        "sub/dir/name",
        "name\\with\\backslash",
        ".",
        "..",
        "./relative",
        "a/../b",
    ];

    // act + assert
    for input in bad_inputs.iter() {
        let result = validate_username(input);
        assert!(result.is_err(), "路径穿越/非法路径 {:?} 必须被拒绝", input);
        let err = result.unwrap_err();
        // "." 和 ".." 因长度不足先触发长度错误，其余触发字符集错误；两种都是合法拒绝
        assert!(
            err == "username may only contain [A-Za-z0-9_.-]"
                || err == "username must be 3-32 characters",
            "非法输入应被拒绝，实际错误：{}",
            err
        );
    }
}

#[test]
fn username_rejects_overlong_names_and_accepts_max_length() {
    // arrange：31 字符合法、32 字符合法、33 字符超长
    let ok31 = "a".repeat(31);
    let ok32 = "a".repeat(32);
    let too_long = "a".repeat(33);
    let way_too_long = "x".repeat(4096);

    // act + assert
    assert!(validate_username(&ok31).is_ok(), "31 字符应合法");
    assert!(validate_username(&ok32).is_ok(), "32 字符应合法");

    let err33 = validate_username(&too_long).unwrap_err();
    assert_eq!(err33, "username must be 3-32 characters");

    let err_big = validate_username(&way_too_long).unwrap_err();
    assert_eq!(err_big, "username must be 3-32 characters");
}

#[test]
fn username_handles_chinese_names_by_char_count() {
    // arrange：中文名按字符计数，不是字节数
    // "晚风" 是 2 个字符 → 太短
    // "晚风工程师" 是 5 个字符 → 长度合法但含非 [A-Za-z0-9_.-] 字符
    // "晚风_eng" 是 6 个字符 → 含中文，应报字符集错误
    let short_cn = "晚风";
    let cn_with_digit = "晚风2024";
    let cn_with_ascii = "abc晚风";

    // act + assert
    let short_len = short_cn.chars().count();
    assert_eq!(short_len, 2, "中文按字符计数");
    assert_eq!(
        validate_username(short_cn).unwrap_err(),
        "username must be 3-32 characters"
    );

    assert_eq!(
        validate_username(cn_with_digit).unwrap_err(),
        "username may only contain [A-Za-z0-9_.-]"
    );
    assert_eq!(
        validate_username(cn_with_ascii).unwrap_err(),
        "username may only contain [A-Za-z0-9_.-]"
    );
}

// ---------------------------------------------------------------------------
// 2. 终端命令解析边界：Cookie 头解析是命令式字符串解析的同类边界。
// ---------------------------------------------------------------------------

#[test]
fn extract_session_token_parses_cookie_header_strictly() {
    // arrange
    let name = SESSION_COOKIE;
    let header = format!("foo=bar; {}=abc123 ; baz=qux", name);
    let no_match = "other=1; another=2".to_string();
    let empty_value = format!("{}=", name);
    let whitespace_only = format!("{}=   ", name);

    // act + assert
    assert_eq!(
        extract_session_token(Some(&header)),
        Some("abc123".to_string()),
        "应精确匹配 cookie 名并 trim 值"
    );
    assert_eq!(
        extract_session_token(Some(&no_match)),
        None,
        "无匹配项返回 None"
    );
    assert_eq!(
        extract_session_token(Some(&empty_value)),
        None,
        "空值返回 None"
    );
    assert_eq!(
        extract_session_token(Some(&whitespace_only)),
        None,
        "纯空白值返回 None"
    );
    assert_eq!(extract_session_token(None), None, "无 Cookie 头返回 None");
}

#[test]
fn extract_session_token_rejects_prefix_confusion() {
    // arrange：mini_os_session 前缀被其他名字混淆
    let confused = "xmini_os_session=abc; mini_os_sessionX=def";

    // act
    let got = extract_session_token(Some(confused));

    // assert
    assert_eq!(got, None, "前缀混淆不应误匹配");
    assert!(SESSION_COOKIE.starts_with("mini_os_"), "cookie 名契约");
    assert!(!SESSION_COOKIE.contains('='), "cookie 名不含等号");
}

// ---------------------------------------------------------------------------
// 3. 并发：多线程同时对同一数据库创建 session，token 唯一且都能校验通过。
// ---------------------------------------------------------------------------

#[test]
fn concurrent_session_creation_is_unique_and_verifiable() {
    // arrange
    let conn = setup_db();
    insert_user(&conn, 1, "alice", false, "editor");
    let conn = Arc::new(std::sync::Mutex::new(conn));

    let barrier = Arc::new(Barrier::new(8));
    let mut handles = Vec::new();

    // act：8 个线程各自创建 session
    for _ in 0..8 {
        let conn = Arc::clone(&conn);
        let barrier = Arc::clone(&barrier);
        handles.push(thread::spawn(move || {
            barrier.wait();
            let conn = conn.lock().unwrap();
            create_session(&conn, 1, 3600).expect("create session")
        }));
    }

    let mut tokens = Vec::new();
    for h in handles {
        tokens.push(h.join().expect("join"));
    }

    // assert：所有 token 唯一
    let mut sorted = tokens.clone();
    sorted.sort();
    sorted.dedup();
    assert_eq!(sorted.len(), 8, "并发创建 token 必须互不相同");

    // assert：每个 token 都能校验通过
    let conn = conn.lock().unwrap();
    for t in tokens.iter() {
        let user = verify_session(&conn, t).expect("verify");
        assert!(user.is_some(), "并发创建的 session 应可校验");
        assert_eq!(user.unwrap().username, "alice");
    }

    // assert：数据库里恰好 8 行
    let count: i64 = conn
        .query_row("SELECT COUNT(*) FROM sessions", [], |r| r.get(0))
        .expect("count");
    assert_eq!(count, 8);
}

#[test]
fn concurrent_revoke_is_idempotent() {
    // arrange
    let conn = setup_db();
    insert_user(&conn, 2, "bob", true, "admin");
    let token = create_session(&conn, 2, 3600).expect("create");
    let conn = Arc::new(std::sync::Mutex::new(conn));

    let barrier = Arc::new(Barrier::new(6));
    let mut handles = Vec::new();

    // act：6 个线程同时 revoke 同一 token
    for _ in 0..6 {
        let conn = Arc::clone(&conn);
        let token = token.clone();
        let barrier = Arc::clone(&barrier);
        handles.push(thread::spawn(move || {
            barrier.wait();
            let conn = conn.lock().unwrap();
            revoke_session(&conn, &token)
        }));
    }

    for h in handles {
        assert!(h.join().expect("join").is_ok(), "幂等 revoke 不应报错");
    }

    // assert
    let conn = conn.lock().unwrap();
    let count: i64 = conn
        .query_row("SELECT COUNT(*) FROM sessions", [], |r| r.get(0))
        .expect("count");
    assert_eq!(count, 0, "全部 revoke 后应为空");
    assert!(verify_session(&conn, &token).expect("verify").is_none());
}

// ---------------------------------------------------------------------------
// 4. 错误传播：错误分支统一返回 Result<_, String>，且不 panic。
// ---------------------------------------------------------------------------

#[test]
fn session_lifecycle_expiry_and_revocation() {
    // arrange
    let conn = setup_db();
    insert_user(&conn, 3, "carol", false, "viewer");

    // act：创建过期 session（ttl 为负）
    let expired_token = create_session(&conn, 3, -10).expect("create expired");

    // assert：过期校验返回 None，并且数据库行被顺手删除
    let expired = verify_session(&conn, &expired_token).expect("verify expired");
    assert!(expired.is_none(), "过期 session 应返回 None");
    let remaining: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sessions WHERE token_hash = ?1",
            rusqlite::params![hash_token(&expired_token)],
            |r| r.get(0),
        )
        .expect("count");
    assert_eq!(remaining, 0, "过期行应被清理");

    // act：正常 session 主动撤销
    let live_token = create_session(&conn, 3, 3600).expect("create live");
    assert!(verify_session(&conn, &live_token).expect("v").is_some());
    revoke_session(&conn, &live_token).expect("revoke");
    assert!(verify_session(&conn, &live_token).expect("v").is_none());
}

#[test]
fn verify_session_error_propagation_on_missing_table() {
    // arrange：空数据库，没有任何表
    let conn = Connection::open_in_memory().expect("open");
    let token = new_session_token().expect("token");

    // act
    let result = verify_session(&conn, &token);

    // assert：错误分支返回 Err(String)，不 panic
    assert!(result.is_err(), "缺失表时应返回 Err");
    let msg = result.unwrap_err();
    assert!(
        msg.starts_with("query session failed:"),
        "错误消息应带前缀，实际: {msg}"
    );

    // act + assert：空 token 走短路分支，仍返回 Ok(None)
    let empty = verify_session(&conn, "").expect("empty token short-circuit");
    assert!(empty.is_none());
}

#[test]
fn revoke_all_user_sessions_is_scoped_and_idempotent() {
    // arrange
    let conn = setup_db();
    insert_user(&conn, 10, "dave", false, "editor");
    insert_user(&conn, 11, "erin", false, "editor");
    let d1 = create_session(&conn, 10, 3600).expect("d1");
    let d2 = create_session(&conn, 10, 3600).expect("d2");
    let e1 = create_session(&conn, 11, 3600).expect("e1");

    // act
    revoke_all_user_sessions(&conn, 10).expect("revoke all dave");
    // 幂等：再调一次不报错
    revoke_all_user_sessions(&conn, 10).expect("revoke all dave again");

    // assert：dave 的两个都失效，erin 的仍在
    assert!(verify_session(&conn, &d1).expect("v").is_none());
    assert!(verify_session(&conn, &d2).expect("v").is_none());
    let erin_user = verify_session(&conn, &e1).expect("v").expect("erin 在线");
    assert_eq!(erin_user.id, 11);
    assert_eq!(erin_user.role, "editor");
}

#[test]
fn token_hashing_and_cookie_values_are_deterministic() {
    // arrange
    let token = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    // act
    let h1 = hash_token(token);
    let h2 = hash_token(token);
    let other = hash_token("different-token");

    // assert：SHA256 hex 长度固定 64，且确定性
    assert_eq!(h1.len(), 64);
    assert_eq!(h1, h2, "同 token 哈希应一致");
    assert_ne!(h1, other, "不同 token 哈希应不同");
    assert!(h1.chars().all(|c| c.is_ascii_hexdigit()));

    // act + assert：Cookie 值格式
    let set_cookie = set_session_cookie_value(token, 3600);
    assert!(set_cookie.starts_with(&format!("{SESSION_COOKIE}={token};")));
    assert!(set_cookie.contains("HttpOnly"));
    assert!(set_cookie.contains("SameSite=Lax"));
    assert!(set_cookie.contains("Max-Age=3600"));

    let clear_cookie = clear_session_cookie_value();
    assert!(clear_cookie.starts_with(&format!("{SESSION_COOKIE}=;")));
    assert!(clear_cookie.contains("Max-Age=0"));
    assert!(clear_cookie.contains("Path=/"));
}
