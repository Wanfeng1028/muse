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

/// 分享读取限流配置。
pub struct ShareReadLimitConfig {
    /// 每秒请求数上限，来源变量 `MINIOS_SHARE_RPS`；必须为正的有限数。
    pub rps: f64,
    /// 突发容量，来源变量 `MINIOS_SHARE_BURST`；必须为大于 0 的整数。
    pub burst: u64,
    /// 是否启用分享读限流，来源变量 `MINIOS_SHARE_RATE_LIMIT_ENABLED`；布尔值。
    pub enabled: bool,
}

const ENV_SHARE_RPS: &str = "MINIOS_SHARE_RPS";
const ENV_SHARE_BURST: &str = "MINIOS_SHARE_BURST";
const ENV_SHARE_ENABLED: &str = "MINIOS_SHARE_RATE_LIMIT_ENABLED";
const ENV_LEGACY_SHARE_RPM: &str = "MINIOS_SHARE_READ_RPM";
const ENV_LEGACY_SHARE_BURST: &str = "MINIOS_SHARE_READ_BURST";

/// 解析每秒请求数上限，默认 `"5"`。
///
/// 非法值（无法解析、非有限数、`<= 0`、NaN、无穷大）一律 fail-fast 返回 Err。
fn parse_share_rps(raw: Option<&str>) -> Result<f64, String> {
    let s = raw.unwrap_or("5");
    let v: f64 = s
        .parse()
        .map_err(|_| format!("{} 非法：'{}'，期望正的有限数", ENV_SHARE_RPS, s))?;
    if !v.is_finite() || v <= 0.0 {
        return Err(format!("{} 非法：'{}'，期望正的有限数", ENV_SHARE_RPS, s));
    }
    Ok(v)
}

/// 解析突发容量，默认 `"30"`。
///
/// 非法值（无法解析为整数、含小数、等于 0）一律 fail-fast 返回 Err。
fn parse_share_burst(raw: Option<&str>) -> Result<u64, String> {
    let s = raw.unwrap_or("30");
    let v: u64 = s
        .parse()
        .map_err(|_| format!("{} 非法：'{}'，期望大于 0 的整数", ENV_SHARE_BURST, s))?;
    if v == 0 {
        return Err(format!(
            "{} 非法：'{}'，期望大于 0 的整数",
            ENV_SHARE_BURST, s
        ));
    }
    Ok(v)
}

/// 解析是否启用分享读限流，默认 `"true"`。
///
/// 合法取值：`1`/`true`/`yes`/`on` 为 true，`0`/`false`/`no`/`off` 为 false（忽略大小写与首尾空白）；
/// 其他值一律 fail-fast 返回 Err。
fn parse_share_enabled(raw: Option<&str>) -> Result<bool, String> {
    let s = raw.unwrap_or("true");
    match s.trim().to_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => Ok(true),
        "0" | "false" | "no" | "off" => Ok(false),
        _ => Err(format!(
            "{} 非法：'{}'，期望 1/true/yes/on 或 0/false/no/off",
            ENV_SHARE_ENABLED, s
        )),
    }
}

/// 校验废弃的旧环境变量是否仍被设置。
///
/// 旧变量存在即 fail-fast 返回 Err，提示迁移到新变量。
fn check_no_legacy(rpm: Option<&str>, burst: Option<&str>) -> Result<(), String> {
    if rpm.is_some() {
        return Err(format!(
            "{} 已废弃，请改用 {}（直接填每秒速率）",
            ENV_LEGACY_SHARE_RPM, ENV_SHARE_RPS
        ));
    }
    if burst.is_some() {
        return Err(format!(
            "{} 已废弃，请改用 {}",
            ENV_LEGACY_SHARE_BURST, ENV_SHARE_BURST
        ));
    }
    Ok(())
}

