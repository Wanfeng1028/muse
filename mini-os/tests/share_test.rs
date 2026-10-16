use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

async fn raw_request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<&str>,
) -> axum::response::Response {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let req = match body {
        Some(v) => {
            builder = builder.header("content-type", "application/json");
            builder.body(axum::body::Body::from(v.to_string())).unwrap()
        }
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    app.oneshot(req).await.unwrap()
}

async fn authed_app(username: &str) -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "register failed for {}",
        username
    );
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("no set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    let cookie = set_cookie.split(';').next().unwrap().to_string();
    assert!(
        cookie.starts_with("mini_os_session="),
        "bad cookie: {}",
        cookie
    );
    (app, cookie)
}

async fn register_second(app: &Router, username: &str) -> String {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("no set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

async fn create_file(app: &Router, cookie: &str, name: &str, content: &str) -> i64 {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": name, "kind": "file", "content": content})),
        Some(cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "create_file failed for {}",
        name
    );
    let v = body_json(resp).await;
    v["id"].as_i64().expect("no id in create_file response")
}

async fn create_folder(app: &Router, cookie: &str, name: &str) -> i64 {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": name, "kind": "folder"})),
        Some(cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "create_folder failed for {}",
        name
    );
    let v = body_json(resp).await;
    v["id"].as_i64().expect("no id in create_folder response")
}

#[tokio::test]
async fn share_file_flow() {
    let (app, alice) = authed_app("alice").await;
    let node_id = create_file(&app, &alice, "shared.txt", "hello share").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": node_id})),
        Some(&alice),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = body_json(resp).await;
    let token = body["token"].as_str().expect("no token").to_string();
    assert_eq!(
        token.len(),
        32,
        "token should be 32 hex chars, got {}",
        token
    );
    let url = body["url"].as_str().expect("no url").to_string();
    assert!(
        url.starts_with("/share.html?token="),
        "url should start with /share.html?token=, got {}",
        url
    );

    let resp = raw_request(app.clone(), "GET", &format!("/api/s/{}", token), None, None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let info = body_json(resp).await;
    assert_eq!(info["name"].as_str(), Some("shared.txt"));

    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/s/{}/download", token),
        None,
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.as_ref(), b"hello share");

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "anon.txt", "kind": "file", "content": "x"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn share_folder_rejected() {
    let (app, alice) = authed_app("alice").await;
    let folder_id = create_folder(&app, &alice, "folder1").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": folder_id})),
        Some(&alice),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn share_nonexistent_node_404() {
    let (app, alice) = authed_app("alice").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": 999999})),
        Some(&alice),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn share_token_not_found_404() {
    let (app, _alice) = authed_app("alice").await;

    let resp = raw_request(
        app.clone(),
        "GET",
        "/api/s/00000000000000000000000000000000",
        None,
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn share_of_other_user_node_404() {
    let (app, alice) = authed_app("alice").await;
    let bob = register_second(&app, "bob").await;
    let node_id = create_file(&app, &alice, "alice_secret.txt", "secret").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": node_id})),
        Some(&bob),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn share_gone_after_node_deleted() {
    let (app, alice) = authed_app("alice").await;
    let node_id = create_file(&app, &alice, "temp.txt", "temp content").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": node_id})),
        Some(&alice),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = body_json(resp).await;
    let token = body["token"].as_str().expect("no token").to_string();

    let resp = raw_request(app.clone(), "GET", &format!("/api/s/{}", token), None, None).await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(
        app.clone(),
        "DELETE",
        &format!("/api/fs/{}", node_id),
        None,
        Some(&alice),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    let resp = raw_request(app.clone(), "GET", &format!("/api/s/{}", token), None, None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}
