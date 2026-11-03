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
async fn recursive_delete_removes_children() {
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "d1", "kind": "folder", "parentId": null })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id_d1 = body["id"].as_i64().expect("d1 id 应为整数");

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "sub", "kind": "folder", "parentId": id_d1 })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["parentId"].as_i64(), Some(id_d1));
    let id_sub = body["id"].as_i64().expect("sub id 应为整数");

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "f.txt", "kind": "file", "parentId": id_sub })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["parentId"].as_i64(), Some(id_sub));
    let id_f = body["id"].as_i64().expect("f id 应为整数");

    let (status, _body) = req(&app, "DELETE", &format!("/api/fs/{}", id_d1), None, &cookie).await;
    assert_eq!(status, StatusCode::NO_CONTENT);

    let (status, _body) = req(&app, "GET", &format!("/api/fs/{}", id_sub), None, &cookie).await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, _body) = req(&app, "GET", &format!("/api/fs/{}", id_f), None, &cookie).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn move_across_dirs() {
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "dir1", "kind": "folder", "parentId": null })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let dir1 = body["id"].as_i64().expect("dir1 id 应为整数");

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "dir2", "kind": "folder", "parentId": null })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let dir2 = body["id"].as_i64().expect("dir2 id 应为整数");

    let (status, body) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "m.txt", "kind": "file", "parentId": null })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    let id = body["id"].as_i64().expect("m.txt id 应为整数");

    let (status, body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", id),
        Some(json!({ "parent_id": dir1 })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["id"].as_i64(), Some(id));
    assert_eq!(body["parentId"].as_i64(), Some(dir1));

    let (status, body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", id),
        Some(json!({ "parent_id": dir2 })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["id"].as_i64(), Some(id));
    assert_eq!(body["parentId"].as_i64(), Some(dir2));
}
