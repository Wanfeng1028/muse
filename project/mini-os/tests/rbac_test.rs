use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX)
        .await
        .expect("读取响应体失败");
    serde_json::from_slice(&bytes).expect("解析 JSON 失败")
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
        Some(v) => builder
            .header("content-type", "application/json")
            .body(axum::body::Body::from(v.to_string()))
            .expect("构造请求失败"),
        None => builder
            .body(axum::body::Body::empty())
            .expect("构造请求失败"),
    };
    app.oneshot(req).await.expect("请求执行失败")
}

/// 注册并返回 (user_id, cookie)；首个注册者为 admin
async fn register(app: &Router, username: &str) -> (i64, String) {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED, "注册应返回 201");
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("注册响应应包含 Set-Cookie")
        .to_str()
        .expect("Set-Cookie 应为合法字符串")
        .to_string();
    let cookie = set_cookie
        .split(';')
        .next()
        .expect("Set-Cookie 应包含会话 cookie")
        .to_string();
    assert!(
        cookie.starts_with("mini_os_session="),
        "会话 cookie 名称应为 mini_os_session"
    );
    let json = body_json(resp).await;
    let id = json
        .get("id")
        .and_then(|v| v.as_i64())
        .expect("响应应包含 id");
    (id, cookie)
}

/// 登录返回 cookie
async fn login(app: &Router, username: &str) -> String {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({"username": username, "password": "password123"})),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK, "登录应返回 200");
    let set_cookie = resp
        .headers()
        .get("set-cookie")
        .expect("登录响应应包含 Set-Cookie")
        .to_str()
        .expect("Set-Cookie 应为合法字符串")
        .to_string();
    set_cookie
        .split(';')
        .next()
        .expect("Set-Cookie 应包含会话 cookie")
        .to_string()
}

/// admin 把某用户设为某角色，返回状态码
async fn set_role(app: &Router, admin_cookie: &str, user_id: i64, role: &str) -> StatusCode {
    let resp = raw_request(
        app.clone(),
        "PUT",
        &format!("/api/users/{}/role", user_id),
        Some(json!({"role": role})),
        Some(admin_cookie),
    )
    .await;
    resp.status()
}

#[tokio::test]
async fn viewer_cannot_write_but_can_read() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (_admin_id, admin_cookie) = register(&app, "admin").await;
    let (v1_id, _v1_cookie) = register(&app, "viewer1").await;

    let status = set_role(&app, &admin_cookie, v1_id, "viewer").await;
    assert_eq!(status, StatusCode::OK, "设置 viewer 角色应返回 200");

    let v1_cookie = login(&app, "viewer1").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "a.txt", "kind": "file"})),
        Some(&v1_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "viewer 写入应返回 403"
    );
    let json = body_json(resp).await;
    let reason = json
        .get("reason")
        .and_then(|v| v.as_str())
        .expect("403 响应应包含 reason 字段");
    assert!(
        reason.contains("文件写入"),
        "reason 应包含「文件写入」，实际为：{}",
        reason
    );

    let resp = raw_request(app.clone(), "GET", "/api/fs", None, Some(&v1_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "viewer 读取应返回 200");
}

#[tokio::test]
async fn viewer_cannot_create_share() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (_admin_id, admin_cookie) = register(&app, "admin").await;
    let (v1_id, _v1_cookie) = register(&app, "viewer1").await;

    let status = set_role(&app, &admin_cookie, v1_id, "viewer").await;
    assert_eq!(status, StatusCode::OK, "设置 viewer 角色应返回 200");

    let v1_cookie = login(&app, "viewer1").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": 1})),
        Some(&v1_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "viewer 创建分享应返回 403"
    );
    let json = body_json(resp).await;
    let reason = json
        .get("reason")
        .and_then(|v| v.as_str())
        .expect("403 响应应包含 reason 字段");
    assert!(
        reason.contains("分享创建"),
        "reason 应包含「分享创建」，实际为：{}",
        reason
    );
}

