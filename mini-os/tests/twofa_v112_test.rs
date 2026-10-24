use axum::body::to_bytes;
use axum::http::{Request, StatusCode};
use axum::Router;
use mini_os::auth;
use mini_os::twofa;
use mini_os::{build_app, init_state};
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(body: axum::body::Body) -> Option<Value> {
    let bytes = to_bytes(body, usize::MAX).await.unwrap();
    if bytes.is_empty() {
        None
    } else {
        Some(serde_json::from_slice(&bytes).unwrap())
    }
}

async fn raw_request(
    app: Router,
    method: &str,
    uri: &str,
    body: Option<Value>,
    cookie: Option<&str>,
) -> (StatusCode, axum::http::HeaderMap, Option<Value>) {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(c) = cookie {
        builder = builder.header("cookie", c);
    }
    let req = if let Some(b) = body {
        builder
            .header("content-type", "application/json")
            .body(axum::body::Body::from(b.to_string()))
            .unwrap()
    } else {
        builder.body(axum::body::Body::from("")).unwrap()
    };
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let headers = resp.headers().clone();
    let v = body_json(resp.into_body()).await;
    (status, headers, v)
}

#[tokio::test]
async fn sweep_expired_challenges_deletes_only_expired() {
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());

    // Register a user so a real users row exists (FK constraint)
    let _ = raw_request(
        app,
        "POST",
        "/api/auth/register",
        Some(json!({"username": "v112user", "password": "s3cureP4ss"})),
        None,
    )
    .await;

    // Obtain the user id from the DB
    let conn = state.db.lock().unwrap();
    let user_id: i64 = conn
        .query_row(
            "SELECT id FROM users WHERE username = 'v112user'",
            [],
            |row| row.get(0),
        )
        .unwrap();

    let now = auth::now_epoch_secs();

    // Insert expired challenge row
    let expired_hash = auth::hash_token("v112-expired");
    conn.execute(
        "INSERT INTO tfa_challenges (token_hash, user_id, expires_at, attempts) VALUES (?1, ?2, ?3, ?4)",
        rusqlite::params![expired_hash, user_id, now - 10, 0],
    )
    .unwrap();

    // Insert valid (not-expired) challenge row
    let valid_hash = auth::hash_token("v112-valid");
    conn.execute(
        "INSERT INTO tfa_challenges (token_hash, user_id, expires_at, attempts) VALUES (?1, ?2, ?3, ?4)",
        rusqlite::params![valid_hash, user_id, now + 300, 0],
    )
    .unwrap();

    // Sweep should delete exactly the expired row
    let deleted = twofa::sweep_expired_challenges(&conn).unwrap();
    assert_eq!(deleted, 1, "sweep should report 1 deleted row");

    // Verify the expired row is gone
    let expired_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM tfa_challenges WHERE token_hash = ?1",
            rusqlite::params![expired_hash],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(expired_count, 0, "expired row should be removed");

    // Verify the valid row remains
    let valid_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM tfa_challenges WHERE token_hash = ?1",
            rusqlite::params![valid_hash],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(valid_count, 1, "valid row should still exist");

    drop(conn);
}

#[tokio::test]
async fn twofa_middleware_bursts_then_429() {
    // Fresh state & app, isolated from other tests
    let state = init_state(":memory:", "static");
    let app = build_app(state);

    let req_body = json!({"challenge": "bogus-challenge", "code": "000000"});

    // First 5 requests must NOT return 429 (handler returns 401 for nonexistent challenge)
    for i in 0..5 {
        let (status, _, _) = raw_request(
            app.clone(),
            "POST",
            "/api/auth/2fa",
            Some(req_body.clone()),
            None,
        )
        .await;
        assert_ne!(
            status,
            StatusCode::TOO_MANY_REQUESTS,
            "request {} should not be 429",
            i + 1
        );
    }

    // 6th request MUST return 429
    let (status, headers, resp_body) = raw_request(
        app.clone(),
        "POST",
        "/api/auth/2fa",
        Some(req_body.clone()),
        None,
    )
    .await;
    assert_eq!(
        status,
        StatusCode::TOO_MANY_REQUESTS,
        "6th request must be 429"
    );

    // retry-after header must be present
    assert!(
        headers.contains_key("retry-after"),
        "retry-after header must exist on 429 response"
    );

    // JSON body error field must contain "过于频繁"
    let v = resp_body.expect("429 response should have a body");
    let error_msg = v["error"].as_str().expect("error field should be a string");
    assert!(
        error_msg.contains("过于频繁"),
        "error should contain '过于频繁', got: {}",
        error_msg
    );
}

#[tokio::test]
async fn parse_twofa_limit_raw_defaults_and_invalid() {
    // Default values: rps == 1.0, burst == 5
    let cfg = mini_os::ratelimit::parse_twofa_limit_raw(None, None).unwrap();
    assert!(
        (cfg.rps - 1.0_f64).abs() < f64::EPSILON,
        "default rps should be 1.0, got {}",
        cfg.rps
    );
    assert_eq!(cfg.burst, 5, "default burst should be 5");

    // Invalid rps string → Err mentioning MINIOS_2FA_RPS
    let err = mini_os::ratelimit::parse_twofa_limit_raw(Some("abc"), None).unwrap_err();
    assert!(
        err.contains("MINIOS_2FA_RPS"),
        "error should mention MINIOS_2FA_RPS, got: {}",
        err
    );

    // Invalid burst value (0) → Err mentioning MINIOS_2FA_BURST
    let err = mini_os::ratelimit::parse_twofa_limit_raw(None, Some("0")).unwrap_err();
    assert!(
        err.contains("MINIOS_2FA_BURST"),
        "error should mention MINIOS_2FA_BURST, got: {}",
        err
    );
}
