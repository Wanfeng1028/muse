use std::process::{Command, Stdio};
use std::time::Duration;

use axum::body::to_bytes;
use axum::http::{HeaderMap, Method, Request, StatusCode};
use axum::Router;
use mini_os::{build_app, init_state_with};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

fn test_app(rps: f64, burst: u64) -> Router {
    let state = init_state_with(":memory:", "static", 50 * 1024 * 1024, 604800, rps, burst);
    build_app(state)
}

async fn raw_request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    headers: &[(&str, &str)],
) -> axum::response::Response {
    let mut builder = Request::builder()
        .method(Method::from_bytes(method.as_bytes()).unwrap())
        .uri(uri);
    for (k, v) in headers {
        builder = builder.header(*k, *v);
    }
    let req = match body {
        Some(v) => {
            let bytes = serde_json::to_vec(&v).unwrap();
            builder
                .header("content-type", "application/json")
                .body(axum::body::Body::from(bytes))
                .unwrap()
        }
        None => builder.body(axum::body::Body::empty()).unwrap(),
    };
    app.oneshot(req).await.unwrap()
}

async fn register(app: &Router, username: &str) {
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/register",
        Some(json!({ "username": username, "password": "correct-horse-battery" })),
        &[],
    )
    .await;
    let status = resp.status();
    let body = body_json(resp).await;
    assert_eq!(
        status,
        StatusCode::CREATED,
        "register {username} should return 201, got {status}, body={body}"
    );
}

async fn login(
    app: &Router,
    username: &str,
    password: &str,
    xff: Option<&str>,
) -> (StatusCode, HeaderMap, Value) {
    let mut headers: Vec<(&str, &str)> = Vec::new();
    if let Some(ip) = xff {
        headers.push(("x-forwarded-for", ip));
    }
    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({ "username": username, "password": password })),
        &headers,
    )
    .await;
    let status = resp.status();
    let hmap = resp.headers().clone();
    let body = body_json(resp).await;
    (status, hmap, body)
}

#[tokio::test]
async fn login_under_limit_ok() {
    let app = test_app(1.0, 5);
    register(&app, "rl_user1").await;

    let (status, headers, body) = login(&app, "rl_user1", "correct-horse-battery", None).await;
    assert_eq!(
        status,
        StatusCode::OK,
        "first login should succeed, got {status}, body={body}"
    );

    let cookie = headers
        .get("set-cookie")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    assert!(
        cookie.contains("mini_os_session="),
        "set-cookie should contain mini_os_session=, got {cookie:?}"
    );
}

#[tokio::test]
async fn login_over_limit_429() {
    let app = test_app(0.05, 2);
    register(&app, "rl_user2").await;

    for i in 0..2 {
        let (status, _, body) = login(&app, "rl_user2", "wrong-password", None).await;
        assert_eq!(
            status,
            StatusCode::UNAUTHORIZED,
            "attempt {i} should be 401, got {status}, body={body}"
        );
    }

    for i in 2..5 {
        let (status, headers, body) = login(&app, "rl_user2", "wrong-password", None).await;
        assert_eq!(
            status,
            StatusCode::TOO_MANY_REQUESTS,
            "attempt {i} should be 429, got {status}, body={body}"
        );

        let retry_after = headers
            .get("retry-after")
            .and_then(|v| v.to_str().ok())
            .expect("429 must include Retry-After header");
        let header_secs: u64 = retry_after.parse().unwrap_or_else(|_| {
            panic!("Retry-After must be a positive integer, got {retry_after:?}")
        });
        assert!(
            header_secs >= 1,
            "Retry-After must be >= 1, got {header_secs}"
        );

        let body_retry = body
            .get("retry_after")
            .and_then(|v| v.as_u64())
            .expect("429 body must contain numeric retry_after");
        assert_eq!(
            body_retry, header_secs,
            "body retry_after must match header"
        );
        assert!(body_retry >= 1, "body retry_after must be >= 1");

        let err = body.get("error").and_then(|v| v.as_str()).unwrap_or("");
        assert!(
            !err.is_empty(),
            "429 body must contain non-empty error, got {body}"
        );
    }
}

