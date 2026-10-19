// 注意（产品行为观察，不修改产品代码）：
// - preview_plugin / install_plugin 在 multipart 中“找不到名为 file 的字段”时，
//   返回 400 且文案为“缺少文件字段”，这与本文件 install_empty_body_400 的断言一致。
// - plugins::uninstall 在“未安装”时错误串包含“未安装”，handler 映射为 404，符合 uninstall_missing_404。

use std::io::Write;
use std::sync::Mutex;

use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use tower::ServiceExt;

static ENV_LOCK: Mutex<()> = Mutex::new(());

fn build_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut zw = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
        for (name, data) in entries {
            zw.start_file(*name, opts).expect("start_file");
            zw.write_all(data).expect("write_all");
        }
        zw.finish().expect("finish");
    }
    buf
}

fn manifest_json(id: &str, permissions: &[&str]) -> Vec<u8> {
    let perms: Vec<String> = permissions.iter().map(|s| s.to_string()).collect();
    serde_json::to_vec(&serde_json::json!({
        "id": id,
        "name": "Demo",
        "version": "1.0.0",
        "entry": "main.js",
        "permissions": perms,
    }))
    .expect("manifest json")
}

fn multipart_body(boundary: &str, filename: &str, data: &[u8]) -> Vec<u8> {
    let mut body = Vec::new();
    body.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    body.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            filename
        )
        .as_bytes(),
    );
    body.extend_from_slice(b"Content-Type: application/octet-stream\r\n\r\n");
    body.extend_from_slice(data);
    body.extend_from_slice(format!("\r\n--{}--\r\n", boundary).as_bytes());
    body
}

fn multipart_other_field_body(boundary: &str) -> Vec<u8> {
    let mut body = Vec::new();
    body.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    body.extend_from_slice(b"Content-Disposition: form-data; name=\"other\"\r\n\r\n");
    body.extend_from_slice(b"not-a-file");
    body.extend_from_slice(format!("\r\n--{}--\r\n", boundary).as_bytes());
    body
}

fn unique_data_dir(test_name: &str) -> std::path::PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    std::env::temp_dir().join(format!(
        "minios-plugin-boundary-{}-{}-{}",
        std::process::id(),
        test_name,
        nanos
    ))
}

/// 在全局 ENV_LOCK 内设置 MINIOS_DATA_DIR 为唯一目录并构建 app。
/// 调用方需持有锁直到测试结束（返回 guard）。
fn app_for(test_name: &str) -> (axum::Router, std::sync::MutexGuard<'static, ()>) {
    let guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let base = unique_data_dir(test_name);
    let db_path = base.join("test.db");
    let static_dir = base.join("static");
    std::fs::create_dir_all(&static_dir).expect("create static dir");
    std::env::set_var("MINIOS_DATA_DIR", &base);
    let db = db_path.to_string_lossy().to_string();
    let state = mini_os::init_state_with(
        &db,
        &static_dir.to_string_lossy(),
        1024 * 1024,
        3600,
        100.0,
        100,
    );
    (mini_os::build_app(state), guard)
}

async fn read_body(resp: axum::response::Response) -> Vec<u8> {
    axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .expect("read body")
        .to_vec()
}

async fn register_cookie(app: &axum::Router, username: &str, password: &str) -> (String, String) {
    let body = serde_json::to_vec(&serde_json::json!({
        "username": username,
        "password": password,
    }))
    .expect("register json");
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .expect("build register req");
    let resp = app.clone().oneshot(req).await.expect("register resp");
    assert_eq!(resp.status(), StatusCode::CREATED, "register should be 201");
    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .and_then(|v| v.to_str().ok())
        .expect("set-cookie")
        .to_string();
    let cookie = set_cookie
        .split(';')
        .next()
        .expect("cookie pair")
        .to_string();
    let body_bytes = read_body(resp).await;
    let v: serde_json::Value = serde_json::from_slice(&body_bytes).expect("register body json");
    let id = v
        .get("id")
        .and_then(|x| x.as_i64())
        .map(|n| n.to_string())
        .unwrap_or_default();
    (id, cookie)
}

fn install_request(boundary: &str, cookie: &str, zip_bytes: &[u8]) -> Request<Body> {
    let body = multipart_body(boundary, "plugin.zip", zip_bytes);
    Request::builder()
        .method(Method::POST)
        .uri("/api/plugins/install")
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .expect("build install req")
}

fn preview_request(boundary: &str, cookie: &str, zip_bytes: &[u8]) -> Request<Body> {
    let body = multipart_body(boundary, "plugin.zip", zip_bytes);
    Request::builder()
        .method(Method::POST)
        .uri("/api/plugins/preview")
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .expect("build preview req")
}

