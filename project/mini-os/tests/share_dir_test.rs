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

async fn share_docs(app: &Router, cookie: &str) -> String {
    let docs = create_node(app, cookie, "docs", "folder", None, None).await;
    create_node(app, cookie, "a.txt", "file", Some(docs), Some("aaa")).await;
    let sub = create_node(app, cookie, "sub", "folder", Some(docs), None).await;
    create_node(app, cookie, "b.txt", "file", Some(sub), Some("bb")).await;
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "dir", "path": "/docs"})),
        Some(cookie.to_string()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "dir share create failed"
    );
    let body = body_json(resp).await;
    body["token"].as_str().expect("no token").to_string()
}

#[tokio::test]
async fn dir_share_create_and_browse_root() {
    let (app, cookie) = authed_app("diralice").await;
    let tok = share_docs(&app, &cookie).await;

    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/share/list?token={}&path=", tok),
        None,
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK, "browse root failed");
    let body = body_json(resp).await;
    assert_eq!(body["path"].as_str(), Some(""), "root path mismatch");
    let entries = body["entries"].as_array().expect("entries missing");
    assert_eq!(entries.len(), 2, "expected 2 entries, got {:?}", entries);
    assert_eq!(
        entries[0]["kind"].as_str(),
        Some("folder"),
        "folders must sort first: {:?}",
        entries
    );
    assert_eq!(entries[0]["name"].as_str(), Some("sub"), "first entry name");
    assert_eq!(
        entries[1]["kind"].as_str(),
        Some("file"),
        "second entry kind"
    );
    assert_eq!(
        entries[1]["name"].as_str(),
        Some("a.txt"),
        "second entry name"
    );
    assert_eq!(entries[1]["size"].as_i64(), Some(3), "a.txt size");
    for e in entries {
        assert!(
            e["mtime"].is_string() && !e["mtime"].as_str().unwrap().is_empty(),
            "mtime missing on {:?}",
            e
        );
    }
}

#[tokio::test]
async fn dir_share_browse_subdir() {
    let (app, cookie) = authed_app("dirbob").await;
    let tok = share_docs(&app, &cookie).await;

    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/share/list?token={}&path=sub", tok),
        None,
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK, "browse sub failed");
    let body = body_json(resp).await;
    let entries = body["entries"].as_array().expect("entries missing");
    assert_eq!(entries.len(), 1, "expected 1 entry, got {:?}", entries);
    assert_eq!(entries[0]["name"].as_str(), Some("b.txt"), "entry name");
    assert_eq!(entries[0]["size"].as_i64(), Some(2), "b.txt size");

    let resp2 = raw_request(
        app.clone(),
        "GET",
        &format!("/api/share/list?token={}&path=sub%2F..%2Fsub", tok),
        None,
        None,
    )
    .await;
    assert_eq!(
        resp2.status(),
        StatusCode::FORBIDDEN,
        "dotdot segment must be rejected even when it stays in tree"
    );
}

#[tokio::test]
async fn dir_share_download_nested_file() {
    let (app, cookie) = authed_app("dircarol").await;
    let tok = share_docs(&app, &cookie).await;

    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/s/{}/download?path=sub/b.txt", tok),
        None,
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK, "nested download failed");
    let cd = resp
        .headers()
        .get("content-disposition")
        .expect("no content-disposition")
        .to_str()
        .unwrap()
        .to_string();
    assert!(
        cd.contains("b.txt"),
        "content-disposition missing name: {}",
        cd
    );
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.as_ref(), b"bb", "nested file body mismatch");
}

#[tokio::test]
async fn dir_share_list_traversal_403() {
    let (app, cookie) = authed_app("dirdave").await;
    let tok = share_docs(&app, &cookie).await;

    let paths = ["..", "../..", "sub/../..", "sub/%2E%2E/%2E%2E"];
    for p in paths {
        let resp = raw_request(
            app.clone(),
            "GET",
            &format!("/api/share/list?token={}&path={}", tok, p),
            None,
            None,
        )
        .await;
        assert_eq!(
            resp.status(),
            StatusCode::FORBIDDEN,
            "traversal path {:?} must be 403",
            p
        );
    }
}

#[tokio::test]
async fn dir_share_download_traversal_403() {
    let (app, cookie) = authed_app("direve").await;
    let tok = share_docs(&app, &cookie).await;

    let resp = raw_request(
        app.clone(),
        "GET",
        &format!("/api/s/{}/download?path=../a.txt", tok),
        None,
        None,
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        ".. download must be 403"
    );

    let resp2 = raw_request(
        app.clone(),
        "GET",
        &format!("/api/s/{}/download?path=sub/../../etc", tok),
        None,
        None,
    )
    .await;
    assert_eq!(
        resp2.status(),
        StatusCode::FORBIDDEN,
        "sub/../../etc download must be 403"
    );
}

