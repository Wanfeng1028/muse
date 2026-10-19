use axum::body::{to_bytes, Body};
use axum::http::{header, Request, StatusCode};
use serde_json::Value;
use std::sync::Arc;
use tower::ServiceExt;

use mini_os::{build_app, init_state_with, AppState};

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

fn multipart_body(boundary: &str, parts: &[(&str, Option<&str>, Option<&str>, &[u8])]) -> Vec<u8> {
    let mut out: Vec<u8> = Vec::new();
    for (name, filename, ctype, data) in parts {
        out.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
        match filename {
            Some(fname) => {
                out.extend_from_slice(
                    format!(
                        "Content-Disposition: form-data; name=\"{}\"; filename=\"{}\"\r\n",
                        name, fname
                    )
                    .as_bytes(),
                );
                if let Some(ct) = ctype {
                    out.extend_from_slice(format!("Content-Type: {}\r\n", ct).as_bytes());
                }
            }
            None => {
                out.extend_from_slice(
                    format!("Content-Disposition: form-data; name=\"{}\"\r\n", name).as_bytes(),
                );
            }
        }
        out.extend_from_slice(b"\r\n");
        out.extend_from_slice(data);
        out.extend_from_slice(b"\r\n");
    }
    out.extend_from_slice(format!("--{}--\r\n", boundary).as_bytes());
    out
}

fn upload_request(
    cookie: &str,
    boundary: &str,
    body: Vec<u8>,
    path: Option<&str>,
) -> Request<Body> {
    let uri = match path {
        Some(p) => format!("/api/files/upload?path={}", p),
        None => "/api/files/upload".to_string(),
    };
    Request::builder()
        .method("POST")
        .uri(uri)
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .unwrap()
}

async fn read_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

fn test_state() -> Arc<AppState> {
    init_state_with(":memory:", "static", 4096, 604800, 1000.0, 1000)
}

async fn do_upload(
    app: &axum::Router,
    cookie: &str,
    fname: &str,
    ctype: Option<&str>,
    data: &[u8],
    path: Option<&str>,
) -> axum::response::Response {
    let boundary = "----miniosboundary123";
    let body = multipart_body(boundary, &[("file", Some(fname), ctype, data)]);
    let req = upload_request(cookie, boundary, body, path);
    app.clone().oneshot(req).await.unwrap()
}

