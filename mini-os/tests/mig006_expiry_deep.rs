// A 组（迁移本身）依据的实现函数：run_migrations / applied_versions / apply_006。
// 006 只动 shares 表（加 expires_at 列）和 schema_migrations（插 '006' 行），所以旧库手写这两张表即可。
// 集成测试里 apply_001..apply_006、is_applied 都是私有的，只能用 pub 的 run_migrations / applied_versions。
// B 组（expires_at 语义）依据的实现函数：now_unix / is_expired / create_share 的 expires_at 校验段，
// 以及 get_share / list_share / download_share 三处过期检查。

use axum::body::to_bytes;
use axum::body::Body;
use axum::http::{header, Request, StatusCode};
use rusqlite::Connection;
use serde_json::{json, Value};
use tower::ServiceExt;

mod common {
    use super::*;
    use axum::Router;

    pub async fn register(app: &Router, username: &str, password: &str) -> String {
        let body = json!({ "username": username, "password": password }).to_string();
        let req = Request::builder()
            .method("POST")
            .uri("/api/auth/register")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(body))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::CREATED,
            "register {username} failed"
        );
        let set_cookie = resp
            .headers()
            .get(header::SET_COOKIE)
            .expect("missing set-cookie")
            .to_str()
            .unwrap()
            .to_string();
        let cookie = set_cookie.split(';').next().unwrap().to_string();
        cookie
    }

    pub async fn read_json(resp: axum::response::Response) -> Value {
        let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }
}

use common::{read_json, register};

async fn get(app: &axum::Router, uri: &str, cookie: Option<&str>) -> axum::response::Response {
    let mut builder = Request::builder().method("GET").uri(uri);
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    app.clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

async fn post_json(
    app: &axum::Router,
    uri: &str,
    cookie: Option<&str>,
    value: &Value,
) -> axum::response::Response {
    let mut builder = Request::builder()
        .method("POST")
        .uri(uri)
        .header(header::CONTENT_TYPE, "application/json");
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    app.clone()
        .oneshot(builder.body(Body::from(value.to_string())).unwrap())
        .await
        .unwrap()
}

async fn create_text_file(
    app: &axum::Router,
    cookie: &str,
    parent: Option<i64>,
    name: &str,
    content: &str,
) -> i64 {
    let mut body = json!({ "name": name, "kind": "file", "content": content });
    if let Some(p) = parent {
        body["parentId"] = json!(p);
    }
    let resp = post_json(app, "/api/fs", Some(cookie), &body).await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "create_text_file {name} failed"
    );
    let v = read_json(resp).await;
    v["id"].as_i64().unwrap()
}

async fn create_folder(app: &axum::Router, cookie: &str, name: &str) -> i64 {
    let body = json!({ "name": name, "kind": "folder" });
    let resp = post_json(app, "/api/fs", Some(cookie), &body).await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "create_folder {name} failed"
    );
    let v = read_json(resp).await;
    v["id"].as_i64().unwrap()
}

async fn create_share(
    app: &axum::Router,
    cookie: &str,
    file_id: i64,
    expires_at: Option<i64>,
) -> axum::response::Response {
    let mut body = json!({ "nodeId": file_id });
    if let Some(e) = expires_at {
        body["expiresAt"] = json!(e);
    }
    post_json(app, "/api/shares", Some(cookie), &body).await
}

fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}

fn fresh_state() -> std::sync::Arc<mini_os::AppState> {
    let tmp = std::env::temp_dir().join(format!(
        "minios_mig006_expiry_{}_{}.db",
        std::process::id(),
        now_secs() as u128 + rand_suffix()
    ));
    let path = tmp.to_string_lossy().to_string();
    mini_os::init_state_with(&path, "static", 10 * 1024 * 1024, 3600, 100.0, 100)
}

fn rand_suffix() -> u128 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .subsec_nanos() as u128
}

fn app_for(state: &std::sync::Arc<mini_os::AppState>) -> axum::Router {
    mini_os::build_app(state.clone())
}

