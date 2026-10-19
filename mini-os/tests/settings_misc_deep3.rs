use axum::body::{to_bytes, Body};
use axum::http::{header, Method, Request, StatusCode};
use axum::Router;
use serde_json::{json, Value};
use std::sync::Arc;
use tower::ServiceExt;

fn init_state(db: &str, static_dir: &str) -> Arc<mini_os::AppState> {
    mini_os::init_state(db, static_dir)
}

fn app(state: Arc<mini_os::AppState>) -> Router {
    mini_os::build_app(state)
}

async fn register(router: &Router, username: &str, _password: &str) -> String {
    let body = json!({"username": username, "password": "password123"}).to_string();
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    resp.headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string()
}

async fn read_json(resp: axum::response::Response) -> (StatusCode, Value) {
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: Value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap()
    };
    (status, v)
}

fn authed(method: Method, uri: &str, token: &str) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header(header::COOKIE, token.to_string())
        .body(Body::empty())
        .unwrap()
}

fn authed_json(method: Method, uri: &str, token: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header(header::COOKIE, token.to_string())
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

#[tokio::test]
async fn settings_empty_object_fresh() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let req = authed(Method::GET, "/api/settings", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.is_object());
    assert_eq!(body.as_object().unwrap().len(), 0);
}

#[tokio::test]
async fn settings_put_get_roundtrip() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let req = authed_json(
        Method::PUT,
        "/api/settings",
        &token,
        json!({"key": "theme", "value": "dark"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["key"], "theme");
    assert_eq!(body["value"], "dark");

    let req = authed(Method::GET, "/api/settings", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["theme"], "dark");
}

#[tokio::test]
async fn settings_empty_key_400() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let req = authed_json(
        Method::PUT,
        "/api/settings",
        &token,
        json!({"key": "   ", "value": "x"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let msg = body["error"].as_str().unwrap_or("");
    assert!(msg.contains("key 不能为空"), "got: {}", msg);
}

#[tokio::test]
async fn settings_upsert_overwrites() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    for v in ["first", "second"] {
        let req = authed_json(
            Method::PUT,
            "/api/settings",
            &token,
            json!({"key": "mode", "value": v}),
        );
        let resp = router.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    let req = authed(Method::GET, "/api/settings", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["mode"], "second");
}

#[tokio::test]
async fn settings_key_not_trimmed_documents() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let req = authed_json(
        Method::PUT,
        "/api/settings",
        &token,
        json!({"key": " k ", "value": "v"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["key"], " k ");

    let req = authed(Method::GET, "/api/settings", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    let map = body.as_object().unwrap();
    assert!(
        map.contains_key(" k "),
        "keys: {:?}",
        map.keys().collect::<Vec<_>>()
    );
    assert_eq!(map.get(" k ").unwrap(), "v");
    assert!(!map.contains_key("k"));
}

#[tokio::test]
async fn settings_isolation_between_users() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token_a = register(&router, "alice", "pw123456").await;
    let token_b = register(&router, "bob", "pw123456").await;

    let req = authed_json(
        Method::PUT,
        "/api/settings",
        &token_a,
        json!({"key": "k", "value": "v1"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let req = authed(Method::GET, "/api/settings", &token_b);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_object().unwrap().len(), 0);
}

fn multipart_body(boundary: &str, filename: &str, data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    out.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    out.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            filename
        )
        .as_bytes(),
    );
    out.extend_from_slice(b"\r\n");
    out.extend_from_slice(data);
    out.extend_from_slice(b"\r\n");
    out.extend_from_slice(format!("--{}--\r\n", boundary).as_bytes());
    out
}

#[tokio::test]
async fn stats_accuracy_mixed() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let boundary = "----miniosboundary1";
    let body = multipart_body(boundary, "ten.bin", &[0u8; 10]);
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/files/upload")
        .header(header::COOKIE, token.to_string())
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .body(Body::from(body))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert!(
        resp.status().is_success(),
        "upload status: {}",
        resp.status()
    );

    let req = authed_json(
        Method::POST,
        "/api/fs",
        &token,
        json!({"name": "a.txt", "kind": "file", "content": "abc"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert!(resp.status().is_success(), "create file: {}", resp.status());

    let req = authed_json(
        Method::POST,
        "/api/fs",
        &token,
        json!({"name": "dir", "kind": "folder"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert!(
        resp.status().is_success(),
        "create folder: {}",
        resp.status()
    );

    let req = authed(Method::GET, "/api/stats", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["files"], 2);
    assert_eq!(body["folders"], 1);
    assert_eq!(body["totalBytes"], 13);
}

#[tokio::test]
async fn stats_isolation() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token_a = register(&router, "alice", "pw123456").await;
    let token_b = register(&router, "bob", "pw123456").await;

    let req = authed_json(
        Method::POST,
        "/api/fs",
        &token_a,
        json!({"name": "a.txt", "kind": "file", "content": "hello"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert!(resp.status().is_success());

    let req = authed(Method::GET, "/api/stats", &token_b);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["files"], 0);
    assert_eq!(body["folders"], 0);
    assert_eq!(body["totalBytes"], 0);
}

#[tokio::test]
async fn apps_list_6_unique_ids() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/apps")
        .header(header::COOKIE, token)
        .body(Body::empty())
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    let arr = body.as_array().unwrap();
    assert_eq!(arr.len(), 6);
    let mut ids: Vec<String> = arr
        .iter()
        .map(|a| a["id"].as_str().unwrap().to_string())
        .collect();
    ids.sort();
    ids.dedup();
    assert_eq!(ids.len(), 6, "duplicate ids: {:?}", ids);
    assert!(ids.iter().any(|i| i == "files"));
}

#[tokio::test]
async fn readyz_200_ready() {
    let state = init_state(":memory:", "static");
    let router = app(state);

    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/readyz")
        .body(Body::empty())
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "ready");
}

#[tokio::test]
async fn setup_needed_true_then_false() {
    let state = init_state(":memory:", "static");
    let router = app(state);

    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/auth/setup-needed")
        .body(Body::empty())
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["needed"], true);

    let _token = register(&router, "alice", "pw123456").await;

    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/auth/setup-needed")
        .body(Body::empty())
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["needed"], false);
}

#[tokio::test]
async fn migrate_legacy_no_legacy_410() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice", "pw123456").await;

    let req = authed_json(Method::POST, "/api/auth/migrate-legacy", &token, json!({}));
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["migrated"], true);

    let req = authed_json(Method::POST, "/api/auth/migrate-legacy", &token, json!({}));
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::GONE);
    let msg = body["error"].as_str().unwrap_or("");
    assert!(msg.contains("无可迁移数据"), "got: {}", msg);
}

#[tokio::test]
async fn migrate_legacy_moves_nodes_and_settings() {
    let state = init_state(":memory:", "static");
    let router = app(state.clone());
    let token = register(&router, "alice", "pw123456").await;

    {
        let conn = state.db.lock().unwrap();
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (1, NULL, 'legacy-file.txt', 'file', 'legacy-data')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (1, 'theme', 'legacy-dark')",
            [],
        )
        .unwrap();
    }

    let req = authed_json(Method::POST, "/api/auth/migrate-legacy", &token, json!({}));
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["migrated"], true);

    let req = authed(Method::GET, "/api/fs", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    let items = body["items"]
        .as_array()
        .or_else(|| body.as_array())
        .unwrap();
    assert!(
        items
            .iter()
            .any(|n| n["name"].as_str() == Some("legacy-file.txt")),
        "fs items: {:?}",
        items
    );

    let req = authed(Method::GET, "/api/settings", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["theme"], "legacy-dark");

    {
        let conn = state.db.lock().unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM users WHERE username = 'legacy'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(count, 0);
    }
}

#[tokio::test]
async fn migrate_legacy_current_setting_wins_on_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state.clone());
    let token = register(&router, "alice", "pw123456").await;

    let req = authed_json(
        Method::PUT,
        "/api/settings",
        &token,
        json!({"key": "theme", "value": "dark"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    {
        let conn = state.db.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (1, 'theme', 'light')",
            [],
        )
        .unwrap();
    }

    let req = authed_json(Method::POST, "/api/auth/migrate-legacy", &token, json!({}));
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["migrated"], true);

    let req = authed(Method::GET, "/api/settings", &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["theme"], "dark");
}
