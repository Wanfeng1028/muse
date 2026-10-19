use axum::body::Body;
use axum::http::{header, Request, StatusCode};
use futures_util::future::join_all;
use serde_json::Value;
use tower::ServiceExt;

async fn register_and_cookie(app: &axum::Router, username: &str) -> String {
    let body = serde_json::json!({
        "username": username,
        "password": "password123"
    });
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body.to_string()))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::CREATED);
    let set_cookie = resp
        .headers()
        .get(header::SET_COOKIE)
        .expect("missing set-cookie")
        .to_str()
        .unwrap()
        .to_string();
    set_cookie.split(';').next().unwrap().to_string()
}

fn multipart_body(boundary: &str, filename: &str, content: &[u8]) -> Vec<u8> {
    let mut body: Vec<u8> = Vec::new();
    body.extend_from_slice(format!("--{}\r\n", boundary).as_bytes());
    body.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            filename
        )
        .as_bytes(),
    );
    body.extend_from_slice(b"Content-Type: text/plain\r\n\r\n");
    body.extend_from_slice(content);
    body.extend_from_slice(b"\r\n");
    body.extend_from_slice(format!("--{}--\r\n", boundary).as_bytes());
    body
}

fn upload_request(
    cookie: &str,
    boundary: &str,
    filename: &str,
    content: &[u8],
    path: &str,
) -> Request<Body> {
    let body = multipart_body(boundary, filename, content);
    Request::builder()
        .method("POST")
        .uri(format!("/api/files/upload?path={}", path))
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={}", boundary),
        )
        .header(header::COOKIE, cookie)
        .body(Body::from(body))
        .unwrap()
}

async fn read_json(resp: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice::<Value>(&bytes).unwrap()
}

#[tokio::test]
async fn concurrent_upload_same_name_only_one_wins() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_cookie(&app, "raceuser1").await;

    let mut handles = Vec::new();
    for i in 0..20usize {
        let app = app.clone();
        let cookie = cookie.clone();
        handles.push(tokio::spawn(async move {
            let boundary = format!("bnd{}", i);
            let content = format!("content-{}", i);
            let req = upload_request(&cookie, &boundary, "race.txt", content.as_bytes(), "/");
            let resp = app.oneshot(req).await.unwrap();
            let status = resp.status();
            let body = read_json(resp).await;
            (status, body)
        }));
    }

    let results = join_all(handles).await;
    let mut created = 0usize;
    let mut conflicts = 0usize;
    for r in results {
        let (status, body) = r.unwrap();
        match status {
            StatusCode::CREATED => created += 1,
            StatusCode::CONFLICT => {
                assert_eq!(body["error"], Value::String("同名文件已存在".to_string()));
                conflicts += 1;
            }
            other => panic!("unexpected status: {}", other),
        }
    }
    assert_eq!(created, 1);
    assert_eq!(conflicts, 19);
}

#[tokio::test]
async fn concurrent_upload_different_names_all_succeed() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_cookie(&app, "raceuser2").await;

    let mut handles = Vec::new();
    for i in 0..10usize {
        let app = app.clone();
        let cookie = cookie.clone();
        handles.push(tokio::spawn(async move {
            let boundary = format!("bnd{}", i);
            let content = format!("content-{}", i);
            let filename = format!("race-{}.txt", i);
            let req = upload_request(&cookie, &boundary, &filename, content.as_bytes(), "/");
            let resp = app.oneshot(req).await.unwrap();
            resp.status()
        }));
    }

    let results = join_all(handles).await;
    let mut created = 0usize;
    for r in results {
        let status = r.unwrap();
        assert_eq!(status, StatusCode::CREATED);
        created += 1;
    }
    assert_eq!(created, 10);
}

