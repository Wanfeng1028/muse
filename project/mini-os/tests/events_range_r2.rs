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
async fn events_range_reversed_returns_400() {
    // 测什么: 测试 from 大于 to 时返回 400 及错误信息。
    // 为什么: 验证区间校验逻辑在规范化后能捕获反向时间范围。
    let (app, cookie) = test_app().await;
    // 创建一个日程
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "TestEvent",
            "startsAt": "2026-10-25T10:00"
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    // 查询反向区间
    let (status, body) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-25T12:00&to=2026-10-25T10:00",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let body_str = serde_json::to_string(&body).unwrap();
    assert!(body_str.contains("开始时间不能晚于结束时间"));
}

#[tokio::test]
async fn events_range_equal_returns_empty_200() {
    // 测什么: 测试 from 等于 to 时返回 200 空数组（开区间 semantics）。
    // 为什么: 确保等值区间不会误判为包含事件。
    let (app, cookie) = test_app().await;
    let (status, body) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-25T10:00&to=2026-10-25T10:00",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.is_array());
    let arr = body.as_array().unwrap();
    assert!(arr.is_empty());
}

#[tokio::test]
async fn events_range_date_only_reversed_returns_400() {
    // 测什么: 测试日期部分反转时返回 400。
    // 为什么: 验证日期简写经规范化后仍能正确捕获反转。
    let (app, cookie) = test_app().await;
    let (status, body) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-26&to=2026-10-25",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let body_str = serde_json::to_string(&body).unwrap();
    assert!(body_str.contains("开始时间不能晚于结束时间"));
}

#[tokio::test]
async fn events_range_normal_still_works() {
    // 测什么: 测试正常区间查询能返回创建的日程。
    // 为什么: 回归验证新校验不会影响正常查询。
    let (app, cookie) = test_app().await;
    // 创建日程
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "NormalEvent",
            "startsAt": "2026-10-25T10:00"
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    // 查询正常区间
    let (status, body) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-25T09:00&to=2026-10-25T11:00",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.is_array());
    let arr = body.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    let event = &arr[0];
    assert_eq!(
        event.get("startsAt").unwrap().as_str().unwrap(),
        "2026-10-25T10:00:00"
    );
}