#[tokio::test]
async fn login_window_recovers() {
    // 时序裕量设计：rps=0.1（10s/token）使并发对的第二个 acquire 在 10s 内必定 429；
    // 恢复等待 12s（>10s 周期）必回满。拒绝不扣 token，语义与耗时无关。
    let app = test_app(0.1, 1);
    register(&app, "rl_user3").await;

    let a1 = app.clone();
    let h1 = tokio::spawn(async move {
        login(&a1, "rl_user3", "correct-horse-battery", None)
            .await
            .0
    });
    let a2 = app.clone();
    let h2 = tokio::spawn(async move {
        login(&a2, "rl_user3", "correct-horse-battery", None)
            .await
            .0
    });

    let s1 = h1.await.expect("join 1");
    let s2 = h2.await.expect("join 2");
    let mut codes = [s1.as_u16(), s2.as_u16()];
    codes.sort();
    assert_eq!(
        codes,
        [
            StatusCode::OK.as_u16(),
            StatusCode::TOO_MANY_REQUESTS.as_u16()
        ],
        "concurrent pair must yield exactly one 200 and one 429, got {s1} and {s2}"
    );

    tokio::time::sleep(Duration::from_millis(12_000)).await;

    let (status, _, body) = login(&app, "rl_user3", "correct-horse-battery", None).await;
    assert_eq!(
        status,
        StatusCode::OK,
        "login after refill should succeed, got {status}, body={body}"
    );
}

#[tokio::test]
async fn dimensions_ip_and_account_independent() {
    let app = test_app(0.01, 1);
    register(&app, "rl_userA").await;
    register(&app, "rl_userB").await;

    let (status, _, body) = login(&app, "rl_userA", "wrong-password", Some("1.1.1.1")).await;
    assert_eq!(
        status,
        StatusCode::UNAUTHORIZED,
        "A@1.1.1.1 first should be 401, got {status}, body={body}"
    );

    let (status, _, body) = login(&app, "rl_userA", "wrong-password", Some("2.2.2.2")).await;
    assert_eq!(
        status,
        StatusCode::TOO_MANY_REQUESTS,
        "A@2.2.2.2 should be 429 (account dim), got {status}, body={body}"
    );

    let (status, _, body) = login(&app, "rl_userB", "wrong-password", Some("1.1.1.1")).await;
    assert_eq!(
        status,
        StatusCode::TOO_MANY_REQUESTS,
        "B@1.1.1.1 should be 429 (ip dim), got {status}, body={body}"
    );

    let (status, _, body) = login(&app, "rl_userB", "wrong-password", Some("3.3.3.3")).await;
    assert_eq!(
        status,
        StatusCode::UNAUTHORIZED,
        "B@3.3.3.3 should be 401 (fresh), got {status}, body={body}"
    );
}

#[tokio::test]
async fn probes_exempt_from_limit() {
    let app = test_app(0.01, 1);
    register(&app, "rl_user4").await;

    let (s1, _, b1) = login(&app, "rl_user4", "wrong-password", None).await;
    assert_eq!(
        s1,
        StatusCode::UNAUTHORIZED,
        "first login should be 401, got {s1}, body={b1}"
    );

    let (s2, _, b2) = login(&app, "rl_user4", "wrong-password", None).await;
    assert_eq!(
        s2,
        StatusCode::TOO_MANY_REQUESTS,
        "second login should be 429, got {s2}, body={b2}"
    );

    for i in 0..10 {
        let resp = raw_request(app.clone(), "GET", "/api/health", None, &[]).await;
        assert_eq!(
            resp.status(),
            StatusCode::OK,
            "health probe {i} should be 200, got {}",
            resp.status()
        );
    }
}