/// 读取分享读取限流配置。
///
/// 先拒绝废弃的旧变量，再解析新变量；任一非法值 fail-fast 返回 Err。
pub fn parse_share_limit() -> Result<ShareReadLimitConfig, String> {
    let legacy_rpm = std::env::var(ENV_LEGACY_SHARE_RPM).ok();
    let legacy_burst = std::env::var(ENV_LEGACY_SHARE_BURST).ok();
    check_no_legacy(legacy_rpm.as_deref(), legacy_burst.as_deref())?;

    let rps = parse_share_rps(std::env::var(ENV_SHARE_RPS).ok().as_deref())?;
    let burst = parse_share_burst(std::env::var(ENV_SHARE_BURST).ok().as_deref())?;
    let enabled = parse_share_enabled(std::env::var(ENV_SHARE_ENABLED).ok().as_deref())?;

    Ok(ShareReadLimitConfig {
        rps,
        burst,
        enabled,
    })
}

/// 分享读限流域的桶键：仅 IP 维度。
///
/// 新类型包装，与登录域 `RateLimiter` 内部的 `String` 键在类型层面隔离，
/// 编译期就不可能把登录桶的 key 串进分享桶（与登录桶解耦的 BucketKey 设计）。
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ShareReadKey(String);

impl ShareReadKey {
    /// 从客户端 IP 构造分享读桶键。
    pub fn from_ip(ip: &str) -> Self {
        Self(ip.to_string())
    }
}

/// 分享读限流器：与登录桶解耦的独立令牌桶。
///
/// 内部以 [`ShareReadKey`] 为键，仅按 IP 维度限流，不与登录域共享任何状态。
pub struct ShareReadLimiter {
    rps: f64,
    burst: u64,
    /// 惰性清理的 idle TTL：max(300s, 10 * burst / rps)。
    idle_ttl: Duration,
    buckets: Mutex<HashMap<ShareReadKey, Bucket>>,
}

impl ShareReadLimiter {
    /// 根据配置构造限流器。所有桶初始为满（capacity = burst）。
    pub fn new(config: &ShareReadLimitConfig) -> Self {
        let ttl_secs = 10.0 * (config.burst as f64) / config.rps;
        let idle_ttl = Duration::from_secs_f64(ttl_secs.max(300.0));
        Self {
            rps: config.rps,
            burst: config.burst,
            idle_ttl,
            buckets: Mutex::new(HashMap::new()),
        }
    }

    /// 尝试获取一个分享读令牌，使用当前时刻。
    pub fn try_acquire(&self, key: &ShareReadKey) -> Result<(), u64> {
        self.try_acquire_at(key, Instant::now())
    }

    /// 在给定时刻尝试获取一个分享读令牌（供单测伪造时间）。
    ///
    /// 语义：按流逝时间 refill（`tokens = min(capacity, tokens + elapsed * rps)`，
    /// 同时更新 last）；`tokens < 1.0` → `Err(retry_after_secs)` 且不扣减，
    /// `retry_after_secs = max(1, ceil((1.0 - tokens) / rps))`；否则扣 1 返回 Ok。
    pub fn try_acquire_at(&self, key: &ShareReadKey, now: Instant) -> Result<(), u64> {
        let mut map = self.buckets.lock().unwrap_or_else(|e| e.into_inner());
        self.maybe_cleanup(&mut map, now);
        let bucket = map.entry(key.clone()).or_insert_with(|| Bucket {
            tokens: self.burst as f64,
            last: now,
        });
        let elapsed = now.saturating_duration_since(bucket.last).as_secs_f64();
        if elapsed > 0.0 {
            bucket.tokens = (bucket.tokens + elapsed * self.rps).min(self.burst as f64);
            bucket.last = now;
        }
        if bucket.tokens < 1.0 {
            return Err(Self::retry_after(1.0 - bucket.tokens, self.rps));
        }
        bucket.tokens -= 1.0;
        Ok(())
    }

    /// 计算 `retry_after` 秒数：`max(1, ceil(deficit / rps))`，带非有限保护。
    fn retry_after(deficit: f64, rps: f64) -> u64 {
        if !deficit.is_finite() || !rps.is_finite() || rps <= 0.0 {
            return 1;
        }
        let secs = (deficit / rps).ceil();
        if !secs.is_finite() || secs <= 1.0 {
            1
        } else {
            secs as u64
        }
    }