fn delete_request(path: &str, cookie: &str) -> Request<Body> {
    Request::builder()
        .method(Method::DELETE)
        .uri(path)
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .expect("build delete req")
}

fn list_request(cookie: &str) -> Request<Body> {
    Request::builder()
        .method(Method::GET)
        .uri("/api/plugins")
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .expect("build list req")
}

async fn login_cookie(app: &axum::Router, username: &str, password: &str) -> String {
    let body = serde_json::to_vec(&serde_json::json!({
        "username": username,
        "password": password,
    }))
    .expect("login json");
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .expect("build login req");
    let resp = app.clone().oneshot(req).await.expect("login resp");
    assert_eq!(resp.status(), StatusCode::OK, "login should be 200");
    resp.headers()
        .get(header::SET_COOKIE)
        .and_then(|v| v.to_str().ok())
        .expect("set-cookie")
        .split(';')
        .next()
        .expect("cookie pair")
        .to_string()
}

fn set_role_request(user_id: &str, cookie: &str, role: &str) -> Request<Body> {
    let body = serde_json::to_vec(&serde_json::json!({ "role": role })).expect("role json");
    Request::builder()
        .method(Method::PUT)
        .uri(format!("/api/users/{}/role", user_id))
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .expect("build set role req")
}

fn demo_zip() -> Vec<u8> {
    build_zip(&[
        ("plugin.json", &manifest_json("demo", &[])),
        ("main.js", b"// demo"),
    ])
}

#[tokio::test]
async fn install_duplicate_400() {
    let (app, _g) = app_for("install_duplicate_400");
    let (_id, cookie) = register_cookie(&app, "admin1", "pw123456").await;
    let zip = demo_zip();

    let resp = app
        .clone()
        .oneshot(install_request("b1", &cookie, &zip))
        .await
        .expect("install first");
    assert_eq!(resp.status(), StatusCode::OK, "first install 200");

    let resp2 = app
        .clone()
        .oneshot(install_request("b2", &cookie, &zip))
        .await
        .expect("install second");
    assert_eq!(resp2.status(), StatusCode::BAD_REQUEST, "duplicate 400");
}

