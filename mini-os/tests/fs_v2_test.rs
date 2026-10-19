use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

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

async fn req(
    app: &Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: &str,
) -> (StatusCode, Value) {
    let builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("cookie", cookie);
    let request = match body {
        Some(v) => builder
            .header("content-type", "application/json")
            .body(axum::body::Body::from(v.to_string()))
            .unwrap(),
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    let resp = app.clone().oneshot(request).await.unwrap();
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let value: Value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    };
    (status, value)
}

async fn register_user(app: &Router, username: &str) -> String {
    let reg = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username": username, "password": "password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(reg).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    resp.headers()
        .get("set-cookie")
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string()
}

async fn create_folder(app: &Router, name: &str, parent_id: Option<i64>, cookie: &str) -> i64 {
    let body = json!({"name": name, "kind": "folder", "parentId": parent_id});
    let (status, v) = req(app, "POST", "/api/fs", Some(body), cookie).await;
    assert_eq!(status, StatusCode::CREATED, "create folder failed: {v}");
    v["id"].as_i64().unwrap()
}

async fn create_file(
    app: &Router,
    name: &str,
    content: &str,
    parent_id: Option<i64>,
    cookie: &str,
) -> i64 {
    let body = json!({"name": name, "kind": "file", "content": content, "parentId": parent_id});
    let (status, v) = req(app, "POST", "/api/fs", Some(body), cookie).await;
    assert_eq!(status, StatusCode::CREATED, "create file failed: {v}");
    v["id"].as_i64().unwrap()
}

