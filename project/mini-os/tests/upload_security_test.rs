use axum::body::{to_bytes, Body};
use axum::http::{Request, StatusCode};
use axum::Router;
use serde_json::Value;
use tower::ServiceExt;

use mini_os::{build_app, init_state};

async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let reg = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(Body::from(
            serde_json::json!({"username": "tester", "password": "password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(reg).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let cookie = resp
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

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

fn multipart_body(boundary: &str, filename: &str, content_type: &str, data: &[u8]) -> Vec<u8> {
    let mut body: Vec<u8> = Vec::new();
    body.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    body.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            filename
        )
        .as_bytes(),
    );
    body.extend_from_slice(format!("Content-Type: {}\r\n\r\n", content_type).as_bytes());
    body.extend_from_slice(data);
    body.extend_from_slice(format!("\r\n--{}--\r\n", boundary).as_bytes());
    body
}

async fn upload_request(
    app: Router,
    uri: &str,
    filename: &str,
    content_type: &str,
    data: &[u8],
    cookie: &str,
) -> axum::response::Response {
    let boundary = "test-boundary-12345";
    let body = multipart_body(boundary, filename, content_type, data);
    let req = Request::builder()
        .method("POST")
        .uri(uri)
        .header("cookie", cookie)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .body(Body::from(body))
        .unwrap();
    app.oneshot(req).await.unwrap()
}

#[tokio::test]
async fn reject_mz_executable() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = &[0x4D, 0x5A, 0x90, 0x00, 0x03, 0x00, 0x00, 0x00];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "evil.exe",
        "application/octet-stream",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = body_json(resp).await;
    assert_eq!(body["error"], "可执行文件不允许上传");
}

#[tokio::test]
async fn reject_elf_executable() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = &[0x7F, 0x45, 0x4C, 0x46, 0x02, 0x01, 0x01, 0x00];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "evil.bin",
        "application/octet-stream",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = body_json(resp).await;
    assert_eq!(body["error"], "可执行文件不允许上传");
}

#[tokio::test]
async fn reject_macho_executable() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = &[0xFE, 0xED, 0xFA, 0xCE, 0x00, 0x00, 0x00, 0x00];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "evil.macho",
        "application/octet-stream",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = body_json(resp).await;
    assert_eq!(body["error"], "可执行文件不允许上传");
}

#[tokio::test]
async fn reject_msi_ole_storage() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = &[0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "evil.msi",
        "application/octet-stream",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = body_json(resp).await;
    assert_eq!(body["error"], "可执行文件不允许上传");
}

#[tokio::test]
async fn reject_shebang_script() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = b"#!/bin/sh\necho pwned\n";
    let resp = upload_request(
        app,
        "/api/files/upload",
        "evil.sh",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = body_json(resp).await;
    assert_eq!(body["error"], "可执行文件不允许上传");
}

#[tokio::test]
async fn reject_mz_with_lies_about_type_and_name() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = &[0x4D, 0x5A, 0x90, 0x00];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "evil.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = body_json(resp).await;
    assert_eq!(body["error"], "可执行文件不允许上传");
}

#[tokio::test]
async fn png_sniff_overrides_octet_stream_header() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = &[
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44,
        0x52,
    ];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "pic.bin",
        "application/octet-stream",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = body_json(resp).await;
    assert_eq!(body["mimeType"], "image/png");
}

#[tokio::test]
async fn plain_text_upload_still_works() {
    let (app, cookie) = test_app().await;
    let data: &[u8] = b"hello";
    let resp = upload_request(
        app,
        "/api/files/upload",
        "hello.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = body_json(resp).await;
    assert_eq!(body["mimeType"], "text/plain");
}
