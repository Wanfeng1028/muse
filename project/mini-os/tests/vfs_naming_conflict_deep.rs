use axum::body::{to_bytes, Body};
use axum::http::{header, Request, StatusCode};
use mini_os::{build_app, init_state};
use serde_json::Value;
use tower::ServiceExt;

async fn register(app: &axum::Router, username: &str) -> String {
    let body = serde_json::json!({"username": username, "password": "password123"}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    resp.headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string()
}

async fn read_json(resp: axum::response::Response) -> Value {
    serde_json::from_slice::<Value>(&to_bytes(resp.into_body(), usize::MAX).await.unwrap()).unwrap()
}

async fn api(
    app: &axum::Router,
    cookie: &str,
    method: &str,
    uri: &str,
    body: Option<Value>,
) -> axum::response::Response {
    let mut b = Request::builder()
        .method(method)
        .uri(uri)
        .header(header::COOKIE, cookie);
    if body.is_some() {
        b = b.header(header::CONTENT_TYPE, "application/json");
    }
    let req = b
        .body(Body::from(body.map(|v| v.to_string()).unwrap_or_default()))
        .unwrap();
    app.clone().oneshot(req).await.unwrap()
}

async fn setup() -> (axum::Router, String, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let admin = register(&app, "admin").await;
    let editor = register(&app, "editor").await;
    (app, admin, editor)
}

#[tokio::test]
async fn create_duplicate_name_409() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "hi"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "hi"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CONFLICT);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(
        msg.contains("同名"),
        "error should mention 同名, got: {msg}"
    );
}

#[tokio::test]
async fn create_file_folder_name_clash_409() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "docs", "kind": "folder"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "docs", "kind": "file", "content": "x"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CONFLICT);
}

#[tokio::test]
async fn rename_to_existing_sibling_409() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "aa"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let a = read_json(resp).await;
    let a_id = a.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "b.txt", "kind": "file", "content": "bb"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let b = read_json(resp).await;
    let b_id = b.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{b_id}"),
        Some(serde_json::json!({"name": "a.txt"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CONFLICT);

    let resp = api(&app, &admin, "GET", &format!("/api/fs/{a_id}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn rename_to_own_name_200() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "aa"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let a = read_json(resp).await;
    let a_id = a.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{a_id}"),
        Some(serde_json::json!({"name": "a.txt"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn same_name_different_folders_201() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "d1", "kind": "folder"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let d1 = read_json(resp).await;
    let d1_id = d1.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "d2", "kind": "folder"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let d2 = read_json(resp).await;
    let d2_id = d2.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(
            serde_json::json!({"name": "x.txt", "kind": "file", "content": "1", "parentId": d1_id}),
        ),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(
            serde_json::json!({"name": "x.txt", "kind": "file", "content": "2", "parentId": d2_id}),
        ),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
}

#[tokio::test]
async fn same_name_different_users_201() {
    let (app, admin, editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "admin"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = api(
        &app,
        &editor,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "editor"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
}

#[tokio::test]
async fn rename_trims_then_conflicts_409() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "aa"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "b.txt", "kind": "file", "content": "bb"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let b = read_json(resp).await;
    let b_id = b.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{b_id}"),
        Some(serde_json::json!({"name": "  a.txt  "})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CONFLICT);
}

#[tokio::test]
async fn rename_nonexistent_404() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "PUT",
        "/api/fs/999999",
        Some(serde_json::json!({"name": "z.txt"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn update_content_only_no_conflict_200() {
    let (app, admin, _editor) = setup().await;

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file", "content": "aa"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let a = read_json(resp).await;
    let a_id = a.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{a_id}"),
        Some(serde_json::json!({"content": "hello"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
}
