use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;
async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}
async fn raw_request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<String>,
) -> axum::response::Response {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let req = match body {
        Some(v) => {
            builder = builder.header("content-type", "application/json");
            builder.body(axum::body::Body::from(v.to_string())).unwrap()
        }
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    app.oneshot(req).await.unwrap()
}
async fn authed_app(username: &str) -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "register failed for {}",
        username
    );
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("no set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    let cookie = set_cookie.split(';').next().unwrap().to_string();
    assert!(
        cookie.starts_with("mini_os_session="),
        "bad cookie: {}",
        cookie
    );
    (app, cookie)
}
async fn create_node(
    app: &Router,
    cookie: &str,
    name: &str,
    kind: &str,
    parent: Option<i64>,
    content: Option<&str>,
) -> i64 {
    let mut v = json!({"name": name, "kind": kind});
    if let Some(p) = parent {
        v["parentId"] = json!(p);
    }
    if let Some(c) = content {
        v["content"] = json!(c);
    }
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(v),
        Some(cookie.to_string()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "create_node failed for {}",
        name
    );
    body_json(resp).await["id"].as_i64().expect("no id")
}
#[tokio::test]
async fn dir_share_nodeid_path_conflict_folder() {
    let (app, cookie) = authed_app("dir_share_conflict_folder").await;
    let docs_id = create_node(&app, &cookie, "docs", "folder", None, None).await;
    create_node(&app, &cookie, "a.txt", "file", Some(docs_id), Some("hello")).await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type":"dir","path":"/docs","nodeId":docs_id})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = body_json(resp).await;
    assert_eq!(
        body["error"].as_str().unwrap(),
        "node_id 与 path 不能同时指定"
    );
    let resp = raw_request(app, "GET", "/api/shares", None, Some(cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body, json!([]), "expected empty shares after 400");
}
#[tokio::test]
async fn dir_share_nodeid_path_conflict_file() {
    let (app, cookie) = authed_app("dir_share_conflict_file").await;
    let docs_id = create_node(&app, &cookie, "docs", "folder", None, None).await;
    let file_id = create_node(&app, &cookie, "a.txt", "file", Some(docs_id), Some("hello")).await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type":"dir","path":"/docs","nodeId":file_id})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = body_json(resp).await;
    assert_eq!(
        body["error"].as_str().unwrap(),
        "node_id 与 path 不能同时指定"
    );
    let resp = raw_request(app, "GET", "/api/shares", None, Some(cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body, json!([]), "expected empty shares after 400");
}
#[tokio::test]
async fn dir_share_only_path_still_works() {
    let (app, cookie) = authed_app("dir_share_only_path").await;
    let docs_id = create_node(&app, &cookie, "docs", "folder", None, None).await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type":"dir","path":"/docs"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = body_json(resp).await;
    let token = body["token"].as_str().expect("no token");
    assert!(!token.is_empty());
}
#[tokio::test]
async fn dir_share_nodeid_without_path_missing_path() {
    let (app, cookie) = authed_app("dir_share_nodeid_no_path").await;
    let docs_id = create_node(&app, &cookie, "docs", "folder", None, None).await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type":"dir","nodeId":docs_id})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = body_json(resp).await;
    assert_eq!(body["error"].as_str().unwrap(), "目录分享需要 path 参数");
}
#[tokio::test]
async fn file_share_with_path_ignored_still_works() {
    let (app, cookie) = authed_app("file_share_path_ignored").await;
    let docs_id = create_node(&app, &cookie, "docs", "folder", None, None).await;
    let file_id = create_node(&app, &cookie, "a.txt", "file", Some(docs_id), Some("hello")).await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type":"file","nodeId":file_id,"path":"/docs"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
}
#[tokio::test]
async fn file_share_missing_nodeid_400() {
    let (app, cookie) = authed_app("file_share_missing_nodeid").await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type":"file"})),
        Some(cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = body_json(resp).await;
    assert_eq!(body["error"].as_str().unwrap(), "文件分享需要 node_id");
}
