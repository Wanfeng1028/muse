use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use axum::Router;
use serde_json::json;
use std::sync::Arc;
use tower::ServiceExt;

fn unique_dir(tag: &str) -> std::path::PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("minios-static-deep2-{}-{}-{}", tag, std::process::id(), nanos))
}

fn setup_static_dir(tag: &str, files: &[(&str, &str)]) -> std::path::PathBuf {
    let dir = unique_dir(tag);
    std::fs::create_dir_all(&dir).unwrap();
    for (name, contents) in files {
        std::fs::write(dir.join(name), contents).unwrap();
    }
    dir
}

fn cleanup(dir: &std::path::Path) {
    let _ = std::fs::remove_dir_all(dir);
}

async fn register_cookie(app: &Router, username: &str) -> String {
    let body = serde_json::to_vec(&json!({
        "username": username,
        "password": "password123"
    }))
    .unwrap();
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .expect("missing set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

async fn get_with_cookie(app: &Router, uri: &str, cookie: Option<&str>) -> axum::response::Response {
    let mut builder = Request::builder().method(Method::GET).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    let req = builder.body(Body::empty()).unwrap();
    app.clone().oneshot(req).await.unwrap()
}

#[tokio::test]
async fn unknown_route_with_auth_serves_index_fallback() {
    let dir = setup_static_dir("fallback-auth", &[("index.html", "<html>MINI-OS-SPA-MARKER</html>")]);
    let state: Arc<mini_os::AppState> = mini_os::init_state(":memory:", dir.to_str().unwrap());
    let app = mini_os::build_app(state);
    let cookie = register_cookie(&app, "fallbackuser1").await;

    let resp = get_with_cookie(&app, "/no/such/page", Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(ct.contains("text/html"), "content-type was {}", ct);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let body = String::from_utf8_lossy(&bytes);
    assert!(body.contains("MINI-OS-SPA-MARKER"), "body was {}", body);

    cleanup(&dir);
}

#[tokio::test]
async fn unknown_route_bypasses_auth_serves_index() {
    // lib.rs 注释原文："route_layer 只包装已注册路由"。
    // build_app 中先挂 route_layer(auth/rbac/metrics)，再挂 fallback_service(serve_dir)，
    // 因此 fallback 不在鉴权中间件之后，未知路径直接由 ServeDir 处理，
    // 无 cookie 也会返回 200 的 index.html —— 这是 SPA 的常规设计（前端页面公开、API 受保护）。
    let dir = setup_static_dir("fallback-noauth", &[("index.html", "<html>MINI-OS-SPA-MARKER</html>")]);
    let state: Arc<mini_os::AppState> = mini_os::init_state(":memory:", dir.to_str().unwrap());
    let app = mini_os::build_app(state);

    let resp = get_with_cookie(&app, "/no/such/page", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let body = String::from_utf8_lossy(&bytes);
    assert!(body.contains("MINI-OS-SPA-MARKER"), "body was {}", body);

    cleanup(&dir);
}

#[tokio::test]
async fn root_serves_index() {
    let dir = setup_static_dir("root-index", &[("index.html", "<html>MINI-OS-SPA-MARKER</html>")]);
    let state: Arc<mini_os::AppState> = mini_os::init_state(":memory:", dir.to_str().unwrap());
    let app = mini_os::build_app(state);
    let cookie = register_cookie(&app, "rootuser1").await;

    let resp = get_with_cookie(&app, "/", Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let body = String::from_utf8_lossy(&bytes);
    assert!(body.contains("MINI-OS-SPA-MARKER"), "body was {}", body);

    cleanup(&dir);
}

#[tokio::test]
async fn static_js_served_with_javascript_content_type() {
    let dir = setup_static_dir(
        "static-js",
        &[
            ("index.html", "<html>MINI-OS-SPA-MARKER</html>"),
            ("app.js", "console.log(1)"),
        ],
    );
    let state: Arc<mini_os::AppState> = mini_os::init_state(":memory:", dir.to_str().unwrap());
    let app = mini_os::build_app(state);
    let cookie = register_cookie(&app, "jsuser1").await;

    let resp = get_with_cookie(&app, "/app.js", Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(ct.contains("javascript"), "content-type was {}", ct);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.as_ref(), b"console.log(1)");

    cleanup(&dir);
}

#[tokio::test]
async fn missing_static_dir_returns_404() {
    let dir = unique_dir("missing-dir");
    // 不创建该目录
    let state: Arc<mini_os::AppState> = mini_os::init_state(":memory:", dir.to_str().unwrap());
    let app = mini_os::build_app(state);
    let cookie = register_cookie(&app, "missinguser1").await;

    let resp = get_with_cookie(&app, "/missing", Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    cleanup(&dir);
}

#[tokio::test]
async fn unknown_api_route_falls_back_to_index() {
    let dir = setup_static_dir("api-fallback", &[("index.html", "<html>MINI-OS-SPA-MARKER</html>")]);
    let state: Arc<mini_os::AppState> = mini_os::init_state(":memory:", dir.to_str().unwrap());
    let app = mini_os::build_app(state);
    let cookie = register_cookie(&app, "apiuser1").await;

    let resp = get_with_cookie(&app, "/api/nope", Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let body = String::from_utf8_lossy(&bytes);
    assert!(body.contains("MINI-OS-SPA-MARKER"), "body was {}", body);

    cleanup(&dir);
}
