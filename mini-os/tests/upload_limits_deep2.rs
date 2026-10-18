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

fn upload_request(cookie: &str, boundary: &str, body: Vec<u8>, path: Option<&str>) -> Request<Body> {
    let uri = match path {
        Some(p) => format!("/api/files/upload?path={}", p),
        None => "/api/files/upload".to_string(),
    };
    Request::builder()
        .method("POST")
        .uri(uri)
        .header(header::CONTENT_TYPE, format!("multipart/form-data; boundary={}", boundary))
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .unwrap()
}

async fn read_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice::<Value>(&bytes).unwrap()
}

async fn build_state() -> Arc<AppState> {
    init_state(":memory:", "static")
}

#[tokio::test]
async fn upload_empty_file_succeeds_with_zero_size() {
    let state = build_state().await;
    let app = build_app(state);
    let cookie = register(&app, "emptyfileuser").await;

    let boundary = "BNDEMPTY001";
    let body = multipart_body(
        boundary,
        &[("file", Some("empty.txt"), Some("text/plain"), b"")],
    );
    let resp = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let json = read_json(resp).await;
    assert_eq!(json["size"], serde_json::json!(0));
    assert_eq!(json["mimeType"], serde_json::json!("text/plain"));
    assert_eq!(json["name"], serde_json::json!("empty.txt"));
}

#[tokio::test]
async fn upload_exactly_at_limit_succeeds() {
    let state = init_state_with(":memory:", "static", 1024, 604800, 1000.0, 1000);
    let app = build_app(state);
    let cookie = register(&app, "limituser1").await;

    let data = vec![b'a'; 1024];
    let boundary = "BNDLIMIT001";
    let body = multipart_body(
        boundary,
        &[("file", Some("exact.bin"), Some("application/octet-stream"), &data)],
    );
    let resp = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let json = read_json(resp).await;
    assert_eq!(json["size"], serde_json::json!(1024));
}

#[tokio::test]
async fn upload_one_byte_over_limit_rejected() {
    let state = init_state_with(":memory:", "static", 1024, 604800, 1000.0, 1000);
    let app = build_app(state);
    let cookie = register(&app, "limituser2").await;

    let data = vec![b'a'; 1025];
    let boundary = "BNDOVER001";
    let body = multipart_body(
        boundary,
        &[("file", Some("over.bin"), Some("application/octet-stream"), &data)],
    );
    let resp = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::PAYLOAD_TOO_LARGE);
    let json = read_json(resp).await;
    assert_eq!(json["error"], serde_json::json!("文件过大，单文件上限为 0 MB"));
}

#[tokio::test]
async fn download_empty_file_zero_content_length() {
    let state = build_state().await;
    let app = build_app(state);
    let cookie = register(&app, "dlzerouser").await;

    let boundary = "BNDDLZERO";
    let body = multipart_body(
        boundary,
        &[("file", Some("empty.txt"), Some("text/plain"), b"")],
    );
    let up = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(up.status(), StatusCode::CREATED);

    let req = Request::builder()
        .method("GET")
        .uri("/api/files/download?path=/empty.txt")
        .header(header::COOKIE, &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers().get("content-length").unwrap().to_str().unwrap(),
        "0"
    );
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.len(), 0);
}

#[tokio::test]
async fn stats_counts_empty_file_bytes() {
    let state = build_state().await;
    let app = build_app(state);
    let cookie = register(&app, "statuser").await;

    let b1 = "BNDSTATA";
    let body_a = multipart_body(b1, &[("file", Some("a.txt"), Some("text/plain"), b"")]);
    let r1 = app
        .clone()
        .oneshot(upload_request(&cookie, b1, body_a, None))
        .await
        .unwrap();
    assert_eq!(r1.status(), StatusCode::CREATED);

    let b2 = "BNDSTATB";
    let body_b = multipart_body(b2, &[("file", Some("b.txt"), Some("text/plain"), b"hello")]);
    let r2 = app
        .clone()
        .oneshot(upload_request(&cookie, b2, body_b, None))
        .await
        .unwrap();
    assert_eq!(r2.status(), StatusCode::CREATED);

    let req = Request::builder()
        .method("GET")
        .uri("/api/stats")
        .header(header::COOKIE, &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let json = read_json(resp).await;
    assert_eq!(json["files"], serde_json::json!(2));
    assert_eq!(json["folders"], serde_json::json!(0));
    assert_eq!(json["totalBytes"], serde_json::json!(5));
}

#[tokio::test]
async fn upload_wrong_field_name_rejected() {
    let state = build_state().await;
    let app = build_app(state);
    let cookie = register(&app, "wrongfield").await;

    let boundary = "BNDWRONGF";
    let body = multipart_body(
        boundary,
        &[("image", Some("pic.png"), Some("image/png"), b"abc")],
    );
    let resp = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let json = read_json(resp).await;
    assert_eq!(json["error"], serde_json::json!("缺少文件字段"));
}

#[tokio::test]
async fn upload_empty_multipart_rejected() {
    let state = build_state().await;
    let app = build_app(state);
    let cookie = register(&app, "emptymulti").await;

    let boundary = "BNDNONE";
    let body = multipart_body(boundary, &[]);
    let resp = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let json = read_json(resp).await;
    assert_eq!(json["error"], serde_json::json!("缺少文件字段"));
}

#[tokio::test]
async fn upload_binary_non_utf8_roundtrips() {
    let state = build_state().await;
    let app = build_app(state);
    let cookie = register(&app, "binuser").await;

    let png_magic: [u8; 8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
    let boundary = "BNDPNG";
    let body = multipart_body(
        boundary,
        &[("file", Some("pic.png"), Some("application/octet-stream"), &png_magic)],
    );
    let up = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(up.status(), StatusCode::CREATED);
    let json = read_json(up).await;
    assert_eq!(json["mimeType"], serde_json::json!("image/png"));
    assert_eq!(json["size"], serde_json::json!(8));

    let req = Request::builder()
        .method("GET")
        .uri("/api/files/download?path=/pic.png")
        .header(header::COOKIE, &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.as_ref(), &png_magic[..]);
}

#[tokio::test]
async fn upload_limit_message_uses_configured_mb() {
    let state = init_state_with(":memory:", "static", 3 * 1024 * 1024, 604800, 1000.0, 1000);
    let app = build_app(state);
    let cookie = register(&app, "biglimituser").await;

    let data = vec![b'x'; 3 * 1024 * 1024 + 1];
    let boundary = "BNDBIG";
    let body = multipart_body(
        boundary,
        &[("file", Some("big.bin"), Some("application/octet-stream"), &data)],
    );
    let resp = app
        .clone()
        .oneshot(upload_request(&cookie, boundary, body, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::PAYLOAD_TOO_LARGE);
    let json = read_json(resp).await;
    assert_eq!(json["error"], serde_json::json!("文件过大，单文件上限为 3 MB"));
}