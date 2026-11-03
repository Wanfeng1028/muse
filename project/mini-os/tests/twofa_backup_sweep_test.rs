use axum::body::to_bytes;
use axum::body::Body;
use axum::http::Request;
use axum::Router;
use mini_os::config::parse_backup_code_retention_days_raw;
use mini_os::twofa::sweep_used_backup_codes;
use mini_os::{build_app, init_state, AppState};
use serde_json::{json, Value};
use std::sync::{Arc, Once};
use tower::ServiceExt;

static MASTER_KEY_INIT: Once = Once::new();

fn ensure_master_key() {
    MASTER_KEY_INIT.call_once(|| {
        std::env::set_var(
            "MINIOS_TOTP_MASTER_KEY",
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        );
    });
}

fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}

async fn raw_request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<&str>,
) -> (u16, Value) {
    let mut b = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        b = b.header("cookie", c);
    }
    let req = if let Some(v) = body {
        b.header("content-type", "application/json")
            .body(Body::from(v.to_string()))
            .unwrap()
    } else {
        b.body(Body::empty()).unwrap()
    };
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status().as_u16();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let val: Value = if bytes.is_empty() {
        json!(null)
    } else {
        serde_json::from_slice(&bytes).unwrap_or(json!(null))
    };
    (status, val)
}

fn fresh_app() -> (Router, Arc<AppState>) {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    (app, state)
}

fn insert_used_ago(conn: &rusqlite::Connection, uid: i64, hash: &str, days: i64) {
    conn.execute(
        "INSERT INTO tfa_backup_codes (user_id, code_hash, used_at) VALUES (?1, ?2, datetime('now', ?3))",
        rusqlite::params![uid, hash, format!("-{} days", days)],
    ).unwrap();
}

fn insert_unused(conn: &rusqlite::Connection, uid: i64, hash: &str) {
    conn.execute(
        "INSERT INTO tfa_backup_codes (user_id, code_hash, used_at) VALUES (?1, ?2, NULL)",
        rusqlite::params![uid, hash],
    )
    .unwrap();
}

fn count_codes(conn: &rusqlite::Connection) -> i64 {
    conn.query_row("SELECT COUNT(*) FROM tfa_backup_codes", [], |r| r.get(0))
        .unwrap()
}

fn exists_hash(conn: &rusqlite::Connection, hash: &str) -> bool {
    let n: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM tfa_backup_codes WHERE code_hash=?1",
            rusqlite::params![hash],
            |r| r.get(0),
        )
        .unwrap();
    n > 0
}

fn used_at_present(conn: &rusqlite::Connection, hash: &str) -> bool {
    let v: Option<String> = conn
        .query_row(
            "SELECT used_at FROM tfa_backup_codes WHERE code_hash=?1",
            rusqlite::params![hash],
            |r| r.get(0),
        )
        .unwrap();
    v.is_some()
}

#[tokio::test]
async fn sweep_deletes_only_old_used_codes() {
    let (app, state) = fresh_app();
    let (st, _) = raw_request(
        app,
        "POST",
        "/api/auth/register",
        Some(json!({"username":"testuser","password":"s3cureP4ss"})),
        None,
    )
    .await;
    assert_eq!(st, 201, "注册应返回201");
    let conn = state.db.lock().unwrap();
    let uid: i64 = conn
        .query_row("SELECT id FROM users WHERE username='testuser'", [], |r| {
            r.get(0)
        })
        .unwrap();
    insert_used_ago(&conn, uid, "h_old", 100);
    insert_used_ago(&conn, uid, "h_recent", 10);
    insert_unused(&conn, uid, "h_unused");
    let del = sweep_used_backup_codes(&conn, 90).expect("sweep不应出错");
    assert_eq!(del, 1, "应只删除1行（-100天已用码）");
    assert_eq!(count_codes(&conn), 2, "删除后应剩2行");
    assert!(!exists_hash(&conn, "h_old"), "-100天已用码应消失");
    assert!(exists_hash(&conn, "h_recent"), "-10天已用码应保留");
    assert!(used_at_present(&conn, "h_recent"), "-10天行used_at应非空");
    assert!(exists_hash(&conn, "h_unused"), "未用码应保留");
}

#[tokio::test]
async fn sweep_boundary_91_deleted_89_kept() {
    let (app, state) = fresh_app();
    let (st, _) = raw_request(
        app,
        "POST",
        "/api/auth/register",
        Some(json!({"username":"testuser","password":"s3cureP4ss"})),
        None,
    )
    .await;
    assert_eq!(st, 201, "注册应返回201");
    let conn = state.db.lock().unwrap();
    let uid: i64 = conn
        .query_row("SELECT id FROM users WHERE username='testuser'", [], |r| {
            r.get(0)
        })
        .unwrap();
    insert_used_ago(&conn, uid, "h_91", 91);
    insert_used_ago(&conn, uid, "h_89", 89);
    let del = sweep_used_backup_codes(&conn, 90).expect("sweep不应出错");
    assert_eq!(del, 1, "应只删除1行（-91天已用码）");
    assert!(!exists_hash(&conn, "h_91"), "-91天已用码应消失");
    assert!(exists_hash(&conn, "h_89"), "-89天已用码应保留");
}

#[tokio::test]
async fn sweep_empty_table_returns_zero() {
    let (_app, state) = fresh_app();
    let conn = state.db.lock().unwrap();
    let del = sweep_used_backup_codes(&conn, 90).expect("空表sweep不应出错");
    assert_eq!(del, 0, "空表应返回0");
}

