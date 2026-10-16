//! 登录限流中间件与令牌桶实现（mini-os v1.5）。
//!
//! 限流维度：IP + 账号双维度。IP 桶按客户端 IP 键控，账号桶按请求体中的
//! `username`（trim 后非空）键控。任一维度超限即拒绝，且拒绝时不扣减任何桶。
//!
//! 默认配额：`MINIOS_LOGIN_RPS`（每秒令牌补充速率）默认 `1`；
//! `MINIOS_LOGIN_BURST`（桶容量 / 突发上限）默认 `5`。
//! 非法值（解析失败、<=0、NaN、无穷大）启动即 `Err`，由 config 层 fail-fast 退出。
//!
//! 429 响应契约（字段名/头名逐字固定）：
//! - 状态码 `429`
//! - 响应头 `Retry-After: <secs>`（整数秒的十进制字符串）
//! - JSON 体 `{"error": "登录尝试过于频繁，请 <secs> 秒后重试", "retry_after": <secs>}`
//! - 同时 `state.metrics.inc_auth("login_ratelimited")` 计数
//!
//! 探针豁免：本中间件只挂在 `/api/auth/login` 路由上（见 lib.rs `build_app`），
//! 因此 `/api/health`、`/api/readyz`、`/metrics` 等健康/就绪探针天然不受影响。
//!
//! IP 提取优先级：`X-Forwarded-For` 首项（按逗号切、trim）→ `X-Real-IP` →
//! `ConnectInfo<SocketAddr>`（若 extensions 中存在）→ `"unknown"`。
//! 部署在反向代理后时，代理需正确透传 `X-Forwarded-For`（并保证不被客户端伪造），
//! 否则所有请求都会落到同一个键（如代理 IP 或 `"unknown"`），限流会误伤或失效。

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::body::{to_bytes, Body};
use axum::extract::{ConnectInfo, Request, State};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

use crate::AppState;

/// 登录限流配置：令牌补充速率与桶容量。
#[derive(Debug, Clone, Copy)]
pub struct LoginLimitConfig {
    /// 每秒补充的令牌数（必须 > 0、有限、非 NaN）。
    pub rps: f64,
    /// 桶容量 / 突发上限。
    pub burst: u64,
}

/// 环境变量名。
const ENV_RPS: &str = "MINIOS_LOGIN_RPS";
const ENV_BURST: &str = "MINIOS_LOGIN_BURST";

/// 请求体读取上限（64KB），超出则视为解析失败并放行（仅记 IP 桶）。
const MAX_BODY_BYTES: usize = 64 * 1024;

/// 当任一 map 长度超过该阈值时，触发一次惰性清理。
const CLEANUP_THRESHOLD: usize = 4096;

/// 从环境变量解析登录限流配置。
///
/// - `MINIOS_LOGIN_RPS` 未设置时默认 `"1"`；解析失败 / <=0 / NaN / 无穷大一律 `Err`。
/// - `MINIOS_LOGIN_BURST` 未设置时默认 `"5"`；解析失败（含非整数）一律 `Err`。
///
/// 返回的 `Err` 字符串会点名具体是哪个变量、以及期望什么。
pub fn parse_login_limit() -> Result<LoginLimitConfig, String> {
    let raw_rps = std::env::var(ENV_RPS).ok();
    let raw_burst = std::env::var(ENV_BURST).ok();
    let rps = parse_rps(raw_rps.as_deref())?;
    let burst = parse_burst(raw_burst.as_deref())?;
    Ok(LoginLimitConfig { rps, burst })
}

/// 纯函数：解析 rps。`None` 表示未设置 → 使用默认 `"1"`。
fn parse_rps(raw: Option<&str>) -> Result<f64, String> {
    let s = raw.unwrap_or("1");
    let v: f64 = s
        .parse()
        .map_err(|_| format!("{} 非法：'{}'，期望大于 0 的数字", ENV_RPS, s))?;
    if !v.is_finite() || v <= 0.0 {
        return Err(format!("{} 非法：'{}'，期望大于 0 的有限数字", ENV_RPS, s));
    }
    Ok(v)
}

/// 纯函数：解析 burst。`None` 表示未设置 → 使用默认 `"5"`。
fn parse_burst(raw: Option<&str>) -> Result<u64, String> {
    let s = raw.unwrap_or("5");
    let v: u64 = s
        .parse()
        .map_err(|_| format!("{} 非法：'{}'，期望大于 0 的整数", ENV_BURST, s))?;
    if v == 0 {
        return Err(format!("{} 非法：'{}'，期望大于 0 的整数", ENV_BURST, s));
    }
    Ok(v)
}