async fn body_contains(resp: axum::response::Response, needle: &str) -> (StatusCode, String) {
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let text = String::from_utf8_lossy(&bytes).to_string();
    assert!(
        text.contains(needle),
        "响应体应包含 {needle}，实际是 {text}"
    );
    (status, text)
}

/// 搭一个 005 时代的旧库：只有 schema_migrations 和 shares 两张表。
/// 006 只动这两张表，所以集成测试手写 SQL 就够了。
fn open_legacy_005_db() -> Connection {
    let conn = Connection::open_in_memory().expect("open in-memory");
    conn.execute(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))",
        [],
    )
    .expect("create schema_migrations");
    conn.execute(
        "INSERT INTO schema_migrations(version) VALUES ('001'),('002'),('003'),('004'),('005')",
        [],
    )
    .expect("seed applied versions");
    conn.execute(
        "CREATE TABLE shares (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE, node_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), share_type TEXT NOT NULL DEFAULT 'file' CHECK(share_type IN ('file','dir')))",
        [],
    )
    .expect("create legacy shares");
    // 008（TOTP）要 ALTER users 表；真实 005 时代库里 003 已建过 users，
    // 手写 fixture 必须补上，否则 008 会报 no such table: users。
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY)",
        [],
    )
    .expect("create legacy users");
    conn
}

// ==================== A 组：迁移本身 ====================

#[test]
fn a1_apply_006_adds_expires_at_column() {
    let conn = open_legacy_005_db();

    // 旧库里先放一条分享行，此时没有 expires_at 列。
    conn.execute(
        "INSERT INTO shares (token, node_id, owner_id) VALUES ('legacy-token', 7, 3)",
        [],
    )
    .expect("insert legacy share");

    mini_os::migrate::run_migrations(&conn).expect("run migrations");

    // pragma_table_info('shares') 里有且仅有一个 expires_at 列。
    let cols: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM pragma_table_info('shares') WHERE name = 'expires_at'",
            [],
            |row| row.get(0),
        )
        .expect("pragma count");
    assert_eq!(cols, 1, "shares 表应恰好有一个 expires_at 列");

    // 旧行的 expires_at 是 NULL（ADD COLUMN 没有 DEFAULT）。
    let legacy_expires: Option<i64> = conn
        .query_row(
            "SELECT expires_at FROM shares WHERE token = 'legacy-token'",
            [],
            |row| row.get(0),
        )
        .expect("legacy expires_at");
    assert_eq!(legacy_expires, None, "旧分享行 expires_at 应为 NULL");

    // applied_versions() 包含 "006"、"007" 与 "008"。
    let versions = mini_os::migrate::applied_versions(&conn).expect("applied_versions");
    assert!(
        versions.contains(&"006".to_string()),
        "applied_versions 应包含 006，实际是 {versions:?}"
    );
    assert!(
        versions.contains(&"007".to_string()),
        "007（notes/events 表）应在版本列表中，实际是 {versions:?}"
    );
    assert!(
        versions.contains(&"008".to_string()),
        "008（TOTP 两步验证）应在版本列表中，实际是 {versions:?}"
    );
}

#[test]
fn a2_run_migrations_is_idempotent() {
    let conn = open_legacy_005_db();

    conn.execute(
        "INSERT INTO shares (token, node_id, owner_id) VALUES ('legacy-token', 7, 3)",
        [],
    )
    .expect("insert legacy share");

    mini_os::migrate::run_migrations(&conn).expect("first run");
    mini_os::migrate::run_migrations(&conn).expect("second run");

    // schema_migrations 总行数还是 8（含 008）。
    let count: i64 = conn
        .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
            row.get(0)
        })
        .expect("count schema_migrations");
    assert_eq!(count, 8, "连跑两遍后 schema_migrations 应还是 8 行");

    // expires_at 列还是只有一个。
    let cols: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM pragma_table_info('shares') WHERE name = 'expires_at'",
            [],
            |row| row.get(0),
        )
        .expect("pragma count");
    assert_eq!(cols, 1, "连跑两遍后 expires_at 列应还是只有一个");
}

