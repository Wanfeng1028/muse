//! 插件 API 全链路集成测试。

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

fn app() -> axum::Router {
    let base = std::env::temp_dir().join(format!("minios-plugin-test-{}", std::process::id()));
    let db_path = base.join("test.db");
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

/// 注册并返回 (user_id, cookie)。首个注册用户自动成为 admin。
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

#[tokio::test]
async fn plugin_flow() {
    init_env();
    let app = app();

    // 未登录访问列表 401
    let req = Request::builder()
        .method("GET")
        .uri("/api/plugins")
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

    // 首个注册用户自动成为 admin
    let (_admin_id, admin_cookie) = register_cookie(&app, "admin", "adminpass123").await;

    // 注册 viewer1 并降为 viewer（刚注册默认是 editor，有插件管理权限，不符合 403 用例）
    let (viewer_id, viewer_cookie) = register_cookie(&app, "viewer1", "viewerpass1").await;
    set_role(&app, &admin_cookie, viewer_id, "viewer").await;

    let zip_ok = build_zip(&[
        ("plugin.json", &manifest_json("demo", &["fs.read"])[..]),
        ("main.js", b"async function main(){}"),
    ]);
    let boundary = "BOUNDARYVIEWER";
    let body = multipart_body(boundary, "demo.zip", &zip_ok);
    let req = Request::builder()
        .method("POST")
        .uri("/api/plugins/install")
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header("cookie", viewer_cookie.clone())
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);

    // permissions 含 net.evil 安装 400
    let zip_evil = build_zip(&[
        ("plugin.json", &manifest_json("evil", &["net.evil"])[..]),
        ("main.js", b"async function main(){}"),
    ]);
    let boundary = "BOUNDARYEVIL";
    let body = multipart_body(boundary, "evil.zip", &zip_evil);
    let req = Request::builder()
        .method("POST")
        .uri("/api/plugins/install")
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header("cookie", admin_cookie.clone())
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let text = body_text(resp).await;
    assert!(text.contains("未知权限"), "err was: {}", text);

    // 正常 zip 安装 200
    let boundary = "BOUNDARYOK";
    let body = multipart_body(boundary, "demo.zip", &zip_ok);
    let req = Request::builder()
        .method("POST")
        .uri("/api/plugins/install")
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header("cookie", admin_cookie.clone())
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    // 列表包含 demo
    let req = Request::builder()
        .method("GET")
        .uri("/api/plugins")
        .header("cookie", admin_cookie.clone())
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let text = body_text(resp).await;
    assert!(text.contains("\"id\":\"demo\""), "list was: {}", text);

    // preview 不落盘：preview 一个全新 id，然后列表仍无该 id
    let zip_prev = build_zip(&[
        (
            "plugin.json",
            &manifest_json("previewonly", &["fs.read"])[..],
        ),
        ("main.js", b"async function main(){}"),
    ]);
    let boundary = "BOUNDARYPREV";
    let body = multipart_body(boundary, "preview.zip", &zip_prev);
    let req = Request::builder()
        .method("POST")
        .uri("/api/plugins/preview")
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header("cookie", admin_cookie.clone())
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let req = Request::builder()
        .method("GET")
        .uri("/api/plugins")
        .header("cookie", admin_cookie.clone())
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    let text = body_text(resp).await;
    assert!(!text.contains("previewonly"), "list was: {}", text);

    // 卸载 204
    let req = Request::builder()
        .method("DELETE")
        .uri("/api/plugins/demo")
        .header("cookie", admin_cookie.clone())
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    // 二次卸载 404
    let req = Request::builder()
        .method("DELETE")
        .uri("/api/plugins/demo")
        .header("cookie", admin_cookie.clone())
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}