#[tokio::test]
async fn dir_share_other_user_404() {
    let (alice_app, alice_cookie) = authed_app("diralice2").await;
    let alice_tok = share_docs(&alice_app, &alice_cookie).await;

    let resp = raw_request(
        alice_app.clone(),
        "GET",
        &format!("/api/share/list?token={}&path=", alice_tok),
        None,
        None,
    )
    .await;
    assert_eq!(resp.status(), StatusCode::OK, "alice browse own share");

    let (bob_app, bob_cookie) = authed_app("dirbob2").await;
    let bob_tok = share_docs(&bob_app, &bob_cookie).await;

    let resp2 = raw_request(
        bob_app.clone(),
        "GET",
        &format!("/api/share/list?token={}&path=", bob_tok),
        None,
        None,
    )
    .await;
    assert_eq!(resp2.status(), StatusCode::OK, "bob browse own share");
    let bob_body = body_json(resp2).await;
    let bob_entries = bob_body["entries"].as_array().expect("bob entries");
    assert_eq!(bob_entries.len(), 2, "bob docs has 2 entries");

    let alice_root = body_json(
        raw_request(
            alice_app.clone(),
            "GET",
            "/api/fs",
            None,
            Some(alice_cookie.clone()),
        )
        .await,
    )
    .await;
    let alice_docs_id = alice_root
        .as_array()
        .and_then(|a| a.iter().find(|e| e["name"].as_str() == Some("docs")))
        .expect("docs node")["id"]
        .as_i64()
        .expect("docs id");

    create_node(
        &alice_app,
        &alice_cookie,
        "secret.txt",
        "file",
        Some(alice_docs_id),
        Some("shh"),
    )
    .await;

    let resp3 = raw_request(
        bob_app.clone(),
        "GET",
        &format!("/api/share/list?token={}&path=", bob_tok),
        None,
        None,
    )
    .await;
    assert_eq!(resp3.status(), StatusCode::OK, "bob re-browse own share");
    let bob_body2 = body_json(resp3).await;
    let bob_entries2 = bob_body2["entries"].as_array().expect("bob entries 2");
    assert!(
        !bob_entries2
            .iter()
            .any(|e| e["name"].as_str() == Some("secret.txt")),
        "bob must not see alice's secret.txt: {:?}",
        bob_entries2
    );
}

#[tokio::test]
async fn dir_share_path_is_file_400() {
    let (app, cookie) = authed_app("dirfrank").await;
    let docs = create_node(&app, &cookie, "docs", "folder", None, None).await;
    create_node(&app, &cookie, "a.txt", "file", Some(docs), Some("aaa")).await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "dir", "path": "/docs/a.txt"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "sharing a file as dir must be 400"
    );
}

#[tokio::test]
async fn dir_share_nonexistent_path_404() {
    let (app, cookie) = authed_app("dirgrace").await;
    create_node(&app, &cookie, "docs", "folder", None, None).await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "dir", "path": "/no-such-dir"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::NOT_FOUND,
        "sharing nonexistent dir must be 404"
    );
}

#[tokio::test]
async fn dir_share_invalid_type_400() {
    let (app, cookie) = authed_app("dirheidi").await;
    create_node(&app, &cookie, "docs", "folder", None, None).await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "weird", "path": "/docs"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "invalid share type must be 400"
    );
}

#[tokio::test]
async fn dir_share_missing_path_400() {
    let (app, cookie) = authed_app("dirivan").await;
    create_node(&app, &cookie, "docs", "folder", None, None).await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "dir"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::BAD_REQUEST,
        "missing path must be 400"
    );
}

#[tokio::test]
async fn file_share_explicit_type_regression() {
    let (app, cookie) = authed_app("dirjudy").await;
    let fid = create_node(&app, &cookie, "f.txt", "file", None, Some("hello")).await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "file", "nodeId": fid})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(
        resp.status(),
        StatusCode::CREATED,
        "explicit file share must be 201"
    );
    let tok = body_json(resp).await["token"]
        .as_str()
        .expect("no token")
        .to_string();

    let info = raw_request(app.clone(), "GET", &format!("/api/s/{}", tok), None, None).await;
    assert_eq!(info.status(), StatusCode::OK, "share info failed");
    let info_body = body_json(info).await;
    assert_eq!(
        info_body["shareType"].as_str(),
        Some("file"),
        "shareType should be file"
    );

    let dl = raw_request(
        app.clone(),
        "GET",
        &format!("/api/s/{}/download", tok),
        None,
        None,
    )
    .await;
    assert_eq!(dl.status(), StatusCode::OK, "file share download failed");
    let bytes = to_bytes(dl.into_body(), usize::MAX).await.unwrap();
    assert_eq!(bytes.as_ref(), b"hello", "file share body mismatch");
}

#[tokio::test]
async fn dir_share_info_meta() {
    let (app, cookie) = authed_app("dirkarl").await;
    let tok = share_docs(&app, &cookie).await;

    let resp = raw_request(app.clone(), "GET", &format!("/api/s/{}", tok), None, None).await;
    assert_eq!(resp.status(), StatusCode::OK, "dir share info failed");
    let body = body_json(resp).await;
    assert_eq!(
        body["shareType"].as_str(),
        Some("dir"),
        "shareType mismatch"
    );
    assert_eq!(body["kind"].as_str(), Some("folder"), "kind mismatch");
    assert_eq!(body["name"].as_str(), Some("docs"), "name mismatch");
    assert_eq!(body["size"].as_i64(), Some(5), "size must aggregate files");
}
