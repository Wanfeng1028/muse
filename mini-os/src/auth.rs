// src/auth.rs
//
// 认证模块：密码哈希（argon2id）+ session token 生成/校验 + Cookie 工具。
//
// 安全说明：
// - 密码使用 Argon2id 默认参数（argon2 0.5 默认即 Argon2id），输出 PHC 字符串。
// - Session token 明文仅在创建时返回一次；数据库中只存 hex(SHA256(token))。
// - verify_password 解析失败返回 false，不做 unwrap；错误分支统一返回 Result<_, String>。

use argon2::password_hash::rand_core::OsRng;
use argon2::password_hash::{PasswordHash, PasswordHasher, SaltString};
use argon2::{Argon2, PasswordVerifier};
use rand::rngs::OsRng as RandOsRng;
use rand::TryRngCore;
use rusqlite::params;
use sha2::{Digest, Sha256};
use std::time::{SystemTime, UNIX_EPOCH};

/// 会话 Cookie 名称。
pub const SESSION_COOKIE: &str = "mini_os_session";

/// 当前登录用户。
#[derive(Debug, Clone)]
pub struct CurrentUser {
    pub id: i64,
    pub username: String,
    pub is_admin: bool,
    /// 取自 users.role，规范值 admin/editor/viewer。
    pub role: String,
}

/// 返回当前 Unix epoch 秒（可能为负，仅在系统时间异常时）。
pub fn now_epoch_secs() -> i64 {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(d) => d.as_secs() as i64,
        Err(e) => -(e.duration().as_secs() as i64),
    }
}

/// 使用 Argon2id 默认参数对明文密码做哈希，返回 PHC 字符串。
pub fn hash_password(plain: &str) -> Result<String, String> {
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();
    let hash = argon2
        .hash_password(plain.as_bytes(), &salt)
        .map_err(|e| format!("argon2 hash failed: {e}"))?;
    Ok(hash.to_string())
}

/// 校验明文密码是否匹配 PHC 哈希。
///
/// 解析失败 / 校验失败均返回 false。为降低用户名枚举与计时差异，
/// 这里不区分“哈希格式非法”和“密码不匹配”两种错误分支。
pub fn verify_password(plain: &str, hash: &str) -> bool {
    let parsed = match PasswordHash::new(hash) {
        Ok(p) => p,
        Err(_) => return false,
    };
    Argon2::default()
        .verify_password(plain.as_bytes(), &parsed)
        .is_ok()
}

/// 生成 32 字节随机 token，返回 64 字符的 hex 字符串。
pub fn new_session_token() -> Result<String, String> {
    let mut buf = [0u8; 32];
    let mut rng = RandOsRng;
    rng.try_fill_bytes(&mut buf)
        .map_err(|e| format!("os rng failed: {e}"))?;
    Ok(hex::encode(buf))
}

/// 对 token 计算 hex(SHA256(token))，用于数据库中存储。
pub fn hash_token(token: &str) -> String {
    let digest = Sha256::digest(token.as_bytes());
    hex::encode(digest)
}

/// 创建新会话：生成明文 token，存 hash，返回明文 token。
pub fn create_session(
    conn: &rusqlite::Connection,
    user_id: i64,
    ttl_secs: i64,
) -> Result<String, String> {
    let token = new_session_token()?;
    let token_hash = hash_token(&token);
    let now = now_epoch_secs();
    let expires_at = now.saturating_add(ttl_secs);
    let created_at = now.to_string();
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) \
         VALUES (?1, ?2, ?3, ?4)",
        params![token_hash, user_id, expires_at, created_at],
    )
    .map_err(|e| format!("insert session failed: {e}"))?;
    Ok(token)
}

/// 校验 token：查到且未过期返回 Some(CurrentUser)；过期会顺手删除该行。
pub fn verify_session(
    conn: &rusqlite::Connection,
    token: &str,
) -> Result<Option<CurrentUser>, String> {
    if token.is_empty() {
        return Ok(None);
    }
    let token_hash = hash_token(token);
    let now = now_epoch_secs();

    let row: Option<(i64, String, i64, i64, String)> = conn
        .query_row(
            "SELECT s.expires_at, u.username, u.is_admin, u.id, u.role \
             FROM sessions s JOIN users u ON u.id = s.user_id \
             WHERE s.token_hash = ?1",
            params![token_hash],
            |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, i64>(2)?,
                    r.get::<_, i64>(3)?,
                    r.get::<_, String>(4)?,
                ))
            },
        )
        .map(Some)
        .or_else(|e| match e {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(format!("query session failed: {other}")),
        })?;

    let Some((expires_at, username, is_admin, id, role)) = row else {
        return Ok(None);
    };

    if expires_at <= now {
        // 过期 session 顺手清理（失败不致命，忽略错误以保持幂等语义）。
        let _ = conn.execute(
            "DELETE FROM sessions WHERE token_hash = ?1",
            params![hash_token(token)],
        );
        return Ok(None);
    }

    Ok(Some(CurrentUser {
        id,
        username,
        is_admin: is_admin != 0,
        role,
    }))
}

