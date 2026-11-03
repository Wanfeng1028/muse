use std::sync::Arc;
use std::time::Duration;

use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state_with_full};
use serde_json::{json, Value};
use tower::ServiceExt;

fn app_with_share_limits(
    share_rps: f64,
    share_burst: u64,
    enabled: bool,
) -> (Router, Arc<mini_os::AppState>) {
    let state = init_state_with_full(
        ":memory:",
        "static",
        1024,
        60,
        100.0,
        100,
        share_rps,
        share_burst,
        enabled,
    );
    let app = build_app(state.clone());
    (app, state)
}

async fn raw_request(
    app: &Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<&str>,
) -> (StatusCode, axum::http::HeaderMap, Value) {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let request = match body {
        Some(v) => builder
            .header("content-type", "application/json")
            .body(axum::body::Body::from(serde_json::to_vec(&v).unwrap()))
            .unwrap(),
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let headers = response.headers().clone();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    };
    (status, headers, value)
}

async fn register_and_login(app: &Router, username: &str) -> String {
    let (status, _h, _b) = raw_request(
        app,
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "pw123456"})),
        None,
    )
    .await;
    assert!(
        status == StatusCode::CREATED || status == StatusCode::OK,
        "register failed: {status}"
    );

    let (status, headers, _b) = raw_request(
        app,
        "POST",
        "/api/auth/login",
        Some(json!({"username": username, "password": "pw123456"})),
        None,
    )
    .await;
    assert_eq!(status, StatusCode::OK, "login failed");
    let cookie = headers
        .get("set-cookie")
        .and_then(|v| v.to_str().ok())
        .expect("no set-cookie")
        .split(';')
        .next()
        .unwrap()
        .to_string();
    cookie
}

async fn create_file(app: &Router, cookie: &str, name: &str) -> i64 {
    let (status, _h, body) = raw_request(
        app,
        "POST",
        "/api/fs",
        Some(json!({"name": name, "kind": "file", "content": "hello"})),
        Some(cookie),
    )
    .await;
    assert_eq!(status, StatusCode::CREATED, "create file failed: {body}");
    body.get("id").and_then(|v| v.as_i64()).expect("no file id")
}

async fn create_share(app: &Router, cookie: &str, node_id: i64) -> String {
    let (status, _h, body) = raw_request(
        app,
        "POST",
        "/api/shares",
        Some(json!({"nodeId": node_id})),
        Some(cookie),
    )
    .await;
    assert_eq!(status, StatusCode::CREATED, "create share failed: {body}");
    body.get("token")
        .and_then(|v| v.as_str())
        .expect("no token")
        .to_string()
}

async fn create_folder(app: &Router, cookie: &str, name: &str, parent: Option<i64>) -> i64 {
    let mut v = json!({"name": name, "kind": "folder"});
    if let Some(p) = parent {
        v["parentId"] = json!(p);
    }
    let (status, _h, body) = raw_request(app, "POST", "/api/fs", Some(v), Some(cookie)).await;
    assert_eq!(status, StatusCode::CREATED, "create folder failed: {body}");
    body.get("id")
        .and_then(|v| v.as_i64())
        .expect("no folder id")
}

async fn create_dir_share(app: &Router, cookie: &str, path: &str) -> String {
    let (status, _h, body) = raw_request(
        app,
        "POST",
        "/api/shares",
        Some(json!({"type": "dir", "path": path})),
        Some(cookie),
    )
    .await;
    assert_eq!(
        status,
        StatusCode::CREATED,
        "create dir share failed: {body}"
    );
    body.get("token")
        .and_then(|v| v.as_str())
        .expect("no token")
        .to_string()
}

