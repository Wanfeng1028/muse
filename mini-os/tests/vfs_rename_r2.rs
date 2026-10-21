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
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(payload.to_string()))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let cookie = response
        .headers()
        .get("set-cookie")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.split(';').next().unwrap_or("").to_string())
        .unwrap_or_default();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, value, cookie)
}

async fn req(
    app: &Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: &str,
) -> (StatusCode, Value) {
    let payload = body.unwrap_or(Value::Null);
    let builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("content-type", "application/json");
    let builder = if cookie.is_empty() {
        builder
    } else {
        builder.header("cookie", cookie)
    };
    let request = builder
        .body(axum::body::Body::from(payload.to_string()))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    };
    (status, value)
}

#[tokio::test]
async fn rename_conflict_409() {
    // 测什么：重命名撞同级同名被拒，但改回自己名字不算冲突。
    // 为什么：冲突检查必须排除自己（id !=），否则正常重命名会被误杀。
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "a.txt", "kind": "file"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id_a = body["id"].as_i64().expect("id_a 应为整数");

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "b.txt", "kind": "file"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id_b = body["id"].as_i64().expect("id_b 应为整数");
    assert_ne!(id_a, id_b);

    let uri_a = format!("/api/fs/{}", id_a);
    let (status, body) = req(&app, "PUT", &uri_a, Some(json!({"name": "b.txt"})), &cookie).await;
    assert_eq!(status, StatusCode::CONFLICT);
    let err = body["error"].as_str().unwrap_or("");
    assert!(
        err.contains("同名文件已存在"),
        "error 应包含同名文件已存在, 实际: {}",
        err
    );

    let (status, body) = req(&app, "PUT", &uri_a, Some(json!({"name": "a.txt"})), &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"].as_str(), Some("a.txt"));
    assert_eq!(body["id"].as_i64(), Some(id_a));
}

#[tokio::test]
async fn rename_trims_whitespace() {
    // 测什么：重命名前后空白被 trim。
    // 为什么：首尾空格文件名在前端展示和下载时都是坑，入库即规范化。
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "sp.txt", "kind": "file"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id = body["id"].as_i64().expect("id 应为整数");

    let uri = format!("/api/fs/{}", id);
    let (status, body) = req(
        &app,
        "PUT",
        &uri,
        Some(json!({"name": "  spaced.txt  "})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"].as_str(), Some("spaced.txt"));

    let (status, body) = req(&app, "GET", &uri, None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["name"].as_str(), Some("spaced.txt"));
    assert_eq!(body["id"].as_i64(), Some(id));
}
