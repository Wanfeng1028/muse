use std::io::Write;
use std::sync::Once;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

static INIT_ENV: Once = Once::new();

fn init_env() {
    INIT_ENV.call_once(|| {
        let base = std::env::temp_dir().join(format!("minios-plugin-test-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&base);
        std::env::set_var("MINIOS_DATA_DIR", &base);
    });
}

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

fn multipart_body_named(boundary: &str, field_name: &str, filename: &str, data: &[u8]) -> Vec<u8> {
    let mut body = Vec::new();
    body.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    body.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"{}\"; filename=\"{}\"\r\n",
            field_name, filename
        )
        .as_bytes(),
    );
    body.extend_from_slice(b"Content-Type: application/octet-stream\r\n\r\n");
    body.extend_from_slice(data);
    body.extend_from_slice(format!("\r\n--{}--\r\n", boundary).as_bytes());
    body
}

static DB_SEQ: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

fn app() -> axum::Router {
    // 每个用例独占一个 DB 文件：并行用例共用 test.db 会在迁移时撞
    // UNIQUE constraint（schema_migrations），且"首个注册用户为 admin"在并行下不可控。
    // data_dir 仍共用（插件 id 唯一，无干扰）。
    let seq = DB_SEQ.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
    let base = std::env::temp_dir().join(format!("minios-plugin-test-{}", std::process::id()));
    let db_path = base.join(format!("test-{}.db", seq));
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

async fn register_cookie(app: &axum::Router, username: &str, password: &str) -> (i64, String) {
    let body = serde_json::to_vec(&serde_json::json!({
        "username": username,
        "password": password,
    }))
    .unwrap();
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "register {} failed",
        username
    );
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("missing set-cookie")
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

async fn login_cookie(app: &axum::Router, username: &str, password: &str) -> String {
    let body = serde_json::to_vec(&serde_json::json!({
        "username": username,
        "password": password,
    }))
    .unwrap();
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/login")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "login {} failed", username);
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("missing set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

async fn set_role(app: &axum::Router, admin_cookie: &str, user_id: i64, role: &str) {
    let body = serde_json::to_vec(&serde_json::json!({ "role": role })).unwrap();
    let req = Request::builder()
        .method("PUT")
        .uri(format!("/api/users/{}/role", user_id))
        .header("content-type", "application/json")
        .header("cookie", admin_cookie)
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "set_role failed");
}

async fn body_text(resp: axum::response::Response) -> String {
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap_or_default();
    String::from_utf8_lossy(&bytes).to_string()
}

async fn preview(
    app: &axum::Router,
    cookie: Option<&str>,
    boundary: &str,
    body: Vec<u8>,
) -> axum::response::Response {
    let mut builder = Request::builder()
        .method("POST")
        .uri("/api/plugins/preview")
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        );
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let req = builder.body(Body::from(body)).unwrap();
    app.clone().oneshot(req).await.unwrap()
}

#[tokio::test]
async fn p1_preview_unauth_401() {
    init_env();
    let app = app();
    let body = multipart_body("BND_p1", "x.zip", b"whatever");
    let resp = preview(&app, None, "BND_p1", body).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn p2_preview_viewer_403() {
    init_env();
    let app = app();
    let (_admin_id, admin_cookie) = register_cookie(&app, "p2_admin", "pw123456").await;
    let (viewer_id, _stale_cookie) = register_cookie(&app, "p2_viewer", "pw123456").await;
    set_role(&app, &admin_cookie, viewer_id, "viewer").await;
    // 真实行为：改角色会撤销该用户全部 session，旧 cookie 已失效（再用是 401）。
    // 重新登录拿新 session，此时 viewer 身份调 preview 应得 403。
    let viewer_cookie = login_cookie(&app, "p2_viewer", "pw123456").await;

    let zip = build_zip(&[
        ("plugin.json", manifest_json("p2_demo", &[]).as_slice()),
        ("main.js", b"console.log(1)"),
    ]);
    let body = multipart_body("BND_p2", "x.zip", &zip);
    let resp = preview(&app, Some(&viewer_cookie), "BND_p2", body).await;
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn p3_preview_missing_field_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p3_admin", "pw123456").await;
    let boundary = "BND_p3";
    let body = format!("--{}--\r\n", boundary).into_bytes();
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let text = body_text(resp).await;
    assert!(text.contains("缺少文件字段"), "body = {}", text);
}

#[tokio::test]
async fn p4_preview_wrong_field_name_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p4_admin", "pw123456").await;
    let boundary = "BND_p4";
    let body = multipart_body_named(boundary, "notfile", "x.zip", b"data");
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let text = body_text(resp).await;
    assert!(text.contains("缺少文件字段"), "body = {}", text);
}

#[tokio::test]
async fn p5_preview_not_a_zip_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p5_admin", "pw123456").await;
    let boundary = "BND_p5";
    let body = multipart_body(boundary, "x.zip", b"this is not a zip");
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn p6_preview_empty_zip_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p6_admin", "pw123456").await;
    let zip = build_zip(&[]);
    let boundary = "BND_p6";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn p7_preview_no_manifest_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p7_admin", "pw123456").await;
    let zip = build_zip(&[("main.js", b"console.log(1)")]);
    let boundary = "BND_p7";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn p8_preview_manifest_invalid_json_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p8_admin", "pw123456").await;
    let zip = build_zip(&[
        ("plugin.json", b"{not json".as_slice()),
        ("main.js", b"console.log(1)"),
    ]);
    let boundary = "BND_p8";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn p9_preview_evil_permission_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p9_admin", "pw123456").await;
    let zip = build_zip(&[
        (
            "plugin.json",
            manifest_json("p9_demo", &["net.evil"]).as_slice(),
        ),
        ("main.js", b"console.log(1)"),
    ]);
    let boundary = "BND_p9";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let text = body_text(resp).await;
    assert!(text.contains("未知权限"), "body = {}", text);
}

