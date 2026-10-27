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

async fn create_file(
    app: Router,
    name: &str,
    content: &str,
    parent_id: Option<i64>,
    cookie: &str,
) -> i64 {
    let body = json!({"name": name, "kind": "file", "content": content, "parentId": parent_id});
    let (status, v) = req(app, "POST", "/api/fs", Some(body), cookie).await;
    assert_eq!(status, StatusCode::CREATED);
    v["id"].as_i64().unwrap()
}

#[tokio::test]
async fn fs_list_parent_id_abc_400() {
    let (app, cookie) = test_app().await;
    let (status, v) = req(app, "GET", "/api/fs?parent_id=abc", None, cookie.as_str()).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(v["error"], "parent_id 参数非法");
}

#[tokio::test]
async fn fs_list_parent_id_float_400() {
    let (app, cookie) = test_app().await;
    let (status, v) = req(app, "GET", "/api/fs?parent_id=1.5", None, cookie.as_str()).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(v["error"], "parent_id 参数非法");
}

#[tokio::test]
async fn fs_list_parent_id_negative_400() {
    let (app, cookie) = test_app().await;
    let (status, v) = req(app, "GET", "/api/fs?parent_id=-1", None, cookie.as_str()).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(v["error"], "parent_id 参数非法");
}

#[tokio::test]
async fn fs_list_parent_id_empty_400() {
    let (app, cookie) = test_app().await;
    let (status, v) = req(app, "GET", "/api/fs?parent_id=", None, cookie.as_str()).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(v["error"], "parent_id 参数非法");
}

#[tokio::test]
async fn fs_list_parent_id_missing_200_empty() {
    let (app, cookie) = test_app().await;
    let (status, v) = req(
        app,
        "GET",
        "/api/fs?parent_id=999999",
        None,
        cookie.as_str(),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(v.as_array().unwrap().is_empty());
}

#[tokio::test]
async fn fs_list_parent_id_valid_folder() {
    let (app, cookie) = test_app().await;
    let folder_p = create_folder(app.clone(), "folder_p", None, &cookie).await;
    create_file(app.clone(), "inner.txt", "content", Some(folder_p), &cookie).await;

    let (status, v) = req(
        app.clone(),
        "GET",
        &format!("/api/fs?parent_id={}", folder_p),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(v
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["name"] == "inner.txt"));

    let (status, v) = req(app, "GET", "/api/fs", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert!(v
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["name"] == "folder_p"));
}
