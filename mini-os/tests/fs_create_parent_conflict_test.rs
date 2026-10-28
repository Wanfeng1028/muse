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

async fn create_folder(app: Router, name: &str, parent_id: Option<i64>, cookie: &str) -> i64 {
    let body = json!({"name": name, "kind": "folder", "parentId": parent_id});
    let (status, v) = req(app, "POST", "/api/fs", Some(body), cookie).await;
    assert_eq!(status, StatusCode::CREATED);
    v["id"].as_i64().unwrap()
}

#[tokio::test]
async fn both_parent_id_and_parent_path_400() {
    let (app, cookie) = test_app().await;
    let docs_id = create_folder(app.clone(), "docs", None, &cookie).await;

    let (status, body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(serde_json::json!({
            "name": "both.txt",
            "kind": "file",
            "content": "x",
            "parentId": docs_id,
            "parent": "/docs"
        })),
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["error"], "parent_id 与 parent 不能同时指定");

    let (status, body) = req(app.clone(), "GET", "/api/fs", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert!(!body
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["name"] == "both.txt"));

    let (status, body) = req(
        app.clone(),
        "GET",
        &format!("/api/fs?parent_id={}", docs_id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(!body
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["name"] == "both.txt"));
}

#[tokio::test]
async fn both_agreeing_still_400() {
    let (app, cookie) = test_app().await;
    let docs2_id = create_folder(app.clone(), "docs2", None, &cookie).await;

    let (status, body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(serde_json::json!({
            "name": "agree.txt",
            "kind": "file",
            "content": "x",
            "parentId": docs2_id,
            "parent": "/docs2"
        })),
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["error"], "parent_id 与 parent 不能同时指定");
}

#[tokio::test]
async fn parent_id_only_201() {
    let (app, cookie) = test_app().await;
    let docs3_id = create_folder(app.clone(), "docs3", None, &cookie).await;

    let (status, _body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(serde_json::json!({
            "name": "only-id.txt",
            "kind": "file",
            "content": "x",
            "parentId": docs3_id
        })),
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::CREATED);

    let (status, body) = req(
        app.clone(),
        "GET",
        &format!("/api/fs?parent_id={}", docs3_id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["name"] == "only-id.txt"));
}

#[tokio::test]
async fn parent_path_only_201() {
    let (app, cookie) = test_app().await;
    let docs4_id = create_folder(app.clone(), "docs4", None, &cookie).await;

    let (status, _body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(serde_json::json!({
            "name": "only-path.txt",
            "kind": "file",
            "content": "x",
            "parent": "/docs4"
        })),
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::CREATED);

    let (status, body) = req(
        app.clone(),
        "GET",
        &format!("/api/fs?parent_id={}", docs4_id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(body
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["name"] == "only-path.txt"));
}

#[tokio::test]
async fn parent_id_plus_empty_parent_201() {
    let (app, cookie) = test_app().await;
    let docs5_id = create_folder(app.clone(), "docs5", None, &cookie).await;

    let (status, _body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(serde_json::json!({
            "name": "empty-parent.txt",
            "kind": "file",
            "content": "x",
            "parentId": docs5_id,
            "parent": ""
        })),
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::CREATED);
}

#[tokio::test]
async fn parent_id_null_plus_parent_path_201() {
    let (app, cookie) = test_app().await;
    let _docs6_id = create_folder(app.clone(), "docs6", None, &cookie).await;

    let (status, _body) = req(
        app.clone(),
        "POST",
        "/api/fs",
        Some(serde_json::json!({
            "name": "null-id.txt",
            "kind": "file",
            "content": "x",
            "parentId": null,
            "parent": "/docs6"
        })),
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::CREATED);
}