#[tokio::test]
async fn editor_can_write_and_share() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (_admin_id, _admin_cookie) = register(&app, "admin").await;
    let (_e1_id, e1_cookie) = register(&app, "editor1").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "doc.txt", "kind": "file", "content": "hi"})),
        Some(&e1_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED, "editor 写入应返回 201");
    let json = body_json(resp).await;
    let node_id = json
        .get("id")
        .and_then(|v| v.as_i64())
        .expect("创建文件响应应包含 id");

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": node_id})),
        Some(&e1_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "editor 创建分享应返回 201"
    );

    let resp = raw_request(app.clone(), "GET", "/api/shares", None, Some(&e1_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "列出分享应返回 200");
    let json = body_json(resp).await;
    let arr = json.as_array().expect("分享列表应为数组");
    assert!(!arr.is_empty(), "分享列表长度应 ≥ 1");
    let has_owner = arr
        .iter()
        .any(|item| item.get("ownerUsername").and_then(|v| v.as_str()) == Some("editor1"));
    assert!(has_owner, "分享列表应包含 ownerUsername 为 e1 的项");
}

#[tokio::test]
async fn non_admin_cannot_manage_users() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (_admin_id, _admin_cookie) = register(&app, "admin").await;
    let (_e1_id, e1_cookie) = register(&app, "editor1").await;

    let resp = raw_request(app.clone(), "GET", "/api/users", None, Some(&e1_cookie)).await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "非 admin 列用户应返回 403"
    );
    let json = body_json(resp).await;
    let reason = json
        .get("reason")
        .and_then(|v| v.as_str())
        .expect("403 响应应包含 reason 字段");
    assert!(
        reason.contains("用户管理"),
        "reason 应包含「用户管理」，实际为：{}",
        reason
    );

    let resp = raw_request(
        app.clone(),
        "PUT",
        "/api/users/1/role",
        Some(json!({"role": "viewer"})),
        Some(&e1_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "非 admin 改角色应返回 403"
    );
}

#[tokio::test]
async fn admin_can_list_users_and_set_role() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (admin_id, admin_cookie) = register(&app, "admin").await;
    let (e2_id, _e2_cookie) = register(&app, "editor2").await;

    let resp = raw_request(app.clone(), "GET", "/api/users", None, Some(&admin_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "admin 列用户应返回 200");
    let json = body_json(resp).await;
    let arr = json.as_array().expect("用户列表应为数组");
    let admin_item = arr
        .iter()
        .find(|item| item.get("id").and_then(|v| v.as_i64()) == Some(admin_id))
        .expect("用户列表应包含 admin");
    assert_eq!(
        admin_item.get("role").and_then(|v| v.as_str()),
        Some("admin"),
        "admin 的 role 应为 admin"
    );
    let e2_item = arr
        .iter()
        .find(|item| item.get("id").and_then(|v| v.as_i64()) == Some(e2_id))
        .expect("用户列表应包含 e2");
    assert_eq!(
        e2_item.get("role").and_then(|v| v.as_str()),
        Some("editor"),
        "e2 的 role 应为 editor"
    );

    let resp = raw_request(
        app.clone(),
        "PUT",
        &format!("/api/users/{}/role", e2_id),
        Some(json!({"role": "viewer"})),
        Some(&admin_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK, "admin 改角色应返回 200");
    let json = body_json(resp).await;
    assert_eq!(
        json.get("role").and_then(|v| v.as_str()),
        Some("viewer"),
        "返回的 role 应为 viewer"
    );

    let e2_cookie = login(&app, "editor2").await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "b.txt", "kind": "file"})),
        Some(&e2_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "降级后 e2 写入应返回 403"
    );
}

#[tokio::test]
async fn cannot_remove_last_admin() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (admin_id, admin_cookie) = register(&app, "admin").await;

    let resp = raw_request(
        app.clone(),
        "PUT",
        &format!("/api/users/{}/role", admin_id),
        Some(json!({"role": "editor"})),
        Some(&admin_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "移除最后一个 admin 应返回 403"
    );
    let json = body_json(resp).await;
    let reason = json
        .get("reason")
        .and_then(|v| v.as_str())
        .expect("403 响应应包含 reason 字段");
    assert!(
        reason.contains("最后一个管理员"),
        "reason 应包含「最后一个管理员」，实际为：{}",
        reason
    );

    let resp = raw_request(app.clone(), "GET", "/api/users", None, Some(&admin_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "列用户应返回 200");
    let json = body_json(resp).await;
    let arr = json.as_array().expect("用户列表应为数组");
    let admin_item = arr
        .iter()
        .find(|item| item.get("id").and_then(|v| v.as_i64()) == Some(admin_id))
        .expect("用户列表应包含 admin");
    assert_eq!(
        admin_item.get("role").and_then(|v| v.as_str()),
        Some("admin"),
        "拒绝后 admin 的 role 应仍为 admin"
    );
}

#[tokio::test]
async fn set_role_revokes_sessions() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (_admin_id, admin_cookie) = register(&app, "admin").await;
    let (e3_id, cookie3) = register(&app, "editor3").await;

    let status = set_role(&app, &admin_cookie, e3_id, "viewer").await;
    assert_eq!(status, StatusCode::OK, "设置 viewer 角色应返回 200");

    let resp = raw_request(app.clone(), "GET", "/api/fs", None, Some(&cookie3)).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "旧会话应返回 401");

    let new_cookie = login(&app, "editor3").await;
    let resp = raw_request(app.clone(), "GET", "/api/fs", None, Some(&new_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "新会话读取应返回 200");
}