// 意图：验证文件能被移动到指定文件夹，返回 parentId 更新，且列表接口能查到。
#[tokio::test]
async fn move_file_to_folder() {
    let (app, cookie) = test_app().await;
    let folder_a = create_folder(&app, "folderA", None, &cookie).await;
    let file1 = create_file(&app, "file1.txt", "hello", None, &cookie).await;

    let (status, v) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{file1}/move"),
        Some(json!({"parent_id": folder_a})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["parentId"].as_i64(), Some(folder_a));

    let (status, list) = req(
        &app,
        "GET",
        &format!("/api/fs?parent_id={folder_a}"),
        None,
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let arr = list.as_array().unwrap();
    assert!(arr.iter().any(|n| n["name"] == "file1.txt"));
}

// 意图：验证文件能被移回根目录，parentId 为 null。
#[tokio::test]
async fn move_to_root() {
    let (app, cookie) = test_app().await;
    let folder_a = create_folder(&app, "folderA", None, &cookie).await;
    let file1 = create_file(&app, "file1.txt", "hello", Some(folder_a), &cookie).await;

    let (status, v) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{file1}/move"),
        Some(json!({"parent_id": null})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(v["parentId"].is_null());
}

// 意图：禁止把文件夹移动到自己的后代中，避免环。
#[tokio::test]
async fn move_into_own_descendant_rejected() {
    let (app, cookie) = test_app().await;
    let folder_a = create_folder(&app, "folderA", None, &cookie).await;
    let folder_b = create_folder(&app, "folderB", Some(folder_a), &cookie).await;

    let (status, _v) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{folder_a}/move"),
        Some(json!({"parent_id": folder_b})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

// 意图：禁止把文件夹移动到自己内部。
#[tokio::test]
async fn move_into_self_rejected() {
    let (app, cookie) = test_app().await;
    let folder_a = create_folder(&app, "folderA", None, &cookie).await;

    let (status, _v) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{folder_a}/move"),
        Some(json!({"parent_id": folder_a})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

// 意图：目标文件夹内已存在同名节点时，移动应返回 409 冲突。
#[tokio::test]
async fn move_name_conflict() {
    let (app, cookie) = test_app().await;
    let folder_a = create_folder(&app, "folderA", None, &cookie).await;
    create_file(&app, "dup.txt", "a", Some(folder_a), &cookie).await;
    let root_dup = create_file(&app, "dup.txt", "b", None, &cookie).await;

    let (status, _v) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{root_dup}/move"),
        Some(json!({"parent_id": folder_a})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CONFLICT);
}

// 意图：跨用户操作不可见，user2 移动 tester 的文件应返回 404。
#[tokio::test]
async fn move_unauthorized_user_404() {
    let (app, cookie) = test_app().await;
    let file1 = create_file(&app, "file1.txt", "hello", None, &cookie).await;
    let user2_cookie = register_user(&app, "user2").await;

    let (status, _v) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{file1}/move"),
        Some(json!({"parent_id": null})),
        &user2_cookie,
    )
    .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

// 意图：viewer 角色无写权限，创建与移动都应被 403 拒绝。
#[tokio::test]
async fn move_viewer_forbidden() {
    let (app, cookie) = test_app().await;
    let _user2_cookie = register_user(&app, "user2").await;

    // 用 admin cookie 取用户列表，找到 user2 的 id
    let (status, users) = req(&app, "GET", "/api/users", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let user2_id = users
        .as_array()
        .unwrap()
        .iter()
        .find(|u| u["username"] == "user2")
        .unwrap()["id"]
        .as_i64()
        .unwrap();

    let (status, _v) = req(
        &app,
        "PUT",
        &format!("/api/users/{user2_id}/role"),
        Some(json!({"role": "viewer"})),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::OK);

    // 角色变更会吊销该用户全部旧会话（set_user_role 的设计），重新登录拿新 cookie
    let login = Request::builder()
        .method("POST")
        .uri("/api/auth/login")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username": "user2", "password": "password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(login).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let user2_cookie = resp
        .headers()
        .get("set-cookie")
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();

    // sanity：viewer 建文件应 403
    let (status, _v) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({"name": "v.txt", "kind": "file", "content": "x", "parentId": null})),
        &user2_cookie,
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);

    // 直接对某个 id 发起 move，也应是 403（无权限，权限检查先于存在性）
    let (status, _v) = req(
        &app,
        "PATCH",
        "/api/fs/1/move",
        Some(json!({"parent_id": null})),
        &user2_cookie,
    )
    .await;
    assert_eq!(status, StatusCode::FORBIDDEN);
}

// 意图：按名称模糊搜索命中多个文件，且每条结果含 path 字段（根目录 path == "/"）。
#[tokio::test]
async fn search_finds_by_name() {
    let (app, cookie) = test_app().await;
    create_file(&app, "项目计划书.md", "a", None, &cookie).await;
    create_file(&app, "计划表.xlsx", "b", None, &cookie).await;
    create_file(&app, "readme.txt", "c", None, &cookie).await;

    let (status, v) = req(&app, "GET", "/api/fs/search?q=计划", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = v.as_array().unwrap();
    assert_eq!(arr.len(), 2);
    for item in arr {
        assert!(item.get("path").is_some());
        assert_eq!(item["path"].as_str(), Some("/"));
    }
}

// 意图：子文件夹中文件的搜索 path 应反映其父路径。
#[tokio::test]
async fn search_in_subfolder_path() {
    let (app, cookie) = test_app().await;
    let folder_a = create_folder(&app, "folderA", None, &cookie).await;
    create_file(&app, "会议纪要.txt", "x", Some(folder_a), &cookie).await;

    let (status, v) = req(&app, "GET", "/api/fs/search?q=会议", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = v.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["path"].as_str(), Some("/folderA"));
}

// 意图：q 为空字符串或缺失 q 参数都应返回 400。
#[tokio::test]
async fn search_empty_q_400() {
    let (app, cookie) = test_app().await;

    let (status, _v) = req(&app, "GET", "/api/fs/search?q=", None, &cookie).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let (status, _v) = req(&app, "GET", "/api/fs/search", None, &cookie).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

// 意图：LIKE 特殊字符需被转义，% 不得作为通配符匹配所有文件。
#[tokio::test]
async fn search_like_injection_safe() {
    let (app, cookie) = test_app().await;
    create_file(&app, "100%.txt", "x", None, &cookie).await;
    create_file(&app, "other.txt", "y", None, &cookie).await;

    let (status, v) = req(&app, "GET", "/api/fs/search?q=%25", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = v.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["name"].as_str(), Some("100%.txt"));
}

// 意图：搜索受用户隔离约束，不得泄露其他用户的文件。
#[tokio::test]
async fn search_cross_user_isolation() {
    let (app, cookie) = test_app().await;
    let user2_cookie = register_user(&app, "user2").await;

    create_file(&app, "user2秘密.txt", "x", None, &user2_cookie).await;

    let (status, v) = req(&app, "GET", "/api/fs/search?q=秘密", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = v.as_array().unwrap();
    assert_eq!(arr.len(), 0);
}

// 意图：limit 参数超范围时被钳制，接口仍返回 200 与数组。
#[tokio::test]
async fn search_limit_clamp() {
    let (app, cookie) = test_app().await;
    create_file(&app, "a.txt", "x", None, &cookie).await;

    let (status, v) = req(&app, "GET", "/api/fs/search?q=a&limit=1000", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    assert!(v.is_array());
}
