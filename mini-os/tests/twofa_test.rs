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
    cookie: Option<&str>,
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

fn test_cookie(resp: &axum::response::Response) -> String {
    let sc = resp.headers().get("set-cookie").expect("no set-cookie").to_str().unwrap().to_string();
    sc.split(';').next().unwrap().to_string()
}

fn now_secs() -> i64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs() as i64
}

static KEY_INIT: std::sync::Once = std::sync::Once::new();
fn ensure_master_key() {
    KEY_INIT.call_once(|| {
        std::env::set_var("MINIOS_TOTP_MASTER_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    });
}

fn make_app() -> Router {
    build_app(init_state(":memory:", "static"))
}

#[tokio::test]
async fn password_policy_via_register() {
    ensure_master_key();
    let app = make_app();
    
    // 纯字母密码 → 400，含"字母和数字"
    let resp = raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "user1", "password": "password"})), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "纯字母密码应返回400");
    let body = body_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("字母和数字"), "错误信息应含'字母和数字'");
    
    // 7字符密码 → 400，含"8 个字符"
    let resp = raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "user2", "password": "short1x"})), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "7字符密码应返回400");
    let body = body_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("8 个字符"), "错误信息应含'8 个字符'");
    
    // 黑名单密码 → 400，含"太常见"
    let resp = raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "user3", "password": "password1"})), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "黑名单密码应返回400");
    let body = body_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("太常见"), "错误信息应含'太常见'");
    
    // 密码与用户名相同 → 400，含"不能与用户名相同"
    let resp = raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "bobby123", "password": "bobby123"})), None).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "密码与用户名相同应返回400");
    let body = body_json(resp).await;
    assert!(body["error"].as_str().unwrap().contains("不能与用户名相同"), "错误信息应含'不能与用户名相同'");
    
    // 合格密码 → 201
    let resp = raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "gooduser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::CREATED, "合格密码应返回201");
}

#[tokio::test]
async fn tfa_status_default_false() {
    ensure_master_key();
    let app = make_app();
    
    // 注册并登录
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    // GET /api/2fa/status → 200, {"enabled": false}
    let resp = raw_request(app.clone(), "GET", "/api/2fa/status", None, Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "2FA状态应返回200");
    let body = body_json(resp).await;
    assert_eq!(body["enabled"], false, "默认2FA应为未启用");
    
    // 未登录 → 401
    let resp = raw_request(app.clone(), "GET", "/api/2fa/status", None, None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "未登录应返回401");
}

#[tokio::test]
async fn tfa_setup_and_enable_flow() {
    ensure_master_key();
    let app = make_app();
    
    // 注册并登录
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    // 密码错误 → 401
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "wrongpass1"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "setup密码错误应返回401");
    
    // 密码正确 → 200
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "setup密码正确应返回200");
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    assert!(!secret.is_empty(), "secret不应为空");
    let otpauth_url = body["otpauthUrl"].as_str().unwrap();
    assert!(otpauth_url.starts_with("otpauth://totp/mini-os:"), "otpauthUrl应以otpauth://totp/mini-os:开头");
    let qr_svg = body["qrSvg"].as_str().unwrap();
    assert!(qr_svg.contains("<svg"), "qrSvg应含<svg");
    
    // 此时status仍为false
    let resp = raw_request(app.clone(), "GET", "/api/2fa/status", None, Some(&cookie)).await;
    let body = body_json(resp).await;
    assert_eq!(body["enabled"], false, "setup后status应仍为false");
    
    // 错误码 → 401
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": "000000"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "enable错误码应返回401");
    
    // 正确码 → 200
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "enable正确码应返回200");
    let body = body_json(resp).await;
    let backup_codes = body["backupCodes"].as_array().unwrap();
    assert_eq!(backup_codes.len(), 10, "应返回10个备用码");
    for bc in backup_codes {
        let c = bc.as_str().unwrap();
        assert_eq!(c.len(), 9, "备用码格式应为xxxx-xxxx");
        assert_eq!(&c[4..5], "-", "备用码格式应为xxxx-xxxx");
        assert!(
            c.chars().enumerate().all(|(i, ch)| i == 4 || "abcdefghjkmnpqrstuvwxyz23456789".contains(ch)),
            "备用码格式应为xxxx-xxxx"
        );
    }
    
    // status为true
    let resp = raw_request(app.clone(), "GET", "/api/2fa/status", None, Some(&cookie)).await;
    let body = body_json(resp).await;
    assert_eq!(body["enabled"], true, "enable后status应为true");
    
    // 重复enable → 400
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "重复enable应返回400");
}

