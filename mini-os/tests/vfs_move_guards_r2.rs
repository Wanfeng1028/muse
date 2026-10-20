use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let (status, _body, cookie) = register(&app, "tester", "password123").await;
    assert_eq!(status, StatusCode::CREATED);
    (app, cookie)
}

async fn register(app: &Router, username: &str, password: &str) -> (StatusCode, Value, String) {
    let payload = json!({ "username": username, "password": password });
    let request = Request::builder()
        .method("POST").uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(payload.to_string())).unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let cookie = response.headers().get("set-cookie").and_then(|v| v.to_str().ok())
        .map(|s| s.split(';').next().unwrap_or("").to_string()).unwrap_or_default();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, value, cookie)
}

async fn req(app: &Router, method: &str, uri: &str, body: Option<Value>, cookie: &str) -> (StatusCode, Value) {
    let payload = body.unwrap_or(Value::Null);
    let builder = Request::builder().method(method).uri(uri).header("content-type", "application/json");
    let builder = if cookie.is_empty() { builder } else { builder.header("cookie", cookie) };
    let request = builder.body(axum::body::Body::from(payload.to_string())).unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let value: Value = if bytes.is_empty() { Value::Null } else { serde_json::from_slice(&bytes).unwrap_or(Value::Null) };
    (status, value)
}

async fn create_folder(app: &Router, cookie: &str, name: &str, parent_id: Option<i64>) -> i64 {
    let body = json!({ "name": name, "kind": "folder", "parentId": parent_id });
    let (status, value) = req(app, "POST", "/api/fs", Some(body), cookie).await;
    assert_eq!(status, StatusCode::CREATED, "创建文件夹失败: {:?}", value);
    value["id"].as_i64().expect("响应缺少 id")
}

async fn create_file(app: &Router, cookie: &str, name: &str, parent_id: Option<i64>) -> i64 {
    let body = json!({ "name": name, "kind": "file", "parentId": parent_id });
    let (status, value) = req(app, "POST", "/api/fs", Some(body), cookie).await;
    assert_eq!(status, StatusCode::CREATED, "创建文件失败: {:?}", value);
    value["id"].as_i64().expect("响应缺少 id")
}

#[tokio::test]
async fn move_into_self_400() {
    // 测什么：文件夹不能通过 move 把自己设为自己的父节点。
    // 为什么：这是成环的最直接形式，若被放行则 parent 链立刻自指，
    // 递归删除与路径解析会陷入死循环，必须在入口拦下并返回 400。
    let (app, cookie) = test_app().await;
    let me = create_folder(&app, &cookie, "me", None).await;

    let (status, _body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", me),
        Some(json!({ "parent_id": me })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "自己移进自己必须返回 400");

    let (get_status, node) = req(&app, "GET", &format!("/api/fs/{}", me), None, &cookie).await;
    assert_eq!(get_status, StatusCode::OK);
    assert_eq!(node["parentId"], Value::Null, "拒绝后节点 parentId 必须保持 null");
}

#[tokio::test]
async fn move_into_descendant_400() {
    // 测什么：沿 parent 链上爬做环检测——父目录不能移动到自己的子孙目录之下。
    // 为什么：树一旦成环，递归删除/路径解析会无限循环，是灾难性 bug；
    // 且被拒绝后节点位置必须原封不动，不能出现半途修改。
    let (app, cookie) = test_app().await;
    let p = create_folder(&app, &cookie, "p", None).await;
    let c = create_folder(&app, &cookie, "c", Some(p)).await;

    let (status, _body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", p),
        Some(json!({ "parent_id": c })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "移进自己后代必须返回 400");

    let (get_status, node) = req(&app, "GET", &format!("/api/fs/{}", p), None, &cookie).await;
    assert_eq!(get_status, StatusCode::OK);
    assert_eq!(node["parentId"], Value::Null, "拒绝后 p 必须仍位于根，parentId 为 null");
    assert_eq!(node["name"], "p");
    assert_eq!(node["kind"], "folder");
}

#[tokio::test]
async fn move_to_file_and_missing_target() {
    // 测什么：移动目标必须是一个存在的文件夹。
    // 为什么：把文件移进普通文件会产生 parent 指向 file 的脏数据，
    // 破坏树结构不变量；指向不存在 id 则会造成悬空引用。两者都要被拒绝。
    let (app, cookie) = test_app().await;
    let f1 = create_file(&app, &cookie, "f1", None).await;
    let f2 = create_file(&app, &cookie, "f2", None).await;

    let (status, _body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", f1),
        Some(json!({ "parent_id": f2 })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "目标不是文件夹必须返回 400");

    let (missing_status, _missing_body) = req(
        &app,
        "PATCH",
        &format!("/api/fs/{}/move", f1),
        Some(json!({ "parent_id": 999999 })),
        &cookie,
    )
    .await;
    assert_eq!(missing_status, StatusCode::NOT_FOUND, "目标不存在必须返回 404");

    let (get_status, node) = req(&app, "GET", &format!("/api/fs/{}", f1), None, &cookie).await;
    assert_eq!(get_status, StatusCode::OK);
    assert_eq!(node["parentId"], Value::Null, "两次失败后 f1 必须仍在根");
    assert_eq!(node["kind"], "file");
}