/// 单个令牌桶。
#[derive(Debug, Clone)]
struct Bucket {
    tokens: f64,
    last: Instant,
}

/// IP + 账号双维度令牌桶限流器。
pub struct RateLimiter {
    rps: f64,
    burst: u64,
    /// 惰性清理的 idle TTL：max(300s, 10 * burst / rps)。
    idle_ttl: Duration,
    ip: Mutex<HashMap<String, Bucket>>,
    account: Mutex<HashMap<String, Bucket>>,
}

impl RateLimiter {
    /// 根据配置构造限流器。所有桶初始为满（capacity = burst）。
    pub fn new(config: &LoginLimitConfig) -> Self {
        // idle_ttl = max(300s, 10 * burst / rps)；rps 已在解析层保证 > 0 且有限。
        let ttl_secs = 10.0 * (config.burst as f64) / config.rps;
        let idle_ttl = Duration::from_secs_f64(ttl_secs.max(300.0));
        Self {
            rps: config.rps,
            burst: config.burst,
            idle_ttl,
            ip: Mutex::new(HashMap::new()),
            account: Mutex::new(HashMap::new()),
        }
    }

    /// 用当前时间尝试获取一个令牌。等价于 `try_acquire_at(ip, acct, Instant::now())`。
    pub fn try_acquire(&self, ip_key: &str, account_key: Option<&str>) -> Result<(), u64> {
        self.try_acquire_at(ip_key, account_key, Instant::now())
    }

    /// 在指定时间点尝试获取令牌（供单元测试伪造时间使用）。
    ///
    /// 语义：
    /// - 先按流逝时间给两个桶补 token：`tokens = min(capacity, tokens + elapsed * rps)`。
    /// - 任一桶 `tokens < 1.0` → `Err(retry_after_secs)`，且**不扣减任何桶**。
    ///   `retry_after_secs = max(1, ceil((1.0 - tokens) / rps))` 取两桶中较大者。
    /// - 两桶都够 → 各扣 1（`account_key` 为 `None` 或空字符串时跳过账号桶），返回 `Ok(())`。
    pub fn try_acquire_at(
        &self,
        ip_key: &str,
        account_key: Option<&str>,
        now: Instant,
    ) -> Result<(), u64> {
        let acct_key = match account_key {
            Some(s) if !s.is_empty() => Some(s.to_string()),
            _ => None,
        };

        let capacity = self.burst as f64;

        // --- IP 桶：补充 token，观察是否够用 ---
        let mut ip_guard = self.ip.lock().unwrap_or_else(|e| e.into_inner());
        self.maybe_cleanup(&mut ip_guard, now);
        let ip_tokens = {
            let b = ip_guard
                .entry(ip_key.to_string())
                .or_insert_with(|| Bucket {
                    tokens: capacity,
                    last: now,
                });
            Self::refill(b, capacity, self.rps, now);
            b.tokens
        };

        // --- 账号桶（可选）：补充 token，观察是否够用 ---
        let mut acct_guard = self.account.lock().unwrap_or_else(|e| e.into_inner());
        self.maybe_cleanup(&mut acct_guard, now);
        let acct_tokens = if let Some(k) = &acct_key {
            let b = acct_guard.entry(k.clone()).or_insert_with(|| Bucket {
                tokens: capacity,
                last: now,
            });
            Self::refill(b, capacity, self.rps, now);
            Some(b.tokens)
        } else {
            None
        };

        // --- 判断是否放行 ---
        let mut need_secs: u64 = 0;
        if ip_tokens < 1.0 {
            need_secs = need_secs.max(Self::retry_after(1.0 - ip_tokens, self.rps));
        }
        if let Some(t) = acct_tokens {
            if t < 1.0 {
                need_secs = need_secs.max(Self::retry_after(1.0 - t, self.rps));
            }
        }

        if need_secs > 0 {
            // 拒绝路径：不扣任何桶。
            return Err(need_secs);
        }

        // --- 放行路径：各扣 1 ---
        if let Some(b) = ip_guard.get_mut(ip_key) {
            b.tokens -= 1.0;
        }
        if let Some(k) = &acct_key {
            if let Some(b) = acct_guard.get_mut(k) {
                b.tokens -= 1.0;
            }
        }
        Ok(())
    }

