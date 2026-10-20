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

#[tokio::test]
async fn concurrent_rename_same_node_all_ok() {
    // 测什么：10 路并发重命名同一节点，全部返回 200，无 500。
    // 为什么：SQLite 连接是 Mutex 串行的，并发写若处理不当会报数据库忙，这里验证串行语义正确。
    let (app, cookie) = test_app().await;

    let (status, node) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "base.txt", "kind": "file" })),
        &cookie,
    ).await;
    assert_eq!(status, StatusCode::CREATED);
    let id = node.get("id").and_then(|v| v.as_i64()).expect("id");

    let mut handles = Vec::new();
    for i in 0..10 {
        let app_clone = app.clone();
        let cookie_clone = cookie.clone();
        let handle = tokio::spawn(async move {
            let uri = format!("/api/fs/{}", id);
            let body = json!({ "name": format!("n{}.txt", i) });
            let payload = body.to_string();
            let request = Request::builder()
                .method("PUT")
                .uri(&uri)
                .header("content-type", "application/json")
                .header("cookie", cookie_clone)
                .body(axum::body::Body::from(payload))
                .unwrap();
            let response = app_clone.oneshot(request).await.unwrap();
            response.status()
        });
        handles.push(handle);
    }

    let mut statuses = Vec::new();
    for handle in handles {
        statuses.push(handle.await.unwrap());
    }

    for status in &statuses {
        assert_eq!(*status, StatusCode::OK);
    }

    let (get_status, get_node) = req(
        &app,
        "GET",
        &format!("/api/fs/{}", id),
        None,
        &cookie,
    ).await;
    assert_eq!(get_status, StatusCode::OK);
    let final_name = get_node.get("name").and_then(|v| v.as_str()).expect("name");
    let expected: Vec<String> = (0..10).map(|i| format!("n{}.txt", i)).collect();
    assert!(expected.iter().any(|n| n == final_name), "unexpected final name: {}", final_name);
}

#[tokio::test]
async fn concurrent_move_same_name_one_wins() {
    // 测什么：并发移动两个同名文件到同一目录，冲突检查串行生效，只有一个能赢。
    // 为什么：这是经典的 check-then-act 竞态，Mutex 串行使得第二个请求的冲突检查能看到第一个的结果，409 语义必须成立。
    let (app, cookie) = test_app().await;

    let (status_a, folder_a) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "A", "kind": "folder" })),
        &cookie,
    ).await;
    assert_eq!(status_a, StatusCode::CREATED);
    let id_a_folder = folder_a.get("id").and_then(|v| v.as_i64()).expect("folder A id");

    let (status_b, folder_b) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "B", "kind": "folder" })),
        &cookie,
    ).await;
    assert_eq!(status_b, StatusCode::CREATED);
    let id_b_folder = folder_b.get("id").and_then(|v| v.as_i64()).expect("folder B id");

    let (status_dup_a, node_dup_a) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "dup.txt", "kind": "file", "parentId": id_a_folder })),
        &cookie,
    ).await;
    assert_eq!(status_dup_a, StatusCode::CREATED);
    let id_a = node_dup_a.get("id").and_then(|v| v.as_i64()).expect("dup a id");

    let (status_dup_b, node_dup_b) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({ "name": "dup.txt", "kind": "file", "parentId": id_b_folder })),
        &cookie,
    ).await;
    assert_eq!(status_dup_b, StatusCode::CREATED);
    let id_b = node_dup_b.get("id").and_then(|v| v.as_i64()).expect("dup b id");

    let app_a = app.clone();
    let cookie_a = cookie.clone();
    let fut_a = async move {
        let uri = format!("/api/fs/{}/move", id_a);
        let payload = json!({ "parent_id": Value::Null }).to_string();
        let request = Request::builder()
            .method("PATCH")
            .uri(&uri)
            .header("content-type", "application/json")
            .header("cookie", cookie_a)
            .body(axum::body::Body::from(payload))
            .unwrap();
        let response = app_a.oneshot(request).await.unwrap();
        response.status()
    };

    let app_b = app.clone();
    let cookie_b = cookie.clone();
    let fut_b = async move {
        let uri = format!("/api/fs/{}/move", id_b);
        let payload = json!({ "parent_id": Value::Null }).to_string();
        let request = Request::builder()
            .method("PATCH")
            .uri(&uri)
            .header("content-type", "application/json")
            .header("cookie", cookie_b)
            .body(axum::body::Body::from(payload))
            .unwrap();
        let response = app_b.oneshot(request).await.unwrap();
        response.status()
    };

    let (status_1, status_2) = tokio::join!(fut_a, fut_b);
    let mut sorted = [status_1, status_2];
    sorted.sort_by_key(|s| s.as_u16());
    assert_eq!(sorted[0], StatusCode::OK);
    assert_eq!(sorted[1], StatusCode::CONFLICT);
}