#[tokio::test]
async fn share_delete_ownership() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let (_admin_id, admin_cookie) = register(&app, "admin").await;
    let (_e4_id, e4_cookie) = register(&app, "editor4").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "e4.txt", "kind": "file", "content": "x"})),
        Some(&e4_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED, "e4 建文件应返回 201");
    let json = body_json(resp).await;
    let e4_node_id = json
        .get("id")
        .and_then(|v| v.as_i64())
        .expect("创建文件响应应包含 id");

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": e4_node_id})),
        Some(&e4_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED, "e4 建分享应返回 201");
    let json = body_json(resp).await;
    let s1_token = json
        .get("token")
        .and_then(|v| v.as_str())
        .expect("创建分享响应应包含 token")
        .to_string();

    let resp = raw_request(app.clone(), "GET", "/api/shares", None, Some(&e4_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "e4 列分享应返回 200");
    let json = body_json(resp).await;
    let arr = json.as_array().expect("分享列表应为数组");
    let s1_id = arr
        .iter()
        .find(|item| item.get("token").and_then(|v| v.as_str()) == Some(s1_token.as_str()))
        .and_then(|item| item.get("id").and_then(|v| v.as_i64()))
        .expect("分享列表应包含 s1");

    let resp = raw_request(
        app.clone(),
        "DELETE",
        &format!("/api/shares/{}", s1_id),
        None,
        Some(&e4_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::NO_CONTENT,
        "e4 删自己的分享应返回 204"
    );

    let resp = raw_request(
        app.clone(),
        "DELETE",
        &format!("/api/shares/{}", s1_id),
        None,
        Some(&e4_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND, "再次删除应返回 404");

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"name": "admin.txt", "kind": "file", "content": "y"})),
        Some(&admin_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED, "admin 建文件应返回 201");
    let json = body_json(resp).await;
    let admin_node_id = json
        .get("id")
        .and_then(|v| v.as_i64())
        .expect("创建文件响应应包含 id");

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"nodeId": admin_node_id})),
        Some(&admin_cookie),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED, "admin 建分享应返回 201");
    let json = body_json(resp).await;
    let s2_token = json
        .get("token")
        .and_then(|v| v.as_str())
        .expect("创建分享响应应包含 token")
        .to_string();

    let resp = raw_request(app.clone(), "GET", "/api/shares", None, Some(&admin_cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "admin 列分享应返回 200");
    let json = body_json(resp).await;
    let arr = json.as_array().expect("分享列表应为数组");
    let s2_id = arr
        .iter()
        .find(|item| item.get("token").and_then(|v| v.as_str()) == Some(s2_token.as_str()))
        .and_then(|item| item.get("id").and_then(|v| v.as_i64()))
        .expect("分享列表应包含 s2");

    let resp = raw_request(
        app.clone(),
        "DELETE",
        &format!("/api/shares/{}", s2_id),
        None,
        Some(&e4_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "e4 删 admin 的分享应返回 403"
    );
    let json = body_json(resp).await;
    let reason = json
        .get("reason")
        .and_then(|v| v.as_str())
        .expect("403 响应应包含 reason 字段");
    assert!(
        reason.contains("自己创建"),
        "reason 应包含「自己创建」，实际为：{}",
        reason
    );

    let resp = raw_request(
        app.clone(),
        "DELETE",
        &format!("/api/shares/{}", s2_id),
        None,
        Some(&admin_cookie),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::NO_CONTENT,
        "admin 删自己的分享应返回 204"
    );
}
