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
async fn event_ends_equal_starts_allowed() {
    // 测什么：POST /api/events 在 endsAt 与 startsAt 完全相等时应返回 201。
    // 为什么：校验规则是 ends < starts 才拒，相等是合法的零时长边界（提醒点场景），必须放行。
    let (app, cookie) = test_app().await;
    let (status, body) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "t1",
            "startsAt": "2026-10-25T10:00",
            "endsAt": "2026-10-25T10:00"
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["title"], json!("t1"));
    assert_eq!(body["startsAt"], json!("2026-10-25T10:00:00"));
    assert_eq!(body["endsAt"], json!("2026-10-25T10:00:00"));
}

#[tokio::test]
async fn event_ends_before_starts_rejected() {
    // 测什么：创建时 endsAt 早于 startsAt 返回 400；更新时把 startsAt 改到 endsAt 之后同样返回 400。
    // 为什么：创建与更新两条路径都必须用合并后的 starts/ends 做一致性校验，更新漏校验是常见漏洞。
    let (app, cookie) = test_app().await;

    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "t2",
            "startsAt": "2026-10-25T12:00",
            "endsAt": "2026-10-25T10:00"
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let (status, created) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "ok",
            "startsAt": "2026-10-25T10:00",
            "endsAt": "2026-10-25T12:00"
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id = created["id"].as_i64().expect("event id");

    let (status, _) = req(
        &app,
        "PUT",
        &format!("/api/events/{}", id),
        Some(json!({ "startsAt": "2026-10-25T13:00" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn event_dt_format_matrix() {
    // 测什么：startsAt 三种合法长度（10/16/19）应 201，三种非法格式应 400。
    // 为什么：时间解析是脏数据入口，格式矩阵锁死后才能保证下游查询语义稳定。
    let (app, cookie) = test_app().await;

    let valid = [
        "2026-10-20",
        "2026-10-20T14:30",
        "2026-10-20T14:30:00",
    ];
    for v in valid.iter() {
        let (status, _) = req(
            &app,
            "POST",
            "/api/events",
            Some(json!({ "title": "fmt", "startsAt": v })),
            &cookie,
        )
        .await;
        assert_eq!(status, StatusCode::CREATED, "expected 201 for {}", v);
    }

    let invalid = [
        "2026/10/20",
        "2026-10-20T14",
        "2026-10-20 14:30",
    ];
    for v in invalid.iter() {
        let (status, _) = req(
            &app,
            "POST",
            "/api/events",
            Some(json!({ "title": "fmt", "startsAt": v })),
            &cookie,
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST, "expected 400 for {}", v);
    }
}

#[tokio::test]
async fn event_range_boundary_inclusive_exclusive() {
    // 测什么：GET /api/events?from=&to= 中 from 为闭区间、to 为开区间。
    // 为什么：区间开闭是日历查询最容易出错的地方，必须锁死语义：包含 from 起点，排除 to 端点。
    let (app, cookie) = test_app().await;

    let (status, e1) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({ "title": "e1", "startsAt": "2026-10-25T10:00" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);

    let (status, e2) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({ "title": "e2", "startsAt": "2026-10-25T12:00" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);

    let (status, list) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-25T10:00&to=2026-10-25T12:00",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    let arr = list.as_array().expect("events array");
    let titles: Vec<&str> = arr
        .iter()
        .filter_map(|v| v.get("title").and_then(|t| t.as_str()))
        .collect();
    assert!(titles.contains(&"e1"), "from boundary must be inclusive");
    assert!(!titles.contains(&"e2"), "to boundary must be exclusive");
    assert_eq!(e1["title"], json!("e1"));
    assert_eq!(e2["title"], json!("e2"));
}