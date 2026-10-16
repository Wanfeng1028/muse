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

fn find_sample(body: &str, metric: &str, labels: &str) -> Option<f64> {
    let prefix = if labels.is_empty() {
        format!("{} ", metric)
    } else {
        format!("{}{} ", metric, labels)
    };
    body.lines().find_map(|l| {
        let t = l.trim();
        if t.starts_with(&prefix) {
            t.rsplit(' ').next()?.parse::<f64>().ok()
        } else {
            None
        }
    })
}

async fn metrics_text(app: &Router) -> String {
    let resp = raw_request(app.clone(), "GET", "/metrics", None, None).await;
    assert_eq!(resp.status(), StatusCode::OK, "GET /metrics failed");
    let ct = resp
        .headers()
        .get("content-type")
        .unwrap()
        .to_str()
        .unwrap()
        .to_string();
    assert!(
        ct.contains("text/plain") && ct.contains("version=0.0.4"),
        "bad content-type: {}",
        ct
    );
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    String::from_utf8(bytes.to_vec()).unwrap()
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

#[tokio::test]
async fn duration_histogram_present() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let resp = raw_request(app.clone(), "GET", "/api/health", None, None).await;
    assert_eq!(resp.status(), StatusCode::OK, "health failed");

    let body = metrics_text(&app).await;
    assert!(
        body.contains("# HELP http_request_duration_seconds"),
        "missing HELP for duration histogram"
    );
    assert!(
        body.contains("# TYPE http_request_duration_seconds histogram"),
        "missing TYPE histogram"
    );

    let inf = find_sample(
        &body,
        "http_request_duration_seconds_bucket",
        r#"{method="GET",route="/api/health",le="+Inf"}"#,
    );
    assert!(
        inf.is_some(),
        "missing +Inf bucket for /api/health: {}",
        body
    );

    let count = find_sample(
        &body,
        "http_request_duration_seconds_count",
        r#"{method="GET",route="/api/health"}"#,
    );
    assert!(count.is_some(), "missing count for /api/health: {}", body);
    assert!(count.unwrap() >= 1.0, "count must be >= 1, got {:?}", count);
}

#[tokio::test]
async fn route_label_uses_template() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let token = "0123456789abcdef0123456789abcdef";
    let resp = raw_request(app.clone(), "GET", &format!("/api/s/{}", token), None, None).await;
    assert_eq!(
        resp.status(),
        StatusCode::NOT_FOUND,
        "unknown token must 404"
    );

    let body = metrics_text(&app).await;
    assert!(
        body.contains(r#"route="/api/s/:token""#),
        "metrics must contain templated route label: {}",
        body
    );
    assert!(
        !body.contains(&format!(r#"route="/api/s/{}""#, token)),
        "raw token must not appear as route label"
    );
}

#[tokio::test]
async fn vfs_gauges_reflect_files() {
    let (app, cookie) = authed_app("metricsalice").await;
    create_node(&app, &cookie, "ten.txt", "file", None, Some("0123456789")).await;

    let body = metrics_text(&app).await;
    let files = find_sample(&body, "vfs_files_total", "");
    assert!(files.is_some(), "vfs_files_total sample missing: {}", body);
    assert!(
        files.unwrap() >= 3.0,
        "vfs_files_total must be >= 3, got {:?}",
        files
    );

    let bytes = find_sample(&body, "vfs_bytes_total", "");
    assert!(bytes.is_some(), "vfs_bytes_total sample missing: {}", body);
    assert!(
        bytes.unwrap() >= 10.0,
        "vfs_bytes_total must be >= 10, got {:?}",
        bytes
    );
}

#[tokio::test]
async fn shares_gauge_by_type() {
    let (app, cookie) = authed_app("metricsbob").await;

    let fid = create_node(&app, &cookie, "s.txt", "file", None, Some("x")).await;
    let r1 = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "file", "nodeId": fid})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(r1.status(), StatusCode::CREATED, "file share failed");

    let did = create_node(&app, &cookie, "d", "folder", None, None).await;
    create_node(&app, &cookie, "inner.txt", "file", Some(did), Some("y")).await;
    let r2 = raw_request(
        app.clone(),
        "POST",
        "/api/shares",
        Some(json!({"type": "dir", "path": "/d"})),
        Some(cookie.clone()),
    )
    .await;
    assert_eq!(r2.status(), StatusCode::CREATED, "dir share failed");

    let body = metrics_text(&app).await;
    let file_share = find_sample(&body, "shares_total", r#"{type="file"}"#);
    let dir_share = find_sample(&body, "shares_total", r#"{type="dir"}"#);
    assert_eq!(file_share, Some(1.0), "file share gauge mismatch: {}", body);
    assert_eq!(dir_share, Some(1.0), "dir share gauge mismatch: {}", body);
}

#[tokio::test]
async fn duration_buckets_cumulative_invariant() {
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    for _ in 0..2 {
        let resp = raw_request(app.clone(), "GET", "/api/health", None, None).await;
        assert_eq!(resp.status(), StatusCode::OK, "health failed");
    }

    let body = metrics_text(&app).await;
    let count = find_sample(
        &body,
        "http_request_duration_seconds_count",
        r#"{method="GET",route="/api/health"}"#,
    );
    let inf = find_sample(
        &body,
        "http_request_duration_seconds_bucket",
        r#"{method="GET",route="/api/health",le="+Inf"}"#,
    );
    assert!(count.is_some(), "count missing: {}", body);
    assert!(inf.is_some(), "+Inf bucket missing: {}", body);
    assert_eq!(
        count, inf,
        "cumulative invariant: count must equal +Inf bucket"
    );
    assert!(
        count.unwrap() >= 2.0,
        "count must be >= 2 after two health calls, got {:?}",
        count
    );
}