#[tokio::test]
async fn upload_mz_header_415() {
    let app = build_app(test_state());
    let cookie = register(&app, "mz_user").await;
    let mut bytes = vec![0x4D, 0x5A];
    bytes.extend_from_slice(&[0u8; 64]);
    let resp = do_upload(&app, &cookie, "evil.exe", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = read_json(resp).await;
    let err = body["error"].as_str().unwrap();
    assert!(err.contains("可执行文件不允许上传"), "got: {}", err);
}

#[tokio::test]
async fn upload_elf_header_415() {
    let app = build_app(test_state());
    let cookie = register(&app, "elf_user").await;
    let mut bytes = vec![0x7F, 0x45, 0x4C, 0x46];
    bytes.extend_from_slice(&[0u8; 64]);
    let resp = do_upload(&app, &cookie, "prog.bin", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = read_json(resp).await;
    assert!(body["error"]
        .as_str()
        .unwrap()
        .contains("可执行文件不允许上传"));
}

#[tokio::test]
async fn upload_shebang_415() {
    let app = build_app(test_state());
    let cookie = register(&app, "sh_user").await;
    let resp = do_upload(
        &app,
        &cookie,
        "script.sh",
        None,
        b"#!/bin/bash\necho hi",
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = read_json(resp).await;
    assert!(body["error"]
        .as_str()
        .unwrap()
        .contains("可执行文件不允许上传"));
}

#[tokio::test]
async fn upload_macho_header_415() {
    let app = build_app(test_state());
    let cookie = register(&app, "macho_user").await;
    let mut bytes = vec![0xFE, 0xED, 0xFA, 0xCE];
    bytes.extend_from_slice(&[0u8; 64]);
    let resp = do_upload(&app, &cookie, "app.bin", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
    let body = read_json(resp).await;
    assert!(body["error"]
        .as_str()
        .unwrap()
        .contains("可执行文件不允许上传"));
}

#[tokio::test]
async fn upload_png_magic_mime() {
    let app = build_app(test_state());
    let cookie = register(&app, "png_user").await;
    let mut bytes = vec![0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
    bytes.extend_from_slice(&[0x00, 0x00, 0x00, 0x0D]);
    let resp = do_upload(&app, &cookie, "pic.bin", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body["mimeType"].as_str().unwrap(), "image/png");
}

#[tokio::test]
async fn upload_jpeg_magic_mime() {
    let app = build_app(test_state());
    let cookie = register(&app, "jpeg_user").await;
    let mut bytes = vec![0xFF, 0xD8, 0xFF];
    bytes.extend_from_slice(&[0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46]);
    let resp = do_upload(&app, &cookie, "photo.bin", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body["mimeType"].as_str().unwrap(), "image/jpeg");
}

#[tokio::test]
async fn upload_pdf_magic_mime() {
    let app = build_app(test_state());
    let cookie = register(&app, "pdf_user").await;
    let resp = do_upload(
        &app,
        &cookie,
        "doc.bin",
        None,
        b"%PDF-1.4\n%fake content\n",
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body["mimeType"].as_str().unwrap(), "application/pdf");
}

#[tokio::test]
async fn upload_zip_magic_mime() {
    let app = build_app(test_state());
    let cookie = register(&app, "zip_user").await;
    let mut bytes = vec![0x50, 0x4B, 0x03, 0x04];
    bytes.extend_from_slice(&[0x14, 0x00, 0x00, 0x00]);
    let resp = do_upload(&app, &cookie, "arc.bin", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body["mimeType"].as_str().unwrap(), "application/zip");
}

#[tokio::test]
async fn upload_declared_ctype_used_when_no_magic() {
    let app = build_app(test_state());
    let cookie = register(&app, "ctype_user").await;
    let resp = do_upload(
        &app,
        &cookie,
        "note.txt",
        Some("application/pdf"),
        b"hello world",
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body["mimeType"].as_str().unwrap(), "application/pdf");
}

#[tokio::test]
async fn upload_octet_stream_fallback() {
    let app = build_app(test_state());
    let cookie = register(&app, "octet_user").await;
    let resp = do_upload(&app, &cookie, "x.unknownext", None, b"hello", None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(
        body["mimeType"].as_str().unwrap(),
        "application/octet-stream"
    );
}

#[tokio::test]
async fn upload_to_existing_subfolder() {
    let app = build_app(test_state());
    let cookie = register(&app, "sub_user").await;

    let mk = Request::builder()
        .method("POST")
        .uri("/api/fs")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::COOKIE, &cookie)
        .body(Body::from(
            serde_json::json!({"name": "docs", "kind": "folder"}).to_string(),
        ))
        .unwrap();
    let mk_resp = app.clone().oneshot(mk).await.unwrap();
    assert_eq!(mk_resp.status(), StatusCode::CREATED);
    let folder = read_json(mk_resp).await;
    let folder_id = folder["id"].as_i64().unwrap();

    let resp = do_upload(&app, &cookie, "note.txt", None, b"content", Some("/docs")).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body["parentId"].as_i64().unwrap(), folder_id);
}

#[tokio::test]
async fn upload_to_nonexistent_path_400() {
    let app = build_app(test_state());
    let cookie = register(&app, "nopath_user").await;
    let resp = do_upload(&app, &cookie, "note.txt", None, b"content", Some("/nope")).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    assert_eq!(body["error"].as_str().unwrap(), "目录不存在或不是文件夹");
}

#[tokio::test]
async fn upload_duplicate_name_409() {
    let app = build_app(test_state());
    let cookie = register(&app, "dup_user").await;

    let first = do_upload(&app, &cookie, "same.txt", None, b"one", None).await;
    assert_eq!(first.status(), StatusCode::CREATED);

    let second = do_upload(&app, &cookie, "same.txt", None, b"two", None).await;
    assert_eq!(second.status(), StatusCode::CONFLICT);
    let body = read_json(second).await;
    assert!(body["error"].as_str().unwrap().contains("同名文件已存在"));
}

#[tokio::test]
async fn upload_filename_with_slash_400() {
    let app = build_app(test_state());
    let cookie = register(&app, "slash_user").await;
    let resp = do_upload(&app, &cookie, "a/b.txt", None, b"content", None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("非法字符"));
}

#[tokio::test]
async fn upload_filename_with_backslash_400() {
    let app = build_app(test_state());
    let cookie = register(&app, "bslash_user").await;
    let resp = do_upload(&app, &cookie, "a\\b.txt", None, b"content", None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("非法字符"));
}

#[tokio::test]
async fn upload_filename_nul_400() {
    let app = build_app(test_state());
    let cookie = register(&app, "nul_user").await;
    let resp = do_upload(&app, &cookie, "a\0.txt", None, b"content", None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn upload_4097_bytes_413_zero_mb_message() {
    let app = build_app(test_state());
    let cookie = register(&app, "limit_user").await;

    let ok_bytes = vec![b'a'; 4096];
    let ok = do_upload(&app, &cookie, "ok.bin", None, &ok_bytes, None).await;
    assert_eq!(ok.status(), StatusCode::CREATED);

    let too_big = vec![b'b'; 4097];
    let resp = do_upload(&app, &cookie, "big.bin", None, &too_big, None).await;
    assert_eq!(resp.status(), StatusCode::PAYLOAD_TOO_LARGE);
    let body = read_json(resp).await;
    let err = body["error"].as_str().unwrap();
    assert!(err.contains("0 MB"), "got: {}", err);
}

#[tokio::test]
async fn upload_non_utf8_empty_content_documents() {
    let app = build_app(test_state());
    let cookie = register(&app, "bin_user").await;

    let bytes: [u8; 4] = [0xFF, 0xFE, 0x00, 0x01];
    let resp = do_upload(&app, &cookie, "bin.dat", None, &bytes, None).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = read_json(resp).await;
    let id = created["id"].as_i64().unwrap();

    let get_req = Request::builder()
        .method("GET")
        .uri(format!("/api/fs/{}", id))
        .header(header::COOKIE, &cookie)
        .body(Body::empty())
        .unwrap();
    let get_resp = app.clone().oneshot(get_req).await.unwrap();
    assert_eq!(get_resp.status(), StatusCode::OK);
    let node = read_json(get_resp).await;
    assert_eq!(node["content"].as_str().unwrap(), "");
}