    /// 惰性清理：桶数量超过阈值时，移除 idle 超过 `idle_ttl` 的桶。
    fn maybe_cleanup(&self, map: &mut HashMap<ShareReadKey, Bucket>, now: Instant) {
        if map.len() <= CLEANUP_THRESHOLD {
            return;
        }
        let idle_ttl = self.idle_ttl;
        map.retain(|_, bucket| now.saturating_duration_since(bucket.last) < idle_ttl);
    }
}

/// 分享读取限流中间件（v1.8 语义）。
///
/// 作用范围：仅覆盖 `GET /api/s/:token/*`（`/api/s/` 前缀）与
/// `GET /api/share/list`；探针（`/api/health`、`/api/readyz`、`/metrics`）
/// 挂在各自路由上，不经过本中间件，因此天然豁免限流。
///
/// 维度：IP 单维度（不再使用 token+IP 双键），使用 `share_limiter` 独立桶，
/// 与其它限流器的桶互不影响。
///
/// 总开关：`state.share_ratelimit_enabled` 为 `false` 时直接放行，
/// 不计数、不记桶、不产生任何指标。
///
/// 429 契约：超限时返回 `429 Too Many Requests`，携带 `Retry-After: <secs>`
/// 响应头（整数秒十进制字符串），响应体为 JSON：
/// `{"error": "分享访问过于频繁，请 <secs> 秒后重试", "retry_after": <secs>}`。
pub async fn share_ratelimit_middleware(
    State(state): State<Arc<AppState>>,
    req: Request,
    next: Next,
) -> Response {
    if !state.share_ratelimit_enabled {
        return next.run(req).await;
    }

    let path = req.uri().path();
    let is_share_read = path.starts_with("/api/s/") || path == "/api/share/list";
    if !is_share_read {
        return next.run(req).await;
    }

    let ip_key = extract_ip_key(&req);

    match state
        .share_limiter
        .try_acquire(&ShareReadKey::from_ip(&ip_key))
    {
        Ok(()) => next.run(req).await,
        Err(secs) => {
            state.metrics.inc_share_ratelimited();
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
    fn parse_share_rps_defaults_and_valid() {
        assert_eq!(parse_share_rps(None).unwrap(), 5.0);
        assert_eq!(parse_share_rps(Some("2.5")).unwrap(), 2.5);
    }

    #[test]
    fn parse_share_rps_invalid_names_var() {
        for raw in ["abc", "0", "-1", "NaN", "inf"] {
            let err = parse_share_rps(Some(raw)).unwrap_err();
            assert!(err.contains("MINIOS_SHARE_RPS"), "err = {err}");
            assert!(err.contains(raw), "err = {err}");
        }
    }

    #[test]
    fn parse_share_burst_defaults_and_valid() {
        assert_eq!(parse_share_burst(None).unwrap(), 30);
        assert_eq!(parse_share_burst(Some("10")).unwrap(), 10);
    }

    #[test]
    fn parse_share_burst_invalid_names_var() {
        for raw in ["abc", "0", "-2", "1.5"] {
            let err = parse_share_burst(Some(raw)).unwrap_err();
            assert!(err.contains("MINIOS_SHARE_BURST"), "err = {err}");
            assert!(err.contains(raw), "err = {err}");
        }
    }

    #[test]
    fn parse_share_enabled_cases() {
        assert!(parse_share_enabled(None).unwrap());

        for raw in ["1", "true", "TRUE", " yes ", "on"] {
            assert!(parse_share_enabled(Some(raw)).unwrap(), "raw = {raw}");
        }

        for raw in ["0", "false", "FALSE", "no", "off"] {
            assert!(!parse_share_enabled(Some(raw)).unwrap(), "raw = {raw}");
        }

        let err = parse_share_enabled(Some("maybe")).unwrap_err();
        assert!(
            err.contains("MINIOS_SHARE_RATE_LIMIT_ENABLED"),
            "err = {err}"
        );
        assert!(err.contains("maybe"), "err = {err}");
    }

    #[test]
    fn check_no_legacy_cases() {
        assert!(check_no_legacy(None, None).is_ok());

        let err = check_no_legacy(Some("30"), None).unwrap_err();
        assert!(err.contains("MINIOS_SHARE_READ_RPM"), "err = {err}");
        assert!(err.contains("MINIOS_SHARE_RPS"), "err = {err}");

        let err = check_no_legacy(None, Some("30")).unwrap_err();
        assert!(err.contains("MINIOS_SHARE_READ_BURST"), "err = {err}");
        assert!(err.contains("MINIOS_SHARE_BURST"), "err = {err}");
    }

    fn make_share_limiter(rps: f64, burst: u64) -> ShareReadLimiter {
        ShareReadLimiter::new(&ShareReadLimitConfig {
            rps,
            burst,
            enabled: true,
        })
    }

    #[test]
    fn share_burst_then_reject() {
        let rl = make_share_limiter(1.0, 2);
        let key = ShareReadKey::from_ip("10.0.0.1");
        let now = Instant::now();

        assert!(rl.try_acquire_at(&key, now).is_ok());
        assert!(rl.try_acquire_at(&key, now).is_ok());

        let err = rl.try_acquire_at(&key, now).unwrap_err();
        assert!(err >= 1, "retry_after = {err}");
    }

    #[test]
    fn share_reject_does_not_consume() {
        let rl = make_share_limiter(1.0, 1);
        let key = ShareReadKey::from_ip("10.0.0.2");
        let now = Instant::now();

        assert!(rl.try_acquire_at(&key, now).is_ok());

        let first = rl.try_acquire_at(&key, now).unwrap_err();
        let second = rl.try_acquire_at(&key, now).unwrap_err();
        assert_eq!(first, second, "reject must not consume tokens");
    }

    #[test]
    fn share_refill_over_time() {
        let rl = make_share_limiter(1.0, 1);
        let key = ShareReadKey::from_ip("10.0.0.3");
        let t0 = Instant::now();

        assert!(rl.try_acquire_at(&key, t0).is_ok());
        assert!(rl.try_acquire_at(&key, t0).is_err());

        let t1 = t0 + Duration::from_secs(1);
        assert!(rl.try_acquire_at(&key, t1).is_ok());
    }

    #[test]
    fn share_ip_key_isolation() {
        let rl = make_share_limiter(1.0, 1);
        let key_a = ShareReadKey::from_ip("ipA");
        let key_b = ShareReadKey::from_ip("ipB");
        let now = Instant::now();

        assert!(rl.try_acquire_at(&key_a, now).is_ok());
        assert!(rl.try_acquire_at(&key_a, now).is_err());

        assert!(rl.try_acquire_at(&key_b, now).is_ok());

        let again = ShareReadKey::from_ip("ipA");
        assert_eq!(key_a, again);
    }

    #[test]
    fn share_retry_after_ceil() {
        let rl_half = make_share_limiter(0.5, 1);
        let key_half = ShareReadKey::from_ip("10.0.0.4");
        let now = Instant::now();
        assert!(rl_half.try_acquire_at(&key_half, now).is_ok());
        let err = rl_half.try_acquire_at(&key_half, now).unwrap_err();
        assert_eq!(err, 2, "deficit=1.0, ceil(1.0/0.5)=2");

        let rl_one = make_share_limiter(1.0, 1);
        let key_one = ShareReadKey::from_ip("10.0.0.5");
        assert!(rl_one.try_acquire_at(&key_one, now).is_ok());
        let err = rl_one.try_acquire_at(&key_one, now).unwrap_err();
        assert_eq!(err, 1, "min retry_after is 1");
    }

    #[test]
    fn share_key_from_ip() {
        let a = ShareReadKey::from_ip("1.2.3.4");
        let b = ShareReadKey::from_ip("1.2.3.4");
        let c = ShareReadKey::from_ip("5.6.7.8");

        assert_eq!(a, b);
        assert_ne!(a, c);
    }
}
