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
    cookie: Option<&str>,
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
        StatusCode::OK,
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

async fn register_second(app: &Router, username: &str) -> String {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("no set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

#[tokio::test]
async fn register_login_me_logout_flow() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(app.clone(), "GET", "/api/auth/setup-needed", None, None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = body_json(resp).await;
    assert_eq!(v.get("needed").and_then(|x| x.as_bool()), Some(true));

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "alice", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("no set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    assert!(
        set_cookie.contains("mini_os_session="),
        "missing cookie: {}",
        set_cookie
    );
    let cookie = set_cookie.split(';').next().unwrap().to_string();
    let v = body_json(resp).await;
    assert_eq!(v.get("username").and_then(|x| x.as_str()), Some("alice"));

    let resp = raw_request(app.clone(), "GET", "/api/me", None, Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = body_json(resp).await;
    assert_eq!(v.get("username").and_then(|x| x.as_str()), Some("alice"));
    assert_eq!(v.get("isAdmin").and_then(|x| x.as_bool()), Some(true));

    let resp = raw_request(app.clone(), "POST", "/api/auth/logout", None, Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(app.clone(), "GET", "/api/me", None, Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn register_duplicate_409() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "bob", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "bob", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CONFLICT);
    let v = body_json(resp).await;
    let err = v.get("error").and_then(|x| x.as_str()).unwrap_or("");
    assert!(
        err.contains("已存在"),
        "error should mention 已存在, got {:?}",
        err
    );
}

#[tokio::test]
async fn register_bad_input() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "ab", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "short username should 400"
    );

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "bad name!", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "invalid chars should 400"
    );

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "legacy", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "legacy name should 400"
    );

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "shorty", "password": "short"})),
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "short password should 400"
    );
}

#[tokio::test]
async fn login_wrong_password_401() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": "carol", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({"username": "carol", "password": "wrongpass"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let v = body_json(resp).await;
    assert_eq!(
        v.get("error").and_then(|x| x.as_str()),
        Some("用户名或密码错误")
    );

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({"username": "nobody", "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let v = body_json(resp).await;
    assert_eq!(
        v.get("error").and_then(|x| x.as_str()),
        Some("用户名或密码错误")
    );
}

#[tokio::test]
async fn legacy_user_cannot_login() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({"username": "legacy", "password": "anypassword"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn second_user_not_admin() {
    let (app, _dave_cookie) = authed_app("dave").await;
    let erin_cookie = register_second(&app, "erin").await;

    let resp = raw_request(app.clone(), "GET", "/api/me", None, Some(&erin_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = body_json(resp).await;
    assert_eq!(v.get("username").and_then(|x| x.as_str()), Some("erin"));
    assert_eq!(v.get("isAdmin").and_then(|x| x.as_bool()), Some(false));
}

#[tokio::test]
async fn migrate_legacy_once() {
    let (app, cookie) = authed_app("frank").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/migrate-legacy",
        None,
        Some(&cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = body_json(resp).await;
    assert_eq!(v.get("migrated").and_then(|x| x.as_bool()), Some(true));

    let resp = raw_request(app.clone(), "GET", "/api/fs", None, Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let v = body_json(resp).await;
    // GET /api/fs 返回裸 JSON 数组
    let arr = v.as_array().cloned().unwrap_or_default();
    let names: Vec<String> = arr
        .iter()
        .filter_map(|n| {
            n.get("name")
                .and_then(|x| x.as_str())
                .map(|s| s.to_string())
        })
        .collect();
    assert!(
        names.iter().any(|n| n == "Desktop"),
        "expected Desktop in {:?}",
        names
    );

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/migrate-legacy",
        None,
        Some(&cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::GONE);
}

#[tokio::test]
async fn unauthenticated_api_401() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(app.clone(), "GET", "/api/fs", None, None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

    let resp = raw_request(app.clone(), "GET", "/api/health", None, None).await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(app.clone(), "GET", "/metrics", None, None).await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = raw_request(app.clone(), "POST", "/api/auth/logout", None, None).await;
    assert_eq!(resp.status(), StatusCode::OK);
}
