use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let (status, _body, cookie) = register(&app, "tester", "password123").await;
    assert_eq!(status, StatusCode::CREATED);
    (app, cookie)
}

async fn register(app: &Router, username: &str, password: &str) -> (StatusCode, Value, String) {
    let payload = json!({ "username": username, "password": password });
    let request = Request::builder()
        .method("POST").uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(payload.to_string())).unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let cookie = response.headers().get("set-cookie").and_then(|v| v.to_str().ok())
        .map(|s| s.split(';').next().unwrap_or("").to_string()).unwrap_or_default();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, value, cookie)
}

async fn req(app: &Router, method: &str, uri: &str, body: Option<Value>, cookie: &str) -> (StatusCode, Value) {
    let payload = body.unwrap_or(Value::Null);
    let builder = Request::builder().method(method).uri(uri).header("content-type", "application/json");
    let builder = if cookie.is_empty() { builder } else { builder.header("cookie", cookie) };
    let request = builder.body(axum::body::Body::from(payload.to_string())).unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = if bytes.is_empty() { Value::Null } else { serde_json::from_slice(&bytes).unwrap_or(Value::Null) };
    (status, value)
}

#[tokio::test]
async fn parent_path_traversal_rejected() {
    // 测什么：POST /api/fs 的 parent 路径参数中出现 ".."、"."、空段等非法段时必须返回 400。
    // 为什么：路径穿越是文件类应用的安全红线，resolve_folder_id 需对每一段做校验，
    // 这三种是最典型的绕过姿势（父级逃逸、中间穿越、当前目录），必须全部拦住。
    // 注意：resolve_folder_id 按段从左到右解析，先查库、后判 ".."，前导段不存在时先报
    // "目录不存在或不是文件夹"；两种 400 都是拒绝，安全语义成立。因此第二组用例需先建一个
    // 真实文件夹 docs，让第一段能查到，第二段 ".." 才会触发 Err("非法路径")。
    let (app, cookie) = test_app().await;

    let (status1, body1) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "x1", "kind": "file", "parent": "../" })),
        &cookie,
    )
    .await;
    assert_eq!(status1, StatusCode::BAD_REQUEST);
    assert_eq!(body1["error"], json!("非法路径"));

    let (_s0, b0) = req(&app, "POST", "/api/fs",
        Some(json!({ "name": "docs", "kind": "folder" })), &cookie).await;
    assert_eq!(_s0, StatusCode::CREATED);
    let _docs_id = b0["id"].as_i64().expect("docs id");
    let (status2, body2) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "x2", "kind": "file", "parent": "docs/../../etc" })),
        &cookie,
    )
    .await;
    assert_eq!(status2, StatusCode::BAD_REQUEST);
    assert_eq!(body2["error"], json!("非法路径"));

    let (status3, body3) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "x3", "kind": "file", "parent": "." })),
        &cookie,
    )
    .await;
    assert_eq!(status3, StatusCode::BAD_REQUEST);
    assert_eq!(body3["error"], json!("非法路径"));
}