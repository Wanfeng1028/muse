use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state, init_state_with};
use serde_json::{json, Value};
use tower::ServiceExt;

/// 构建带已登录用户（tester）的 app，返回 (app, cookie)
async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let reg = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username": "tester", "password": "password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(reg).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
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

async fn request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: &str,
) -> axum::response::Response {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("cookie", cookie);
    let req = match body {
        Some(v) => {
            builder = builder.header("content-type", "application/json");
            builder.body(axum::body::Body::from(v.to_string())).unwrap()
        }
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    app.oneshot(req).await.unwrap()
}

#[tokio::test]
async fn health_returns_ok() {
    let (app, cookie) = test_app().await;
    let resp = request(app, "GET", "/api/health", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    assert_eq!(json["status"], "ok");
    assert_eq!(json["version"], "1.3.0");
}

#[tokio::test]
async fn apps_has_five_entries() {
    let (app, cookie) = test_app().await;
    let resp = request(app, "GET", "/api/apps", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    let arr = json.as_array().expect("apps should be an array");
    assert_eq!(arr.len(), 5);
    let ids: Vec<String> = arr
        .iter()
        .map(|a| a["id"].as_str().unwrap().to_string())
        .collect();
    for expected in ["files", "editor", "terminal", "settings", "about"] {
        assert!(
            ids.contains(&expected.to_string()),
            "missing app {}",
            expected
        );
    }
}

#[tokio::test]
async fn create_folder_then_list() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "myfolder", "kind": "folder", "content": ""})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    assert_eq!(created["name"], "myfolder");
    assert_eq!(created["kind"], "folder");

    let resp = request(app, "GET", "/api/fs", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let list = body_json(resp).await;
    let arr = list.as_array().expect("fs list should be an array");
    assert!(arr.iter().any(|n| n["name"] == "myfolder"));
}

#[tokio::test]
async fn create_file_then_update_content() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "note.txt", "kind": "file", "content": "hello"})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    let id = created["id"].as_i64().unwrap().to_string();
    assert_eq!(created["content"], "hello");

    let resp = request(
        app.clone(),
        "PUT",
        &format!("/api/fs/{}", id),
        Some(json!({"content": "updated content"})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let updated = body_json(resp).await;
    assert_eq!(updated["content"], "updated content");

    let resp = request(app, "GET", &format!("/api/fs/{}", id), None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let fetched = body_json(resp).await;
    assert_eq!(fetched["content"], "updated content");
}

#[tokio::test]
async fn settings_initial_and_update() {
    let (app, cookie) = test_app().await;
    let resp = request(app.clone(), "GET", "/api/settings", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    // v1.3：设置按用户隔离，新用户初始为空对象（种子设置归属 legacy 占位用户）
    assert_eq!(
        json,
        serde_json::json!({}),
        "new user should start with empty settings"
    );

    let resp = request(
        app.clone(),
        "PUT",
        "/api/settings",
        Some(json!({"key": "wallpaper", "value": "starfield"})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = request(app, "GET", "/api/settings", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    assert_eq!(json["wallpaper"], "starfield");
}

#[tokio::test]
async fn stats_counts_files() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "counted.txt", "kind": "file", "content": "abc"})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = request(app, "GET", "/api/stats", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    let files = json["files"].as_u64().unwrap();
    assert!(files >= 1, "expected at least 1 file, got {}", files);
    assert!(json.get("folders").is_some());
    assert!(json.get("totalBytes").is_some());
}

#[tokio::test]
async fn delete_file_then_get_returns_404() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "temp.txt", "kind": "file", "content": "x"})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    let id = created["id"].as_i64().unwrap().to_string();

    let resp = request(
        app.clone(),
        "DELETE",
        &format!("/api/fs/{}", id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    let resp = request(app, "GET", &format!("/api/fs/{}", id), None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn invalid_kind_returns_400() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app,
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "weird", "kind": "banana", "content": ""})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

// ---------- 上传/下载测试辅助 ----------

/// 手工构造 multipart/form-data 请求体
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
        .body(axum::body::Body::from(body))
        .unwrap();
    app.oneshot(req).await.unwrap()
}

async fn body_bytes(resp: axum::response::Response) -> Vec<u8> {
    to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap()
        .to_vec()
}

#[tokio::test]
async fn upload_text_then_download_bytes_match() {
    let (app, cookie) = test_app().await;
    let data = "hello mini-os 上传测试\n第二行".as_bytes();

    // 上传
    let resp = upload_request(
        app.clone(),
        "/api/files/upload?path=/",
        "greet.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    assert_eq!(created["name"], "greet.txt");
    assert_eq!(created["size"], data.len() as u64);
    let id = created["id"].as_i64().unwrap();

    // 列表可见
    let resp = request(app.clone(), "GET", "/api/fs", None, &cookie).await;
    let list = body_json(resp).await;
    assert!(list
        .as_array()
        .unwrap()
        .iter()
        .any(|n| n["name"] == "greet.txt"));

    // 下载字节一致
    let resp = request(
        app.clone(),
        "GET",
        "/api/files/download?path=/greet.txt",
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let cd = resp
        .headers()
        .get("content-disposition")
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(
        cd.starts_with("attachment"),
        "unexpected content-disposition: {}",
        cd
    );
    let bytes = body_bytes(resp).await;
    assert_eq!(bytes, data);

    // 删除后下载 404
    let resp = request(
        app.clone(),
        "DELETE",
        &format!("/api/fs/{}", id),
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);
    let resp = request(
        app,
        "GET",
        "/api/files/download?path=/greet.txt",
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn upload_binary_roundtrip() {
    let (app, cookie) = test_app().await;
    // 非法 UTF-8 的二进制
    let data: Vec<u8> = (0u8..=255u8).collect();
    assert!(std::str::from_utf8(&data).is_err());

    let resp = upload_request(
        app.clone(),
        "/api/files/upload",
        "blob.bin",
        "application/octet-stream",
        &data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    assert_eq!(created["size"], 256u64);
    // 二进制文件 JSON content 为空串
    assert_eq!(created["content"], "");

    let resp = request(
        app,
        "GET",
        "/api/files/download?path=/blob.bin",
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers().get("content-type").unwrap(),
        "application/octet-stream"
    );
    let bytes = body_bytes(resp).await;
    assert_eq!(bytes, data);
}

#[tokio::test]
async fn upload_to_subfolder_and_download() {
    let (app, cookie) = test_app().await;
    // 建目录
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "docs", "kind": "folder", "content": ""})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let data = b"subfolder file";
    let resp = upload_request(
        app.clone(),
        "/api/files/upload?path=/docs",
        "a.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = request(
        app.clone(),
        "GET",
        "/api/files/download?path=/docs/a.txt",
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_bytes(resp).await, data);

    // 不存在的目录 400
    let resp = upload_request(
        app,
        "/api/files/upload?path=/nope",
        "b.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn upload_oversize_returns_413() {
    let state = init_state_with(":memory:", "static", 1024, 60);
    let app = build_app(state);
    let reg = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username": "tester", "password": "password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(reg).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
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
    let data = vec![b'x'; 2048];
    let resp = upload_request(
        app,
        "/api/files/upload",
        "big.txt",
        "text/plain",
        &data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::PAYLOAD_TOO_LARGE);
}

#[tokio::test]
async fn upload_path_traversal_rejected() {
    let (app, cookie) = test_app().await;
    let data = b"evil";
    // 文件名含路径穿越
    let resp = upload_request(
        app.clone(),
        "/api/files/upload",
        "../../evil.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    // path 参数含 ..
    let resp = upload_request(
        app.clone(),
        "/api/files/upload?path=/../",
        "ok.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    // 确认没有写进去
    let resp = request(app, "GET", "/api/fs", None, &cookie).await;
    let list = body_json(resp).await;
    assert!(!list
        .as_array()
        .unwrap()
        .iter()
        .any(|n| n["name"] == "evil.txt"));
}

#[tokio::test]
async fn upload_duplicate_name_returns_409() {
    let (app, cookie) = test_app().await;
    let data = b"one";
    let resp = upload_request(
        app.clone(),
        "/api/files/upload",
        "dup.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let resp = upload_request(
        app,
        "/api/files/upload",
        "dup.txt",
        "text/plain",
        data,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CONFLICT);
}

#[tokio::test]
async fn download_directory_returns_400() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "adir", "kind": "folder", "content": ""})),
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let resp = request(app, "GET", "/api/files/download?path=/adir", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn download_missing_returns_404() {
    let (app, cookie) = test_app().await;
    let resp = request(
        app,
        "GET",
        "/api/files/download?path=/not-here.txt",
        None,
        &cookie,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let (app2, cookie2) = test_app().await;
    let resp = request(app2, "GET", "/api/files/download", None, &cookie2).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}