#[test]
fn a3_old_share_row_survives_migration() {
    let conn = open_legacy_005_db();

    conn.execute(
        "INSERT INTO shares (token, node_id, owner_id, share_type) VALUES ('keep-token', 42, 9, 'dir')",
        [],
    )
    .expect("insert legacy share");

    mini_os::migrate::run_migrations(&conn).expect("run migrations");

    let (token, node_id, owner_id, share_type): (String, i64, i64, String) = conn
        .query_row(
            "SELECT token, node_id, owner_id, share_type FROM shares WHERE token = 'keep-token'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .expect("legacy row");
    assert_eq!(token, "keep-token");
    assert_eq!(node_id, 42);
    assert_eq!(owner_id, 9);
    assert_eq!(share_type, "dir");
}

#[test]
fn a4_new_row_defaults_expires_at_to_null() {
    let conn = open_legacy_005_db();

    conn.execute(
        "INSERT INTO shares (token, node_id, owner_id) VALUES ('legacy-token', 7, 3)",
        [],
    )
    .expect("insert legacy share");

    mini_os::migrate::run_migrations(&conn).expect("run migrations");

    // 006 之后新插入一行，不带 expires_at 列。
    conn.execute(
        "INSERT INTO shares (token, node_id, owner_id) VALUES ('new-token', 8, 4)",
        [],
    )
    .expect("insert new share");

    let new_expires: Option<i64> = conn
        .query_row(
            "SELECT expires_at FROM shares WHERE token = 'new-token'",
            [],
            |row| row.get(0),
        )
        .expect("new expires_at");
    assert_eq!(new_expires, None, "新插入行 expires_at 应为 NULL");
}

// ==================== B 组：expires_at 语义 ====================

#[tokio::test]
async fn b1_null_expires_at_never_expires() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;
    let file_id = create_text_file(&app, &cookie, None, "keep.txt", "hello").await;

    // 不传 expiresAt。
    let resp = create_share(&app, &cookie, file_id, None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();
    assert_eq!(v["expiresAt"], Value::Null, "没传 expiresAt 应回 null");

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK, "NULL 过期时间应永不过期");
}

#[tokio::test]
async fn b2_future_expires_at_is_accessible() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;
    let file_id = create_text_file(&app, &cookie, None, "future.txt", "hello").await;

    let future = now_secs() + 3600;
    let resp = create_share(&app, &cookie, file_id, Some(future)).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();
    assert_eq!(
        v["expiresAt"].as_i64(),
        Some(future),
        "响应 JSON 的 expiresAt 应等于传入值"
    );

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK, "未来时间应能访问");
}

#[tokio::test]
async fn b3_past_expires_at_rejected_on_create() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;
    let file_id = create_text_file(&app, &cookie, None, "past.txt", "hello").await;

    let past = now_secs() - 3600;
    let resp = create_share(&app, &cookie, file_id, Some(past)).await;
    let (status, _) = body_contains(resp, "过期时间必须是未来时间").await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn b4_expires_at_now_rejected_on_create() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;
    let file_id = create_text_file(&app, &cookie, None, "now.txt", "hello").await;

    // create_share 里 ts <= now_unix() 就拒绝，所以创建要求严格未来时间。
    let now = now_secs();
    let resp = create_share(&app, &cookie, file_id, Some(now)).await;
    let (status, _) = body_contains(resp, "过期时间必须是未来时间").await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn b5_share_expires_at_current_second_returns_gone() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;
    let file_id = create_text_file(&app, &cookie, None, "expire.txt", "hello").await;

    let future = now_secs() + 3600;
    let resp = create_share(&app, &cookie, file_id, Some(future)).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();

    {
        let conn = state.db.lock().unwrap();
        let past = now_secs() - 10;
        let n = conn
            .execute(
                "UPDATE shares SET expires_at = ?1 WHERE token = ?2",
                rusqlite::params![past, token],
            )
            .expect("update expires_at failed");
        assert_eq!(n, 1, "应恰好更新一行分享");
    }

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    let (status, _) = body_contains(resp, "分享已过期").await;
    assert_eq!(status, StatusCode::GONE);
}

