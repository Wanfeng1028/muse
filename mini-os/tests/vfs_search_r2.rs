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

// 测什么：搜索一个肯定不存在的关键字时，接口返回 200 且 body 是空数组。
// 为什么：无结果是搜索的正常业务状态，用 404 会逼前端把「无结果」当异常处理，属于契约设计错误。
#[tokio::test]
async fn search_empty_result_200() {
    let (app, cookie) = test_app().await;

    let (status, body) = req(
        &app,
        "GET",
        "/api/fs/search?q=zzz-no-such-file-zzz",
        None,
        &cookie,
    )
    .await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, json!([]));
    let arr = body.as_array().expect("body should be a JSON array");
    assert_eq!(arr.len(), 0);
}

// 测什么：按名称子串搜索能命中已创建的文件。
// 为什么：搜索是文件管理核心入口，子串匹配是底线能力，必须验证能按部分名称找回文件。
#[tokio::test]
async fn search_finds_by_name_substring() {
    let (app, cookie) = test_app().await;

    let (status, created) = req(
        &app,
        "POST",
        "/api/fs",
        Some(json!({
            "name": "quarter-report-2026.txt",
            "kind": "file",
            "content": "hello"
        })),
        &cookie,
    )
    .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(created["name"], "quarter-report-2026.txt");
    assert_eq!(created["kind"], "file");

    let (status, body) = req(&app, "GET", "/api/fs/search?q=report", None, &cookie).await;
    assert_eq!(status, StatusCode::OK);
    let arr = body.as_array().expect("body should be a JSON array");
    assert!(
        arr.iter().any(|node| node["name"] == "quarter-report-2026.txt"),
        "expected search result to contain quarter-report-2026.txt, got: {:?}",
        body
    );
}