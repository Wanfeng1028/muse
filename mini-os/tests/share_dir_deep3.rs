use axum::body::to_bytes;
use axum::body::Body;
use axum::http::{header, Request, StatusCode};
use serde_json::{json, Value};
use tower::ServiceExt;

mod common {
    use super::*;
    use axum::Router;

    pub async fn register(app: &Router, username: &str, password: &str) -> String {
        let body = json!({ "username": username, "password": password }).to_string();
        let req = Request::builder()
            .method("POST")
            .uri("/api/auth/register")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(body))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::CREATED,
            "register {username} failed"
        );
        let set_cookie = resp
            .headers()
            .get(header::SET_COOKIE)
            .expect("missing set-cookie")
            .to_str()
            .unwrap()
            .to_string();
        let cookie = set_cookie.split(';').next().unwrap().to_string();
        cookie
    }

    pub async fn read_json(resp: axum::response::Response) -> Value {
        let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    pub async fn read_bytes(resp: axum::response::Response) -> Vec<u8> {
        to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec()
    }

    pub fn multipart_body(boundary: &str, field: &str, filename: &str, data: &[u8]) -> Vec<u8> {
        let mut body = Vec::new();
        body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
        body.extend_from_slice(
            format!(
                "Content-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            )
            .as_bytes(),
        );
        body.extend_from_slice(b"Content-Type: application/octet-stream\r\n\r\n");
        body.extend_from_slice(data);
        body.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());
        body
    }
}

use common::{multipart_body, read_bytes, read_json, register};

async fn get(app: &axum::Router, uri: &str, cookie: Option<&str>) -> axum::response::Response {
    let mut builder = Request::builder().method("GET").uri(uri);
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    app.clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

async fn post_json(
    app: &axum::Router,
    uri: &str,
    cookie: Option<&str>,
    value: &Value,
) -> axum::response::Response {
    let mut builder = Request::builder()
        .method("POST")
        .uri(uri)
        .header(header::CONTENT_TYPE, "application/json");
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    app.clone()
        .oneshot(builder.body(Body::from(value.to_string())).unwrap())
        .await
        .unwrap()
}

async fn create_dir(app: &axum::Router, cookie: &str, parent: Option<i64>, name: &str) -> i64 {
    let mut body = json!({ "name": name, "kind": "folder" });
    if let Some(p) = parent {
        body["parentId"] = json!(p);
    }
    let resp = post_json(app, "/api/fs", Some(cookie), &body).await;
    assert_eq!(resp.status(), StatusCode::OK, "create_dir {name} failed");
    let v = read_json(resp).await;
    v["id"].as_i64().unwrap()
}

async fn create_text_file(
    app: &axum::Router,
    cookie: &str,
    parent: Option<i64>,
    name: &str,
    content: &str,
) -> i64 {
    let mut body = json!({ "name": name, "kind": "file", "content": content });
    if let Some(p) = parent {
        body["parentId"] = json!(p);
    }
    let resp = post_json(app, "/api/fs", Some(cookie), &body).await;
    assert_eq!(resp.status(), StatusCode::OK, "create_file {name} failed");
    let v = read_json(resp).await;
    v["id"].as_i64().unwrap()
}

async fn create_share(app: &axum::Router, cookie: &str, body: &Value) -> axum::response::Response {
    post_json(app, "/api/shares", Some(cookie), body).await
}

async fn upload_binary(
    app: &axum::Router,
    cookie: &str,
    parent: Option<i64>,
    filename: &str,
    data: &[u8],
) -> i64 {
    let boundary = "----testboundaryXYZ";
    let body = multipart_body(boundary, "file", filename, data);
    let mut uri = "/api/fs/upload".to_string();
    if let Some(p) = parent {
        uri = format!("{uri}?parentId={p}");
    }
    let req = Request::builder()
        .method("POST")
        .uri(&uri)
        .header(header::COOKIE, cookie)
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={boundary}"),
        )
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "upload failed");
    let v = read_json(resp).await;
    v["id"].as_i64().unwrap()
}

async fn build_app() -> (axum::Router, String, String) {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let admin = register(&app, "admin", "adminpass123").await;
    let editor = register(&app, "editor", "editorpass123").await;
    (app, admin, editor)
}