#[tokio::test]
async fn share_read_burst_then_429() {
    let (app, _state) = app_with_share_limits(0.5, 3, true);
    let cookie = register_and_login(&app, "u_burst").await;
    let file_id = create_file(&app, &cookie, "burst.txt").await;
    let token = create_share(&app, &cookie, file_id).await;

    let uri = format!("/api/s/{token}");
    for i in 0..3 {
        let (status, _h, body) = raw_request(&app, "GET", &uri, None, None).await;
        assert_eq!(status, StatusCode::OK, "req {i} should pass: {body}");
    }

    let (status, headers, body) = raw_request(&app, "GET", &uri, None, None).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS, "4th should be 429");

    let retry_after = headers
        .get("retry-after")
        .and_then(|v| v.to_str().ok())
        .expect("missing retry-after header");
    let secs: u64 = retry_after.parse().expect("retry-after not integer");
    assert!(secs > 0, "retry-after must be positive");

    let body_secs = body
        .get("retry_after")
        .and_then(|v| v.as_u64())
        .expect("no retry_after in body");
    assert_eq!(body_secs, secs, "header/body retry_after mismatch");

    let err = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(
        err.contains("分享访问过于频繁"),
        "error message mismatch: {err}"
    );
}

#[tokio::test]
async fn share_read_window_recovers() {
    let (app, _state) = app_with_share_limits(0.5, 3, true);
    let cookie = register_and_login(&app, "u_recover").await;
    let file_id = create_file(&app, &cookie, "recover.txt").await;
    let token = create_share(&app, &cookie, file_id).await;

    let uri = format!("/api/s/{token}");
    for _ in 0..3 {
        let (status, _h, _b) = raw_request(&app, "GET", &uri, None, None).await;
        assert_eq!(status, StatusCode::OK);
    }
    let (status, _h, _b) = raw_request(&app, "GET", &uri, None, None).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);

    tokio::time::sleep(Duration::from_secs(3)).await;

    let (status, _h, body) = raw_request(&app, "GET", &uri, None, None).await;
    assert_eq!(
        status,
        StatusCode::OK,
        "should recover after window: {body}"
    );
}

#[tokio::test]
async fn share_read_probes_exempt() {
    let (app, _state) = app_with_share_limits(0.5, 2, true);
    let cookie = register_and_login(&app, "u_probes").await;
    let file_id = create_file(&app, &cookie, "probes.txt").await;
    let token = create_share(&app, &cookie, file_id).await;

    let uri = format!("/api/s/{token}");
    for _ in 0..2 {
        let (status, _h, _b) = raw_request(&app, "GET", &uri, None, None).await;
        assert_eq!(status, StatusCode::OK);
    }
    let (status, _h, _b) = raw_request(&app, "GET", &uri, None, None).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);

    let (health_status, _h, _b) = raw_request(&app, "GET", "/api/health", None, None).await;
    assert_eq!(health_status, StatusCode::OK, "health should be exempt");

    let (ready_status, _h, _b) = raw_request(&app, "GET", "/api/readyz", None, None).await;
    assert_eq!(ready_status, StatusCode::OK, "readyz should be exempt");

    let (metrics_status, _h, _b) = raw_request(&app, "GET", "/metrics", None, None).await;
    assert_eq!(metrics_status, StatusCode::OK, "metrics should be exempt");
}

#[tokio::test]
async fn share_read_ip_dimension_across_tokens() {
    let (app, _state) = app_with_share_limits(0.5, 3, true);
    let cookie = register_and_login(&app, "u_ipdim").await;
    let file_a = create_file(&app, &cookie, "a.txt").await;
    let file_b = create_file(&app, &cookie, "b.txt").await;
    let token_a = create_share(&app, &cookie, file_a).await;
    let token_b = create_share(&app, &cookie, file_b).await;

    let uri_a = format!("/api/s/{token_a}");
    for _ in 0..3 {
        let (status, _h, _b) = raw_request(&app, "GET", &uri_a, None, None).await;
        assert_eq!(status, StatusCode::OK);
    }
    let (status, headers, _b) = raw_request(&app, "GET", &uri_a, None, None).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
    assert!(headers.contains_key("retry-after"));

    let uri_b = format!("/api/s/{token_b}");
    let (status, _h, body) = raw_request(&app, "GET", &uri_b, None, None).await;
    assert_eq!(
        status,
        StatusCode::TOO_MANY_REQUESTS,
        "same IP with another token should also be limited: {body}"
    );
}

#[tokio::test]
async fn share_read_disabled_no_limit() {
    let (app, _state) = app_with_share_limits(0.5, 1, false);
    let cookie = register_and_login(&app, "u_disabled").await;
    let file_id = create_file(&app, &cookie, "disabled.txt").await;
    let token = create_share(&app, &cookie, file_id).await;

    let uri = format!("/api/s/{token}");
    for i in 0..5 {
        let (status, _h, body) = raw_request(&app, "GET", &uri, None, None).await;
        assert_eq!(
            status,
            StatusCode::OK,
            "req {i} should pass when disabled: {body}"
        );
    }
}

