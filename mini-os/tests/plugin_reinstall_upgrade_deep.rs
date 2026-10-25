//! 集成测试：插件"重装 / 升级 / 热替换"路径的边界行为。
//!
//! 聚焦语义：
//! - 同 id 重复安装被拒绝（无原地热替换）
//! - 卸载后可重新安装
//! - 失败安装不占坑
//! - 无原地升级：升级必须先卸载
//! - 权限边界
//! - 未安装卸载 404
//! - 缺文件字段 400

use std::path::PathBuf;
use std::sync::Once;

use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use axum::Router;
use serde_json::json;
use tower::ServiceExt;

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

static INIT_ENV: Once = Once::new();

fn init_env() -> PathBuf {
    INIT_ENV.call_once(|| {
        let base = std::env::temp_dir().join(format!("minios-plugin-test-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&base);
        std::env::set_var("MINIOS_DATA_DIR", &base);
    });
    PathBuf::from(std::env::var("MINIOS_DATA_DIR").expect("MINIOS_DATA_DIR must be set"))
}

static DB_SEQ: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

fn build_zip(files: &[(&str, &[u8])]) -> Vec<u8> {
    use std::io::Write;
    use zip::write::FileOptions;
    let mut buf: Vec<u8> = Vec::new();
    {
        let mut zw = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts = FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, data) in files {
            zw.start_file(*name, opts).unwrap();
            zw.write_all(data).unwrap();
        }
        zw.finish().unwrap();
    }
    buf
}

fn manifest_json(id: &str, permissions: &[&str]) -> Vec<u8> {
    let m = json!({
        "id": id,
        "name": id,
        "version": "1.0.0",
        "entry": "main.js",
        "permissions": permissions,
    });
    serde_json::to_vec(&m).unwrap()
}

fn manifest_json_version(id: &str, version: &str, permissions: &[&str]) -> Vec<u8> {
    let m = json!({
        "id": id,
        "name": id,
        "version": version,
        "entry": "main.js",
        "permissions": permissions,
    });
    serde_json::to_vec(&m).unwrap()
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
    body.extend_from_slice(b"Content-Type: application/zip\r\n\r\n");
    body.extend_from_slice(data);
    body.extend_from_slice(format!("\r\n--{}--\r\n", boundary).as_bytes());
    body
}

async fn app() -> Router {
    // 每个用例独占一个 DB 文件（并行隔离）；data_dir 共用，插件 id 唯一无干扰。
    let _ = init_env();
    let seq = DB_SEQ.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
    let base = std::env::temp_dir().join(format!("minios-plugin-test-{}", std::process::id()));
    let db_path = base.join(format!("test-r-{}.db", seq));
    let db = db_path.to_string_lossy().to_string();
    let static_dir = base.join("static");
    let _ = std::fs::create_dir_all(&static_dir);
    let state = mini_os::init_state_with(
        &db,
        &static_dir.to_string_lossy(),
        1024 * 1024,
        3600,
        100.0,
        100,
    );
    mini_os::build_app(state)
}

async fn body_text(resp: axum::response::Response) -> String {
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    String::from_utf8_lossy(&bytes).to_string()
}

async fn register_cookie(router: &Router, username: &str) -> (i64, String) {
    let body = json!({
        "username": username,
        "password": "pw12345678",
    });
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(serde_json::to_vec(&body).unwrap()))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "register should succeed"
    );
    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .expect("Set-Cookie missing")
        .to_str()
        .unwrap()
        .to_string();
    let cookie = set_cookie.split(';').next().unwrap().to_string();
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    let id = v.get("id").and_then(|x| x.as_i64()).expect("missing id");
    (id, cookie)
}

async fn login_cookie(router: &Router, username: &str) -> String {
    let body = json!({
        "username": username,
        "password": "pw12345678",
    });
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(serde_json::to_vec(&body).unwrap()))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "login should succeed");
    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .expect("Set-Cookie missing")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

