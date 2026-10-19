use std::fs;
use std::path::{Path, PathBuf};

use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use mini_os::{build_app, db, init_state, init_state_with, migrate};
use serde_json::{json, Value};
use tower::ServiceExt;

fn workdir(name: &str) -> PathBuf {
    let dir = Path::new("target/test-work").join(name);
    let _ = fs::create_dir_all(&dir);
    dir
}

fn cleanup(path: &Path) {
    let _ = fs::remove_file(path);
    let _ = fs::remove_dir_all(path);
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

fn legacy_create_sql() -> &'static str {
    "CREATE TABLE vfs_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER,
        name TEXT NOT NULL,
        is_dir INTEGER NOT NULL DEFAULT 0,
        size INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL DEFAULT 0
    )"
}

fn legacy_settings_sql() -> &'static str {
    "CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )"
}

#[test]
fn open_db_rejects_garbage_file() {
    let dir = workdir("open_db_rejects_garbage_file");
    let path = dir.join("garbage.db");
    cleanup(&path);

    let garbage = [0x7fu8; 64];
    fs::write(&path, garbage).unwrap();

    let result = db::open_db(path.to_str().unwrap());
    assert!(result.is_err(), "open_db should reject garbage file");

    cleanup(&path);
}

#[test]
fn open_db_rejects_uncreatable_parent() {
    let dir = workdir("open_db_rejects_uncreatable_parent");
    let notadir = dir.join("notadir");
    let sub = notadir.join("sub.db");
    cleanup(&notadir);

    fs::write(&notadir, b"i am a file").unwrap();

    let result = db::open_db(sub.to_str().unwrap());
    assert!(result.is_err(), "open_db should fail when parent is a file");

    cleanup(&notadir);
}