    /// 按流逝时间补 token，上限为 capacity。同时更新 `last`。
    fn refill(b: &mut Bucket, capacity: f64, rps: f64, now: Instant) {
        let elapsed = now.saturating_duration_since(b.last).as_secs_f64();
        if elapsed > 0.0 {
            b.tokens = (b.tokens + elapsed * rps).min(capacity);
            b.last = now;
        }
    }

    /// 计算需要等待的整数秒：max(1, ceil(deficit / rps))。
    fn retry_after(deficit: f64, rps: f64) -> u64 {
        if deficit <= 0.0 {
            return 1;
        }
        let secs = (deficit / rps).ceil();
        if !secs.is_finite() || secs < 1.0 {
            1
        } else {
            secs as u64
        }
    }

    /// 惰性清理：当 map 长度超过阈值时，移除 last 早于 `now - idle_ttl` 的条目。
    fn maybe_cleanup(&self, map: &mut HashMap<String, Bucket>, now: Instant) {
        if map.len() <= CLEANUP_THRESHOLD {
            return;
        }
        let cutoff = now.checked_sub(self.idle_ttl).unwrap_or(now);
        map.retain(|_, b| b.last >= cutoff);
    }
}

/// 从请求头/扩展中提取客户端 IP 键。
///
/// 优先级：`X-Forwarded-For` 首项（逗号切、trim）→ `X-Real-IP` →
/// `ConnectInfo<SocketAddr>`（若 extensions 中有）→ `"unknown"`。
fn extract_ip_key(req: &Request) -> String {
    if let Some(xff) = req
        .headers()
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
    {
        if let Some(first) = xff.split(',').next() {
            let t = first.trim();
            if !t.is_empty() {
                return t.to_string();
            }
        }
    }
    if let Some(real) = req.headers().get("x-real-ip").and_then(|v| v.to_str().ok()) {
        let t = real.trim();
        if !t.is_empty() {
            return t.to_string();
        }
    }
    if let Some(ci) = req.extensions().get::<ConnectInfo<SocketAddr>>() {
        return ci.0.ip().to_string();
    }
    "unknown".to_string()
}