async fn set_role(router: &Router, admin_cookie: &str, user_id: i64, role: &str) {
    let body = json!({ "role": role });
    let req = Request::builder()
        .method(Method::PUT)
        .uri(format!("/api/users/{}/role", user_id))
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::COOKIE, admin_cookie)
        .body(Body::from(serde_json::to_vec(&body).unwrap()))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "set_role should succeed");
}

async fn install_zip(
    router: &Router,
    cookie: &str,
    filename: &str,
    zip: &[u8],
) -> axum::response::Response {
    let boundary = "----minios-test-boundary";
    let body = multipart_body(boundary, filename, zip);
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/plugins/install")
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .unwrap();
    router.clone().oneshot(req).await.unwrap()
}

async fn install_zip_no_file(router: &Router, cookie: &str) -> axum::response::Response {
    // 缺少 file 字段：multipart 中只有一个无关字段。
    let boundary = "----minios-test-boundary-nofile";
    let mut body = Vec::new();
    body.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    body.extend_from_slice(b"Content-Disposition: form-data; name=\"other\"\r\n\r\nhello\r\n");
    body.extend_from_slice(format!("--{}--\r\n", boundary).as_bytes());
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/plugins/install")
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .unwrap();
    router.clone().oneshot(req).await.unwrap()
}

async fn uninstall(router: &Router, cookie: &str, id: &str) -> axum::response::Response {
    let req = Request::builder()
        .method(Method::DELETE)
        .uri(format!("/api/plugins/{}", id))
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .unwrap();
    router.clone().oneshot(req).await.unwrap()
}

async fn uninstall_no_cookie(router: &Router, id: &str) -> axum::response::Response {
    let req = Request::builder()
        .method(Method::DELETE)
        .uri(format!("/api/plugins/{}", id))
        .body(Body::empty())
        .unwrap();
    router.clone().oneshot(req).await.unwrap()
}

async fn list_plugins(router: &Router, cookie: &str) -> serde_json::Value {
    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/plugins")
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let text = body_text(resp).await;
    serde_json::from_str(&text).expect("plugins list should be JSON")
}

fn plugin_version_in_list(list: &serde_json::Value, id: &str) -> Option<String> {
    // 列表可能是裸数组，也可能包成 {"plugins":[...]}，两种都试。
    let arr = list
        .as_array()
        .or_else(|| list.get("plugins").and_then(|v| v.as_array()))
        .cloned()?;
    for item in arr {
        if item.get("id").and_then(|v| v.as_str()) == Some(id) {
            return item
                .get("version")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
        }
    }
    None
}

fn plugin_dir(data_dir: &std::path::Path, id: &str) -> PathBuf {
    data_dir.join("plugins").join(id)
}

fn read_file(p: &std::path::Path) -> Option<Vec<u8>> {
    std::fs::read(p).ok()
}

// ---------------------------------------------------------------------------
// r1: 同 id 重装被拒绝，磁盘内容保持旧版本
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r1_reinstall_same_id_rejected() {
    let data_dir = init_env();
    let router = app().await;
    let (_, admin) = register_cookie(&router, "r1admin").await;

    let zip_v1 = build_zip(&[
        ("plugin.json", &manifest_json("r1plug", &[])),
        ("main.js", b"v1-marker"),
    ]);
    let resp = install_zip(&router, &admin, "r1plug.zip", &zip_v1).await;
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "first install should succeed"
    );
    let _ = body_text(resp).await;

    // 磁盘上应该是 v1-marker
    let main_js = plugin_dir(&data_dir, "r1plug").join("main.js");
    assert_eq!(
        read_file(&main_js).as_deref(),
        Some(&b"v1-marker"[..]),
        "installed main.js should be v1-marker"
    );

    // 用同 id 不同内容再次安装
    let zip_v2 = build_zip(&[
        ("plugin.json", &manifest_json("r1plug", &[])),
        ("main.js", b"v2-marker"),
    ]);
    let resp = install_zip(&router, &admin, "r1plug.zip", &zip_v2).await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "reinstall same id should be rejected"
    );
    let text = body_text(resp).await;
    assert!(
        text.contains("已安装"),
        "body should mention 已安装, got: {}",
        text
    );

    // 热替换被拒绝：磁盘上仍是 v1-marker
    assert_eq!(
        read_file(&main_js).as_deref(),
        Some(&b"v1-marker"[..]),
        "after rejected reinstall, main.js must still be v1-marker"
    );

    // 列表中 version 仍为 1.0.0
    let list = list_plugins(&router, &admin).await;
    assert_eq!(
        plugin_version_in_list(&list, "r1plug").as_deref(),
        Some("1.0.0"),
        "version in list should still be 1.0.0"
    );
}

