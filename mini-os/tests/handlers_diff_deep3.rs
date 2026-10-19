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
async fn register(router: &Router, username: &str) -> String {
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

async fn create_node(
    router: &Router,
    token: &str,
    body: Value,
) -> (StatusCode, Value) {
    let req = authed_json(Method::POST, "/api/fs", token, body);
    let resp = router.clone().oneshot(req).await.unwrap();
    read_json(resp).await
}

async fn create_file(router: &Router, token: &str, name: &str) -> (StatusCode, Value) {
    create_node(
        router,
        token,
        json!({"name": name, "kind": "file", "content": "hi"}),
    )
    .await
}

async fn create_folder(router: &Router, token: &str, name: &str) -> (StatusCode, Value) {
    create_node(router, token, json!({"name": name, "kind": "folder"})).await
}

#[tokio::test]
async fn create_fs_duplicate_same_parent_file_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, v1) = create_file(&router, &token, "dup.txt").await;
    assert_eq!(s1, StatusCode::CREATED, "first create should succeed: {:?}", v1);

    let (s2, v2) = create_file(&router, &token, "dup.txt").await;
    assert_eq!(s2, StatusCode::CONFLICT);
    assert_eq!(v2["error"], "同名文件已存在");
}

#[tokio::test]
async fn create_fs_file_and_folder_conflict_both_directions() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, _) = create_file(&router, &token, "x").await;
    assert_eq!(s1, StatusCode::CREATED);
    let (s2, v2) = create_folder(&router, &token, "x").await;
    assert_eq!(s2, StatusCode::CONFLICT);
    assert_eq!(v2["error"], "同名文件已存在");

    let (s3, _) = create_folder(&router, &token, "y").await;
    assert_eq!(s3, StatusCode::CREATED);
    let (s4, v4) = create_file(&router, &token, "y").await;
    assert_eq!(s4, StatusCode::CONFLICT);
    assert_eq!(v4["error"], "同名文件已存在");
}

#[tokio::test]
async fn create_fs_same_name_different_parent_no_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (sa, va) = create_folder(&router, &token, "A").await;
    assert_eq!(sa, StatusCode::CREATED, "{:?}", va);
    let a_id = va["id"].as_i64().unwrap();

    let (sb, vb) = create_folder(&router, &token, "B").await;
    assert_eq!(sb, StatusCode::CREATED, "{:?}", vb);
    let b_id = vb["id"].as_i64().unwrap();

    let (s1, v1) = create_node(
        &router,
        &token,
        json!({"name": "same.txt", "kind": "file", "content": "a", "parentId": a_id}),
    )
    .await;
    assert_eq!(s1, StatusCode::CREATED, "{:?}", v1);

    let (s2, v2) = create_node(
        &router,
        &token,
        json!({"name": "same.txt", "kind": "file", "content": "b", "parentId": b_id}),
    )
    .await;
    assert_eq!(s2, StatusCode::CREATED, "{:?}", v2);
}

#[tokio::test]
async fn create_fs_name_is_trimmed_before_conflict_check() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, _) = create_file(&router, &token, "dup").await;
    assert_eq!(s1, StatusCode::CREATED);

    let (s2, v2) = create_file(&router, &token, " dup ").await;
    assert_eq!(s2, StatusCode::CONFLICT);
    assert_eq!(v2["error"], "同名文件已存在");
}

#[tokio::test]
async fn create_fs_same_name_different_user_no_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let alice = register(&router, "alice").await;
    let bob = register(&router, "bob").await;

    let (s1, _) = create_file(&router, &alice, "same.txt").await;
    assert_eq!(s1, StatusCode::CREATED);

    let (s2, v2) = create_file(&router, &bob, "same.txt").await;
    assert_eq!(s2, StatusCode::CREATED, "{:?}", v2);
}

