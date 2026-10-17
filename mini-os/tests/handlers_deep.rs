//! handlers 模块深度测试：文件管理边界、终端命令解析边界、并发、错误传播。
//!
//! 说明：本文件只对【事实来源】中逐字出现的公开标识符做断言，
//! 私有函数（sniff_mime / sanitize_filename / resolve_folder_id / percent_encode）
//! 通过其在 HTTP 层的可观测行为间接验证；能被 pub 导出的直接调用。

use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

use axum::response::IntoResponse;
use mini_os::handlers::{apps_registry, health, DownloadQuery, FsQuery, UploadQuery};

/// 构造一个最小可用的 AppState 用于路由测试。
/// 每个调用使用独立临时目录（同进程内测试并行跑，不许共用 db 文件）。
static ROUTER_SEQ: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

fn build_router() -> axum::Router {
    let n = ROUTER_SEQ.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
    let dir = std::env::temp_dir().join(format!(
        "mini_os_handlers_deep_{}_{}",
        std::process::id(),
        n
    ));
    std::fs::create_dir_all(&dir).expect("create tmp dir");
    let db_path = dir.join("t.db").to_string_lossy().to_string();
    let static_dir = dir.join("static").to_string_lossy().to_string();
    let _ = std::fs::create_dir_all(&static_dir);
    let state = mini_os::init_state_with_full(
        &db_path, &static_dir, 16 * 1024 * 1024, 3600, 1000.0, 1000, 1000.0, 1000, false,
    );
    mini_os::build_app(state)
}

/// 带登录态的路由：新建用户 + session，返回 (Router, Cookie 头值)。
fn build_router_authed() -> (axum::Router, String) {
    let n = ROUTER_SEQ.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
    let dir = std::env::temp_dir().join(format!(
        "mini_os_handlers_deep_auth_{}_{}",
        std::process::id(),
        n
    ));
    std::fs::create_dir_all(&dir).expect("create tmp dir");
    let db_path = dir.join("t.db").to_string_lossy().to_string();
    let static_dir = dir.join("static").to_string_lossy().to_string();
    let _ = std::fs::create_dir_all(&static_dir);
    let state = mini_os::init_state_with_full(
        &db_path, &static_dir, 16 * 1024 * 1024, 3600, 1000.0, 1000, 1000.0, 1000, false,
    );
    let token = {
        let conn = state.db.lock().expect("db lock");
        let hash = mini_os::auth::hash_password("pw-for-test").expect("hash");
        conn.execute(
            "INSERT INTO users(username, password_hash, is_admin, role) VALUES(?1, ?2, 0, 'editor')",
            rusqlite::params!["deep_tester", hash],
        )
        .expect("insert user");
        let id: i64 = conn
            .query_row("SELECT id FROM users WHERE username='deep_tester'", [], |r| r.get(0))
            .expect("user id");
        mini_os::auth::create_session(&conn, id, 3600).expect("session")
    };
    let cookie = format!("mini_os_session={}", token);
    (mini_os::build_app(state), cookie)
}

#[tokio::test]
async fn health_returns_ok_and_version() {
    let resp = health().await.into_response();
    assert_eq!(resp.status(), StatusCode::OK);

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .expect("读取 health 响应体失败");
    let v: serde_json::Value = serde_json::from_slice(&body).expect("health 响应不是合法 JSON");

    assert_eq!(v["status"], "ok");
    assert!(v["version"].is_string());
    assert!(!v["version"].as_str().unwrap().is_empty());
}

#[test]
fn apps_registry_contains_files_editor_terminal() {
    let apps = apps_registry();
    assert_eq!(apps.len(), 6);

    let ids: Vec<&str> = apps.iter().map(|a| a.id.as_str()).collect();
    assert!(ids.contains(&"files"));
    assert!(ids.contains(&"editor"));
    assert!(ids.contains(&"terminal"));
    assert!(ids.contains(&"settings"));
    assert!(ids.contains(&"about"));
    assert!(ids.contains(&"users"));

    let files = apps.iter().find(|a| a.id == "files").expect("缺少 files 应用");
    assert_eq!(files.name, "文件管理器");
    assert_eq!(files.description, "浏览与管理虚拟文件系统");
}

// percent_encode 是 src/handlers.rs 私有函数，不可直调；
// 其行为由下面的上传文件名 multipart 测试在 HTTP 层覆盖。


#[tokio::test]
async fn download_query_rejects_dotdot_traversal() {
    let (router, cookie) = build_router_authed();

    let req = Request::builder()
        .uri("/api/files/download?path=..%2F..%2Fetc%2Fpasswd")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = tower::ServiceExt::oneshot(router, req).await.unwrap();
    assert_ne!(resp.status(), StatusCode::OK);

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert!(v["error"].is_string());
    assert_eq!(v["error"], "非法路径");
}

#[tokio::test]
async fn download_query_rejects_absolute_illegal_path() {
    let (router, cookie) = build_router_authed();

    let req = Request::builder()
        .uri("/api/files/download?path=/")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = tower::ServiceExt::oneshot(router, req).await.unwrap();
    assert_ne!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert!(v["error"].is_string());
}