// ---------------------------------------------------------------------------
// r2: 卸载后可重装
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r2_uninstall_then_reinstall_ok() {
    let data_dir = init_env();
    let router = app().await;
    let (_, admin) = register_cookie(&router, "r2admin").await;

    let zip_v1 = build_zip(&[
        ("plugin.json", &manifest_json("r2plug", &[])),
        ("main.js", b"r2-v1"),
    ]);
    let resp = install_zip(&router, &admin, "r2plug.zip", &zip_v1).await;
    assert_eq!(resp.status(), StatusCode::OK);

    // 卸载
    let resp = uninstall(&router, &admin, "r2plug").await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    // 目录已消失
    assert!(
        !plugin_dir(&data_dir, "r2plug").exists(),
        "plugin dir should be removed after uninstall"
    );

    // 重新安装同 id 新内容
    let zip_v2 = build_zip(&[
        ("plugin.json", &manifest_json("r2plug", &[])),
        ("main.js", b"r2-v2"),
    ]);
    let resp = install_zip(&router, &admin, "r2plug.zip", &zip_v2).await;
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "reinstall after uninstall should succeed"
    );

    // 列表含 r2plug
    let list = list_plugins(&router, &admin).await;
    assert!(
        plugin_version_in_list(&list, "r2plug").is_some(),
        "list should contain r2plug"
    );

    // 磁盘上应是新内容
    let main_js = plugin_dir(&data_dir, "r2plug").join("main.js");
    assert_eq!(read_file(&main_js).as_deref(), Some(&b"r2-v2"[..]));
}

// ---------------------------------------------------------------------------
// r3: 失败安装不占坑
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r3_reinstall_after_failed_install_ok() {
    let router = app().await;
    let (_, admin) = register_cookie(&router, "r3admin").await;

    // 缺 plugin.json 的坏 zip
    let bad_zip = build_zip(&[("main.js", b"no-manifest")]);
    let resp = install_zip(&router, &admin, "r3plug.zip", &bad_zip).await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "zip without plugin.json should fail"
    );

    // 合法 zip 同 id 应成功（失败没占坑）
    let good_zip = build_zip(&[
        ("plugin.json", &manifest_json("r3plug", &[])),
        ("main.js", b"r3-ok"),
    ]);
    let resp = install_zip(&router, &admin, "r3plug.zip", &good_zip).await;
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "install after failed attempt should succeed"
    );

    let list = list_plugins(&router, &admin).await;
    assert!(plugin_version_in_list(&list, "r3plug").is_some());
}