#[tokio::test]
async fn create_fs_after_delete_same_name_succeeds() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, v1) = create_file(&router, &token, "recreate.txt").await;
    assert_eq!(s1, StatusCode::CREATED);
    let id = v1["id"].as_i64().unwrap();

    let req = authed(Method::DELETE, &format!("/api/fs/{}", id), &token);
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    let (s3, v3) = create_file(&router, &token, "recreate.txt").await;
    assert_eq!(s3, StatusCode::CREATED, "{:?}", v3);
}

#[tokio::test]
async fn create_fs_invalid_inputs_still_bad_request() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s_empty, _) = create_file(&router, &token, "").await;
    assert_eq!(s_empty, StatusCode::BAD_REQUEST);

    let (s_ws, _) = create_file(&router, &token, "   ").await;
    assert_eq!(s_ws, StatusCode::BAD_REQUEST);

    let (s_kind, _) = create_node(
        &router,
        &token,
        json!({"name": "bad", "kind": "symlink"}),
    )
    .await;
    assert_eq!(s_kind, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn update_fs_rename_to_sibling_existing_returns_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, v1) = create_file(&router, &token, "one.txt").await;
    assert_eq!(s1, StatusCode::CREATED);
    let id1 = v1["id"].as_i64().unwrap();

    let (s2, _) = create_file(&router, &token, "two.txt").await;
    assert_eq!(s2, StatusCode::CREATED);

    let req = authed_json(
        Method::PUT,
        &format!("/api/fs/{}", id1),
        &token,
        json!({"name": "two.txt"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["error"], "同名文件已存在");
}

#[tokio::test]
async fn update_fs_rename_to_own_name_succeeds() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, v1) = create_file(&router, &token, "self.txt").await;
    assert_eq!(s1, StatusCode::CREATED);
    let id = v1["id"].as_i64().unwrap();

    let req = authed_json(
        Method::PUT,
        &format!("/api/fs/{}", id),
        &token,
        json!({"name": "self.txt"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn update_fs_rename_trimmed_sibling_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, v1) = create_file(&router, &token, "one.txt").await;
    assert_eq!(s1, StatusCode::CREATED);
    let id1 = v1["id"].as_i64().unwrap();

    let (s2, _) = create_file(&router, &token, "target").await;
    assert_eq!(s2, StatusCode::CREATED);

    let req = authed_json(
        Method::PUT,
        &format!("/api/fs/{}", id1),
        &token,
        json!({"name": " target "}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["error"], "同名文件已存在");
}

#[tokio::test]
async fn update_fs_rename_to_name_in_other_parent_succeeds() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (sa, va) = create_folder(&router, &token, "A").await;
    assert_eq!(sa, StatusCode::CREATED, "{:?}", va);
    let a_id = va["id"].as_i64().unwrap();

    let (sb, vb) = create_folder(&router, &token, "B").await;
    assert_eq!(sb, StatusCode::CREATED, "{:?}", vb);
    let b_id = vb["id"].as_i64().unwrap();

    let (s1, v1) = create_node(
        &router,
        &token,
        json!({"name": "inside.txt", "kind": "file", "content": "x", "parentId": a_id}),
    )
    .await;
    assert_eq!(s1, StatusCode::CREATED, "{:?}", v1);
    let node_a = v1["id"].as_i64().unwrap();

    let (s2, _) = create_node(
        &router,
        &token,
        json!({"name": "inside.txt", "kind": "file", "content": "y", "parentId": b_id}),
    )
    .await;
    assert_eq!(s2, StatusCode::CREATED);

    let req = authed_json(
        Method::PUT,
        &format!("/api/fs/{}", node_a),
        &token,
        json!({"name": "inside.txt"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn update_fs_content_only_succeeds() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (s1, v1) = create_file(&router, &token, "data.txt").await;
    assert_eq!(s1, StatusCode::CREATED);
    let id = v1["id"].as_i64().unwrap();

    let (s2, _) = create_file(&router, &token, "other.txt").await;
    assert_eq!(s2, StatusCode::CREATED);

    let req = authed_json(
        Method::PUT,
        &format!("/api/fs/{}", id),
        &token,
        json!({"content": "new content"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn update_fs_rename_folder_to_file_name_conflict() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let token = register(&router, "alice").await;

    let (sf, vf) = create_file(&router, &token, "clash").await;
    assert_eq!(sf, StatusCode::CREATED, "{:?}", vf);

    let (sd, vd) = create_folder(&router, &token, "mydir").await;
    assert_eq!(sd, StatusCode::CREATED, "{:?}", vd);
    let dir_id = vd["id"].as_i64().unwrap();

    let req = authed_json(
        Method::PUT,
        &format!("/api/fs/{}", dir_id),
        &token,
        json!({"name": "clash"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["error"], "同名文件已存在");
}

#[tokio::test]
async fn migrate_legacy_current_user_settings_take_precedence() {
    let state = init_state(":memory:", "static");
    let router = app(state.clone());
    let alice = register(&router, "alice").await;

    let req = authed_json(
        Method::PUT,
        "/api/settings",
        &alice,
        json!({"key": "theme", "value": "dark"}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    {
        let conn = state.db.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?1, ?2, ?3)",
            rusqlite::params![1i64, "theme", "light"],
        )
        .unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?1, ?2, ?3)",
            rusqlite::params![1i64, "lang", "zh"],
        )
        .unwrap();
    }

    let req = authed_json(
        Method::POST,
        "/api/auth/migrate-legacy",
        &alice,
        json!({}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let req = authed(Method::GET, "/api/settings", &alice);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["theme"], "dark");
    assert_eq!(body["lang"], "zh");

    {
        let conn = state.db.lock().unwrap();
        let legacy_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM users WHERE id = ?1",
                rusqlite::params![1i64],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(legacy_count, 0, "legacy user should be deleted");

        let legacy_conflict: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM settings WHERE user_id = ?1 AND key = ?2",
                rusqlite::params![1i64, "theme"],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(legacy_conflict, 0, "legacy conflicting row should be deleted");
    }
}

#[tokio::test]
async fn migrate_legacy_without_legacy_returns_gone() {
    let state = init_state(":memory:", "static");
    let router = app(state);
    let alice = register(&router, "alice").await;

    let req = authed_json(
        Method::POST,
        "/api/auth/migrate-legacy",
        &alice,
        json!({}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let req = authed_json(
        Method::POST,
        "/api/auth/migrate-legacy",
        &alice,
        json!({}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::GONE);
    assert!(
        body["error"]
            .as_str()
            .unwrap_or("")
            .contains("无可迁移数据"),
        "expected error to contain 无可迁移数据, got {:?}",
        body
    );
}

#[tokio::test]
async fn migrate_legacy_moves_vfs_nodes_to_current_user() {
    let state = init_state(":memory:", "static");
    let router = app(state.clone());
    let alice = register(&router, "alice").await;

    {
        let conn = state.db.lock().unwrap();
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content) VALUES (?1, ?2, ?3, ?4, ?5)",
            rusqlite::params![1i64, Option::<i64>::None, "legacy.txt", "file", "hello"],
        )
        .unwrap();
    }

    let req = authed_json(
        Method::POST,
        "/api/auth/migrate-legacy",
        &alice,
        json!({}),
    );
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let req = authed(Method::GET, "/api/fs", &alice);
    let resp = router.clone().oneshot(req).await.unwrap();
    let (status, body) = read_json(resp).await;
    assert_eq!(status, StatusCode::OK);

    let found = body
        .as_array()
        .map(|arr| {
            arr.iter().any(|n| {
                n.get("name").and_then(|v| v.as_str()) == Some("legacy.txt")
            })
        })
        .unwrap_or(false);
    assert!(found, "expected migrated legacy.txt in listing, got {:?}", body);
}