#[tokio::test]
async fn write_to_broken_db_returns_500_not_panic() {
    // 故障注入：删掉业务表 vfs_nodes，后续一切读写必然走 rusqlite 错误分支。
    // 覆盖：SQLITE I/O 错误/只读/磁盘满等所有写失败在 handler 层的同一处理路径——必须 500，不能 panic。
    // 注：不用 chmod 只读文件做注入——容器内常以 root 运行，root 无视文件权限位，注入不确定。
    let dir = workdir("write_to_broken_db_returns_500_not_panic");
    let db_path = dir.join("tmp.db");
    cleanup(&db_path);

    let state = init_state_with(db_path.to_str().unwrap(), "static", 1024, 60, 1.0, 5);
    {
        let conn = state.db.lock().unwrap();
        conn.execute("DROP TABLE vfs_nodes", []).unwrap();
    }
    let app = build_app(state);

    // v1.3：先注册拿 session cookie（users 表未被 DROP，注册可用）
    let reg = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username":"drill","password":"password123"}).to_string(),
        ))
        .unwrap();
    let reg_resp = app.clone().oneshot(reg).await.unwrap();
    assert_eq!(reg_resp.status(), StatusCode::CREATED);
    let cookie = reg_resp
        .headers()
        .get("set-cookie")
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();

    // 写 → 500，body 带 error 字段，不 panic
    let req = Request::builder()
        .method("POST")
        .uri("/api/fs")
        .header("content-type", "application/json")
        .header("cookie", &cookie)
        .body(axum::body::Body::from(
            serde_json::to_vec(
                &json!({"parentId": null, "name": "brokentest", "kind": "folder", "content": ""}),
            )
            .unwrap(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    let value = body_json(resp).await;
    assert!(
        value.get("error").is_some(),
        "500 body must contain error field"
    );

    // 读 → 同样 500 不 panic
    let req2 = Request::builder()
        .method("GET")
        .uri("/api/fs")
        .header("cookie", &cookie)
        .body(axum::body::Body::empty())
        .unwrap();
    let resp2 = app.oneshot(req2).await.unwrap();
    assert_eq!(resp2.status(), StatusCode::INTERNAL_SERVER_ERROR);

    cleanup(&db_path);
}

#[tokio::test]
async fn readyz_reflects_db_health() {
    let dir = workdir("readyz_reflects_db_health");
    let db_path = dir.join("ready.db");
    cleanup(&db_path);

    let state = init_state_with(db_path.to_str().unwrap(), "static", 1024, 60, 1.0, 5);
    let app = build_app(state.clone());

    let req = Request::builder()
        .method("GET")
        .uri("/api/readyz")
        .body(axum::body::Body::empty())
        .unwrap();

    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let value = body_json(resp).await;
    assert_eq!(value["status"], "ready");

    {
        let conn = state.db.lock().unwrap();
        conn.execute("DROP TABLE schema_migrations", []).unwrap();
    }

    let req2 = Request::builder()
        .method("GET")
        .uri("/api/readyz")
        .body(axum::body::Body::empty())
        .unwrap();

    let resp2 = app.oneshot(req2).await.unwrap();
    assert_eq!(resp2.status(), StatusCode::SERVICE_UNAVAILABLE);
    let value2 = body_json(resp2).await;
    assert_eq!(value2["status"], "not_ready");

    cleanup(&db_path);
}

#[tokio::test]
async fn request_id_passthrough() {
    let dir = workdir("request_id_passthrough");
    let db_path = dir.join("rid.db");
    cleanup(&db_path);

    let state = init_state_with(db_path.to_str().unwrap(), "static", 1024, 60, 1.0, 5);
    let app = build_app(state);

    let req = Request::builder()
        .method("GET")
        .uri("/api/health")
        .header("x-request-id", "test-abc-123")
        .body(axum::body::Body::empty())
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    let header = resp
        .headers()
        .get("x-request-id")
        .expect("x-request-id header missing");
    assert_eq!(header.to_str().unwrap(), "test-abc-123");

    cleanup(&db_path);
}

#[tokio::test]
async fn request_id_generated_when_absent() {
    let dir = workdir("request_id_generated_when_absent");
    let db_path = dir.join("rid2.db");
    cleanup(&db_path);

    let state = init_state_with(db_path.to_str().unwrap(), "static", 1024, 60, 1.0, 5);
    let app = build_app(state);

    let req1 = Request::builder()
        .method("GET")
        .uri("/api/health")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp1 = app.clone().oneshot(req1).await.unwrap();
    let id1 = resp1
        .headers()
        .get("x-request-id")
        .expect("first x-request-id missing")
        .to_str()
        .unwrap()
        .to_string();
    assert!(!id1.is_empty(), "generated request id must be non-empty");

    let req2 = Request::builder()
        .method("GET")
        .uri("/api/health")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp2 = app.oneshot(req2).await.unwrap();
    let id2 = resp2
        .headers()
        .get("x-request-id")
        .expect("second x-request-id missing")
        .to_str()
        .unwrap()
        .to_string();
    assert!(!id2.is_empty(), "generated request id must be non-empty");
    assert_ne!(id1, id2, "generated request ids should differ");

    cleanup(&db_path);
}

#[test]
fn migrations_idempotent_on_same_file() {
    let dir = workdir("migrations_idempotent_on_same_file");
    let db_path = dir.join("idem.db");
    cleanup(&db_path);

    {
        let conn = db::open_db(db_path.to_str().unwrap()).unwrap();
        let versions = migrate::applied_versions(&conn).unwrap();
        assert_eq!(
            versions,
            vec![
                "001".to_string(),
                "002".to_string(),
                "003".to_string(),
                "004".to_string(),
                "005".to_string(),
                "006".to_string()
            ]
        );
    }

    {
        let conn = db::open_db(db_path.to_str().unwrap()).unwrap();
        let versions = migrate::applied_versions(&conn).unwrap();
        assert_eq!(
            versions,
            vec![
                "001".to_string(),
                "002".to_string(),
                "003".to_string(),
                "004".to_string(),
                "005".to_string(),
                "006".to_string()
            ]
        );
        db::seed(&conn).unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM vfs_nodes WHERE name IN ('Desktop', 'Documents')",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 2);
    }

    cleanup(&db_path);
}

#[test]
fn migrations_upgrade_legacy_db() {
    let dir = workdir("migrations_upgrade_legacy_db");
    let db_path = dir.join("legacy.db");
    cleanup(&db_path);

    {
        let conn = rusqlite::Connection::open(db_path.to_str().unwrap()).unwrap();
        conn.execute(legacy_create_sql(), []).unwrap();
        conn.execute(legacy_settings_sql(), []).unwrap();
        conn.execute(
            "INSERT INTO vfs_nodes (parent_id, name, is_dir, size, created_at) VALUES (NULL, 'LegacyFolder', 1, 0, 12345)",
            [],
        )
        .unwrap();
    }

    let conn = db::open_db(db_path.to_str().unwrap()).unwrap();

    let versions = migrate::applied_versions(&conn).unwrap();
    assert_eq!(
        versions,
        vec![
            "001".to_string(),
            "002".to_string(),
            "003".to_string(),
            "004".to_string(),
            "005".to_string(),
            "006".to_string()
        ]
    );

    let mut has_content_blob = false;
    let mut has_mime_type = false;
    {
        let mut stmt = conn.prepare("PRAGMA table_info(vfs_nodes)").unwrap();
        let mut rows = stmt.query([]).unwrap();
        while let Some(row) = rows.next().unwrap() {
            let name: String = row.get(1).unwrap();
            if name == "content_blob" {
                has_content_blob = true;
            }
            if name == "mime_type" {
                has_mime_type = true;
            }
        }
    }
    assert!(has_content_blob, "content_blob column must exist");
    assert!(has_mime_type, "mime_type column must exist");

    let legacy_name: String = conn
        .query_row(
            "SELECT name FROM vfs_nodes WHERE name = 'LegacyFolder'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(legacy_name, "LegacyFolder");

    drop(conn);
    cleanup(&db_path);
}

#[tokio::test]
async fn forged_token_gets_401_not_panic() {
    // 伪造 token → 401，不 panic
    let state = init_state_with(":memory:", "static", 1024, 60, 1.0, 5);
    let app = build_app(state);
    let req = Request::builder()
        .method("GET")
        .uri("/api/fs")
        .header(
            "cookie",
            "mini_os_session=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        )
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn expired_session_gets_401() {
    // 直接插一条过期 session → 401
    let state = init_state(":memory:", "static");
    {
        let conn = state.db.lock().unwrap();
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES ('ghost','x',0)",
            [],
        )
        .unwrap();
        let uid = conn.last_insert_rowid();
        let past = mini_os::auth::now_epoch_secs() - 100;
        let th = mini_os::auth::hash_token("expiredtoken123");
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?1,?2,?3)",
            rusqlite::params![th, uid, past],
        )
        .unwrap();
    }
    let app = build_app(state);
    let req = Request::builder()
        .method("GET")
        .uri("/api/fs")
        .header("cookie", "mini_os_session=expiredtoken123")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn broken_users_table_returns_500_not_panic() {
    // 删 users 表后注册 → 500 不 panic（鉴权中间件/处理器错误路径）
    let state = init_state(":memory:", "static");
    {
        let conn = state.db.lock().unwrap();
        conn.execute("DROP TABLE users", []).unwrap();
    }
    let app = build_app(state);
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username":"drilluser","password":"password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
}
