use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

fn test_app() -> Router {
    let state = init_state(":memory:", "static");
    build_app(state)
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

async fn request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
) -> axum::response::Response {
    let mut builder = Request::builder().method(method).uri(uri);
    let req = match body {
        Some(v) => {
            builder = builder.header("content-type", "application/json");
            builder.body(axum::body::Body::from(v.to_string())).unwrap()
        }
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    app.oneshot(req).await.unwrap()
}

#[tokio::test]
async fn health_returns_ok() {
    let app = test_app();
    let resp = request(app, "GET", "/api/health", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    assert_eq!(json["status"], "ok");
    assert_eq!(json["version"], "1.0.0");
}

#[tokio::test]
async fn apps_has_five_entries() {
    let app = test_app();
    let resp = request(app, "GET", "/api/apps", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    let arr = json.as_array().expect("apps should be an array");
    assert_eq!(arr.len(), 5);
    let ids: Vec<String> = arr
        .iter()
        .map(|a| a["id"].as_str().unwrap().to_string())
        .collect();
    for expected in ["files", "editor", "terminal", "settings", "about"] {
        assert!(ids.contains(&expected.to_string()), "missing app {}", expected);
    }
}

#[tokio::test]
async fn create_folder_then_list() {
    let app = test_app();
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "myfolder", "kind": "folder", "content": ""})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    assert_eq!(created["name"], "myfolder");
    assert_eq!(created["kind"], "folder");

    let resp = request(app, "GET", "/api/fs", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let list = body_json(resp).await;
    let arr = list.as_array().expect("fs list should be an array");
    assert!(arr.iter().any(|n| n["name"] == "myfolder"));
}

#[tokio::test]
async fn create_file_then_update_content() {
    let app = test_app();
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "note.txt", "kind": "file", "content": "hello"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    let id = created["id"].as_i64().unwrap().to_string();
    assert_eq!(created["content"], "hello");

    let resp = request(
        app.clone(),
        "PUT",
        &format!("/api/fs/{}", id),
        Some(json!({"content": "updated content"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let updated = body_json(resp).await;
    assert_eq!(updated["content"], "updated content");

    let resp = request(app, "GET", &format!("/api/fs/{}", id), None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let fetched = body_json(resp).await;
    assert_eq!(fetched["content"], "updated content");
}

#[tokio::test]
async fn settings_initial_and_update() {
    let app = test_app();
    let resp = request(app.clone(), "GET", "/api/settings", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    assert!(json.get("theme").is_some(), "settings should contain theme");

    let resp = request(
        app.clone(),
        "PUT",
        "/api/settings",
        Some(json!({"key": "wallpaper", "value": "starfield"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = request(app, "GET", "/api/settings", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    assert_eq!(json["wallpaper"], "starfield");
}

#[tokio::test]
async fn stats_counts_files() {
    let app = test_app();
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "counted.txt", "kind": "file", "content": "abc"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);

    let resp = request(app, "GET", "/api/stats", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let json = body_json(resp).await;
    let files = json["files"].as_u64().unwrap();
    assert!(files >= 1, "expected at least 1 file, got {}", files);
    assert!(json.get("folders").is_some());
    assert!(json.get("totalBytes").is_some());
}

#[tokio::test]
async fn delete_file_then_get_returns_404() {
    let app = test_app();
    let resp = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "temp.txt", "kind": "file", "content": "x"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let created = body_json(resp).await;
    let id = created["id"].as_i64().unwrap().to_string();

    let resp = request(app.clone(), "DELETE", &format!("/api/fs/{}", id), None).await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    let resp = request(app, "GET", &format!("/api/fs/{}", id), None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn invalid_kind_returns_400() {
    let app = test_app();
    let resp = request(
        app,
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "weird", "kind": "banana", "content": ""})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}