#[test]
fn retention_parse_cases() {
    assert_eq!(
        parse_backup_code_retention_days_raw(None).unwrap(),
        90,
        "None应默认90"
    );
    assert_eq!(
        parse_backup_code_retention_days_raw(Some("30")).unwrap(),
        30,
        "\"30\"应得30"
    );
    assert_eq!(
        parse_backup_code_retention_days_raw(Some("  90  ")).unwrap(),
        90,
        "带空格\"  90  \"应得90"
    );
    assert_eq!(
        parse_backup_code_retention_days_raw(Some("1")).unwrap(),
        1,
        "\"1\"应得1"
    );
    assert_eq!(
        parse_backup_code_retention_days_raw(Some("3650")).unwrap(),
        3650,
        "\"3650\"应得3650"
    );
    for bad in &["", "0", "-1", "3651", "abc", "1.5"] {
        let res = parse_backup_code_retention_days_raw(Some(bad));
        assert!(res.is_err(), "非法值\"{}\"应返回Err", bad);
        let err = res.unwrap_err();
        assert!(
            err.contains("MINIOS_BACKUP_CODE_RETENTION_DAYS"),
            "错误应含MINIOS_BACKUP_CODE_RETENTION_DAYS，实际:{}",
            err,
        );
    }
}

#[test]
fn init_state_default_retention_is_90() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    assert_eq!(
        state.backup_code_retention_days, 90,
        "默认backup_code_retention_days应为90"
    );
}
fn count(state: &Arc<AppState>, sql: &str) -> i64 {
    let conn = state.db.lock().unwrap();
    conn.query_row(sql, [], |r| r.get(0)).unwrap()
}

pub async fn raw_request_cookie(
    app: axum::Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<&str>,
) -> (u16, Value, Option<String>) {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let req = if let Some(b) = body {
        builder
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap()
    } else {
        builder.body(Body::empty()).unwrap()
    };
    let res = app.oneshot(req).await.unwrap();
    let set_cookie = res
        .headers()
        .get("set-cookie")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.split(';').next())
        .map(|s| s.to_string());
    let status = res.status().as_u16();
    let body_bytes = to_bytes(res.into_body(), usize::MAX).await.unwrap();
    let val = if body_bytes.is_empty() {
        json!(null)
    } else {
        serde_json::from_slice(&body_bytes).unwrap()
    };
    (status, val, set_cookie)
}

#[tokio::test]
async fn backup_login_sweeps_old_used_codes_e2e() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());

    let (status, _, _) = raw_request_cookie(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "testuser", "password": "s3cureP4ss"})),
        None,
    )
    .await;
    assert_eq!(status, 201, "注册应返回 201");

    let (status, _, cookie) = raw_request_cookie(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({"username": "testuser", "password": "s3cureP4ss"})),
        None,
    )
    .await;
    assert_eq!(status, 200, "登录应返回 200");
    let cookie = cookie.expect("登录应返回 Cookie");

    let (status, val, _) = raw_request_cookie(
        app.clone(),
        "POST",
        "/api/2fa/setup",
        Some(json!({"password": "s3cureP4ss"})),
        Some(&cookie),
    )
    .await;
    assert_eq!(status, 200, "2FA setup 应返回 200");
    let secret = val.get("secret").unwrap().as_str().unwrap().to_string();

    let bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&bytes, now_secs());
    let (status, val, _) = raw_request_cookie(
        app.clone(),
        "POST",
        "/api/2fa/enable",
        Some(json!({"code": code})),
        Some(&cookie),
    )
    .await;
    assert_eq!(status, 200, "2FA enable 应返回 200");
    let backup_codes = val.get("backupCodes").unwrap().as_array().unwrap().clone();
    assert_eq!(backup_codes.len(), 10, "备用码数量应为 10");
    let first_code = backup_codes[0].as_str().unwrap();

    let user_id: i64 = {
        let db = state.db.lock().unwrap();
        db.query_row(
            "SELECT id FROM users WHERE username = 'testuser'",
            [],
            |r| r.get(0),
        )
        .unwrap()
    };
    {
        let db = state.db.lock().unwrap();
        db.execute("INSERT INTO tfa_backup_codes (user_id, code_hash, used_at) VALUES (?1, 'hash-planted-old', datetime('now', '-100 days'))", rusqlite::params![user_id]).unwrap();
    }

    let (status, val, _) = raw_request_cookie(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({"username": "testuser", "password": "s3cureP4ss"})),
        None,
    )
    .await;
    assert_eq!(status, 202, "2FA 登录应返回 202");
    let challenge = val.get("challenge").unwrap().as_str().unwrap();

    let (status, _, _) = raw_request_cookie(
        app.clone(),
        "POST",
        "/api/auth/2fa",
        Some(json!({"challenge": challenge, "code": first_code})),
        None,
    )
    .await;
    assert_eq!(status, 200, "2FA 认证应返回 200");

    let planted_count = count(
        &state,
        "SELECT COUNT(*) FROM tfa_backup_codes WHERE code_hash = 'hash-planted-old'",
    );
    assert_eq!(
        planted_count, 0,
        "code_hash='hash-planted-old' 的行数应为 0"
    );

    let total_count = count(&state, "SELECT COUNT(*) FROM tfa_backup_codes");
    assert_eq!(total_count, 10, "备用码总行数应为 10");

    let used_count = count(
        &state,
        "SELECT COUNT(*) FROM tfa_backup_codes WHERE used_at IS NOT NULL",
    );
    assert_eq!(used_count, 1, "used_at 非空的行数应为 1");
}
