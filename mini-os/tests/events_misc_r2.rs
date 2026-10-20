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
async fn event_all_day_date_only_normalized() {
    // 测什么：全天日程传日期-only 的 startsAt 时，响应中的 starts_at 应规范化为 19 位完整时间戳。
    // 为什么：字典序比较依赖固定的 19 位格式，若不补齐 T00:00:00，排序与区间过滤都会出错。
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({ "title": "allday", "startsAt": "2026-10-25", "allDay": true })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["startsAt"], json!("2026-10-25T00:00:00"));
    assert_eq!(body["allDay"], json!(true));
}

#[tokio::test]
async fn event_done_toggle_and_cross_user() {
    // 测什么：done 标记可通过 PUT 切换为 true；第二个用户对该日程的 PUT 与 GET 列表均按隔离处理。
    // 为什么：done 是日程核心状态；用户隔离同样适用于日程，跨用户读写必须表现为不可见。
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({ "title": "meeting", "startsAt": "2026-10-25T10:00" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id = body["id"].as_i64().expect("event id should be a number");

    let (status, body) = req(
        &app,
        "PUT",
        &format!("/api/events/{}", id),
        Some(json!({ "done": true })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["done"], json!(true));

    let (status, _body, cookie2) = register(&app, "tester2", "password123").await;
    assert_eq!(status, StatusCode::CREATED);

    let (status, _body) = req(
        &app,
        "PUT",
        &format!("/api/events/{}", id),
        Some(json!({ "done": true })),
        &cookie2,
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, body) = req(&app, "GET", "/api/events", None, &cookie2).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().map(|a| a.len()), Some(0));
}