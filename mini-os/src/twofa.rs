use std::sync::Arc;

use axum::extract::{Extension, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use rand::TryRngCore;
use rusqlite::{params, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::auth;
use crate::handlers::{err, ApiResult};
use crate::totp;
use crate::AppState;

#[derive(Deserialize)]
pub struct TwoFaSetupRequest {
    pub password: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TwoFaSetupResponse {
    pub secret: String,
    pub otpauth_url: String,
    pub qr_svg: String,
}

#[derive(Deserialize)]
pub struct TwoFaEnableRequest {
    pub code: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TwoFaEnableResponse {
    pub backup_codes: Vec<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TwoFaStatusResponse {
    pub enabled: bool,
}

/// 删除已过期的登录二次验证挑战，返回删除行数。供 verify 入口与发挑战入口调用，
/// 避免过期行在长期运行中堆积；不删除未过期行，不碰 attempts 计数。
pub fn sweep_expired_challenges(conn: &rusqlite::Connection) -> Result<usize, String> {
    let now = auth::now_epoch_secs();
    conn.execute(
        "DELETE FROM tfa_challenges WHERE expires_at <= ?1",
        rusqlite::params![now],
    )
    .map_err(|e| format!("db error: {e}"))
}

/// 与 sweep_expired_challenges 相同，但排除 token_hash 等于 except_token_hash 的行。
/// 供 verify_login 调用：本次请求的 challenge 行必须留给 handler 自己的过期分支处理
/// （过期返回 410 GONE，不存在返回 401），清扫不得先把它删掉导致 410 退化为 401。
pub fn sweep_expired_challenges_except(
    conn: &rusqlite::Connection,
    except_token_hash: &str,
) -> Result<usize, String> {
    let now = auth::now_epoch_secs();
    conn.execute(
        "DELETE FROM tfa_challenges WHERE expires_at <= ?1 AND token_hash != ?2",
        rusqlite::params![now, except_token_hash],
    )
    .map_err(|e| format!("db error: {e}"))
}

pub fn create_tfa_challenge(conn: &rusqlite::Connection, user_id: i64) -> Result<String, String> {
    let _ = sweep_expired_challenges(conn);
    let plain = auth::new_session_token()?;
    let h = auth::hash_token(&plain);
    let expires_at = auth::now_epoch_secs() + 300;

    conn.execute(
        "INSERT INTO tfa_challenges (token_hash, user_id, expires_at, attempts) VALUES (?1,?2,?3,0)",
        rusqlite::params![h, user_id, expires_at],
    )
    .map_err(|e| format!("db error: {e}"))?;
    Ok(plain)
}

pub async fn status(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
) -> ApiResult {
    let enabled: i32 = state
        .db
        .lock()
        .unwrap()
        .query_row(
            "SELECT totp_enabled FROM users WHERE id=?1",
            rusqlite::params![user.id],
            |row| row.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    Ok(Json(TwoFaStatusResponse {
        enabled: enabled != 0,
    })
    .into_response())
}

pub async fn setup(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Json(req): Json<TwoFaSetupRequest>,
) -> ApiResult {
    if req.password.is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "密码不能为空"));
    }

    let db = state.db.lock().unwrap();

    let password_hash: Option<String> = db
        .query_row(
            "SELECT password_hash FROM users WHERE id=?1",
            rusqlite::params![user.id],
            |row| row.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let hash = match password_hash {
        Some(h) => h,
        None => return Err(err(StatusCode::UNAUTHORIZED, "密码错误")),
    };

    if !auth::verify_password(&req.password, &hash) {
        return Err(err(StatusCode::UNAUTHORIZED, "密码错误"));
    }

    let secret = totp::generate_secret().map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    let enc =
        totp::encrypt_secret(&secret).map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;

    db.execute(
        "UPDATE users SET totp_secret=?1, totp_enabled=0 WHERE id=?2",
        rusqlite::params![enc, user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    drop(db);
    state.metrics.inc_auth("2fa_setup");

    let otpauth_url = totp::otpauth_url(&user.username, &secret);
    let qr_svg = totp::qr_svg(&otpauth_url)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "二维码生成失败"))?;

    let resp = TwoFaSetupResponse {
        secret,
        otpauth_url,
        qr_svg,
    };
    Ok(Json(resp).into_response())
}

pub async fn enable(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Json(req): Json<TwoFaEnableRequest>,
) -> ApiResult {
    let db = state.db.lock().unwrap();

    let (totp_secret, totp_enabled): (Option<String>, i32) = db
        .query_row(
            "SELECT totp_secret, totp_enabled FROM users WHERE id=?1",
            rusqlite::params![user.id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    if totp_secret.is_none() {
        return Err(err(StatusCode::BAD_REQUEST, "请先完成设置步骤，获取二维码"));
    }
    if totp_enabled != 0 {
        return Err(err(StatusCode::BAD_REQUEST, "两步验证已启用"));
    }

    let secret_enc = totp_secret.unwrap();
    let secret_b32 = totp::decrypt_secret(&secret_enc).map_err(|_| {
        err(
            StatusCode::INTERNAL_SERVER_ERROR,
            "密钥数据损坏，请重新设置",
        )
    })?;
    let bytes = totp::base32_decode(&secret_b32).map_err(|_| {
        err(
            StatusCode::INTERNAL_SERVER_ERROR,
            "密钥数据损坏，请重新设置",
        )
    })?;

    let now = auth::now_epoch_secs();
    if !totp::verify_totp(&bytes, &req.code, now) {
        return Err(err(
            StatusCode::UNAUTHORIZED,
            "验证码错误，请检查手机时间是否准确",
        ));
    }

    db.execute(
        "UPDATE users SET totp_enabled=1 WHERE id=?1",
        rusqlite::params![user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    db.execute(
        "DELETE FROM tfa_backup_codes WHERE user_id=?1",
        rusqlite::params![user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let charset = "abcdefghjkmnpqrstuvwxyz23456789";
    let mut backup_codes: Vec<String> = Vec::new();

    for _ in 0..10 {
        let mut rng = rand::rngs::OsRng;
        let mut buf = [0u8; 8];
        rng.try_fill_bytes(&mut buf).map_err(|e| {
            err(
                StatusCode::INTERNAL_SERVER_ERROR,
                &format!("os rng failed: {e}"),
            )
        })?;
        let cs = charset.as_bytes();
        let chars: String = buf
            .iter()
            .map(|&b| cs[(b % cs.len() as u8) as usize] as char)
            .collect();
        let code = format!("{}-{}", &chars[0..4], &chars[4..8]);
        // 入库哈希用去横线规范形，验证时同样规范化后再比对（用户输带/不带横线均可）。
        let code_hash = auth::hash_password(&code.replace('-', ""))
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
        db.execute(
            "INSERT INTO tfa_backup_codes (user_id, code_hash) VALUES (?1,?2)",
            rusqlite::params![user.id, code_hash],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        backup_codes.push(code);
    }

    drop(db);
    state.metrics.inc_auth("2fa_enabled");

    let resp = TwoFaEnableResponse { backup_codes };
    Ok(Json(resp).into_response())
}

#[derive(Deserialize)]
pub struct TwoFaDisableRequest {
    pub password: String,
}

#[derive(Deserialize)]
pub struct TwoFaVerifyRequest {
    pub challenge: String,
    pub code: String,
}

pub async fn disable(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Json(req): Json<TwoFaDisableRequest>,
) -> ApiResult {
    if req.password.is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "密码不能为空"));
    }
    let conn = state.db.lock().unwrap();
    let hash: Option<String> = conn
        .query_row(
            "SELECT password_hash FROM users WHERE id = ?1",
            params![user.id],
            |r| r.get(0),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?
        .flatten();
    if !auth::verify_password(&req.password, &hash.unwrap_or_default()) {
        return Err(err(StatusCode::UNAUTHORIZED, "密码错误"));
    }
    conn.execute(
        "UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?1",
        params![user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    conn.execute(
        "DELETE FROM tfa_backup_codes WHERE user_id = ?1",
        params![user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    state.metrics.inc_auth("2fa_disabled");
    Ok(StatusCode::NO_CONTENT.into_response())
}

pub async fn regenerate_backup_codes(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Json(req): Json<TwoFaDisableRequest>,
) -> ApiResult {
    use rand::TryRngCore;
    if req.password.is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "密码不能为空"));
    }
    let conn = state.db.lock().unwrap();
    let hash: Option<String> = conn
        .query_row(
            "SELECT password_hash FROM users WHERE id = ?1",
            params![user.id],
            |r| r.get(0),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?
        .flatten();
    if !auth::verify_password(&req.password, &hash.unwrap_or_default()) {
        return Err(err(StatusCode::UNAUTHORIZED, "密码错误"));
    }
    let totp_enabled: i64 = conn
        .query_row(
            "SELECT totp_enabled FROM users WHERE id = ?1",
            params![user.id],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    if totp_enabled != 1 {
        return Err(err(StatusCode::BAD_REQUEST, "请先启用两步验证"));
    }
    conn.execute(
        "DELETE FROM tfa_backup_codes WHERE user_id = ?1",
        params![user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let alphabet = "abcdefghjkmnpqrstuvwxyz23456789";
    let mut codes = Vec::new();
    let mut rng = rand::rngs::OsRng;
    for _ in 0..10 {
        let mut buf = [0u8; 8];
        rng.try_fill_bytes(&mut buf).map_err(|e| {
            err(
                StatusCode::INTERNAL_SERVER_ERROR,
                &format!("os rng failed: {e}"),
            )
        })?;
        let code: String = buf
            .iter()
            .map(|&b| alphabet.as_bytes()[(b % alphabet.len() as u8) as usize] as char)
            .collect();
        let code = format!("{}-{}", &code[..4], &code[4..]);
        let h = auth::hash_password(&code.replace('-', ""))
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
        conn.execute(
            "INSERT INTO tfa_backup_codes (user_id, code_hash) VALUES (?1, ?2)",
            params![user.id, h],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        codes.push(code);
    }
    state.metrics.inc_auth("2fa_backup_regenerated");

    #[derive(Serialize)]
    #[serde(rename_all = "camelCase")]
    struct Resp {
        backup_codes: Vec<String>,
    }
    Ok((
        StatusCode::OK,
        Json(Resp {
            backup_codes: codes,
        }),
    )
        .into_response())
}

pub async fn verify_login(
    State(state): State<Arc<AppState>>,
    Json(req): Json<TwoFaVerifyRequest>,
) -> ApiResult {
    let th = auth::hash_token(&req.challenge);
    let conn = state.db.lock().unwrap();
    let now = auth::now_epoch_secs();
    let _ = sweep_expired_challenges_except(&conn, &th);
    let row: Option<(i64, i64, i64)> = conn
        .query_row(
            "SELECT user_id, expires_at, attempts FROM tfa_challenges WHERE token_hash = ?1",
            params![th],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let (user_id, expires_at, attempts) = match row {
        Some(r) => r,
        None => return Err(err(StatusCode::UNAUTHORIZED, "验证已过期，请重新登录")),
    };

    if expires_at <= now {
        conn.execute(
            "DELETE FROM tfa_challenges WHERE token_hash = ?1",
            params![th],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        return Err(err(StatusCode::GONE, "验证已过期，请重新登录"));
    }

    if attempts >= 5 {
        conn.execute(
            "DELETE FROM tfa_challenges WHERE token_hash = ?1",
            params![th],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        return Err(err(
            StatusCode::TOO_MANY_REQUESTS,
            "尝试次数过多，请重新登录",
        ));
    }

    let user_row: (Option<String>, i64, String, i64, String) = conn
        .query_row(
            "SELECT totp_secret, totp_enabled, username, is_admin, role FROM users WHERE id = ?1",
            params![user_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let (enc, totp_enabled, username, is_admin, role) = user_row;
    if totp_enabled != 1 || enc.is_none() {
        conn.execute(
            "DELETE FROM tfa_challenges WHERE token_hash = ?1",
            params![th],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        return Err(err(StatusCode::GONE, "两步验证未启用，请重新登录"));
    }

    let norm: String = req
        .code
        .chars()
        .filter(|c| *c != '-')
        .collect::<String>()
        .to_lowercase();
    let mut valid = false;
    let mut used_backup = false;

    let sec = enc.unwrap();
    if let Ok(dec) = totp::decrypt_secret(&sec) {
        if let Ok(bytes) = totp::base32_decode(&dec) {
            if totp::verify_totp(&bytes, &req.code, now) {
                valid = true;
            }
        }
    }

    if !valid {
        let mut stmt = conn
            .prepare(
                "SELECT id, code_hash FROM tfa_backup_codes WHERE user_id = ?1 AND used_at IS NULL",
            )
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map(params![user_id], |r| {
                Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?))
            })
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        for r in rows {
            let (id, hash) =
                r.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
            if auth::verify_password(&norm, &hash) {
                conn.execute(
                    "UPDATE tfa_backup_codes SET used_at = datetime('now') WHERE id = ?1",
                    params![id],
                )
                .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
                valid = true;
                used_backup = true;
                break;
            }
        }
    }

    if valid {
        conn.execute(
            "DELETE FROM tfa_challenges WHERE token_hash = ?1",
            params![th],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let ttl = state.session_ttl_secs;
        let token = auth::create_session(&conn, user_id, ttl as i64)
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
        let cookie = auth::set_session_cookie_value(&token, ttl as i64);
        state.metrics.inc_auth("2fa_login_ok");
        if used_backup {
            state.metrics.inc_auth("2fa_backup_used");
        }
        Ok((
            StatusCode::OK,
            [(axum::http::header::SET_COOKIE, cookie)],
            Json(crate::models::UserInfo {
                id: user_id,
                username,
                is_admin: is_admin != 0,
                role,
            }),
        )
            .into_response())
    } else {
        conn.execute(
            "UPDATE tfa_challenges SET attempts = attempts + 1 WHERE token_hash = ?1",
            params![th],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        state.metrics.inc_auth("2fa_login_fail");
        Err(err(StatusCode::UNAUTHORIZED, "验证码错误"))
    }
}
