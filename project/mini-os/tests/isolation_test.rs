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

/// 注册用户并返回 (app, cookie)。cookie 为 "mini_os_session=<token>"（去掉属性部分）。
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
        StatusCode::CREATED,
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

/// 同一 DB 内注册第二个用户（隔离测试用）
async fn register_second(app: &Router, username: &str) -> String {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("no set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

fn multipart_body(boundary: &str, filename: &str, content: &[u8]) -> Vec<u8> {
    let mut b = Vec::new();
    b.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    b.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            filename
        )
        .as_bytes(),
    );
    b.extend_from_slice(b"Content-Type: text/plain\r\n\r\n");
    b.extend_from_slice(content);
    b.extend_from_slice(format!("\r\n--{}--\r\n", boundary).as_bytes());
    b
}

async fn raw_request_bytes(
    app: Router,
    method: &str,
    uri: &str,
    content_type: &str,
    body: Vec<u8>,
    cookie: Option<&str>,
) -> axum::response::Response {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    builder = builder.header("content-type", content_type);
    let req = builder.body(axum::body::Body::from(body)).unwrap();
    app.oneshot(req).await.unwrap()
}

#[tokio::test]
async fn file_isolation() {
    let (app, alice_cookie) = authed_app("alice").await;
    let bob_cookie = register_second(&app, "bob").await;

    // alice 建文件夹 docs
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "docs", "kind": "folder"})),
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let docs = body_json(resp).await;
    let docs_id = docs["id"].as_i64().expect("docs id");

    // alice 在 docs 下建文件 a.txt
    let resp = raw_request(app.clone(), "POST", "/api/fs",
        Some(json!({"name": "a.txt", "kind": "file", "parentId": docs_id, "content": "alice secret"})),
        Some(&alice_cookie)).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let a = body_json(resp).await;
    let a_id = a["id"].as_i64().expect("a.txt id");

    // alice GET /api/fs/{id} → 200
    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/fs/{}", a_id),
        None,
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let got = body_json(resp).await;
    assert_eq!(got["name"].as_str(), Some("a.txt"));

    // bob GET 同 id → 404
    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/fs/{}", a_id),
        None,
        Some(&bob_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // bob GET /api/fs 根 → 空数组（种子数据属 legacy）
    let resp = raw_request(app.clone(), "GET", "/api/fs", None, Some(&bob_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let listing = body_json(resp).await;
    let arr = listing.as_array().expect("root listing array");
    assert!(
        arr.is_empty(),
        "bob root should be empty, got {:?}",
        listing
    );
}

#[tokio::test]
async fn settings_isolation() {
    let (app, alice_cookie) = authed_app("alice").await;
    let bob_cookie = register_second(&app, "bob").await;

    let resp = raw_request(
        app.clone(),
        "PUT",
        "/api/settings",
        Some(json!({"key": "theme", "value": "dark"})),
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(
        app.clone(),
        "GET",
        "/api/settings",
        None,
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let alice_settings = body_json(resp).await;
    assert_eq!(alice_settings["theme"].as_str(), Some("dark"));

    let resp = raw_request(app.clone(), "GET", "/api/settings", None, Some(&bob_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bob_settings = body_json(resp).await;
    assert!(
        bob_settings.get("theme").is_none(),
        "bob should not see alice theme, got {:?}",
        bob_settings
    );
}

#[tokio::test]
async fn upload_download_isolation() {
    let (app, alice_cookie) = authed_app("alice").await;
    let bob_cookie = register_second(&app, "bob").await;

    let boundary = "----miniostestboundary1234";
    let body = multipart_body(boundary, "secret.txt", b"alice secret content");
    let ct = format!("multipart/form-data; boundary={}", boundary);

    let resp = raw_request_bytes(
        app.clone(),
        "POST",
        "/api/files/upload",
        &ct,
        body,
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "alice upload should succeed"
    );

    // alice 可下载
    let resp = raw_request(
        app.clone(),
        "GET",
        "/api/files/download?path=/secret.txt",
        None,
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);

    // bob 下载同路径 → 404
    let resp = raw_request(
        app.clone(),
        "GET",
        "/api/files/download?path=/secret.txt",
        None,
        Some(&bob_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn stats_isolation() {
    let (app, alice_cookie) = authed_app("alice").await;
    let bob_cookie = register_second(&app, "bob").await;

    // alice 建 2 个文件
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "f1.txt", "kind": "file", "content": "one"})),
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "f2.txt", "kind": "file", "content": "two"})),
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = raw_request(app.clone(), "GET", "/api/stats", None, Some(&alice_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let alice_stats = body_json(resp).await;
    assert_eq!(
        alice_stats["files"].as_i64(),
        Some(2),
        "alice files should be 2, got {:?}",
        alice_stats
    );

    let resp = raw_request(app.clone(), "GET", "/api/stats", None, Some(&bob_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bob_stats = body_json(resp).await;
    assert_eq!(
        bob_stats["files"].as_i64(),
        Some(0),
        "bob files should be 0, got {:?}",
        bob_stats
    );
}

#[tokio::test]
async fn cross_user_parent_rejected() {
    let (app, alice_cookie) = authed_app("alice").await;
    let bob_cookie = register_second(&app, "bob").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "alice_dir", "kind": "folder"})),
        Some(&alice_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let dir = body_json(resp).await;
    let dir_id = dir["id"].as_i64().expect("dir id");

    // bob 用 alice 的父节点 → 404
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "bob_inside", "kind": "folder", "parentId": dir_id})),
        Some(&bob_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}