/// 删除指定 token 对应的会话（幂等）。
pub fn revoke_session(conn: &rusqlite::Connection, token: &str) -> Result<(), String> {
    let token_hash = hash_token(token);
    conn.execute(
        "DELETE FROM sessions WHERE token_hash = ?1",
        params![token_hash],
    )
    .map_err(|e| format!("delete session failed: {e}"))?;
    Ok(())
}

/// 删除某个用户的所有会话（幂等）。
pub fn revoke_all_user_sessions(conn: &rusqlite::Connection, user_id: i64) -> Result<(), String> {
    conn.execute("DELETE FROM sessions WHERE user_id = ?1", params![user_id])
        .map_err(|e| format!("delete user sessions failed: {e}"))?;
    Ok(())
}

/// 从 Cookie 头中提取 session token。
///
/// 规则：按 `;` 分隔，逐段 trim，精确匹配 `mini_os_session=` 前缀；
/// 值经过 trim 后为空则返回 None。
pub fn extract_session_token(cookie_header: Option<&str>) -> Option<String> {
    let header = cookie_header?;
    let prefix = format!("{SESSION_COOKIE}=");
    for part in header.split(';') {
        let piece = part.trim();
        if let Some(value) = piece.strip_prefix(&prefix) {
            let v = value.trim();
            if v.is_empty() {
                return None;
            }
            return Some(v.to_string());
        }
    }
    None
}

/// 构造 Set-Cookie 值：`mini_os_session=<token>; Path=/; HttpOnly; SameSite=Lax; Max-Age=<ttl>`。
pub fn set_session_cookie_value(token: &str, ttl_secs: i64) -> String {
    format!(
        "{name}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={ttl}",
        name = SESSION_COOKIE,
        token = token,
        ttl = ttl_secs,
    )
}

/// 构造清除 Cookie 的 Set-Cookie 值。
pub fn clear_session_cookie_value() -> String {
    format!(
        "{name}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
        name = SESSION_COOKIE,
    )
}

/// 校验用户名：3–32 字符，仅 [A-Za-z0-9_.-]，且不能是保留名 "legacy"。
pub fn validate_username(name: &str) -> Result<(), &'static str> {
    let len = name.chars().count();
    if !(3..=32).contains(&len) {
        return Err("username must be 3-32 characters");
    }
    for c in name.chars() {
        let ok = c.is_ascii_alphanumeric() || c == '_' || c == '.' || c == '-';
        if !ok {
            return Err("username may only contain [A-Za-z0-9_.-]");
        }
    }
    if name.eq_ignore_ascii_case("legacy") {
        return Err("username is reserved");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_and_verify_roundtrip() {
        let plain = "correct horse battery staple";
        let hash = hash_password(plain).unwrap();
        assert!(hash.starts_with("$argon2id$"));
        assert!(verify_password(plain, &hash));
    }

    #[test]
    fn verify_wrong_password_is_false() {
        let hash = hash_password("hunter2").unwrap();
        assert!(!verify_password("hunter3", &hash));
        assert!(!verify_password("", &hash));
        assert!(!verify_password("hunter2", "not-a-phc-string"));
    }

    #[test]
    fn validate_username_rules() {
        assert!(validate_username("alice").is_ok());
        assert!(validate_username("a.b-c_1").is_ok());
        assert!(validate_username("abc").is_ok());

        assert!(validate_username("ab").is_err());
        assert!(validate_username("").is_err());
        assert!(validate_username("a".repeat(33).as_str()).is_err());
        assert!(validate_username("has space").is_err());
        assert!(validate_username("bad@char").is_err());
        assert!(validate_username("legacy").is_err());
        assert!(validate_username("LEGACY").is_err());
    }

    #[test]
    fn token_is_64_hex_and_unique() {
        let t1 = new_session_token().unwrap();
        let t2 = new_session_token().unwrap();
        assert_eq!(t1.len(), 64);
        assert!(t1.chars().all(|c| c.is_ascii_hexdigit()));
        assert_eq!(hash_token(&t1).len(), 64);
        assert_ne!(t1, t2);
    }
}