#[tokio::test]
async fn dir_share_list_root_ordering() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    let sub = create_dir(&app, &admin, Some(docs), "sub").await;
    create_text_file(&app, &admin, Some(docs), "b.txt", "bb").await;
    create_text_file(&app, &admin, Some(docs), "a.txt", "a").await;
    create_text_file(&app, &admin, Some(sub), "c.txt", "ccc").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let v = read_json(resp).await;
    let token = v["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/share/list?token={token}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = read_json(resp).await;
    assert_eq!(v["path"].as_str().unwrap(), "");
    let entries = v["entries"].as_array().unwrap();
    let names: Vec<&str> = entries
        .iter()
        .map(|e| e["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, vec!["sub", "a.txt", "b.txt"]);
    assert_eq!(entries[0]["kind"].as_str().unwrap(), "folder");
    assert_eq!(entries[1]["kind"].as_str().unwrap(), "file");
    assert_eq!(entries[2]["kind"].as_str().unwrap(), "file");
}

#[tokio::test]
async fn dir_share_list_subpath() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    let sub = create_dir(&app, &admin, Some(docs), "sub").await;
    create_text_file(&app, &admin, Some(docs), "a.txt", "a").await;
    create_text_file(&app, &admin, Some(sub), "c.txt", "ccc").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(
        &app,
        &format!("/api/share/list?token={token}&path=sub"),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = read_json(resp).await;
    let entries = v["entries"].as_array().unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0]["name"].as_str().unwrap(), "c.txt");
    assert_eq!(entries[0]["kind"].as_str().unwrap(), "file");
}

#[tokio::test]
async fn dir_share_list_path_to_file_400() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    create_text_file(&app, &admin, Some(docs), "a.txt", "a").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(
        &app,
        &format!("/api/share/list?token={token}&path=a.txt"),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("path 不是目录"));
}

#[tokio::test]
async fn dir_share_list_dotdot_403() {
    let (app, admin, _editor) = build_app().await;
    create_dir(&app, &admin, None, "docs").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(
        &app,
        &format!("/api/share/list?token={token}&path=../x"),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("非法路径"));
}

#[tokio::test]
async fn list_share_on_file_share_400() {
    let (app, admin, _editor) = build_app().await;
    let fid = create_text_file(&app, &admin, None, "note.txt", "hello").await;

    let resp = create_share(&app, &admin, &json!({ "nodeId": fid })).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/share/list?token={token}"), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("仅目录分享支持浏览"));
}

#[tokio::test]
async fn dir_share_download_nested_file() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    let sub = create_dir(&app, &admin, Some(docs), "sub").await;
    create_text_file(&app, &admin, Some(sub), "c.txt", "hello-nested").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(
        &app,
        &format!("/api/s/{token}/download?path=sub/c.txt"),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(ct.contains("text/plain"), "content-type = {ct}");
    let bytes = read_bytes(resp).await;
    assert_eq!(bytes, b"hello-nested");
}

#[tokio::test]
async fn dir_share_download_missing_path_400() {
    let (app, admin, _editor) = build_app().await;
    create_dir(&app, &admin, None, "docs").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/s/{token}/download"), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"]
        .as_str()
        .unwrap()
        .contains("目录分享下载需要 path 参数"));
}

#[tokio::test]
async fn dir_share_download_folder_400() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    create_dir(&app, &admin, Some(docs), "sub").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/s/{token}/download?path=sub"), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("不能下载目录"));
}

#[tokio::test]
async fn dir_share_download_dotdot_403() {
    let (app, admin, _editor) = build_app().await;
    create_dir(&app, &admin, None, "docs").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(
        &app,
        &format!("/api/s/{token}/download?path=../secret.txt"),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("非法路径"));
}

#[tokio::test]
async fn file_share_metadata() {
    let (app, admin, _editor) = build_app().await;
    let fid = create_text_file(&app, &admin, None, "note.txt", "hello world").await;

    let resp = create_share(&app, &admin, &json!({ "nodeId": fid })).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = read_json(resp).await;
    assert_eq!(v["name"].as_str().unwrap(), "note.txt");
    assert_eq!(v["kind"].as_str().unwrap(), "file");
    assert_eq!(v["size"].as_i64().unwrap(), 11);
    assert_eq!(v["shareType"].as_str().unwrap(), "file");
    let mime = v["mimeType"].as_str().unwrap();
    assert!(mime.contains("text/plain"), "mimeType = {mime}");
}

