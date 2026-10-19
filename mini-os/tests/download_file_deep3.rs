use axum::body::{to_bytes, Body};
use axum::http::{header, Request, StatusCode};
use serde_json::Value;
use std::sync::Arc;
use tower::ServiceExt;

use mini_os::{build_app, init_state, init_state_with, AppState};

async fn register(app: &axum::Router, username: &str) -> String {
    let body = serde_json::json!({
        "username": username,
        "password": "password123",
    })
    .to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();
    assert!(cookie.starts_with("mini_os_session="));
    cookie
}

async fn read_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

async fn post_fs(app: &axum::Router, cookie: &str, payload: &Value) -> axum::response::Response {
    let req = Request::builder()
        .method("POST")
        .uri("/api/fs")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::COOKIE, cookie)
        .body(Body::from(payload.to_string()))
        .unwrap();
    app.clone().oneshot(req).await.unwrap()
}

async fn download(app: &axum::Router, cookie: &str, uri: &str) -> axum::response::Response {
    let req = Request::builder()
        .method("GET")
        .uri(uri)
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .unwrap();
    app.clone().oneshot(req).await.unwrap()
}

#[tokio::test]
async fn download_missing_path_400() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_missing_path").await;

    let resp = download(&app, &cookie, "/api/files/download").await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let json = read_json(resp).await;
    assert!(
        json["error"].as_str().unwrap().contains("缺少 path 参数"),
        "unexpected error body: {}",
        json
    );

    let resp2 = download(&app, &cookie, "/api/files/download?path=%20%20").await;
    assert_eq!(resp2.status(), StatusCode::BAD_REQUEST);
    let json2 = read_json(resp2).await;
    assert!(
        json2["error"].as_str().unwrap().contains("缺少 path 参数"),
        "unexpected error body: {}",
        json2
    );
}

#[tokio::test]
async fn download_nonexistent_404() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_nonexistent").await;

    let resp = download(&app, &cookie, "/api/files/download?path=/nope.txt").await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let json = read_json(resp).await;
    assert!(
        json["error"].as_str().unwrap().contains("文件不存在"),
        "unexpected error body: {}",
        json
    );
}

#[tokio::test]
async fn download_text_file_bytes_and_headers() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_text_file").await;

    let create = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "a.txt",
            "content": "hello",
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/a.txt").await;
    assert_eq!(resp.status(), StatusCode::OK);

    let ct = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(ct, "text/plain");

    let cl = resp
        .headers()
        .get(header::CONTENT_LENGTH)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(cl, "5");

    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(&bytes[..], b"hello");
}

#[tokio::test]
async fn download_blob_priority_over_text_content() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_blob_priority").await;

    let payload: Vec<u8> = vec![0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0xFF];
    let create = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "x.bin",
            "bytes": payload,
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/x.bin").await;
    assert_eq!(resp.status(), StatusCode::OK);

    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.as_ref(), payload.as_slice());
}

#[tokio::test]
async fn download_uses_stored_mime() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_stored_mime").await;

    let payload: Vec<u8> = vec![0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00];
    let create = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "p.png",
            "bytes": payload,
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/p.png").await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(ct, "image/png");
}

#[tokio::test]
async fn download_octet_stream_fallback() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_octet_fallback").await;

    let create = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "x.unknownext",
            "content": "hi",
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/x.unknownext").await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(ct, "application/octet-stream");
}

#[tokio::test]
async fn download_cjk_filename_disposition() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_cjk_disp").await;

    let create = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "报告.txt",
            "content": "x",
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/报告.txt").await;
    assert_eq!(resp.status(), StatusCode::OK);
    let cd = resp
        .headers()
        .get(header::CONTENT_DISPOSITION)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(cd, "attachment; filename*=UTF-8''%E6%8A%A5%E5%91%8A.txt");
}

#[tokio::test]
async fn download_ascii_filename_disposition() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_ascii_disp").await;

    let create = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "a b.txt",
            "content": "y",
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/a%20b.txt").await;
    assert_eq!(resp.status(), StatusCode::OK);
    let cd = resp
        .headers()
        .get(header::CONTENT_DISPOSITION)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(cd, "attachment; filename*=UTF-8''a%20b.txt");
}

#[tokio::test]
async fn download_nested_path_ok() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_nested_ok").await;

    let mkdir = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "folder",
            "name": "docs",
        }),
    )
    .await;
    assert_eq!(mkdir.status(), StatusCode::CREATED);

    let mkfile = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "parent": "/docs",
            "name": "a.txt",
            "content": "deep",
        }),
    )
    .await;
    assert_eq!(mkfile.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/docs/a.txt").await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(&bytes[..], b"deep");
}

#[tokio::test]
async fn download_other_user_404() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie_a = register(&app, "u_owner").await;
    let cookie_b = register(&app, "u_intruder").await;

    let create = post_fs(
        &app,
        &cookie_a,
        &serde_json::json!({
            "action": "create",
            "kind": "file",
            "name": "secret.txt",
            "content": "top",
        }),
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie_b, "/api/files/download?path=/secret.txt").await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let json = read_json(resp).await;
    assert!(
        json["error"].as_str().unwrap().contains("文件不存在"),
        "unexpected error body: {}",
        json
    );
}

#[tokio::test]
async fn download_folder_nested_400() {
    let state: Arc<AppState> = init_state(":memory:", "static");
    let app = build_app(state);
    let cookie = register(&app, "u_folder_400").await;

    let mkdir = post_fs(
        &app,
        &cookie,
        &serde_json::json!({
            "action": "create",
            "kind": "folder",
            "name": "docs",
        }),
    )
    .await;
    assert_eq!(mkdir.status(), StatusCode::CREATED);

    let resp = download(&app, &cookie, "/api/files/download?path=/docs").await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let json = read_json(resp).await;
    assert!(
        json["error"].as_str().unwrap().contains("不能下载目录"),
        "unexpected error body: {}",
        json
    );
}
