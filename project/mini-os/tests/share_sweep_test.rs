use axum::body::{to_bytes, Body};
use axum::http::{header, Request, StatusCode};
use serde_json::{json, Value};
use tower::ServiceExt;

fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}

fn fresh_state() -> std::sync::Arc<mini_os::AppState> {
    let ns = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "minios_share_sweep_{}_{}.db",
        std::process::id(),
        ns
    ));
    mini_os::init_state_with(
        &path.to_string_lossy(),
        "static",
        10 * 1024 * 1024,
        3600,
        100.0,
        100,
    )
}

fn app_for(state: &std::sync::Arc<mini_os::AppState>) -> axum::Router {
    mini_os::build_app(state.clone())
}

async fn register(app: &mut axum::Router, username: &str) -> String {
    let body = json!({"username": username, "password": "pw12345678"}).to_string();
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/register")
                .header(header::CONTENT_TYPE, "application/json")
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
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
        .unwrap();
    set_cookie.split(';').next().unwrap().to_string()
}

async fn post_json(
    app: &mut axum::Router,
    uri: &str,
    cookie: &str,
    body: Value,
) -> (StatusCode, Value) {
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(uri)
                .header(header::COOKIE, cookie)
                .header(header::CONTENT_TYPE, "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: Value = serde_json::from_slice(&bytes).unwrap_or(json!(null));
    (status, v)
}

async fn get(app: &mut axum::Router, uri: &str, cookie: &str) -> (StatusCode, Value) {
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri(uri)
                .header(header::COOKIE, cookie)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: Value = serde_json::from_slice(&bytes).unwrap_or(json!(null));
    (status, v)
}

async fn create_text_file(app: &mut axum::Router, cookie: &str, name: &str) -> i64 {
    let (status, v) = post_json(
        app,
        "/api/fs",
        cookie,
        json!({"name": name, "kind": "file", "content": "hello"}),
    )
    .await;
    assert_eq!(
        status,
        StatusCode::CREATED,
        "create_text_file {name} failed"
    );
    v["id"].as_i64().expect("missing file id")
}

async fn create_share(
    app: &mut axum::Router,
    cookie: &str,
    node_id: i64,
    expires_at: Option<i64>,
) -> String {
    let mut body = json!({"nodeId": node_id});
    if let Some(exp) = expires_at {
        body["expiresAt"] = json!(exp);
    }
    let (status, v) = post_json(app, "/api/shares", cookie, body).await;
    assert_eq!(status, StatusCode::CREATED, "create_share failed");
    v["token"].as_str().expect("missing token").to_string()
}

fn shares_count(state: &std::sync::Arc<mini_os::AppState>) -> i64 {
    let conn = state.db.lock().unwrap();
    conn.query_row("SELECT COUNT(*) FROM shares", [], |r| r.get::<_, i64>(0))
        .unwrap()
}

fn expire_share(state: &std::sync::Arc<mini_os::AppState>, token: &str) {
    let past = now_secs() - 10;
    let conn = state.db.lock().unwrap();
    let n = conn
        .execute(
            "UPDATE shares SET expires_at = ?1 WHERE token = ?2",
            rusqlite::params![past, token],
        )
        .expect("update expires_at failed");
    assert_eq!(n, 1, "expected exactly one share row updated");
}

#[tokio::test]
async fn list_sweeps_expired_share() {
    let state = fresh_state();
    let mut app = app_for(&state);

    let cookie = register(&mut app, "list_sweeps_expired_owner").await;
    let file_id = create_text_file(&mut app, &cookie, "f1.txt").await;
    let token = create_share(&mut app, &cookie, file_id, Some(now_secs() + 3600)).await;

    expire_share(&state, &token);

    let (status, v) = get(&mut app, "/api/shares", &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = v.as_array().unwrap();
    assert_eq!(arr.len(), 0);
    assert_eq!(shares_count(&state), 0);
}

#[tokio::test]
async fn list_keeps_unexpired_shares() {
    let state = fresh_state();
    let mut app = app_for(&state);

    let cookie = register(&mut app, "list_keeps_unexpired_owner").await;
    let file_a = create_text_file(&mut app, &cookie, "fa.txt").await;
    let file_b = create_text_file(&mut app, &cookie, "fb.txt").await;

    let _tok_a = create_share(&mut app, &cookie, file_a, None).await;
    let _tok_b = create_share(&mut app, &cookie, file_b, Some(now_secs() + 3600)).await;

    let (status, v) = get(&mut app, "/api/shares", &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = v.as_array().unwrap();
    assert_eq!(arr.len(), 2);
    assert_eq!(shares_count(&state), 2);
}

#[tokio::test]
async fn list_sweeps_other_owners_expired_share() {
    let state = fresh_state();
    let mut app = app_for(&state);

    let cookie_a = register(&mut app, "sweep_other_owner_a").await;
    let cookie_b = register(&mut app, "sweep_other_owner_b").await;

    let file_id = create_text_file(&mut app, &cookie_a, "fc.txt").await;
    let token = create_share(&mut app, &cookie_a, file_id, Some(now_secs() + 3600)).await;

    expire_share(&state, &token);

    let (status, _v) = get(&mut app, "/api/shares", &cookie_b).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(shares_count(&state), 0);
}
