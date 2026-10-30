use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let body = json!({"username": "tester", "password": "password123"});
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::to_string(&body).unwrap(),
        ))
        .unwrap();
    let res = app.clone().oneshot(req).await.unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);
    let cookie = res
        .headers()
        .get("set-cookie")
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();
    (app, cookie)
}

async fn req(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: &str,
) -> (StatusCode, Value) {
    let builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("cookie", cookie);
    let request = match body {
        Some(body_val) => builder
            .header("content-type", "application/json")
            .body(axum::body::Body::from(
                serde_json::to_string(&body_val).unwrap(),
            ))
            .unwrap(),
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    let res = app.oneshot(request).await.unwrap();
    let status = res.status();
    let bytes = to_bytes(res.into_body(), usize::MAX).await.unwrap();
    let v = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    };
    (status, v)
}

#[tokio::test]
async fn both_bytes_and_content_400() {
    let (app, cookie) = test_app().await;
    let (status, body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({
            "name": "both.txt",
            "kind": "file",
            "content": "hello",
            "bytes": [104, 105],
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["error"], "bytes 与 content 不能同时指定");

    let (status, body) = req(app, "GET", "/api/fs", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let list = body.as_array().unwrap();
    assert!(list.iter().all(|item| item["name"] != "both.txt"));
}

#[tokio::test]
async fn bytes_only_201() {
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        app,
        "POST",
        "/api/fs",
        Some(json!({
            "name": "bytes-only.bin",
            "kind": "file",
            "bytes": [1, 2, 3],
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn content_only_201() {
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        app,
        "POST",
        "/api/fs",
        Some(json!({
            "name": "content-only.txt",
            "kind": "file",
            "content": "hello",
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn empty_content_plus_bytes_201() {
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        app,
        "POST",
        "/api/fs",
        Some(json!({
            "name": "empty-content.bin",
            "kind": "file",
            "content": "",
            "bytes": [9],
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn whitespace_content_plus_bytes_201() {
    let (app, cookie) = test_app().await;
    let (status, _body) = req(
        app,
        "POST",
        "/api/fs",
        Some(json!({
            "name": "ws-content.bin",
            "kind": "file",
            "content": "   ",
            "bytes": [9],
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn empty_bytes_plus_content_400() {
    let (app, cookie) = test_app().await;
    let (status, body) = req(
        app,
        "POST",
        "/api/fs",
        Some(json!({
            "name": "empty-bytes.txt",
            "kind": "file",
            "content": "hello",
            "bytes": [],
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["error"], "bytes 与 content 不能同时指定");
}