#[tokio::test]
async fn tfa_login_2fa_flow() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    
    // 登录获取cookie
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    // setup
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    
    // enable
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "enable应返回200");
    
    // login → 202
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED, "启用2FA后login应返回202");
    let body = body_json(resp).await;
    assert_eq!(body["requires2fa"], true, "requires2fa应为true");
    let challenge = body["challenge"].as_str().unwrap().to_string();
    assert!(!challenge.is_empty(), "challenge不应为空");
    
    // 错误码 → 401
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": challenge, "code": "000000"})), None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "2FA验证错误码应返回401");
    
    // 正确码 → 200
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": challenge, "code": code})), None).await;
    assert_eq!(resp.status(), StatusCode::OK, "2FA验证正确码应返回200");
    let cookie2 = test_cookie(&resp);
    let body = body_json(resp).await;
    assert_eq!(body["username"], "testuser", "返回的用户名应正确");
    
    // GET /api/me → 200
    let resp = raw_request(app.clone(), "GET", "/api/me", None, Some(&cookie2)).await;
    assert_eq!(resp.status(), StatusCode::OK, "me应返回200");
}

#[tokio::test]
async fn tfa_backup_code_single_use() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册、登录、setup、enable
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let first_backup_code = body["backupCodes"][0].as_str().unwrap().to_string();
    
    // login → 202
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED);
    let body = body_json(resp).await;
    let challenge = body["challenge"].as_str().unwrap().to_string();
    
    // 用去掉"-"的备用码 → 200
    let code_no_dash = first_backup_code.replace("-", "");
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": challenge, "code": code_no_dash})), None).await;
    assert_eq!(resp.status(), StatusCode::OK, "备用码（无连字符）应验证成功");
    
    // 再次login → 202
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED);
    let body = body_json(resp).await;
    let challenge = body["challenge"].as_str().unwrap().to_string();
    
    // 同一码 → 401（已使用）
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": challenge, "code": first_backup_code})), None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "已使用的备用码应返回401");
}

#[tokio::test]
async fn tfa_challenge_lockout_after_5() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册、启用2FA
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    
    // login → 202
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED);
    let body = body_json(resp).await;
    let challenge = body["challenge"].as_str().unwrap().to_string();
    
    // 5次错误码 → 401
    for i in 0..5 {
        let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": &challenge, "code": "000000"})), None).await;
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "第{}次错误码应返回401", i + 1);
    }
    
    // 第6次真码 → 429
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": &challenge, "code": code})), None).await;
    assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS, "超过5次尝试应返回429");
}

#[tokio::test]
async fn tfa_challenge_expiry() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册、启用2FA
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    
    // login → 202
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED);
    let body = body_json(resp).await;
    let challenge = body["challenge"].as_str().unwrap().to_string();
    
    // 直接修改DB使challenge过期
    let token_hash = mini_os::auth::hash_token(&challenge);
    {
        let db = state.db.lock().unwrap();
        db.execute("UPDATE tfa_challenges SET expires_at = 1 WHERE token_hash = ?1", rusqlite::params![token_hash]).unwrap();
    }
    
    // 用真码 → 410
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": &challenge, "code": code})), None).await;
    assert_eq!(resp.status(), StatusCode::GONE, "过期challenge应返回410");
}

