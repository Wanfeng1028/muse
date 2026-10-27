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

async fn register_and_cookie(app: &Router) -> String {
    let body = json!({"username": "tester", "password": "password123"}).to_string();
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/register")
                .header("content-type", "application/json")
                .body(axum::body::Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    resp.headers()
        .get("set-cookie")
        .expect("set-cookie header missing")
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string()
}

async fn create_event(app: &Router, cookie: &str) {
    let body = json!({"title": "t", "startsAt": "2026-10-25T10:00"}).to_string();
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/events")
                .header("content-type", "application/json")
                .header("cookie", cookie)
                .body(axum::body::Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
}

async fn req(
    app: &Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<&str>,
) -> (StatusCode, Value) {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let body_bytes = match body {
        Some(b) => {
            builder = builder.header("content-type", "application/json");
            axum::body::Body::from(b.to_string())
        }
        None => axum::body::Body::empty(),
    };
    let resp = app
        .clone()
        .oneshot(builder.body(body_bytes).unwrap())
        .await
        .unwrap();
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), 1024 * 1024).await.unwrap();
    let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, value)
}

#[tokio::test]
async fn no_param_list_returns_created_event() {
    let app = test_app();
    let cookie = register_and_cookie(&app).await;
    create_event(&app, &cookie).await;
    let (status, value) = req(&app, "GET", "/api/events", None, Some(&cookie)).await;
    assert_eq!(status, StatusCode::OK);
    let events = value.as_array().expect("events should be an array");
    assert!(!events.is_empty());
    assert!(events.iter().any(|e| e["title"] == "t"));
}

#[tokio::test]
async fn only_to_list_returns_200() {
    let app = test_app();
    let cookie = register_and_cookie(&app).await;
    create_event(&app, &cookie).await;
    let (status, value) = req(
        &app,
        "GET",
        "/api/events?to=2026-12-31",
        None,
        Some(&cookie),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let events = value.as_array().expect("events should be an array");
    assert!(events.iter().any(|e| e["title"] == "t"));
}

#[tokio::test]
async fn explicit_bad_from_still_400() {
    let app = test_app();
    let cookie = register_and_cookie(&app).await;
    let (status, _) = req(
        &app,
        "GET",
        "/api/events?from=2026-02-30&to=2026-03-01",
        None,
        Some(&cookie),
    )
    .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn no_param_empty_list_returns_200_empty() {
    let app = test_app();
    let cookie = register_and_cookie(&app).await;
    let (status, value) = req(&app, "GET", "/api/events", None, Some(&cookie)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(value, json!([]));
}