#[tokio::test]
async fn share_read_three_routes_share_one_limiter() {
    let (app, _state) = app_with_share_limits(0.5, 2, true);
    let cookie = register_and_login(&app, "u_routes").await;
    let docs = create_folder(&app, &cookie, "docs", None).await;
    let mut v = json!({"name": "a.txt", "kind": "file", "content": "aaa"});
    v["parentId"] = json!(docs);
    let (status, _h, body) = raw_request(&app, "POST", "/api/fs", Some(v), Some(&cookie)).await;
    assert_eq!(
        status,
        StatusCode::CREATED,
        "create inner file failed: {body}"
    );
    let token = create_dir_share(&app, &cookie, "/docs").await;

    let meta_uri = format!("/api/s/{token}");
    let list_uri = format!("/api/share/list?token={token}");
    let download_uri = format!("/api/s/{token}/download?path=/a.txt");

    let (s1, _h, b1) = raw_request(&app, "GET", &meta_uri, None, None).await;
    assert_eq!(s1, StatusCode::OK, "1st meta: {b1}");

    let (s2, _h, b2) = raw_request(&app, "GET", &list_uri, None, None).await;
    assert_eq!(s2, StatusCode::OK, "2nd list: {b2}");

    let (s3, headers, b3) = raw_request(&app, "GET", &download_uri, None, None).await;
    assert_eq!(
        s3,
        StatusCode::TOO_MANY_REQUESTS,
        "3rd should be 429 shared limiter: {b3}"
    );
    assert!(headers.contains_key("retry-after"));
}

#[tokio::test]
async fn share_read_metrics_counted() {
    let (app, _state) = app_with_share_limits(0.5, 1, true);
    let cookie = register_and_login(&app, "u_metrics").await;
    let file_id = create_file(&app, &cookie, "metrics.txt").await;
    let token = create_share(&app, &cookie, file_id).await;

    let uri = format!("/api/s/{token}");
    let (status, _h, _b) = raw_request(&app, "GET", &uri, None, None).await;
    assert_eq!(status, StatusCode::OK);
    let (status, _h, _b) = raw_request(&app, "GET", &uri, None, None).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);

    let request = Request::builder()
        .method("GET")
        .uri("/metrics")
        .body(axum::body::Body::empty())
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let text = String::from_utf8(bytes.to_vec()).unwrap();

    let needle = "minios_share_rate_limited_total";
    let line = text
        .lines()
        .find(|l| l.starts_with(needle) && !l.starts_with("#"))
        .unwrap_or_else(|| panic!("metrics missing {needle}\n---\n{text}"));

    let value_str = line
        .rsplit_once(' ')
        .map(|(_, v)| v)
        .expect("no value in metrics line");
    let value: f64 = value_str.parse().expect("metrics value not numeric");
    assert!(
        value >= 1.0,
        "minios_share_rate_limited_total should be >=1, got {value}"
    );

    let help_line = format!("# HELP {needle}");
    let type_line = format!("# TYPE {needle}");
    assert!(
        text.lines().any(|l| l.starts_with(&help_line)),
        "metrics missing HELP line for {needle}\n---\n{text}"
    );
    assert!(
        text.lines().any(|l| l.starts_with(&type_line)),
        "metrics missing TYPE line for {needle}\n---\n{text}"
    );
}

#[tokio::test]
async fn share_create_not_limited() {
    let (app, _state) = app_with_share_limits(0.5, 1, true);
    let cookie = register_and_login(&app, "u_create").await;

    for i in 0..5 {
        let name = format!("create_{i}.txt");
        let file_id = create_file(&app, &cookie, &name).await;
        let (status, _h, body) = raw_request(
            &app,
            "POST",
            "/api/shares",
            Some(json!({"nodeId": file_id})),
            Some(&cookie),
        )
        .await;
        assert_eq!(
            status,
            StatusCode::CREATED,
            "create share {i} should not be limited: {body}"
        );
        assert!(body.get("token").and_then(|v| v.as_str()).is_some());
    }
}