#[tokio::test]
async fn concurrent_create_fs_same_name_documents_behavior() {
    // NOTE 2026-10-19: create_fs now rejects duplicate sibling names with 409.
    // The db mutex serializes check+insert, so exactly one concurrent
    // same-name creation wins (1x 201, 9x 409).
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_cookie(&app, "raceuser3").await;

    let mut handles = Vec::new();
    for _ in 0..10usize {
        let app = app.clone();
        let cookie = cookie.clone();
        handles.push(tokio::spawn(async move {
            let body = serde_json::json!({ "name": "dup", "kind": "folder" });
            let req = Request::builder()
                .method("POST")
                .uri("/api/fs")
                .header(header::CONTENT_TYPE, "application/json")
                .header(header::COOKIE, cookie)
                .body(Body::from(body.to_string()))
                .unwrap();
            let resp = app.oneshot(req).await.unwrap();
            resp.status()
        }));
    }

    let results = join_all(handles).await;
    let mut created = 0usize;
    let mut conflicted = 0usize;
    for r in results {
        match r.unwrap() {
            StatusCode::CREATED => created += 1,
            StatusCode::CONFLICT => conflicted += 1,
            other => panic!("unexpected status: {other}"),
        }
    }
    assert_eq!(
        created, 1,
        "exactly one concurrent same-name create should win"
    );
    assert_eq!(conflicted, 9);

    let req = Request::builder()
        .method("GET")
        .uri("/api/fs")
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let json = read_json(resp).await;

    let items = json.as_array().expect("expected array of nodes").clone();
    let dup_count = items
        .iter()
        .filter(|n| n["name"] == Value::String("dup".to_string()))
        .count();
    assert_eq!(dup_count, 1);
}

#[tokio::test]
async fn concurrent_settings_upsert_single_row() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_cookie(&app, "raceuser4").await;

    let mut handles = Vec::new();
    for i in 0..20usize {
        let app = app.clone();
        let cookie = cookie.clone();
        handles.push(tokio::spawn(async move {
            let body = serde_json::json!({ "key": "theme", "value": format!("v{}", i) });
            let req = Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header(header::CONTENT_TYPE, "application/json")
                .header(header::COOKIE, cookie)
                .body(Body::from(body.to_string()))
                .unwrap();
            let resp = app.oneshot(req).await.unwrap();
            resp.status()
        }));
    }

    let results = join_all(handles).await;
    let mut ok_count = 0usize;
    for r in results {
        let status = r.unwrap();
        assert_eq!(status, StatusCode::OK);
        ok_count += 1;
    }
    assert_eq!(ok_count, 20);

    let req = Request::builder()
        .method("GET")
        .uri("/api/settings")
        .header(header::COOKIE, cookie)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let json = read_json(resp).await;

    let theme_val = json
        .get("theme")
        .expect("theme key must exist")
        .as_str()
        .unwrap()
        .to_string();
    let expected: Vec<String> = (0..20).map(|i| format!("v{}", i)).collect();
    assert!(
        expected.contains(&theme_val),
        "theme value {} not in v0..v19",
        theme_val
    );

    let keys = json.as_object().unwrap();
    let theme_keys = keys.keys().filter(|k| *k == "theme").count();
    assert_eq!(theme_keys, 1);
}

#[tokio::test]
async fn concurrent_delete_same_node_only_one_wins() {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let cookie = register_and_cookie(&app, "raceuser5").await;

    let create_body = serde_json::json!({ "name": "del.txt", "kind": "file" });
    let create_req = Request::builder()
        .method("POST")
        .uri("/api/fs")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::COOKIE, cookie.clone())
        .body(Body::from(create_body.to_string()))
        .unwrap();
    let create_resp = app.clone().oneshot(create_req).await.unwrap();
    assert_eq!(create_resp.status(), StatusCode::CREATED);
    let node_json = read_json(create_resp).await;
    let node_id = node_json["id"].as_i64().expect("node id must be int");

    let mut handles = Vec::new();
    for _ in 0..10usize {
        let app = app.clone();
        let cookie = cookie.clone();
        let id = node_id;
        handles.push(tokio::spawn(async move {
            let req = Request::builder()
                .method("DELETE")
                .uri(format!("/api/fs/{}", id))
                .header(header::COOKIE, cookie)
                .body(Body::empty())
                .unwrap();
            let resp = app.oneshot(req).await.unwrap();
            let status = resp.status();
            let body = if status == StatusCode::NO_CONTENT {
                Value::Null
            } else {
                read_json(resp).await
            };
            (status, body)
        }));
    }

    let results = join_all(handles).await;
    let mut deleted = 0usize;
    let mut not_found = 0usize;
    for r in results {
        let (status, body) = r.unwrap();
        match status {
            StatusCode::NO_CONTENT => deleted += 1,
            StatusCode::NOT_FOUND => {
                assert_eq!(body["error"], Value::String("节点不存在".to_string()));
                not_found += 1;
            }
            other => panic!("unexpected status: {}", other),
        }
    }
    assert_eq!(deleted, 1);
    assert_eq!(not_found, 9);
}