fn run_invalid_config(env_key: &str, env_val: &str) -> std::process::Output {
    let bin = env!("CARGO_BIN_EXE_mini-os");
    let mut child = Command::new(bin)
        .arg("serve")
        .env(env_key, env_val)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap_or_else(|e| panic!("failed to spawn {bin}: {e}"));

    for _ in 0..100 {
        match child.try_wait().expect("try_wait failed") {
            Some(_) => {
                return child.wait_with_output().expect("wait_with_output failed");
            }
            None => std::thread::sleep(Duration::from_millis(100)),
        }
    }
    let _ = child.kill();
    let _ = child.wait();
    panic!("进程未按预期退出");
}

#[tokio::test]
async fn invalid_config_fails_fast() {
    let out1 = run_invalid_config("MINIOS_LOGIN_RPS", "abc");
    assert!(
        !out1.status.success(),
        "MINIOS_LOGIN_RPS=abc should exit non-zero, got {:?}",
        out1.status
    );
    let stderr1 = String::from_utf8_lossy(&out1.stderr);
    assert!(
        stderr1.contains("MINIOS_LOGIN_RPS"),
        "stderr should mention MINIOS_LOGIN_RPS, got: {stderr1}"
    );

    let out2 = run_invalid_config("MINIOS_LOGIN_BURST", "0");
    assert!(
        !out2.status.success(),
        "MINIOS_LOGIN_BURST=0 should exit non-zero, got {:?}",
        out2.status
    );
    let stderr2 = String::from_utf8_lossy(&out2.stderr);
    assert!(
        stderr2.contains("MINIOS_LOGIN_BURST"),
        "stderr should mention MINIOS_LOGIN_BURST, got: {stderr2}"
    );
}

#[tokio::test]
async fn concurrent_burst_exhaustion() {
    let app = test_app(0.01, 3);
    register(&app, "rl_user5").await;

    let mut handles = Vec::new();
    for _ in 0..10 {
        let app = app.clone();
        handles.push(tokio::spawn(async move {
            let resp = raw_request(
                app,
                "POST",
                "/api/auth/login",
                Some(json!({ "username": "rl_user5", "password": "wrong-password" })),
                &[],
            )
            .await;
            resp.status()
        }));
    }

    let mut statuses = Vec::new();
    for h in handles {
        statuses.push(h.await.expect("task panicked"));
    }

    let non_429 = statuses
        .iter()
        .filter(|s| **s != StatusCode::TOO_MANY_REQUESTS)
        .count();
    let n_429 = statuses
        .iter()
        .filter(|s| **s == StatusCode::TOO_MANY_REQUESTS)
        .count();
    assert_eq!(
        non_429, 3,
        "expected exactly 3 non-429 (401), got {non_429}; statuses={statuses:?}"
    );
    assert_eq!(
        n_429, 7,
        "expected exactly 7 429, got {n_429}; statuses={statuses:?}"
    );

    for s in &statuses {
        assert!(
            *s == StatusCode::UNAUTHORIZED || *s == StatusCode::TOO_MANY_REQUESTS,
            "unexpected status {s}; expected only 401 or 429"
        );
    }
}

#[tokio::test]
async fn malformed_body_passes_through() {
    let app = test_app(100.0, 100);
    register(&app, "rl_user6").await;

    let resp = raw_request(
        app.clone(),
        "POST",
        "/api/auth/login",
        Some(json!({ "username": 123 })),
        &[],
    )
    .await;
    assert_ne!(
        resp.status(),
        StatusCode::TOO_MANY_REQUESTS,
        "malformed body must not be rate limited to 429"
    );

    let truncated = r#"{"username": "rl_user6", "password":"#;
    let req = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/login")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(truncated))
        .unwrap();
    let resp2 = app.clone().oneshot(req).await.unwrap();
    assert_ne!(
        resp2.status(),
        StatusCode::TOO_MANY_REQUESTS,
        "truncated body must not be rate limited to 429"
    );

    let resp3 = raw_request(app.clone(), "GET", "/api/health", None, &[]).await;
    assert_eq!(
        resp3.status(),
        StatusCode::OK,
        "server should still be alive after malformed bodies"
    );
}
