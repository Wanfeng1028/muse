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
async fn move_name_conflict_409() {
    // 测什么：目标目录已存在同名文件时，移动请求必须返回 409，且源文件仍留在原目录。
    // 为什么：若不做同名检查，移动会静默覆盖用户文件，导致数据丢失。
    let (app, cookie) = test_app().await;

    let (s1, dir1) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "dir1", "kind": "folder"})),
        &cookie,
    )
    .await;
    assert_eq!(s1, StatusCode::CREATED);
    let dir1_id = dir1["id"].as_i64().unwrap();

    let (s2, dir2) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "dir2", "kind": "folder"})),
        &cookie,
    )
    .await;
    assert_eq!(s2, StatusCode::CREATED);
    let dir2_id = dir2["id"].as_i64().unwrap();

    let (s3, f1) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "same.txt", "kind": "file", "parentId": dir1_id})),
        &cookie,
    )
    .await;
    assert_eq!(s3, StatusCode::CREATED);
    assert_eq!(f1["parentId"].as_i64().unwrap(), dir1_id);
    let f1_id = f1["id"].as_i64().unwrap();

    let (s4, f2) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "same.txt", "kind": "file", "parentId": dir2_id})),
        &cookie,
    )
    .await;
    assert_eq!(s4, StatusCode::CREATED);
    assert_eq!(f2["parentId"].as_i64().unwrap(), dir2_id);

    let (sm, body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", f1_id),
        Some(json!({"parent_id": dir2_id})),
        &cookie,
    )
    .await;
    assert_eq!(sm, StatusCode::CONFLICT);
    let err = body["error"].as_str().unwrap_or("");
    assert!(err.contains("同名文件已存在"), "unexpected error: {}", err);

    let (sg, got) = req(&app, "GET", &format!("/api/fs/{}", f1_id), None, &cookie).await;
    assert_eq!(sg, StatusCode::OK);
    assert_eq!(got["parentId"].as_i64().unwrap(), dir1_id);
}

#[tokio::test]
async fn move_idempotent_same_parent() {
    // 测什么：把文件移动到自己当前所在的目录应幂等成功返回 200。
    // 为什么：前端拖拽可能产生原地移动请求，必须成功而非报错。
    let (app, cookie) = test_app().await;

    let (s1, dir1) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "dir1", "kind": "folder"})),
        &cookie,
    )
    .await;
    assert_eq!(s1, StatusCode::CREATED);
    let dir1_id = dir1["id"].as_i64().unwrap();

    let (s2, f) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "k.txt", "kind": "file", "parentId": dir1_id})),
        &cookie,
    )
    .await;
    assert_eq!(s2, StatusCode::CREATED);
    assert_eq!(f["parentId"].as_i64().unwrap(), dir1_id);
    let f_id = f["id"].as_i64().unwrap();

    let (sm, body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", f_id),
        Some(json!({"parent_id": dir1_id})),
        &cookie,
    )
    .await;
    assert_eq!(sm, StatusCode::OK);
    assert_eq!(body["parentId"].as_i64().unwrap(), dir1_id);
    assert_eq!(body["id"].as_i64().unwrap(), f_id);
}