#[tokio::test]
async fn file_share_download_bytes_and_disposition() {
    let (app, admin, _editor) = build_app().await;
    let mut data = vec![0x89u8, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
    data.extend_from_slice(&[0xFFu8, 0x00, 0x11, 0x22, 0x33]);
    let fid = upload_binary(&app, &admin, None, "img.png", &data).await;

    let resp = create_share(&app, &admin, &json!({ "nodeId": fid })).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/s/{token}/download"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let cd = resp
        .headers()
        .get(header::CONTENT_DISPOSITION)
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(
        cd.contains("filename*=UTF-8''"),
        "content-disposition = {cd}"
    );
    let bytes = read_bytes(resp).await;
    assert_eq!(bytes, data);
}

#[tokio::test]
async fn file_share_bad_token_404() {
    let (app, _admin, _editor) = build_app().await;
    let resp = get(&app, "/api/s/badtoken123", None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("分享不存在或已失效"));
}

#[tokio::test]
async fn create_share_folder_node_as_file_400() {
    let (app, admin, _editor) = build_app().await;
    let folder = create_dir(&app, &admin, None, "docs").await;

    let resp = create_share(&app, &admin, &json!({ "nodeId": folder })).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("仅支持分享文件"));
}

#[tokio::test]
async fn create_share_nonexistent_node_404() {
    let (app, admin, _editor) = build_app().await;
    let resp = create_share(&app, &admin, &json!({ "nodeId": 999999 })).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("节点不存在"));
}

#[tokio::test]
async fn create_share_other_user_node_404() {
    let (app, admin, editor) = build_app().await;
    let fid = create_text_file(&app, &admin, None, "secret.txt", "admin-secret").await;

    let resp = create_share(&app, &editor, &json!({ "nodeId": fid })).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("节点不存在"));
}

#[tokio::test]
async fn create_share_bad_type_400() {
    let (app, admin, _editor) = build_app().await;
    create_dir(&app, &admin, None, "docs").await;

    let resp = create_share(&app, &admin, &json!({ "type": "banana", "path": "/docs" })).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("type 只支持"));
}

#[tokio::test]
async fn create_share_dir_missing_path_400() {
    let (app, admin, _editor) = build_app().await;
    let resp = create_share(&app, &admin, &json!({ "type": "dir" })).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"]
        .as_str()
        .unwrap()
        .contains("目录分享需要 path 参数"));
}

#[tokio::test]
async fn create_share_dir_path_not_found_404() {
    let (app, admin, _editor) = build_app().await;
    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/nope" })).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("目录不存在"));
}

#[tokio::test]
async fn create_share_dir_path_is_file_400() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    create_text_file(&app, &admin, Some(docs), "a.txt", "aaa").await;

    let resp = create_share(
        &app,
        &admin,
        &json!({ "type": "dir", "path": "/docs/a.txt" }),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("path 不是目录"));
}

#[tokio::test]
async fn share_tokens_unique() {
    let (app, admin, _editor) = build_app().await;
    let fid = create_text_file(&app, &admin, None, "note.txt", "hello").await;

    let resp1 = create_share(&app, &admin, &json!({ "nodeId": fid })).await;
    assert_eq!(resp1.status(), StatusCode::CREATED);
    let t1 = read_json(resp1).await["token"]
        .as_str()
        .unwrap()
        .to_string();

    let resp2 = create_share(&app, &admin, &json!({ "nodeId": fid })).await;
    assert_eq!(resp2.status(), StatusCode::CREATED);
    let t2 = read_json(resp2).await["token"]
        .as_str()
        .unwrap()
        .to_string();

    assert_ne!(t1, t2);
    assert!(!t1.is_empty());
    assert!(!t2.is_empty());
}

#[tokio::test]
async fn delete_node_then_share_gone_404() {
    let (app, admin, _editor) = build_app().await;
    let fid = create_text_file(&app, &admin, None, "note.txt", "hello").await;

    let resp = create_share(&app, &admin, &json!({ "nodeId": fid })).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let req = Request::builder()
        .method("DELETE")
        .uri(format!("/api/fs/{fid}"))
        .header(header::COOKIE, &admin)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let v = read_json(resp).await;
    assert!(v["error"].as_str().unwrap().contains("分享不存在或已失效"));
}

#[tokio::test]
async fn dir_share_metadata_size() {
    let (app, admin, _editor) = build_app().await;
    let docs = create_dir(&app, &admin, None, "docs").await;
    let sub = create_dir(&app, &admin, Some(docs), "sub").await;
    create_text_file(&app, &admin, Some(docs), "a.txt", "aaa").await;
    create_text_file(&app, &admin, Some(sub), "b.txt", "bbbb").await;

    let resp = create_share(&app, &admin, &json!({ "type": "dir", "path": "/docs" })).await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let token = read_json(resp).await["token"].as_str().unwrap().to_string();

    let resp = get(&app, &format!("/api/s/{token}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = read_json(resp).await;
    assert_eq!(v["kind"].as_str().unwrap(), "folder");
    assert_eq!(v["shareType"].as_str().unwrap(), "dir");
    assert_eq!(v["size"].as_i64().unwrap(), 7);
    assert_eq!(v["name"].as_str().unwrap(), "docs");
}
