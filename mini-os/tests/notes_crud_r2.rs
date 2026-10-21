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
async fn note_title_length_boundary() {
    // 测什么：POST /api/notes 时 title 长度 200 应成功、201 应拒绝。
    // 为什么：边界值最容易出现差一错误，必须锁死 200/201 的分界。
    let (app, cookie) = test_app().await;

    let ok_title = "a".repeat(200);
    let (status, body) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": ok_title })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["title"].as_str().unwrap().len(), 200);

    let bad_title = "a".repeat(201);
    let (status, _body) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": bad_title })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn note_blank_title_400_and_trim() {
    // 测什么：纯空白 title 返回 400；带前后空格的 title 入库后应被 trim。
    // 为什么：空白标题会变成列表里的幽灵条目，trim 后入库能保持数据干净。
    let (app, cookie) = test_app().await;

    let (status, _body) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "   " })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let (status, body) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "  padded  " })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["title"].as_str().unwrap(), "padded");
}

#[tokio::test]
async fn note_partial_update_body_only() {
    // 测什么：PUT /api/notes/{id} 只传 body 时，title 与 pinned 应保持不变。
    // 为什么：部分更新若把未传字段清空，会造成前端 PATCH 式更新的数据丢失。
    let (app, cookie) = test_app().await;

    let (status, created) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "T-keep", "body": "B1" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id = created["id"].as_i64().unwrap();

    let uri = format!("/api/notes/{}", id);
    let (status, body) = req(&app, "PUT", &uri, Some(json!({ "body": "B2" })), &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["title"].as_str().unwrap(), "T-keep");
    assert_eq!(body["body"].as_str().unwrap(), "B2");
    assert_eq!(body["pinned"].as_bool().unwrap(), false);
}

#[tokio::test]
async fn note_delete_missing_and_cross_user_404() {
    // 测什么：删除不存在笔记返回 404；跨用户删除按 404 处理，且对方列表看不到该笔记。
    // 为什么：越权读写是安全红线，IDOR 必须按"不存在"处理以避免泄露存在性。
    let (app, cookie) = test_app().await;

    let (status, _body) = req(&app, "DELETE", "/api/notes/999999", None, &cookie).await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, created) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "secret" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id = created["id"].as_i64().unwrap();

    let (status2, _body2, cookie2) = register(&app, "user2", "password123").await;
    assert_eq!(status2, StatusCode::CREATED);

    let uri = format!("/api/notes/{}", id);
    let (status, _body) = req(&app, "DELETE", &uri, None, &cookie2).await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, body) = req(&app, "GET", "/api/notes", None, &cookie2).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 0);
}
