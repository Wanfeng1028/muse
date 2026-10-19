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

async fn mkdir(app: Router, cookie: &str, name: &str) -> axum::response::Response {
    let req = Request::builder()
        .method("POST")
        .uri("/api/fs")
        .header("cookie", cookie)
        .header("content-type", "application/json")
        .body(Body::from(
            serde_json::json!({"name": name, "kind": "folder"}).to_string(),
        ))
        .unwrap();
    app.oneshot(req).await.unwrap()
}

#[tokio::test]
async fn upload_path_mid_segment_dotdot_rejected() {
    let (app, cookie) = test_app().await;
    let resp = mkdir(app.clone(), &cookie, "a").await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let resp = upload_request(
        app,
        "/api/files/upload?path=/a/../b",
        "ok.txt",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法路径");
}

#[tokio::test]
async fn upload_path_dot_segment_rejected() {
    let (app, cookie) = test_app().await;
    let resp = upload_request(
        app,
        "/api/files/upload?path=/./",
        "ok.txt",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法路径");
}

#[tokio::test]
async fn upload_path_empty_segment_rejected() {
    let (app, cookie) = test_app().await;
    let resp = mkdir(app.clone(), &cookie, "a").await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let resp = upload_request(
        app,
        "/api/files/upload?path=/a//b",
        "ok.txt",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法路径");
}
#[tokio::test]
async fn upload_path_percent_encoded_control_char_rejected() {
    let (app, cookie) = test_app().await;
    let resp = upload_request(
        app,
        "/api/files/upload?path=/a%01b",
        "ok.txt",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法路径");
}

#[tokio::test]
async fn upload_filename_dotdot_rejected() {
    let (app, cookie) = test_app().await;
    let resp = upload_request(
        app,
        "/api/files/upload",
        "..",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法文件名");
}

#[tokio::test]
async fn upload_filename_dot_rejected() {
    let (app, cookie) = test_app().await;
    let resp = upload_request(
        app,
        "/api/files/upload",
        ".",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法文件名");
}

#[tokio::test]
async fn upload_filename_length_boundary() {
    let (app, cookie) = test_app().await;

    let name200: String = std::iter::repeat('a').take(200).collect();
    let resp200 = upload_request(
        app.clone(),
        "/api/files/upload",
        &name200,
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp200.status(), StatusCode::CREATED);
    let v200 = body_json(resp200).await;
    assert_eq!(v200["name"], serde_json::json!(name200));

    let name201: String = std::iter::repeat('b').take(201).collect();
    let resp201 = upload_request(
        app,
        "/api/files/upload",
        &name201,
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(resp201.status(), StatusCode::BAD_REQUEST);
    let v201 = body_json(resp201).await;
    assert_eq!(v201["error"], "文件名过长");
}

#[tokio::test]
async fn download_dir_segment_dotdot_rejected() {
    let (app, cookie) = test_app().await;

    let mk = mkdir(app.clone(), &cookie, "sub").await;
    assert_eq!(mk.status(), StatusCode::CREATED);

    let up = upload_request(
        app.clone(),
        "/api/files/upload",
        "file.txt",
        "text/plain",
        b"hello",
        &cookie,
    )
    .await;
    assert_eq!(up.status(), StatusCode::CREATED);

    let req = Request::builder()
        .method("GET")
        .uri("/api/files/download?path=/sub/../file.txt")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "非法路径");
}

#[tokio::test]
async fn download_root_slash_missing_path() {
    let (app, cookie) = test_app().await;
    let req = Request::builder()
        .method("GET")
        .uri("/api/files/download?path=/")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "缺少 path 参数");
}

#[tokio::test]
async fn download_folder_rejected() {
    let (app, cookie) = test_app().await;

    let mk = mkdir(app.clone(), &cookie, "mydir").await;
    assert_eq!(mk.status(), StatusCode::CREATED);

    let req = Request::builder()
        .method("GET")
        .uri("/api/files/download?path=/mydir")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "不能下载目录");
}

#[tokio::test]
async fn share_dir_create_dotdot_path_not_found() {
    let (app, cookie) = test_app().await;

    let mk = mkdir(app.clone(), &cookie, "docs").await;
    assert_eq!(mk.status(), StatusCode::CREATED);

    let req = Request::builder()
        .method("POST")
        .uri("/api/shares")
        .header("cookie", &cookie)
        .header("content-type", "application/json")
        .body(Body::from(
            serde_json::json!({"type": "dir", "path": "/../docs"}).to_string(),
        ))
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let v = body_json(resp).await;
    assert_eq!(v["error"], "目录不存在");
}

#[tokio::test]
async fn share_walk_dotdot_forbidden() {
    let (app, cookie) = test_app().await;

    let mk = mkdir(app.clone(), &cookie, "docs").await;
    assert_eq!(mk.status(), StatusCode::CREATED);

    let share_req = Request::builder()
        .method("POST")
        .uri("/api/shares")
        .header("cookie", &cookie)
        .header("content-type", "application/json")
        .body(Body::from(
            serde_json::json!({"type": "dir", "path": "/docs"}).to_string(),
        ))
        .unwrap();
    let share_resp = app.clone().oneshot(share_req).await.unwrap();
    assert_eq!(share_resp.status(), StatusCode::CREATED);
    let sv = body_json(share_resp).await;
    let token = sv["token"].as_str().unwrap().to_string();
    assert!(!token.is_empty());

    let list_req = Request::builder()
        .method("GET")
        .uri(format!("/api/share/list?token={}&path=..", token))
        .body(Body::empty())
        .unwrap();
    let list_resp = app.clone().oneshot(list_req).await.unwrap();
    assert_eq!(list_resp.status(), StatusCode::FORBIDDEN);
    let lv = body_json(list_resp).await;
    assert_eq!(lv["error"], "非法路径");

    let dl_req = Request::builder()
        .method("GET")
        .uri(format!("/api/s/{}/download?path=../../x", token))
        .body(Body::empty())
        .unwrap();
    let dl_resp = app.oneshot(dl_req).await.unwrap();
    assert_eq!(dl_resp.status(), StatusCode::FORBIDDEN);
    let dv = body_json(dl_resp).await;
    assert_eq!(dv["error"], "非法路径");
}