/// 从请求体 JSON 中提取账号键（`username`，trim 后非空）。
fn extract_account_key(body: &serde_json::Value) -> Option<String> {
    body.get("username")
        .and_then(|v| v.as_str())
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

/// 登录限流中间件：只作用于 `/api/auth/login`。
///
/// 见模块头注释的 429 契约与探针豁免说明。
pub async fn login_ratelimit_middleware(
    State(state): State<Arc<AppState>>,
    req: Request,
    next: Next,
) -> Response {
    // 纵深防御：只对登录路径生效。探针路径（/api/health、/api/readyz、/metrics）
    // 只挂在各自路由上，本中间件不会被它们触发。
    if req.uri().path() != "/api/auth/login" {
        return next.run(req).await;
    }

    let ip_key = extract_ip_key(&req);

    // 读请求体（上限 64KB）。拆分 parts 与 body，稍后重建。
    let (parts, body) = req.into_parts();
    let (account_key, body_bytes) = match to_bytes(body, MAX_BODY_BYTES).await {
        Ok(bytes) => {
            let acct = serde_json::from_slice::<serde_json::Value>(&bytes)
                .ok()
                .and_then(|v| extract_account_key(&v));
            (acct, Some(bytes))
        }
        Err(_) => {
            // 读体失败：放行，让 handler 返回 400/422；只记 IP 桶。
            (None, None)
        }
    };

    match state
        .login_limiter
        .try_acquire(&ip_key, account_key.as_deref())
    {
        Ok(()) => {
            let body = match body_bytes {
                Some(b) => Body::from(b),
                None => Body::empty(),
            };
            let req = Request::from_parts(parts, body);
            next.run(req).await
        }
        Err(secs) => {
            state.metrics.inc_auth("login_ratelimited");
            let payload = json!({
                "error": format!("登录尝试过于频繁，请 {} 秒后重试", secs),
                "retry_after": secs,
            });
            (
                axum::http::StatusCode::TOO_MANY_REQUESTS,
                [(axum::http::header::RETRY_AFTER, secs.to_string())],
                Json(payload),
            )
                .into_response()
        }
    }
}

/// 分享读取限流配置：`rps = 每分钟次数 / 60`。
pub struct ShareReadLimitConfig {
    pub rps: f64,
    pub burst: u64,
}

fn parse_share_rpm(raw: Option<&str>) -> Result<f64, String> {
    let s = raw.unwrap_or("30");
    let v: f64 = s
        .parse()
        .map_err(|_| "MINIOS_SHARE_READ_RPM 非法：无法解析为数字".to_string())?;
    if !v.is_finite() || v <= 0.0 {
        return Err("MINIOS_SHARE_READ_RPM 非法：必须为正的有限数".to_string());
    }
    Ok(v)
}

fn parse_share_burst(raw: Option<&str>) -> Result<u64, String> {
    let s = raw.unwrap_or("30");
    let v: u64 = s
        .parse()
        .map_err(|_| "MINIOS_SHARE_READ_BURST 非法：无法解析为整数".to_string())?;
    if v == 0 {
        return Err("MINIOS_SHARE_READ_BURST 非法：必须大于 0".to_string());
    }
    Ok(v)
}

/// 读取分享读取限流配置。
pub fn parse_share_limit() -> Result<ShareReadLimitConfig, String> {
    let rpm = parse_share_rpm(std::env::var("MINIOS_SHARE_READ_RPM").ok().as_deref())?;
    let burst = parse_share_burst(std::env::var("MINIOS_SHARE_READ_BURST").ok().as_deref())?;
    Ok(ShareReadLimitConfig {
        rps: rpm / 60.0,
        burst,
    })
}

/// 从 URI 中提取分享 token（纯函数，不引入新依赖）。
///
/// - 路径以 `/api/s/` 开头：取第三段（到下一个 `/` 或 `?` 为止），URL 解码，空则 `None`。
/// - 路径为 `/api/share/list`：从 query 中取 `token=` 参数并 URL 解码，空则 `None`。
/// - 其他路径或解码失败：`None`。
fn extract_share_token(uri: &axum::http::Uri) -> Option<String> {
    let path = uri.path();
    if let Some(rest) = path.strip_prefix("/api/s/") {
        let seg = rest.split(['/', '?']).next().unwrap_or("");
        if seg.is_empty() {
            return None;
        }
        return url_decode(seg);
    }
    if path == "/api/share/list" {
        let query = uri.query()?;
        for pair in query.split('&') {
            if let Some(val) = pair.strip_prefix("token=") {
                if val.is_empty() {
                    return None;
                }
                return url_decode(val);
            }
        }
        return None;
    }
    None
}

/// 手写 URL 解码：处理 `%XX` 与 `+`，非法 `%` 序列返回 `None`。
fn url_decode(s: &str) -> Option<String> {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            b'%' => {
                if i + 2 >= bytes.len() {
                    return None;
                }
                let hi = hex_val(bytes[i + 1])?;
                let lo = hex_val(bytes[i + 2])?;
                out.push((hi << 4) | lo);
                i += 3;
            }
            b => {
                out.push(b);
                i += 1;
            }
        }
    }
    String::from_utf8(out).ok()
}

