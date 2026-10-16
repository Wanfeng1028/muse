use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn test_app() -> (Router, String) {
    let state = init_state(":memory:", "static");
    let app = build_app(state);
    let reg = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"username": "metrics", "password": "password123"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(reg).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let cookie = resp
        .headers()
        .get("set-cookie")
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();
    (app, cookie)
}

async fn body_text(resp: axum::response::Response) -> String {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    String::from_utf8(bytes.to_vec()).unwrap()
}

async fn request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: &str,
) -> axum::response::Response {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("cookie", cookie);
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
async fn metrics_endpoint_returns_prometheus_text() {
    let (app, cookie) = test_app().await;
    let resp = request(app, "GET", "/metrics", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get("content-type")
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(ct.contains("text/plain"), "content-type: {ct}");
    assert!(ct.contains("version=0.0.4"), "content-type: {ct}");

    let body = body_text(resp).await;
    assert!(body.contains("# HELP http_requests_total"), "{body}");
    assert!(
        body.contains("# TYPE http_requests_total counter"),
        "{body}"
    );
    assert!(body.contains("# HELP vfs_ops_total"), "{body}");
    assert!(body.contains("# TYPE vfs_ops_total counter"), "{body}");
    assert!(body.contains("# HELP ws_connections"), "{body}");
    assert!(body.contains("# HELP auth_ops_total"), "{body}");
    assert!(body.contains("# TYPE auth_ops_total counter"), "{body}");
    assert!(body.contains("# TYPE ws_connections gauge"), "{body}");
    assert!(
        body.lines().any(|l| l == "ws_connections 0"),
        "expected ws_connections 0 line, got:\n{body}"
    );
}

#[tokio::test]
async fn http_requests_counted_per_route_method_status() {
    let (app, cookie) = test_app().await;
    let r1 = request(app.clone(), "GET", "/api/health", None, &cookie).await;
    assert_eq!(r1.status(), StatusCode::OK);
    let r2 = request(app.clone(), "GET", "/api/health", None, &cookie).await;
    assert_eq!(r2.status(), StatusCode::OK);
    let r3 = request(app.clone(), "GET", "/api/apps", None, &cookie).await;
    assert_eq!(r3.status(), StatusCode::OK);

    let resp = request(app, "GET", "/metrics", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_text(resp).await;

    assert!(
        body.lines().any(|l| l
            == r#"http_requests_total{method="GET",route="/api/health",status="200"} 2"#),
        "missing /api/health count line, got:\n{body}"
    );
    assert!(
        body.lines()
            .any(|l| l == r#"http_requests_total{method="GET",route="/api/apps",status="200"} 1"#),
        "missing /api/apps count line, got:\n{body}"
    );
}

#[tokio::test]
async fn vfs_ops_counted() {
    let (app, cookie) = test_app().await;

    let create = request(
        app.clone(),
        "POST",
        "/api/fs",
        Some(json!({"parentId": null, "name": "m.txt", "kind": "file", "content": "x"})),
        &cookie,
    )
    .await;
    assert_eq!(create.status(), StatusCode::CREATED);
    let create_body = body_text(create).await;
    let created: Value = serde_json::from_str(&create_body).unwrap();
    let id = created["id"].as_i64().unwrap().to_string();

    let update = request(
        app.clone(),
        "PUT",
        &format!("/api/fs/{id}"),
        Some(json!({"content": "yy"})),
        &cookie,
    )
    .await;
    assert_eq!(update.status(), StatusCode::OK);

    let list = request(app.clone(), "GET", "/api/fs", None, &cookie).await;
    assert_eq!(list.status(), StatusCode::OK);

    let delete = request(
        app.clone(),
        "DELETE",
        &format!("/api/fs/{id}"),
        None,
        &cookie,
    )
    .await;
    assert_eq!(delete.status(), StatusCode::NO_CONTENT);

    let resp = request(app, "GET", "/metrics", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_text(resp).await;

    for line in [
        r#"vfs_ops_total{op="create"} 1"#,
        r#"vfs_ops_total{op="update"} 1"#,
        r#"vfs_ops_total{op="read"} 1"#,
        r#"vfs_ops_total{op="delete"} 1"#,
        r#"http_requests_total{method="POST",route="/api/fs",status="201"} 1"#,
    ] {
        assert!(
            body.lines().any(|l| l == line),
            "missing line {line:?}, got:\n{body}"
        );
    }
}

#[tokio::test]
async fn metrics_lines_have_valid_format() {
    let (app, cookie) = test_app().await;
    let _ = request(app.clone(), "GET", "/api/health", None, &cookie).await;
    let _ = request(app.clone(), "GET", "/api/apps", None, &cookie).await;
    let _ = request(app.clone(), "GET", "/api/stats", None, &cookie).await;

    let resp = request(app, "GET", "/metrics", None, &cookie).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_text(resp).await;

    for line in body.lines() {
        if line.is_empty() {
            continue;
        }
        if line.starts_with('#') {
            continue;
        }
        let (sample, value) = line
            .rsplit_once(' ')
            .unwrap_or_else(|| panic!("no space separator in line: {line:?}"));
        assert!(
            value.parse::<f64>().is_ok(),
            "value not a float in line {line:?}"
        );

        let name = match sample.split_once('{') {
            Some((n, rest)) => {
                assert!(rest.ends_with('}'), "unbalanced braces in line {line:?}");
                let inner = &rest[..rest.len() - 1];
                assert_eq!(inner.matches('{').count(), 0, "extra '{{' in line {line:?}");
                n
            }
            None => sample,
        };
        assert!(!name.is_empty(), "empty metric name in line {line:?}");
        assert!(
            name.chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == ':'),
            "invalid metric name {name:?} in line {line:?}"
        );
    }
}