// ---------------------------------------------------------------------------
// r4: 升级必须先卸载（无原地升级）
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r4_upgrade_intent_requires_uninstall() {
    let router = app().await;
    let (_, admin) = register_cookie(&router, "r4admin").await;

    // v1.0.0
    let zip_v1 = build_zip(&[
        ("plugin.json", &manifest_json("r4plug", &[])),
        ("main.js", b"r4-v1"),
    ]);
    let resp = install_zip(&router, &admin, "r4plug.zip", &zip_v1).await;
    assert_eq!(resp.status(), StatusCode::OK);

    // 同 id v2.0.0 -> 400 已安装
    let zip_v2 = build_zip(&[
        (
            "plugin.json",
            &manifest_json_version("r4plug", "2.0.0", &[]),
        ),
        ("main.js", b"r4-v2"),
    ]);
    let resp = install_zip(&router, &admin, "r4plug.zip", &zip_v2).await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "in-place upgrade should be rejected"
    );
    let text = body_text(resp).await;
    assert!(
        text.contains("已安装"),
        "body should mention 已安装, got: {}",
        text
    );

    // 卸载 -> 204
    let resp = uninstall(&router, &admin, "r4plug").await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    // 再装 v2.0.0 -> 200
    let resp = install_zip(&router, &admin, "r4plug.zip", &zip_v2).await;
    assert_eq!(resp.status(), StatusCode::OK, "install v2 after uninstall");

    // 列表 version = 2.0.0
    let list = list_plugins(&router, &admin).await;
    assert_eq!(
        plugin_version_in_list(&list, "r4plug").as_deref(),
        Some("2.0.0"),
        "version in list should be 2.0.0 after reinstall"
    );
}

// ---------------------------------------------------------------------------
// r5: 权限边界
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r5_viewer_cannot_install_uninstall() {
    let router = app().await;
    // 首个注册用户是 admin
    let (_, admin) = register_cookie(&router, "r5admin").await;

    // 预置一个插件供 viewer 尝试卸载
    let zip = build_zip(&[
        ("plugin.json", &manifest_json("r5plug", &[])),
        ("main.js", b"r5"),
    ]);
    let resp = install_zip(&router, &admin, "r5plug.zip", &zip).await;
    assert_eq!(resp.status(), StatusCode::OK);

    // 注册 viewer 并设置角色；改角色会撤销其全部 session，必须重新登录拿新 cookie。
    let (viewer_id, _stale) = register_cookie(&router, "r5viewer").await;
    set_role(&router, &admin, viewer_id, "viewer").await;
    let viewer = login_cookie(&router, "r5viewer").await;

    // viewer 安装 -> 403
    let zip2 = build_zip(&[
        ("plugin.json", &manifest_json("r5plug2", &[])),
        ("main.js", b"r5b"),
    ]);
    let resp = install_zip(&router, &viewer, "r5plug2.zip", &zip2).await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "viewer install should be forbidden"
    );

    // viewer 卸载已存在插件 -> 403
    let resp = uninstall(&router, &viewer, "r5plug").await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "viewer uninstall should be forbidden"
    );

    // 未登录卸载 -> 401
    let resp = uninstall_no_cookie(&router, "r5plug").await;
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "unauthenticated uninstall should be 401"
    );
}

// ---------------------------------------------------------------------------
// r6: 卸载不存在的 id -> 404
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r6_uninstall_missing_404() {
    let router = app().await;
    let (_, admin) = register_cookie(&router, "r6admin").await;

    let resp = uninstall(&router, &admin, "r6-never-installed").await;
    assert_eq!(
        resp.status(),
        StatusCode::NOT_FOUND,
        "uninstall missing plugin should be 404"
    );
    let text = body_text(resp).await;
    assert!(
        text.contains("未安装"),
        "body should mention 未安装, got: {}",
        text
    );
}

// ---------------------------------------------------------------------------
// r7: multipart 缺 file 字段 -> 400
// ---------------------------------------------------------------------------

#[tokio::test]
async fn r7_install_empty_file_field_400() {
    let router = app().await;
    let (_, admin) = register_cookie(&router, "r7admin").await;

    let resp = install_zip_no_file(&router, &admin).await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "missing file field should be 400"
    );
    let text = body_text(resp).await;
    assert!(
        text.contains("缺少文件字段"),
        "body should mention 缺少文件字段, got: {}",
        text
    );
}
