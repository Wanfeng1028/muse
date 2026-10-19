use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let (status, body, cookie) = register(&app, "tester", "password123").await;
    assert_eq!(status, StatusCode::CREATED);
    let _ = body;
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

// 便签完整增删改查：创建、查询、更新置顶、删除后列表为空。
#[tokio::test]
async fn note_crud() {
    let (app, cookie) = test_app().await;

    let (status, created) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "买菜", "body": "牛奶鸡蛋" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(created["title"], "买菜");
    assert_eq!(created["body"], "牛奶鸡蛋");
    assert_eq!(created["pinned"], false);
    assert!(created["id"].is_number());
    assert!(created["userId"].is_number());

    let note_id_num = created["id"].as_i64().unwrap();
    let note_id = note_id_num.to_string();

    let (status, list) = req(&app, "GET", "/api/notes", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["title"], "买菜");

    let (status, updated) = req(
        &app,
        "PUT",
        &format!("/api/notes/{}", note_id),
        Some(json!({ "title": "买菜改", "body": "只买牛奶", "pinned": true })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(updated["title"], "买菜改");
    assert_eq!(updated["body"], "只买牛奶");
    assert_eq!(updated["pinned"], true);

    let (status, list) = req(&app, "GET", "/api/notes", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["id"].as_i64().unwrap(), note_id_num);
    assert_eq!(arr[0]["pinned"], true);

    let (status, _) = req(
        &app,
        "DELETE",
        &format!("/api/notes/{}", note_id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::NO_CONTENT);

    let (status, list) = req(&app, "GET", "/api/notes", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert!(list.as_array().unwrap().is_empty());
}

// 缺省标题：空 body 创建便签应使用默认标题。
#[tokio::test]
async fn note_default_title() {
    let (app, cookie) = test_app().await;

    let (status, created) = req(&app, "POST", "/api/notes", Some(json!({})), &cookie).await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(created["title"], "未命名便签");
}

// 标题为空校验：仅空白字符的标题应被拒绝。
#[tokio::test]
async fn note_title_empty_400() {
    let (app, cookie) = test_app().await;

    let (status, _) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "  " })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

// 跨用户隔离：无法操作他人便签，且看不到他人列表。
#[tokio::test]
async fn note_cross_user_404() {
    let (app, cookie) = test_app().await;

    let (status, created) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "私密", "body": "内容" })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let note_id_num = created["id"].as_i64().unwrap();
    let note_id = note_id_num.to_string();

    let (status, _, _) = register(&app, "user2", "password123").await;
    assert_eq!(status, StatusCode::CREATED);
    let (status, _body, cookie2) = register(&app, "user2", "password123").await;
    assert_eq!(status, StatusCode::CONFLICT);
    let _ = cookie2;
    let (_, _, cookie2) = login(&app, "user2", "password123").await;

    let (status, _) = req(
        &app,
        "PUT",
        &format!("/api/notes/{}", note_id),
        Some(json!({ "title": "篡改" })),
        &cookie2,
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, _) = req(
        &app,
        "DELETE",
        &format!("/api/notes/{}", note_id),
        None,
        &cookie2,
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, list) = req(&app, "GET", "/api/notes", None, &cookie2).await;
    assert_eq!(status, StatusCode::OK);
    assert!(list.as_array().unwrap().is_empty());
}

async fn login(app: &Router, username: &str, password: &str) -> (StatusCode, Value, String) {
    let payload = json!({ "username": username, "password": password });
    let request = Request::builder()
        .method("POST")
        .uri("/api/auth/login")
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

// viewer 只读：viewer 角色可读列表但禁止创建便签。
#[tokio::test]
async fn note_viewer_read_only() {
    let (app, admin_cookie) = test_app().await;

    let (status, _, _) = register(&app, "user2", "password123").await;
    assert_eq!(status, StatusCode::CREATED);
    let (_, _, cookie2) = login(&app, "user2", "password123").await;

    let (status, me) = req(&app, "GET", "/api/me", None, &cookie2).await;
    assert_eq!(status, StatusCode::OK);
    let user2_id = me["id"].as_i64().unwrap().to_string();

    let (status, _) = req(
        &app,
        "PUT",
        &format!("/api/users/{}/role", user2_id),
        Some(json!({ "role": "viewer" })),
        &admin_cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    let (status, _, cookie2_new) = login(&app, "user2", "password123").await;
    assert_eq!(status, StatusCode::OK);

    let (status, _) = req(
        &app,
        "POST",
        "/api/notes",
        Some(json!({ "title": "viewer 尝试", "body": "x" })),
        &cookie2_new,
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);

    let (status, _) = req(&app, "GET", "/api/notes", None, &cookie2_new).await;
    assert_eq!(status, StatusCode::OK);
}

// 日程完整增删改查：创建、范围命中、完成标记、删除。
#[tokio::test]
async fn event_crud() {
    let (app, cookie) = test_app().await;

    let (status, created) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "晨会",
            "startsAt": "2026-10-21T09:00",
            "endsAt": "2026-10-21T10:00",
            "allDay": false
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(created["title"], "晨会");
    assert_eq!(created["allDay"], false);
    assert_eq!(created["done"], false);
    assert!(created["id"].is_number());
    assert!(created["userId"].is_number());
    assert!(created["startsAt"].is_string());
    assert!(created["endsAt"].is_string());

    let event_id_num = created["id"].as_i64().unwrap();
    let event_id = event_id_num.to_string();

    let (status, list) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-21T00:00:00&to=2026-10-22T00:00:00",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["id"].as_i64().unwrap(), event_id_num);

    let (status, updated) = req(
        &app,
        "PUT",
        &format!("/api/events/{}", event_id),
        Some(json!({
            "title": "晨会",
            "startsAt": "2026-10-21T09:00",
            "endsAt": "2026-10-21T10:00",
            "allDay": false,
            "done": true
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(updated["done"], true);

    let (status, _) = req(
        &app,
        "DELETE",
        &format!("/api/events/{}", event_id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::NO_CONTENT);
}

// 日程校验：非法 startsAt、endsAt 早于 startsAt、空标题均返回 400。
#[tokio::test]
async fn event_validation() {
    let (app, cookie) = test_app().await;

    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "非法时间",
            "startsAt": "明天",
            "endsAt": "2026-10-21T10:00",
            "allDay": false
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "时间倒挂",
            "startsAt": "2026-10-21T10:00",
            "endsAt": "2026-10-21T09:00",
            "allDay": false
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let (status, _) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "   ",
            "startsAt": "2026-10-21T09:00",
            "endsAt": "2026-10-21T10:00",
            "allDay": false
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

// 日程范围过滤：左闭右开区间，命中且按 startsAt 升序。
#[tokio::test]
async fn event_range_filter() {
    let (app, cookie) = test_app().await;

    for (title, start, end) in [
        ("事件A", "2026-10-21T09:00", "2026-10-21T10:00"),
        ("事件B", "2026-10-22T09:00", "2026-10-22T10:00"),
        ("事件C", "2026-10-23T09:00", "2026-10-23T10:00"),
    ] {
        let (status, _) = req(
            &app,
            "POST",
            "/api/events",
            Some(json!({
                "title": title,
                "startsAt": start,
                "endsAt": end,
                "allDay": false
            })),
            &cookie,
        )
        .await;
        assert_eq!(status, StatusCode::CREATED);
    }

    let (status, list) = req(
        &app,
        "GET",
        "/api/events?from=2026-10-22T00:00:00&to=2026-10-23T00:00:00",
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["title"], "事件B");

    let (status, all) = req(&app, "GET", "/api/events", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = all.as_array().unwrap();
    assert_eq!(arr.len(), 3);
    let mut prev = String::new();
    for item in arr {
        let cur = item["startsAt"].as_str().unwrap_or("").to_string();
        assert!(cur >= prev);
        prev = cur;
    }
}

// 跨用户隔离：user2 无法修改 tester 的事件。
#[tokio::test]
async fn event_cross_user_404() {
    let (app, cookie) = test_app().await;

    let (status, created) = req(
        &app,
        "POST",
        "/api/events",
        Some(json!({
            "title": "tester 事件",
            "startsAt": "2026-10-21T09:00",
            "endsAt": "2026-10-21T10:00",
            "allDay": false
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let event_id_num = created["id"].as_i64().unwrap();
    let event_id = event_id_num.to_string();

    let (status, _, _) = register(&app, "user2", "password123").await;
    assert_eq!(status, StatusCode::CREATED);
    let (_, _, cookie2) = login(&app, "user2", "password123").await;

    let (status, _) = req(
        &app,
        "PUT",
        &format!("/api/events/{}", event_id),
        Some(json!({
            "title": "篡改",
            "startsAt": "2026-10-21T09:00",
            "endsAt": "2026-10-21T10:00",
            "allDay": false,
            "done": true
        })),
        &cookie2,
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}
