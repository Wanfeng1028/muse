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
async fn event_calendar_feb30_rejected() {
    // 测什么：测试2026年2月30日这个不存在的日期
    // 为什么：验证日历范围校验能够正确拒绝无效的日期格式并返回400状态码
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-02-30T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_feb29_non_leap_rejected() {
    // 测什么：测试2025年2月29日这个不存在的日期
    // 为什么：验证日历范围校验能够正确识别平年并拒绝2月29日的请求
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2025-02-29T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_feb29_leap_accepted() {
    // 测什么：测试2024年2月29日这个存在的闰年日期
    // 为什么：验证日历范围校验能够正确接受闰年的2月29日并返回201状态码及正确格式化的时间
    let (app, cookie) = test_app().await;
    let (status, body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2024-02-29T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["startsAt"], json!("2024-02-29T10:00:00"));
}

#[tokio::test]
async fn event_calendar_feb29_century400_accepted() {
    // 测什么：测试2000年2月29日这个世纪闰年日期
    // 为什么：验证日历范围校验能够正确处理世纪闰年规则并接受2000年2月29日的请求
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2000-02-29T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn event_calendar_feb29_century100_rejected() {
    // 测什么：测试1900年2月29日这个不存在的日期
    // 为什么：验证日历范围校验能够正确处理世纪非闰年规则并拒绝1900年2月29日的请求
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "1900-02-29T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_month13_rejected() {
    // 测什么：测试2026年13月01日这个不存在的月份
    // 为什么：验证日历范围校验能够正确拒绝月份超出1-12范围的请求并返回400状态码
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-13-01T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_month00_rejected() {
    // 测什么：测试2026年00月10日这个不存在的月份
    // 为什么：验证日历范围校验能够正确拒绝月份为0的边界值并返回400状态码
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-00-10T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_apr31_rejected() {
    // 测什么：校验 startsAt 的 4月31日非法日期是否被拒绝
    // 为什么：验证日历范围真实校验，防止逻辑日历回退
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-04-31T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_day00_rejected() {
    // 测什么：校验 startsAt 的 0日非法日期是否被拒绝
    // 为什么：验证日期下界校验，拒绝不可能的日历日
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-01-00T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_hour24_rejected() {
    // 测什么：校验 startsAt 的 24:00 非法时刻是否被拒绝
    // 为什么：验证时刻上界校验，24:00 超出 23:59:59
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-10-25T24:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_minute60_rejected() {
    // 测什么：校验 startsAt 的 60分非法时刻是否被拒绝
    // 为什么：验证分钟范围校验，拒绝 60 分
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-10-25T10:60"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_second60_rejected() {
    // 测什么：校验 startsAt 的 60秒非法时刻是否被拒绝
    // 为什么：验证秒数范围校验，拒绝 60 秒
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-10-25T10:00:60"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_calendar_boundary_accepted() {
    // 测什么：校验合法边界时间 2026-12-31T23:59:59 与 2026-01-01 是否接受
    // 为什么：确认边界不误判，且支持纯日期格式
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-12-31T23:59:59"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-01-01"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn event_calendar_range_query_invalid_from() {
    // 测什么：GET 范围查询 from 非法日期是否返回 400
    // 为什么：确认查询参数同样经真实日历校验
    let (app, cookie) = test_app().await;
    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({"title": "t", "startsAt": "2026-10-25T10:00"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let (status, _) = req(
        &app,
        "GET",
        "/api/events?from=2026-02-30&to=2026-03-01",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}