#[tokio::test]
async fn uninstall_missing_404() {
    let (app, _g) = app_for("uninstall_missing_404");
    let (_id, cookie) = register_cookie(&app, "admin2", "pw123456").await;

    let resp = app
        .clone()
        .oneshot(delete_request("/api/plugins/no-such-plugin", &cookie))
        .await
        .expect("uninstall missing");
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn install_uninstall_reinstall_200() {
    let (app, _g) = app_for("install_uninstall_reinstall_200");
    let (_id, cookie) = register_cookie(&app, "admin3", "pw123456").await;
    let zip = demo_zip();

    let resp = app
        .clone()
        .oneshot(install_request("b1", &cookie, &zip))
        .await
        .expect("install");
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = app
        .clone()
        .oneshot(delete_request("/api/plugins/demo", &cookie))
        .await
        .expect("uninstall");
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    let resp = app
        .clone()
        .oneshot(install_request("b2", &cookie, &zip))
        .await
        .expect("reinstall");
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn install_evil_manifest_id_400() {
    let (app, _g) = app_for("install_evil_manifest_id_400");
    let (_id, cookie) = register_cookie(&app, "admin4", "pw123456").await;

    let zip = build_zip(&[
        ("plugin.json", &manifest_json("../evil", &[])),
        ("main.js", b"// evil"),
    ]);

    let resp = app
        .clone()
        .oneshot(install_request("b1", &cookie, &zip))
        .await
        .expect("install evil id");
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn install_missing_manifest_400() {
    let (app, _g) = app_for("install_missing_manifest_400");
    let (_id, cookie) = register_cookie(&app, "admin5", "pw123456").await;

    let zip = build_zip(&[("main.js", b"// no manifest")]);

    let resp = app
        .clone()
        .oneshot(install_request("b1", &cookie, &zip))
        .await
        .expect("install no manifest");
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn install_then_list_contains() {
    let (app, _g) = app_for("install_then_list_contains");
    let (_id, cookie) = register_cookie(&app, "admin6", "pw123456").await;
    let zip = demo_zip();

    let resp = app
        .clone()
        .oneshot(install_request("b1", &cookie, &zip))
        .await
        .expect("install");
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = app
        .clone()
        .oneshot(list_request(&cookie))
        .await
        .expect("list");
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = read_body(resp).await;
    let v: serde_json::Value = serde_json::from_slice(&bytes).expect("list json");
    let arr = v.as_array().expect("list is array");
    let found = arr.iter().any(|item| {
        item.get("id")
            .and_then(|x| x.as_str())
            .map(|s| s == "demo")
            .unwrap_or(false)
    });
    assert!(found, "list should contain demo: {:?}", v);
}

#[tokio::test]
async fn uninstall_then_list_gone() {
    let (app, _g) = app_for("uninstall_then_list_gone");
    let (_id, cookie) = register_cookie(&app, "admin7", "pw123456").await;
    let zip = demo_zip();

    let resp = app
        .clone()
        .oneshot(install_request("b1", &cookie, &zip))
        .await
        .expect("install");
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = app
        .clone()
        .oneshot(delete_request("/api/plugins/demo", &cookie))
        .await
        .expect("uninstall");
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    let resp = app
        .clone()
        .oneshot(list_request(&cookie))
        .await
        .expect("list");
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = read_body(resp).await;
    let v: serde_json::Value = serde_json::from_slice(&bytes).expect("list json");
    let arr = v.as_array().expect("list is array");
    let found = arr.iter().any(|item| {
        item.get("id")
            .and_then(|x| x.as_str())
            .map(|s| s == "demo")
            .unwrap_or(false)
    });
    assert!(!found, "list should not contain demo: {:?}", v);
}

#[tokio::test]
async fn preview_zip_slip_400() {
    let (app, _g) = app_for("preview_zip_slip_400");
    let (_id, cookie) = register_cookie(&app, "admin8", "pw123456").await;

    let zip = build_zip(&[
        ("../evil.js", b"x"),
        ("plugin.json", &manifest_json("demo", &[])),
    ]);

    let resp = app
        .clone()
        .oneshot(preview_request("b1", &cookie, &zip))
        .await
        .expect("preview zip slip");
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn preview_ok_200() {
    let (app, _g) = app_for("preview_ok_200");
    let (_id, cookie) = register_cookie(&app, "admin9", "pw123456").await;
    let zip = demo_zip();

    let resp = app
        .clone()
        .oneshot(preview_request("b1", &cookie, &zip))
        .await
        .expect("preview ok");
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = read_body(resp).await;
    let text = String::from_utf8_lossy(&bytes);
    assert!(
        text.contains("\"id\":\"demo\""),
        "preview body should contain id demo: {}",
        text
    );
}

#[tokio::test]
async fn viewer_cannot_install_403() {
    let (app, _g) = app_for("viewer_cannot_install_403");
    let (_admin_id, admin_cookie) = register_cookie(&app, "adminA", "pw123456").await;
    let (u2_id, u2_cookie) = register_cookie(&app, "userB", "pw123456").await;

    let resp = app
        .clone()
        .oneshot(set_role_request(&u2_id, &admin_cookie, "viewer"))
        .await
        .expect("set role");
    assert_eq!(resp.status(), StatusCode::OK, "set role 200");

    // 角色变更会吊销该用户旧会话（产品安全行为），重新登录拿新会话再测权限。
    let u2_cookie = login_cookie(&app, "userB", "pw123456").await;
    let zip = demo_zip();
    let resp = app
        .clone()
        .oneshot(install_request("b1", &u2_cookie, &zip))
        .await
        .expect("viewer install");
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn viewer_cannot_uninstall_403() {
    let (app, _g) = app_for("viewer_cannot_uninstall_403");
    let (_admin_id, admin_cookie) = register_cookie(&app, "adminC", "pw123456").await;
    let (u2_id, u2_cookie) = register_cookie(&app, "userD", "pw123456").await;

    let zip = demo_zip();
    let resp = app
        .clone()
        .oneshot(install_request("b1", &admin_cookie, &zip))
        .await
        .expect("admin install");
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = app
        .clone()
        .oneshot(set_role_request(&u2_id, &admin_cookie, "viewer"))
        .await
        .expect("set role");
    assert_eq!(resp.status(), StatusCode::OK, "set role 200");

    // 角色变更会吊销该用户旧会话（产品安全行为），重新登录拿新会话再测权限。
    let u2_cookie = login_cookie(&app, "userD", "pw123456").await;
    let resp = app
        .clone()
        .oneshot(delete_request("/api/plugins/demo", &u2_cookie))
        .await
        .expect("viewer uninstall");
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn install_empty_body_400() {
    let (app, _g) = app_for("install_empty_body_400");
    let (_id, cookie) = register_cookie(&app, "adminE", "pw123456").await;

    let body = multipart_other_field_body("b1");
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/plugins/install")
        .header(
            header::CONTENT_TYPE,
            "multipart/form-data; boundary=b1".to_string(),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .expect("build empty-body req");

    let resp = app.clone().oneshot(req).await.expect("install no file");
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}
