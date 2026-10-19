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
async fn create_name_whitespace_only_400() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "   ", "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("名称不能为空"), "got error: {}", msg);
}

#[tokio::test]
async fn create_invalid_kind_400() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "x", "kind": "directory"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("kind 必须为"), "got error: {}", msg);
}

#[tokio::test]
async fn create_parent_is_file_400() {
    let (app, admin, _editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "f.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let f = read_json(r).await;
    let fid = f.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"parentId": fid, "name": "child", "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("父节点不是文件夹"), "got error: {}", msg);
}

#[tokio::test]
async fn create_parent_not_found_404() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"parentId": 999999, "name": "x", "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("父节点不存在"), "got error: {}", msg);
}

#[tokio::test]
async fn create_parent_of_other_user_404() {
    let (app, admin, editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "adminfolder", "kind": "folder"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let folder = read_json(r).await;
    let fid = folder.get("id").and_then(|v| v.as_i64()).unwrap();

    let resp = api(
        &app,
        &editor,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"parentId": fid, "name": "x", "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("父节点不存在"), "got error: {}", msg);
}

#[tokio::test]
async fn create_duplicate_name_same_dir_409() {
    // 2026-10-19：同级同名不再允许，第二个创建返回 409。
    let (app, admin, _editor) = setup().await;
    let payload = serde_json::json!({"name": "dup.txt", "kind": "file"});
    let r1 = api(&app, &admin, "POST", "/api/fs", Some(payload.clone())).await;
    assert_eq!(r1.status(), StatusCode::CREATED);

    let r2 = api(&app, &admin, "POST", "/api/fs", Some(payload)).await;
    assert_eq!(r2.status(), StatusCode::CONFLICT);
    let body = read_json(r2).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(
        msg.contains("同名"),
        "error should mention 同名, got: {msg}"
    );
}

#[tokio::test]
async fn create_300_char_name_201_documents() {
    let (app, admin, _editor) = setup().await;
    let long_name: String = "a".repeat(300);
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": long_name, "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    let stored = body.get("name").and_then(|v| v.as_str()).unwrap();
    assert_eq!(stored.len(), 300);
}

#[tokio::test]
async fn create_unicode_name_roundtrip() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "测试文档.txt", "kind": "file", "content": "你好"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    let id = body.get("id").and_then(|v| v.as_i64()).unwrap();
    assert_eq!(
        body.get("name").and_then(|v| v.as_str()).unwrap(),
        "测试文档.txt"
    );
    assert_eq!(
        body.get("content").and_then(|v| v.as_str()).unwrap(),
        "你好"
    );

    let g = api(&app, &admin, "GET", &format!("/api/fs/{}", id), None).await;
    assert_eq!(g.status(), StatusCode::OK);
    let node = read_json(g).await;
    assert_eq!(
        node.get("name").and_then(|v| v.as_str()).unwrap(),
        "测试文档.txt"
    );
    assert_eq!(
        node.get("content").and_then(|v| v.as_str()).unwrap(),
        "你好"
    );
}

#[tokio::test]
async fn create_name_trimmed() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "  spaced  ", "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body.get("name").and_then(|v| v.as_str()).unwrap(), "spaced");
}

