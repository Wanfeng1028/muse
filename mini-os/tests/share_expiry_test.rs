use axum::body::to_bytes;
use axum::body::Body;
use axum::http::{header, Request, StatusCode};
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

async fn delete(app: &axum::Router, uri: &str, cookie: Option<&str>) -> axum::response::Response {
    let mut builder = Request::builder().method("DELETE").uri(uri);
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    app.clone()
        .oneshot(builder.body(Body::empty()).unwrap())
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
        "minios_share_expiry_{}_{}.db",
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
        "expected body to contain {needle:?}, got: {text}"
    );
    (status, text)
}

#[tokio::test]
async fn share_with_future_expiry_is_accessible() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "owner_future", "pw12345678").await;

    let file_id = create_text_file(&app, &cookie, None, "future.txt", "hello").await;
    let future = now_secs() + 3600;
    let resp = create_share(&app, &cookie, file_id, Some(future)).await;
    assert_eq!(resp.status(), StatusCode::CREATED, "create share failed");
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn share_with_past_expiry_is_rejected() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "owner_past", "pw12345678").await;

    let file_id = create_text_file(&app, &cookie, None, "past.txt", "hello").await;
    let past = now_secs() - 3600;
    let resp = create_share(&app, &cookie, file_id, Some(past)).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn expired_share_returns_410_everywhere() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "owner_expired", "pw12345678").await;

    let file_id = create_text_file(&app, &cookie, None, "expire_me.txt", "payload").await;
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
        assert_eq!(n, 1, "expected exactly one share row updated");
    }

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    let (status, _) = body_contains(resp, "过期").await;
    assert_eq!(status, StatusCode::GONE, "GET /api/s/:token");

    let resp = get(&app, &format!("/api/s/{token}/download"), None).await;
    let (status, _) = body_contains(resp, "过期").await;
    assert_eq!(status, StatusCode::GONE, "GET /api/s/:token/download");

    let resp = get(&app, &format!("/api/share/list?token={token}"), None).await;
    let (status, _) = body_contains(resp, "过期").await;
    assert_eq!(status, StatusCode::GONE, "GET /api/share/list?token=");
}

#[tokio::test]
async fn revoked_share_returns_404() {
    let state = fresh_state();
    let app = app_for(&state);
    let cookie = register(&app, "owner_revoke", "pw12345678").await;

    let file_id = create_text_file(&app, &cookie, None, "revoke.txt", "payload").await;
    let future = now_secs() + 3600;
    let resp = create_share(&app, &cookie, file_id, Some(future)).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();

    let resp = delete(&app, &format!("/api/shares/token/{token}"), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT, "delete share failed");

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn non_owner_editor_cannot_revoke_and_missing_token_is_404() {
    let state = fresh_state();
    let app = app_for(&state);
    let owner = register(&app, "owner_priv", "pw12345678").await;
    let editor = register(&app, "editor_priv", "pw12345678").await;

    let file_id = create_text_file(&app, &owner, None, "priv.txt", "payload").await;

    let future = now_secs() + 3600;
    let resp = create_share(&app, &owner, file_id, Some(future)).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token = v["token"].as_str().expect("missing token").to_string();

    let resp = delete(&app, &format!("/api/shares/token/{token}"), Some(&editor)).await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "editor must not revoke"
    );

    let resp = delete(
        &app,
        "/api/shares/token/nonexistent-token-xyz",
        Some(&owner),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::NOT_FOUND,
        "missing token must be 404"
    );
}