#[tokio::test]
async fn p10_preview_dotdot_entry_400() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p10_admin", "pw123456").await;
    let zip = build_zip(&[
        ("plugin.json", manifest_json("p10_demo", &[]).as_slice()),
        ("main.js", b"console.log(1)"),
        ("../evil.js", b"evil"),
    ]);
    let boundary = "BND_p10";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn p11_preview_ok_no_disk_write() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p11_admin", "pw123456").await;
    let plugin_id = "p11_ok_plugin";
    let zip = build_zip(&[
        ("plugin.json", manifest_json(plugin_id, &[]).as_slice()),
        ("main.js", b"console.log(1)"),
    ]);
    let boundary = "BND_p11";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).expect("json body");
    assert_eq!(v.get("id").and_then(|x| x.as_str()), Some(plugin_id));
    assert_eq!(v.get("version").and_then(|x| x.as_str()), Some("1.0.0"));

    // 列表不含该 id
    let req = Request::builder()
        .method("GET")
        .uri("/api/plugins")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let list: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    let arr = list.as_array().cloned().unwrap_or_default();
    let contains = arr
        .iter()
        .any(|item| item.get("id").and_then(|x| x.as_str()) == Some(plugin_id));
    assert!(!contains, "list should not contain {}", plugin_id);

    // data_dir 下 plugins/<id> 目录不存在
    let data_dir = std::env::var("MINIOS_DATA_DIR").expect("MINIOS_DATA_DIR");
    let plugin_dir = std::path::Path::new(&data_dir)
        .join("plugins")
        .join(plugin_id);
    assert!(
        !plugin_dir.exists(),
        "plugin dir should not exist: {:?}",
        plugin_dir
    );
}

#[tokio::test]
async fn p12_preview_installed_id_still_ok() {
    init_env();
    let app = app();
    let (_id, cookie) = register_cookie(&app, "p12_admin", "pw123456").await;
    let plugin_id = "p12_installed_plugin";
    let zip = build_zip(&[
        ("plugin.json", manifest_json(plugin_id, &[]).as_slice()),
        ("main.js", b"console.log(1)"),
    ]);

    // install
    let boundary = "BND_p12_install";
    let body = multipart_body(boundary, "x.zip", &zip);
    let req = Request::builder()
        .method("POST")
        .uri("/api/plugins/install")
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header("cookie", &cookie)
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "install failed");

    // 列表含该 id
    let req = Request::builder()
        .method("GET")
        .uri("/api/plugins")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let list: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    let arr = list.as_array().cloned().unwrap_or_default();
    let contains = arr
        .iter()
        .any(|item| item.get("id").and_then(|x| x.as_str()) == Some(plugin_id));
    assert!(contains, "list should contain {}", plugin_id);

    // 同 id 再 preview -> 200
    let boundary = "BND_p12_preview";
    let body = multipart_body(boundary, "x.zip", &zip);
    let resp = preview(&app, Some(&cookie), boundary, body).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).expect("json body");
    assert_eq!(v.get("id").and_then(|x| x.as_str()), Some(plugin_id));
    assert_eq!(v.get("version").and_then(|x| x.as_str()), Some("1.0.0"));
}