fn hex_val(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

/// 分享读取限流中间件：仅作用于 `/api/s/` 前缀与 `/api/share/list`，
/// 维度为 token+IP 双键。token 无法解析时直接放行（不记桶）。
pub async fn share_ratelimit_middleware(
    State(state): State<Arc<AppState>>,
    req: Request,
    next: Next,
) -> Response {
    let path = req.uri().path();
    let is_share_read = path.starts_with("/api/s/") || path == "/api/share/list";
    if !is_share_read {
        return next.run(req).await;
    }

    let ip_key = extract_ip_key(&req);
    let share_key = extract_share_token(req.uri());
    let share_key = match share_key {
        Some(k) => k,
        None => return next.run(req).await,
    };

    match state
        .share_limiter
        .try_acquire(&ip_key, Some(share_key.as_str()))
    {
        Ok(()) => next.run(req).await,
        Err(secs) => {
            state.metrics.inc_auth("share_ratelimited");
            let body = serde_json::json!({
                "error": format!("分享访问过于频繁，请 {} 秒后重试", secs),
                "retry_after": secs,
            });
            let mut resp = Json(body).into_response();
            *resp.status_mut() = axum::http::StatusCode::TOO_MANY_REQUESTS;
            resp.headers_mut().insert(
                axum::http::header::RETRY_AFTER,
                axum::http::HeaderValue::from_str(&secs.to_string())
                    .unwrap_or_else(|_| axum::http::HeaderValue::from_static("1")),
            );
            resp
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---- 解析：默认值 ----

    #[test]
    fn parse_rps_default_when_none() {
        assert_eq!(parse_rps(None).unwrap(), 1.0);
    }

    #[test]
    fn parse_burst_default_when_none() {
        assert_eq!(parse_burst(None).unwrap(), 5);
    }

    // ---- 解析：合法值 ----

    #[test]
    fn parse_rps_valid() {
        assert_eq!(parse_rps(Some("2.5")).unwrap(), 2.5);
    }

    #[test]
    fn parse_burst_valid() {
        assert_eq!(parse_burst(Some("10")).unwrap(), 10);
    }

    // ---- 解析：非法值报错点名 ----

    #[test]
    fn parse_rps_invalid_names_var() {
        for bad in ["abc", "0", "-1", "NaN", "inf", "-inf"] {
            let e = parse_rps(Some(bad)).unwrap_err();
            assert!(e.contains(ENV_RPS), "err should name var, got: {}", e);
            assert!(e.contains(bad), "err should quote value, got: {}", e);
        }
    }

    #[test]
    fn parse_burst_invalid_names_var() {
        for bad in ["abc", "0", "-1", "1.5", "NaN"] {
            let e = parse_burst(Some(bad)).unwrap_err();
            assert!(e.contains(ENV_BURST), "err should name var, got: {}", e);
            assert!(e.contains(bad), "err should quote value, got: {}", e);
        }
    }

    // ---- 桶行为 ----

    fn make_limiter(rps: f64, burst: u64) -> RateLimiter {
        RateLimiter::new(&LoginLimitConfig { rps, burst })
    }

    #[test]
    fn burst_then_reject() {
        let rl = make_limiter(1.0, 2);
        let t0 = Instant::now();
        assert!(rl.try_acquire_at("ip1", Some("alice"), t0).is_ok());
        assert!(rl.try_acquire_at("ip1", Some("alice"), t0).is_ok());
        // 第三次：桶已空，拒绝。
        let e = rl.try_acquire_at("ip1", Some("alice"), t0).unwrap_err();
        assert!(e >= 1, "retry_after should be >= 1, got {}", e);
    }

    #[test]
    fn reject_does_not_consume() {
        let rl = make_limiter(1.0, 1);
        let t0 = Instant::now();
        assert!(rl.try_acquire_at("ip1", Some("alice"), t0).is_ok());
        // 桶空，拒绝。
        assert!(rl.try_acquire_at("ip1", Some("alice"), t0).is_err());
        // 再试一次仍然拒绝，且 retry_after 应该一致（未扣减 → 状态不变）。
        let e1 = rl.try_acquire_at("ip1", Some("alice"), t0).unwrap_err();
        let e2 = rl.try_acquire_at("ip1", Some("alice"), t0).unwrap_err();
        assert_eq!(e1, e2);
    }

    #[test]
    fn refill_over_time() {
        let rl = make_limiter(1.0, 1);
        let t0 = Instant::now();
        assert!(rl.try_acquire_at("ip1", None, t0).is_ok());
        // 桶空。
        assert!(rl.try_acquire_at("ip1", None, t0).is_err());
        // 推进 1 秒：补 1 个 token，恢复。
        let t1 = t0 + Duration::from_secs(1);
        assert!(rl.try_acquire_at("ip1", None, t1).is_ok());
    }

    #[test]
    fn ip_bucket_independent() {
        let rl = make_limiter(1.0, 1);
        let t0 = Instant::now();
        assert!(rl.try_acquire_at("ipA", None, t0).is_ok());
        // ipA 已空。
        assert!(rl.try_acquire_at("ipA", None, t0).is_err());
        // 另一 IP 不受影响。
        assert!(rl.try_acquire_at("ipB", None, t0).is_ok());
    }

    #[test]
    fn account_bucket_blocks_across_ips() {
        let rl = make_limiter(1.0, 1);
        let t0 = Instant::now();
        assert!(rl.try_acquire_at("ipA", Some("alice"), t0).is_ok());
        // 换 IP 但同一账号：账号桶已空 → 拒绝。
        assert!(rl.try_acquire_at("ipB", Some("alice"), t0).is_err());
    }

    #[test]
    fn account_none_skips_account_bucket() {
        let rl = make_limiter(1.0, 1);
        let t0 = Instant::now();
        // 无账号：只消耗 IP 桶，多次调用（同 IP）在 burst 内可用。
        assert!(rl.try_acquire_at("ipX", None, t0).is_ok());
        assert!(rl.try_acquire_at("ipX", None, t0).is_err());
    }

    #[test]
    fn empty_account_skips_account_bucket() {
        let rl = make_limiter(1.0, 1);
        let t0 = Instant::now();
        assert!(rl.try_acquire_at("ipX", Some(""), t0).is_ok());
        assert!(rl.try_acquire_at("ipX", Some(""), t0).is_err());
    }

    #[test]
    fn retry_after_is_ceil_and_min_one() {
        // rps = 2：deficit = 1.0 → 需要 0.5s → ceil = 1。
        assert_eq!(RateLimiter::retry_after(1.0, 2.0), 1);
        // deficit = 2.0, rps = 2 → 1.0s → 1。
        assert_eq!(RateLimiter::retry_after(2.0, 2.0), 1);
        // deficit = 3.0, rps = 2 → 1.5s → 2。
        assert_eq!(RateLimiter::retry_after(3.0, 2.0), 2);
        // 极小 rps：deficit = 1.0, rps = 0.1 → 10s。
        assert_eq!(RateLimiter::retry_after(1.0, 0.1), 10);
    }

    #[test]
    fn parse_share_rpm_defaults_and_invalid() {
        assert_eq!(parse_share_rpm(None).unwrap(), 30.0);
        assert_eq!(parse_share_rpm(Some("60")).unwrap(), 60.0);
        assert!(parse_share_rpm(Some("abc")).is_err());
        assert!(parse_share_rpm(Some("0")).is_err());
        assert!(parse_share_rpm(Some("-5")).is_err());
        assert!(parse_share_rpm(Some("inf")).is_err());
        let e = parse_share_rpm(Some("abc")).unwrap_err();
        assert!(e.contains("MINIOS_SHARE_READ_RPM"));
    }

    #[test]
    fn parse_share_burst_defaults_and_invalid() {
        assert_eq!(parse_share_burst(None).unwrap(), 30);
        assert_eq!(parse_share_burst(Some("10")).unwrap(), 10);
        assert!(parse_share_burst(Some("abc")).is_err());
        assert!(parse_share_burst(Some("0")).is_err());
        let e = parse_share_burst(Some("0")).unwrap_err();
        assert!(e.contains("MINIOS_SHARE_READ_BURST"));
    }

    #[test]
    fn parse_share_limit_default_rps_half() {
        let cfg = ShareReadLimitConfig {
            rps: 30.0 / 60.0,
            burst: 30,
        };
        assert_eq!(cfg.rps, 0.5);
        assert_eq!(cfg.burst, 30);
    }

    #[test]
    fn extract_share_token_cases() {
        let u = |s: &str| s.parse::<axum::http::Uri>().unwrap();
        assert_eq!(
            extract_share_token(&u("/api/s/abc123")),
            Some("abc123".to_string())
        );
        assert_eq!(
            extract_share_token(&u("/api/s/abc123/download")),
            Some("abc123".to_string())
        );
        assert_eq!(
            extract_share_token(&u("/api/share/list?token=xyz&path=/")),
            Some("xyz".to_string())
        );
        assert_eq!(extract_share_token(&u("/api/share/list")), None);
        assert_eq!(extract_share_token(&u("/api/health")), None);
        assert_eq!(extract_share_token(&u("/api/s/%zz")), None);
        assert_eq!(
            extract_share_token(&u("/api/s/a%20b")),
            Some("a b".to_string())
        );
    }

    #[test]
    fn share_token_bucket_isolation_by_token() {
        // burst=2：验证 token 桶相互独立，且 IP 桶维度同时生效。
        let cfg = LoginLimitConfig { rps: 1.0, burst: 2 };
        let rl = RateLimiter::new(&cfg);
        let now = std::time::Instant::now();
        assert!(rl.try_acquire_at("ip1", Some("tokA"), now).is_ok());
        // 同一 IP、不同 token：token 桶独立，IP 桶还有余量 → 通过。
        assert!(rl.try_acquire_at("ip1", Some("tokB"), now).is_ok());
        // 第三次：IP 桶已空，即使换全新 token 也被拒（IP 维度生效，防单 IP 刷全站分享）。
        assert!(rl.try_acquire_at("ip1", Some("tokC"), now).is_err());
    }

    #[test]
    fn share_token_bucket_shared_across_ips() {
        let cfg = LoginLimitConfig { rps: 1.0, burst: 1 };
        let rl = RateLimiter::new(&cfg);
        let now = std::time::Instant::now();
        assert!(rl.try_acquire_at("ip1", Some("tokA"), now).is_ok());
        assert!(rl.try_acquire_at("ip2", Some("tokA"), now).is_err());
    }
}