#[tokio::test]
async fn tfa_disable_flow() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册、启用2FA
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    
    // disable密码错误 → 401
    let resp = raw_request(app.clone(), "POST", "/api/2fa/disable", Some(json!({"password": "wrongpass1"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "disable密码错误应返回401");
    
    // disable密码正确 → 204
    let resp = raw_request(app.clone(), "POST", "/api/2fa/disable", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::NO_CONTENT, "disable密码正确应返回204");
    
    // status回false
    let resp = raw_request(app.clone(), "GET", "/api/2fa/status", None, Some(&cookie)).await;
    let body = body_json(resp).await;
    assert_eq!(body["enabled"], false, "disable后status应为false");
    
    // login直接200（不再202）
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::OK, "disable后login应返回200");
}

#[tokio::test]
async fn tfa_regenerate_backup_codes() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册、启用2FA
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    let secret_bytes = mini_os::totp::base32_decode(&secret).unwrap();
    let code = mini_os::totp::totp_code(&secret_bytes, now_secs());
    let resp = raw_request(app.clone(), "POST", "/api/2fa/enable", Some(json!({"code": code})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let old_code = body["backupCodes"][0].as_str().unwrap().to_string();
    
    // regenerate密码错误 → 401
    let resp = raw_request(app.clone(), "POST", "/api/2fa/backup-codes/regenerate", Some(json!({"password": "wrongpass1"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "regenerate密码错误应返回401");
    
    // regenerate密码正确 → 200
    let resp = raw_request(app.clone(), "POST", "/api/2fa/backup-codes/regenerate", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    assert_eq!(resp.status(), StatusCode::OK, "regenerate密码正确应返回200");
    let body = body_json(resp).await;
    let new_codes = body["backupCodes"].as_array().unwrap();
    assert_eq!(new_codes.len(), 10, "应返回10个新备用码");
    let new_code = new_codes[0].as_str().unwrap().to_string();
    
    // login → 202，用旧码 → 401
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED);
    let body = body_json(resp).await;
    let challenge = body["challenge"].as_str().unwrap().to_string();
    
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": &challenge, "code": &old_code})), None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "旧备用码应返回401");
    
    // login → 202，用新码 → 200
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    assert_eq!(resp.status(), StatusCode::ACCEPTED);
    let body = body_json(resp).await;
    let challenge = body["challenge"].as_str().unwrap().to_string();
    
    let resp = raw_request(app.clone(), "POST", "/api/auth/2fa", Some(json!({"challenge": &challenge, "code": &new_code})), None).await;
    assert_eq!(resp.status(), StatusCode::OK, "新备用码应验证成功");
}

#[tokio::test]
async fn tfa_secret_encrypted_at_rest() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let app = build_app(state.clone());
    
    // 注册、登录、setup
    raw_request(app.clone(), "POST", "/api/auth/register", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let resp = raw_request(app.clone(), "POST", "/api/auth/login", Some(json!({"username": "testuser", "password": "s3cureP4ss"})), None).await;
    let cookie = test_cookie(&resp);
    
    let resp = raw_request(app.clone(), "POST", "/api/2fa/setup", Some(json!({"password": "s3cureP4ss"})), Some(&cookie)).await;
    let body = body_json(resp).await;
    let secret = body["secret"].as_str().unwrap().to_string();
    
    // 查DB
    let stored: String;
    {
        let db = state.db.lock().unwrap();
        stored = db.query_row("SELECT totp_secret FROM users WHERE username = 'testuser'", [], |row| row.get(0)).unwrap();
    }
    assert!(!stored.contains(&secret), "DB中存储的secret不应包含明文");
    
    // 解密回原文
    let decrypted = mini_os::totp::decrypt_secret(&stored).unwrap();
    assert_eq!(decrypted, secret, "解密后应与明文secret一致");
}

#[tokio::test]
async fn migration_008_applied() {
    ensure_master_key();
    let state = init_state(":memory:", "static");
    let _app = build_app(state.clone());
    
    // SELECT COUNT(*) FROM schema_migrations ≥ 8
    let count: i64;
    {
        let db = state.db.lock().unwrap();
        count = db.query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| row.get(0)).unwrap();
    }
    assert!(count >= 8, "schema_migrations记录数应≥8，实际为{}", count);
    
    // PRAGMA table_info(users) 列名含 totp_secret 与 totp_enabled
    let mut has_totp_secret = false;
    let mut has_totp_enabled = false;
    {
        let db = state.db.lock().unwrap();
        let mut stmt = db.prepare("PRAGMA table_info(users)").unwrap();
        let mut rows = stmt.query([]).unwrap();
        while let Ok(Some(row)) = rows.next() {
            let col_name: String = row.get(1).unwrap();
            if col_name == "totp_secret" { has_totp_secret = true; }
            if col_name == "totp_enabled" { has_totp_enabled = true; }
        }
    }
    assert!(has_totp_secret, "users表应含totp_secret列");
    assert!(has_totp_enabled, "users表应含totp_enabled列");
}