#[tokio::test]
async fn create_nested_5_levels() {
    let (app, admin, _editor) = setup().await;
    let mut parent: Option<i64> = None;
    let mut ids: Vec<i64> = Vec::new();
    for i in 0..5 {
        let mut payload = serde_json::json!({"name": format!("lvl{}", i), "kind": "folder"});
        if let Some(p) = parent {
            payload["parentId"] = serde_json::json!(p);
        }
        let resp = api(&app, &admin, "POST", "/api/fs", Some(payload)).await;
        assert_eq!(resp.status(), StatusCode::CREATED, "level {}", i);
        let body = read_json(resp).await;
        let id = body.get("id").and_then(|v| v.as_i64()).unwrap();
        assert_eq!(body.get("parentId").and_then(|v| v.as_i64()), parent);
        ids.push(id);
        parent = Some(id);
    }
    assert_eq!(ids.len(), 5);

    // 逐层 GET 校验 parentId 链
    for (i, id) in ids.iter().enumerate() {
        let g = api(&app, &admin, "GET", &format!("/api/fs/{}", id), None).await;
        assert_eq!(g.status(), StatusCode::OK);
        let node = read_json(g).await;
        if i == 0 {
            assert!(node.get("parentId").map(|v| v.is_null()).unwrap_or(true));
        } else {
            assert_eq!(
                node.get("parentId").and_then(|v| v.as_i64()),
                Some(ids[i - 1])
            );
        }
    }
}

#[tokio::test]
async fn create_content_defaults_empty() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "empty.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::CREATED);
    let body = read_json(resp).await;
    assert_eq!(body.get("content").and_then(|v| v.as_str()).unwrap(), "");
}

