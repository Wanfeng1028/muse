//! 深度边界测试：结构化日志与 request_id 生成。
//!
//! 被测模块 src/log.rs 里的公开接口：
//!   format_rfc3339_millis / now_rfc3339_millis / new_request_id
//!   sanitize_request_id / request_log_middleware / log_event
//!
//! 该模块为 lib crate 的一部分（lib.rs 里 `pub mod log;`），因此集成测试
//! 走 tests/ 目录，直接 use 库名调用。库名按 Cargo.toml 里的 `name` 取
//! `mini_os`（Rust 会把连字符转下划线）。

use std::collections::HashSet;
use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::middleware::from_fn;
use axum::response::IntoResponse;
use axum::routing::get;
use axum::Router;
use tower::ServiceExt;

use mini_os::log::{
    format_rfc3339_millis, log_event, new_request_id, now_rfc3339_millis, request_log_middleware,
    sanitize_request_id,
};

// ---------------------------------------------------------------------------
// 1. 时间格式化边界：epoch 与毫秒为 0 的省略行为
// ---------------------------------------------------------------------------

#[test]
fn format_rfc3339_millis_epoch_and_zero_millis() {
    // epoch 0 且毫秒为 0 → 不带毫秒段
    assert_eq!(format_rfc3339_millis(0), "1970-01-01T00:00:00Z");
    // 正好 1000ms → 秒进位，毫秒为 0 仍省略毫秒段
    assert_eq!(format_rfc3339_millis(1000), "1970-01-01T00:00:01Z");
    // 1ms → 保留三位毫秒
    assert_eq!(format_rfc3339_millis(1), "1970-01-01T00:00:00.001Z");
}

#[test]
fn format_rfc3339_millis_day_rollover_and_leap_day() {
    // 一天的毫秒数 = 86_400_000，跨到次日
    assert_eq!(format_rfc3339_millis(86_400_000), "1970-01-02T00:00:00Z");
    // 2024-02-29T12:00:00.500Z（闰年 2 月 29 日）
    // 2024-02-29 相对 epoch 的天数 = 19782
    let days_2024_02_29: u64 = 19782;
    let base = days_2024_02_29 * 86_400_000 + 12 * 3_600_000 + 500;
    assert_eq!(format_rfc3339_millis(base), "2024-02-29T12:00:00.500Z");
}

#[test]
fn format_rfc3339_millis_pinned_and_boundary_seconds() {
    // 钉住已知值（与单元测试一致，确保集成层没被改坏）
    assert_eq!(
        format_rfc3339_millis(1792133085123),
        "2026-10-16T06:44:45.123Z"
    );
    assert_eq!(format_rfc3339_millis(1792133085000), "2026-10-16T06:44:45Z");
    // 999ms 不跨秒
    assert_eq!(
        format_rfc3339_millis(1792133085999),
        "2026-10-16T06:44:45.999Z"
    );
}

// ---------------------------------------------------------------------------
// 2. now_rfc3339_millis：真实时钟下返回合法 RFC3339 且单调不倒退
// ---------------------------------------------------------------------------

#[test]
fn now_rfc3339_millis_is_wellformed_and_monotonic() {
    let a = now_rfc3339_millis();
    let b = now_rfc3339_millis();

    // 形状检查：YYYY-MM-DDTHH:MM:SS(.mmm)?Z
    assert!(a.ends_with('Z'), "now() 必须以 Z 结尾，实际 = {a}");
    assert!(a.len() >= 20, "now() 太短，实际 = {a}");
    assert_eq!(&a[4..5], "-");
    assert_eq!(&a[7..8], "-");
    assert_eq!(&a[10..11], "T");
    assert_eq!(&a[13..14], ":");
    assert_eq!(&a[16..17], ":");

    // 两次调用之间时间不倒退（字符串可直接按字典序比较，RFC3339 定长前缀可比）
    assert!(b >= a, "时间倒退：a={a}, b={b}");
}

// ---------------------------------------------------------------------------
// 3. request id：格式、唯一性、并发唯一
// ---------------------------------------------------------------------------

#[test]
fn new_request_id_has_fixed_shape() {
    let id = new_request_id();
    // 格式 "{:012x}-{:06x}"：12 位 hex + '-' + 6 位 hex = 19 字符
    assert_eq!(id.len(), 19, "id 长度应为 19，实际 = {id}");
    assert_eq!(&id[12..13], "-");
    assert!(
        id[..12].chars().all(|c| c.is_ascii_hexdigit()),
        "前 12 位应为 hex，实际 = {id}"
    );
    assert!(
        id[13..].chars().all(|c| c.is_ascii_hexdigit()),
        "后 6 位应为 hex，实际 = {id}"
    );
}

#[test]
fn new_request_id_unique_under_concurrency() {
    const N: usize = 5000;
    let mut handles = Vec::with_capacity(N);
    for _ in 0..N {
        handles.push(std::thread::spawn(new_request_id));
    }
    let mut ids: HashSet<String> = HashSet::with_capacity(N);
    for h in handles {
        let id = h.join().expect("线程 panic");
        assert!(ids.insert(id.clone()), "出现重复 request id: {id}");
    }
    assert_eq!(ids.len(), N, "并发生成的 id 数量应等于线程数");
}

// ---------------------------------------------------------------------------
// 4. sanitize_request_id：非法字符 / 空串 / 超长 / 中文名
// ---------------------------------------------------------------------------

