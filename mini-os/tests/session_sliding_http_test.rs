//! session_sliding_http_test — 滑动续期命中后中间件重发 Set-Cookie 的 HTTP 级测试
use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use mini_os::auth::{hash_token, now_epoch_secs};
use mini_os::{build_app, init_state};
use serde_json::json;
use tower::ServiceExt;

#[tokio::test]
async fn middleware_reissues_cookie_when_session_renewed() {
    // 1. 初始化状态与构建应用
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());

    // 2. 注册用户 httprenew1，提取 Set-Cookie 首段作为后续请求的 Cookie
    let body = json!({"username": "httprenew1", "password": "secret123"}).to_string();
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);

    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap();
    let cookie_pair = set_cookie.split(';').next().unwrap();
    let token = cookie_pair.split('=').nth(1).unwrap();

    // 3. 在数据库中手动缩短该会话的过期时间至 10 秒后，以触发滑动续期
    {
        let conn = state.db.lock().unwrap();
        conn.execute(
            "UPDATE sessions SET expires_at = ?1 WHERE token_hash = ?2",
            rusqlite::params![now_epoch_secs() + 10, hash_token(token)],
        )
        .unwrap();
    }

    // 4. 携带 Cookie 请求 /api/fs，断言中间件续期后重发 Set-Cookie
    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/fs")
        .header(header::COOKIE, cookie_pair)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let renewed_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap();
    assert!(renewed_cookie.contains("mini_os_session="));
    assert!(renewed_cookie.contains("Max-Age=604800"));

    // 5. 注册新用户 httprenew2，使用其新鲜会话请求 /api/fs，断言未续期不重发 Set-Cookie
    let body = json!({"username": "httprenew2", "password": "secret123"}).to_string();
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);

    let set_cookie2 = resp
        .headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap();
    let cookie_pair2 = set_cookie2.split(';').next().unwrap();

    let req = Request::builder()
        .method(Method::GET)
        .uri("/api/fs")
        .header(header::COOKIE, cookie_pair2)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert!(resp.headers().get(header::SET_COOKIE).is_none());
}
