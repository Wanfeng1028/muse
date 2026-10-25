use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use tower::ServiceExt;

async fn register_and_get_cookie(app: &axum::Router) -> String {
    let body = serde_json::json!({
        "username": "wsuser",
        "password": "password123"
    });
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(serde_json::to_vec(&body).unwrap()))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .expect("register must set cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

fn ws_upgrade_request(cookie: Option<&str>, version: &str, upgrade: &str) -> Request<Body> {
    let mut builder = Request::builder()
        .method(Method::GET)
        .uri("/ws")
        .header("connection", "upgrade")
        .header("upgrade", upgrade)
        .header("sec-websocket-version", version)
        .header("sec-websocket-key", "dGhlIHNhbXBsZSBub25jZQ==");
    if let Some(c) = cookie {
        builder = builder.header(header::COOKIE, c);
    }
    builder.body(Body::empty()).unwrap()
}

#[tokio::test]
async fn ws_requires_auth() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);

    let req = ws_upgrade_request(None, "13", "websocket");
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(json["error"], "未登录");
}

#[tokio::test]
async fn ws_missing_upgrade_headers_returns_400() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_get_cookie(&app).await;

    let req = Request::builder()
        .method(Method::GET)
        .uri("/ws")
        .header(header::COOKIE, &cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn ws_wrong_version_rejected() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_get_cookie(&app).await;

    let req = ws_upgrade_request(Some(&cookie), "12", "websocket");
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn ws_wrong_upgrade_protocol_rejected() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_get_cookie(&app).await;

    let req = ws_upgrade_request(Some(&cookie), "13", "h2c");
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn ws_valid_headers_reach_upgrade_stage_expect_426() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_get_cookie(&app).await;

    // 426 (UPGRADE_REQUIRED) 恰好证明四个 WebSocket 头校验全部通过：
    // 任一头非法会先返回 400。axum 的 WebSocketUpgrade 在校验完四个头后
    // 会从请求扩展里取 hyper::upgrade::OnUpgrade，缺失时映射为 426。
    // tower::ServiceExt::oneshot 没有真实 hyper 连接，扩展里没有 OnUpgrade，
    // 因此这里只能到达升级阶段并返回 426；101 只在真实 TCP 连接升级时出现。
    let req = ws_upgrade_request(Some(&cookie), "13", "websocket");
    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UPGRADE_REQUIRED);
}

#[tokio::test]
async fn ws_metrics_inc_dec_render() {
    let metrics = mini_os::metrics::Metrics::new();
    metrics.ws_inc();
    metrics.ws_inc();
    metrics.ws_dec();
    let out = metrics.render();
    assert!(
        out.lines().any(|l| l == "ws_connections 1"),
        "expected ws_connections 1 in:\n{out}"
    );

    metrics.ws_dec();
    let out2 = metrics.render();
    assert!(
        out2.lines().any(|l| l == "ws_connections 0"),
        "expected ws_connections 0 in:\n{out2}"
    );
}

#[tokio::test]
async fn ws_metrics_dec_without_inc_documents_behavior() {
    let metrics = mini_os::metrics::Metrics::new();
    metrics.ws_dec();
    let out = metrics.render();
    assert!(
        out.lines().any(|l| l == "ws_connections -1"),
        "expected ws_connections -1 in:\n{out}"
    );
}