#[test]
fn sanitize_strips_illegal_and_keeps_allowed() {
    // 控制字符、标点、空格全部剔除，只留 [A-Za-z0-9-_]
    assert_eq!(
        sanitize_request_id("abc\u{0000}\u{0007}def-_.!@#"),
        "abcdef-_"
    );
    // 斜杠与点号（路径穿越味道的输入）必须被剔除
    assert_eq!(sanitize_request_id("../../etc/passwd"), "etcpasswd");
    // 全是非法字符 → 回退到新生成的 id（非空且合法）
    let fallback = sanitize_request_id("\u{0000}\u{0001}");
    assert!(!fallback.is_empty());
    assert_eq!(fallback.len(), 19);
}

#[test]
fn sanitize_truncates_to_128_and_handles_unicode() {
    // 超长 ASCII 截断到 128
    let long = "a".repeat(300);
    let got = sanitize_request_id(&long);
    assert_eq!(got.len(), 128);
    assert!(got.chars().all(|c| c == 'a'));

    // 中文名：非 ASCII 一律剔除，只保留 ASCII 部分（`-` 是合法字符，会被保留）
    assert_eq!(sanitize_request_id("请求-123"), "-123");
    assert_eq!(sanitize_request_id("用户abc用户"), "abc");

    // 全中文 → 回退到新 id，长度 19
    let cn_only = sanitize_request_id("纯中文请求标识");
    assert_eq!(cn_only.len(), 19);

    // 恰好 128 个合法字符不截断
    let exact = "z".repeat(128);
    assert_eq!(sanitize_request_id(&exact).len(), 128);
}

// ---------------------------------------------------------------------------
// 5. 中间件：注入 x-request-id 响应头 + 非法入参回退
// ---------------------------------------------------------------------------

async fn ok_handler() -> impl IntoResponse {
    (StatusCode::OK, "ok")
}

fn build_app() -> Router {
    Router::new()
        .route("/ping", get(ok_handler))
        .layer(from_fn(request_log_middleware))
}

#[tokio::test]
async fn middleware_injects_request_id_from_header() {
    let app = build_app();

    let req = Request::builder()
        .uri("/ping")
        .header("x-request-id", "client-abc_123")
        .body(Body::empty())
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let got = resp
        .headers()
        .get("x-request-id")
        .expect("响应应带 x-request-id")
        .to_str()
        .unwrap();
    assert_eq!(got, "client-abc_123");
}

#[tokio::test]
async fn middleware_falls_back_when_header_is_illegal() {
    let app = build_app();

    // 全中文 header 值是合法 HTTP 头值（obs-text），能构造出请求；
    // 但 sanitize 会剔除全部非 ASCII 字符 → 为空 → 回退到新生成 id
    let req = Request::builder()
        .uri("/ping")
        .header("x-request-id", "请求标识")
        .body(Body::empty())
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let got = resp
        .headers()
        .get("x-request-id")
        .expect("响应应带 x-request-id")
        .to_str()
        .unwrap()
        .to_string();

    // 回退 id 必须是合法形状：19 字符、含 '-'、全是 hex
    assert_eq!(got.len(), 19, "回退 id 长度不对: {got}");
    assert_eq!(&got[12..13], "-");
    assert!(got[..12].chars().all(|c| c.is_ascii_hexdigit()));
    assert!(got[13..].chars().all(|c| c.is_ascii_hexdigit()));
}

#[tokio::test]
async fn middleware_missing_header_still_injects_id() {
    let app = build_app();

    let req = Request::builder().uri("/ping").body(Body::empty()).unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    let got = resp
        .headers()
        .get("x-request-id")
        .expect("缺 header 时也必须注入 id")
        .to_str()
        .unwrap()
        .to_string();
    assert_eq!(got.len(), 19);
    assert!(got.chars().all(|c| c.is_ascii_hexdigit() || c == '-'));
}

#[tokio::test]
async fn middleware_propagates_error_status_and_id() {
    // 上游 handler 返回 500，中间件不应吞掉状态码，同时仍注入 id
    async fn boom() -> impl IntoResponse {
        (StatusCode::INTERNAL_SERVER_ERROR, "boom")
    }

    let app = Router::new()
        .route("/boom", get(boom))
        .layer(from_fn(request_log_middleware));

    let req = Request::builder()
        .uri("/boom")
        .header("x-request-id", "trace-42")
        .body(Body::empty())
        .unwrap();

    let resp = app.oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);

    let got = resp
        .headers()
        .get("x-request-id")
        .expect("错误响应也应带 id")
        .to_str()
        .unwrap();
    assert_eq!(got, "trace-42");
}

// ---------------------------------------------------------------------------
// 6. log_event：字段合并、事件名保留、非对象 fields 不污染
// ---------------------------------------------------------------------------

#[test]
fn log_event_accepts_object_fields_and_string_payload() {
    // 这些调用不应 panic，且行为稳定（emit 到 stderr，测试只验证不崩）
    log_event(
        "user.login",
        serde_json::json!({"user_id": 42, "path": "/a/b"}),
    );
    // fields 不是对象时，额外的键不合并，但 event/ts/level 仍应存在
    log_event("non_object", serde_json::json!("just a string"));
    log_event("null_fields", serde_json::Value::Null);
    // 空事件名也不应崩
    log_event("", serde_json::json!({}));
}

#[test]
fn log_event_concurrent_does_not_panic() {
    let shared = Arc::new(());
    let mut handles = Vec::new();
    for i in 0..64 {
        let s = Arc::clone(&shared);
        handles.push(std::thread::spawn(move || {
            let _keep = s;
            log_event(
                "concurrent.event",
                serde_json::json!({"i": i, "name": "并发中文名"}),
            );
        }));
    }
    for h in handles {
        h.join().expect("并发 log_event 线程 panic");
    }
    // 到这里没 panic 即通过；再用一次格式化确认接口还活着
    assert_eq!(format_rfc3339_millis(0), "1970-01-01T00:00:00Z");
}