#[tokio::test]
async fn upload_query_rejects_overlong_filename() {
    let (router, cookie) = build_router_authed();
    let long_name = "a".repeat(201);
    let boundary = "minios-test-boundary";
    let body_text = format!(
        "--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{f}\"\r\nContent-Type: application/octet-stream\r\n\r\nhello\r\n--{b}--\r\n",
        b = boundary,
        f = long_name
    );

    let req = Request::builder()
        .uri("/api/files/upload?path=/")
        .method(axum::http::Method::POST)
        .header("cookie", &cookie)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .body(Body::from(body_text))
        .unwrap();
    let resp = tower::ServiceExt::oneshot(router, req).await.unwrap();
    assert_ne!(resp.status(), StatusCode::OK);

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(v["error"], "文件名过长");
}

#[tokio::test]
async fn upload_query_rejects_control_char_filename() {
    let (router, cookie) = build_router_authed();
    let boundary = "minios-test-boundary";
    // NUL 无法通过 multipart 传输（multer 解析不到文件名），改用同样被 sanitize_filename
    // 拒绝的 "/"（"文件名含非法字符"），覆盖同一校验分支
    let bad_name = "evil/name.txt";
    let body_text = format!(
        "--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{f}\"\r\nContent-Type: application/octet-stream\r\n\r\nhello\r\n--{b}--\r\n",
        b = boundary,
        f = bad_name
    );

    let req = Request::builder()
        .uri("/api/files/upload?path=/")
        .method(axum::http::Method::POST)
        .header("cookie", &cookie)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .body(Body::from(body_text))
        .unwrap();
    let resp = tower::ServiceExt::oneshot(router, req).await.unwrap();
    assert_ne!(resp.status(), StatusCode::OK);

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(v["error"], "文件名含非法字符");
}

#[tokio::test]
async fn upload_query_accepts_chinese_filename() {
    let (router, cookie) = build_router_authed();
    let boundary = "minios-test-boundary";
    let body_text = format!(
        "--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"报告.txt\"\r\nContent-Type: application/octet-stream\r\n\r\nhello\r\n--{b}--\r\n",
        b = boundary
    );

    let req = Request::builder()
        .uri("/api/files/upload?path=/")
        .method(axum::http::Method::POST)
        .header("cookie", &cookie)
        .header(
            "content-type",
            format!("multipart/form-data; boundary={}", boundary),
        )
        .body(Body::from(body_text))
        .unwrap();
    let resp = tower::ServiceExt::oneshot(router, req).await.unwrap();

    assert_eq!(resp.status(), StatusCode::CREATED); // 上传成功返回 201

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert!(v.get("error").is_none());
}

#[tokio::test]
async fn download_query_dot_only_is_illegal() {
    let (router, cookie) = build_router_authed();

    let req = Request::builder()
        .uri("/api/files/download?path=.")
        .header("cookie", &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = tower::ServiceExt::oneshot(router, req).await.unwrap();
    let status = resp.status();

    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(v["error"], "非法文件名");
    assert_ne!(status, StatusCode::OK);
}

#[tokio::test]
async fn concurrent_health_requests_all_succeed() {
    let router = Arc::new(build_router());
    let mut handles = Vec::new();

    for _ in 0..16 {
        let r = Arc::clone(&router);
        handles.push(tokio::spawn(async move {
            let req = Request::builder()
                .uri("/api/health")
                .body(Body::empty())
                .unwrap();
            let svc = (*r).clone();
            let resp = tower::ServiceExt::oneshot(svc, req).await.unwrap();
            resp.status()
        }));
    }

    let mut ok = 0;
    for h in handles {
        if h.await.unwrap() == StatusCode::OK {
            ok += 1;
        }
    }
    assert_eq!(ok, 16);
}

#[test]
fn query_structs_deserialize_none_by_default() {
    let up: UploadQuery = serde_json::from_str("{}").expect("UploadQuery 反序列化失败");
    assert!(up.path.is_none());

    let down: DownloadQuery = serde_json::from_str("{}").expect("DownloadQuery 反序列化失败");
    assert!(down.path.is_none());

    let fs: FsQuery = serde_json::from_str("{}").expect("FsQuery 反序列化失败");
    assert!(fs.parent_id.is_none());
}

#[test]
fn query_structs_deserialize_provided_values() {
    let up: UploadQuery =
        serde_json::from_str(r#"{"path":"a/b.txt"}"#).expect("UploadQuery 反序列化失败");
    assert_eq!(up.path.as_deref(), Some("a/b.txt"));

    let down: DownloadQuery =
        serde_json::from_str(r#"{"path":"报告.txt"}"#).expect("DownloadQuery 反序列化失败");
    assert_eq!(down.path.as_deref(), Some("报告.txt"));

    let fs: FsQuery = serde_json::from_str(r#"{"parent_id":7}"#).expect("FsQuery 反序列化失败");
    assert_eq!(fs.parent_id, Some(7));
}