#[tokio::test]
async fn b6_expired_dir_share_gone_in_all_three_endpoints() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;

    let dir_id = create_folder(&app, &cookie, "docs").await;
    let _file_id = create_text_file(&app, &cookie, Some(dir_id), "note.txt", "hi").await;

    let future = now_secs() + 3600;
    let body = json!({ "type": "dir", "path": "/docs", "expiresAt": future });
    let resp = post_json(&app, "/api/shares", Some(&cookie), &body).await;
    assert_eq!(resp.status(), StatusCode::CREATED, "创建目录分享失败");
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();

    {
        let conn = state.db.lock().unwrap();
        let past = now_secs() - 10;
        let n = conn
            .execute(
                "UPDATE shares SET expires_at = ?1 WHERE token = ?2",
                rusqlite::params![past, token],
            )
            .expect("update expires_at failed");
        assert_eq!(n, 1, "应恰好更新一行分享");
    }

    // 三处 handler 都调 is_expired(expires_at)，都应返回 410。
    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    let (status, _) = body_contains(resp, "分享已过期").await;
    assert_eq!(status, StatusCode::GONE, "get_share 应返回 410");

    let resp = get(&app, &format!("/api/share/list?token={token}"), None).await;
    let (status, _) = body_contains(resp, "分享已过期").await;
    assert_eq!(status, StatusCode::GONE, "list_share 应返回 410");

    let resp = get(
        &app,
        &format!("/api/s/{token}/download?path=note.txt"),
        None,
    )
    .await;
    let (status, _) = body_contains(resp, "分享已过期").await;
    assert_eq!(status, StatusCode::GONE, "download_share 应返回 410");
}

#[tokio::test]
async fn b7_admin_list_exposes_expires_at() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "alice", "pw-alice9").await;

    let file_a = create_text_file(&app, &cookie, None, "a.txt", "a").await;
    let future = now_secs() + 3600;
    let resp = create_share(&app, &cookie, file_a, Some(future)).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token_a = v["token"].as_str().expect("missing token").to_string();

    let file_b = create_text_file(&app, &cookie, None, "b.txt", "b").await;
    let resp = create_share(&app, &cookie, file_b, None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token_b = v["token"].as_str().expect("missing token").to_string();

    let resp = get(&app, "/api/shares", Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let list = read_json(resp).await;
    let arr = list.as_array().expect("管理列表应是数组");

    let item_a = arr
        .iter()
        .find(|it| it["token"].as_str() == Some(token_a.as_str()))
        .expect("管理列表里应找到 token_a");
    assert_eq!(
        item_a["expiresAt"].as_i64(),
        Some(future),
        "带过期时间的分享在管理列表里 expiresAt 应等于传入值"
    );

    let item_b = arr
        .iter()
        .find(|it| it["token"].as_str() == Some(token_b.as_str()))
        .expect("管理列表里应找到 token_b");
    assert_eq!(
        item_b["expiresAt"],
        Value::Null,
        "不带过期时间的分享在管理列表里 expiresAt 应为 null"
    );
}
// 缺口清单：
// 1) create_share 的 expires_at 校验只覆盖 ts <= now_unix()，没看到对超大值（比如远超 i64 合理范围）的额外防护，
//    当前测试只验证严格未来时间的拒绝，未对上限做断言。
// 2) lookup_share 返回的 ShareRow 只到 expires_at，未见任何在 SQL 层过滤过期行的写法，
//    所以过期判定完全依赖各 handler 手动调 is_expired；若将来新增读取入口忘了调用，
//    测试 b6 只覆盖 get_share / list_share / download_share 三处，无法拦住新入口漏判。