#[tokio::test]
async fn update_empty_name_400() {
    let (app, admin, _editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{}", id),
        Some(serde_json::json!({"name": ""})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("名称不能为空"), "got error: {}", msg);
}

#[tokio::test]
async fn update_nonexistent_404() {
    let (app, admin, _editor) = setup().await;
    let resp = api(
        &app,
        &admin,
        "PUT",
        "/api/fs/999999",
        Some(serde_json::json!({"name": "nope"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("节点不存在"), "got error: {}", msg);
}

#[tokio::test]
async fn update_other_user_node_404() {
    let (app, admin, editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "adm.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(
        &app,
        &editor,
        "PUT",
        &format!("/api/fs/{}", id),
        Some(serde_json::json!({"name": "hijack"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("节点不存在"), "got error: {}", msg);
}

#[tokio::test]
async fn update_no_fields_200() {
    let (app, admin, _editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "keep.txt", "kind": "file", "content": "orig"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{}", id),
        Some(serde_json::json!({})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = read_json(resp).await;
    assert_eq!(
        body.get("name").and_then(|v| v.as_str()).unwrap(),
        "keep.txt"
    );
    assert_eq!(
        body.get("content").and_then(|v| v.as_str()).unwrap(),
        "orig"
    );
}

#[tokio::test]
async fn update_folder_content_200_documents() {
    let (app, admin, _editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "folder", "kind": "folder"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{}", id),
        Some(serde_json::json!({"content": "weird"})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = read_json(resp).await;
    assert_eq!(body.get("kind").and_then(|v| v.as_str()).unwrap(), "folder");
    assert_eq!(
        body.get("content").and_then(|v| v.as_str()).unwrap(),
        "weird"
    );
}

#[tokio::test]
async fn update_rename_trims() {
    let (app, admin, _editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "old.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(
        &app,
        &admin,
        "PUT",
        &format!("/api/fs/{}", id),
        Some(serde_json::json!({"name": "  new  "})),
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = read_json(resp).await;
    assert_eq!(body.get("name").and_then(|v| v.as_str()).unwrap(), "new");
}

#[tokio::test]
async fn delete_cascade_removes_children() {
    let (app, admin, _editor) = setup().await;
    // root folder
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "root", "kind": "folder"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let root_id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    // child file
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"parentId": root_id, "name": "f.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let child_file_id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    // subfolder
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"parentId": root_id, "name": "sub", "kind": "folder"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let sub_id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    // grandchild file
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"parentId": sub_id, "name": "g.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let grandchild_id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    // delete root
    let resp = api(
        &app,
        &admin,
        "DELETE",
        &format!("/api/fs/{}", root_id),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT);

    for id in [root_id, child_file_id, sub_id, grandchild_id] {
        let g = api(&app, &admin, "GET", &format!("/api/fs/{}", id), None).await;
        assert_eq!(
            g.status(),
            StatusCode::NOT_FOUND,
            "id {} should be gone",
            id
        );
    }
}

#[tokio::test]
async fn delete_twice_second_404() {
    let (app, admin, _editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "once.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let d1 = api(&app, &admin, "DELETE", &format!("/api/fs/{}", id), None).await;
    assert_eq!(d1.status(), StatusCode::NO_CONTENT);

    let d2 = api(&app, &admin, "DELETE", &format!("/api/fs/{}", id), None).await;
    assert_eq!(d2.status(), StatusCode::NOT_FOUND);
    let body = read_json(d2).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("节点不存在"), "got error: {}", msg);
}

#[tokio::test]
async fn delete_other_user_404() {
    let (app, admin, editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "adm.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(&app, &editor, "DELETE", &format!("/api/fs/{}", id), None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);

    // 原主仍能 GET 到
    let g = api(&app, &admin, "GET", &format!("/api/fs/{}", id), None).await;
    assert_eq!(g.status(), StatusCode::OK);
}

#[tokio::test]
async fn list_order_folders_first_then_alpha() {
    let (app, admin, _editor) = setup().await;
    // 建 file "b"
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "b", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    // 建 folder "a"
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "a", "kind": "folder"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    // 建 file "c"（2026-10-19 起文件与文件夹同名互斥，改用 c 保序）
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "c", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);

    let resp = api(&app, &admin, "GET", "/api/fs", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let arr = read_json(resp).await;
    let items = arr.as_array().unwrap();
    assert_eq!(items.len(), 3);
    assert_eq!(
        items[0].get("kind").and_then(|v| v.as_str()).unwrap(),
        "folder"
    );
    assert_eq!(items[0].get("name").and_then(|v| v.as_str()).unwrap(), "a");
    assert_eq!(
        items[1].get("kind").and_then(|v| v.as_str()).unwrap(),
        "file"
    );
    assert_eq!(items[1].get("name").and_then(|v| v.as_str()).unwrap(), "b");
    assert_eq!(
        items[2].get("kind").and_then(|v| v.as_str()).unwrap(),
        "file"
    );
    assert_eq!(items[2].get("name").and_then(|v| v.as_str()).unwrap(), "c");
}

#[tokio::test]
async fn list_parent_of_other_user_empty_200() {
    let (app, admin, editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "adminfolder", "kind": "folder"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let fid = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(
        &app,
        &editor,
        "GET",
        &format!("/api/fs?parent_id={}", fid),
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK);
    let arr = read_json(resp).await;
    let items = arr.as_array().unwrap();
    assert!(items.is_empty(), "expected empty, got {:?}", items);
}

#[tokio::test]
async fn get_other_user_404() {
    let (app, admin, editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "adm.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);
    let id = read_json(r)
        .await
        .get("id")
        .and_then(|v| v.as_i64())
        .unwrap();

    let resp = api(&app, &editor, "GET", &format!("/api/fs/{}", id), None).await;
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body = read_json(resp).await;
    let msg = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
    assert!(msg.contains("节点不存在"), "got error: {}", msg);
}

#[tokio::test]
async fn root_list_isolates_users() {
    let (app, admin, editor) = setup().await;
    let r = api(
        &app,
        &admin,
        "POST",
        "/api/fs",
        Some(serde_json::json!({"name": "admin-only.txt", "kind": "file"})),
    )
    .await;
    assert_eq!(r.status(), StatusCode::CREATED);

    let resp = api(&app, &editor, "GET", "/api/fs", None).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let arr = read_json(resp).await;
    let items = arr.as_array().unwrap();
    assert!(
        items.is_empty(),
        "editor root should be empty, got {:?}",
        items
    );

    // admin 的根列表仍有 1 项
    let resp2 = api(&app, &admin, "GET", "/api/fs", None).await;
    assert_eq!(resp2.status(), StatusCode::OK);
    let arr2 = read_json(resp2).await;
    assert_eq!(arr2.as_array().unwrap().len(), 1);
}
