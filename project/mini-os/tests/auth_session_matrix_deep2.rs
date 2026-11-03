use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn register(app: &axum::Router, username: &str) -> (Value, String) {
    let body = serde_json::to_vec(&json!({
        "username": username,
        "password": "password123",
    }))
    .unwrap();
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    (v, cookie)
}

async fn login(app: &axum::Router, username: &str) -> String {
    let body = serde_json::to_vec(&json!({
        "username": username,
        "password": "password123",
    }))
    .unwrap();
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
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

async fn json_body(resp: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

fn get_with_cookie(uri: &str, cookie: Option<&str>) -> Request<Body> {
    let mut b = Request::builder().method(Method::GET).uri(uri);
    if let Some(c) = cookie {
        b = b.header(header::COOKIE, c);
    }
    b.body(Body::empty()).unwrap()
}

fn put_json(uri: &str, cookie: Option<&str>, body: &Value) -> Request<Body> {
    let mut b = Request::builder()
        .method(Method::PUT)
        .uri(uri)
        .header(header::CONTENT_TYPE, "application/json");
    if let Some(c) = cookie {
        b = b.header(header::COOKIE, c);
    }
    b.body(Body::from(serde_json::to_vec(body).unwrap()))
        .unwrap()
}

fn post_json(uri: &str, cookie: Option<&str>, body: &Value) -> Request<Body> {
    let mut b = Request::builder()
        .method(Method::POST)
        .uri(uri)
        .header(header::CONTENT_TYPE, "application/json");
    if let Some(c) = cookie {
        b = b.header(header::COOKIE, c);
    }
    b.body(Body::from(serde_json::to_vec(body).unwrap()))
        .unwrap()
}

#[tokio::test]
async fn expired_session_rejected_and_row_cleaned() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state.clone());

    let (user, _cookie) = register(&app, "matrixexpired").await;
    let user_id = user["id"].as_i64().unwrap();

    let token = {
        let conn = state.db.lock().unwrap();
        mini_os::auth::create_session(&conn, user_id, -10).unwrap()
    };

    // 注册本身也会创建一个会话，所以 /api/me 之前 sessions 表里不止过期会话这一行。
    // 记录调用前的行数，之后只断言过期会话那一行被删除（before - after == 1）。
    let before: i64 = {
        let conn = state.db.lock().unwrap();
        conn.query_row("SELECT COUNT(*) FROM sessions", [], |r| r.get::<_, i64>(0))
            .unwrap()
    };

    let cookie = format!("mini_os_session={token}");
    let resp = app
        .clone()
        .oneshot(get_with_cookie("/api/me", Some(&cookie)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "未登录");

    let conn = state.db.lock().unwrap();
    let after: i64 = conn
        .query_row("SELECT COUNT(*) FROM sessions", [], |r| r.get::<_, i64>(0))
        .unwrap();
    assert_eq!(before - after, 1);

    // 过期 token 对应的行已被清理。
    let expired_hash = mini_os::auth::hash_token(&token);
    let remaining: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sessions WHERE token_hash = ?1",
            rusqlite::params![expired_hash],
            |r| r.get::<_, i64>(0),
        )
        .unwrap();
    assert_eq!(remaining, 0);
}

#[tokio::test]
async fn set_role_revokes_old_sessions() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state.clone());

    let (admin, admin_cookie) = register(&app, "matrixroleadmin").await;
    assert_eq!(admin["role"].as_str().unwrap(), "admin");

    let (user2, user2_cookie) = register(&app, "matrixroleuser2").await;
    let user2_id = user2["id"].as_i64().unwrap();

    let resp = app
        .clone()
        .oneshot(put_json(
            &format!("/api/users/{user2_id}/role"),
            Some(&admin_cookie),
            &json!({"role": "viewer"}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let v = json_body(resp).await;
    assert_eq!(v["id"].as_i64().unwrap(), user2_id);
    assert_eq!(v["role"].as_str().unwrap(), "viewer");

    let resp = app
        .clone()
        .oneshot(get_with_cookie("/api/me", Some(&user2_cookie)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "未登录");
}

#[tokio::test]
async fn unknown_role_string_fails_closed_to_viewer() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state.clone());

    let (user, cookie) = register(&app, "matrixunknownrole").await;
    let user_id = user["id"].as_i64().unwrap();

    {
        let conn = state.db.lock().unwrap();
        // users.role 上有 CHECK(role IN ('admin','editor','viewer')) 约束，正常写入
        // 无法产生非法角色。这里用 PRAGMA ignore_check_constraints 临时关闭约束来
        // 模拟"脏数据"场景，以覆盖 rbac_middleware 中 unwrap_or(Viewer) 的 fail-closed 分支。
        // PRAGMA 按连接生效，state.db 锁住的是同一个 Connection，中间件读到的就是这个连接。
        conn.execute("PRAGMA ignore_check_constraints=ON", [])
            .unwrap();
        conn.execute(
            "UPDATE users SET role = 'superuser' WHERE id = ?1",
            rusqlite::params![user_id],
        )
        .unwrap();
    }

    let resp = app
        .clone()
        .oneshot(get_with_cookie("/api/users", Some(&cookie)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "权限不足");

    let resp = app
        .clone()
        .oneshot(get_with_cookie("/api/fs", Some(&cookie)))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
}

#[tokio::test]
async fn missing_cookie_rejected() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);

    let resp = app
        .clone()
        .oneshot(get_with_cookie("/api/me", None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "未登录");
}

#[tokio::test]
async fn empty_cookie_value_rejected() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);

    let resp = app
        .clone()
        .oneshot(get_with_cookie("/api/me", Some("mini_os_session=")))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "未登录");
}

#[tokio::test]
async fn viewer_cannot_create_share() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state.clone());

    let (_admin, admin_cookie) = register(&app, "matrixshareadmin").await;
    let (user2, _user2_cookie) = register(&app, "matrixshareuser2").await;
    let user2_id = user2["id"].as_i64().unwrap();

    let resp = app
        .clone()
        .oneshot(post_json(
            "/api/fs",
            Some(&admin_cookie),
            &json!({"name": "f.txt", "kind": "file"}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let node = json_body(resp).await;
    let node_id = node["id"].as_i64().unwrap();

    let resp = app
        .clone()
        .oneshot(put_json(
            &format!("/api/users/{user2_id}/role"),
            Some(&admin_cookie),
            &json!({"role": "viewer"}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let user2_cookie = login(&app, "matrixshareuser2").await;

    let resp = app
        .clone()
        .oneshot(post_json(
            "/api/shares",
            Some(&user2_cookie),
            &json!({"node_id": node_id}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "权限不足");
}

#[tokio::test]
async fn editor_cannot_manage_users() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state.clone());

    let (admin, _admin_cookie) = register(&app, "matrixeditoradmin").await;
    let admin_id = admin["id"].as_i64().unwrap();
    assert_eq!(admin["role"].as_str().unwrap(), "admin");

    let (user2, user2_cookie) = register(&app, "matrixeditoruser2").await;
    assert_eq!(user2["role"].as_str().unwrap(), "editor");

    let resp = app
        .clone()
        .oneshot(put_json(
            &format!("/api/users/{admin_id}/role"),
            Some(&user2_cookie),
            &json!({"role": "viewer"}),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let v = json_body(resp).await;
    assert_eq!(v["error"].as_str().unwrap(), "权限不足");
}
