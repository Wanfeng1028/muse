// src/log.rs
// 结构化日志（JSONL 写 stderr）与 request_id 生成

use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use axum::extract::Request;
use axum::middleware::Next;
use axum::response::Response;
use axum::http::HeaderValue;

/// days-to-civil 算法（Howard Hinnant），返回 (year, month, day)
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let y = if m <= 2 { y + 1 } else { y };
    (y, m, d)
}

/// 纯函数：epoch 毫秒 → RFC3339 UTC 字符串（毫秒为 0 时省略毫秒部分）
pub fn format_rfc3339_millis(epoch_millis: u64) -> String {
    let secs = (epoch_millis / 1000) as i64;
    let millis = (epoch_millis % 1000) as u32;

    let days = secs.div_euclid(86400);
    let rem = secs.rem_euclid(86400);
    let hour = (rem / 3600) as u32;
    let minute = ((rem % 3600) / 60) as u32;
    let second = (rem % 60) as u32;

    let (year, month, day) = civil_from_days(days);

    if millis == 0 {
        format!(
            "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
            year, month, day, hour, minute, second
        )
    } else {
        format!(
            "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:03}Z",
            year, month, day, hour, minute, second, millis
        )
    }
}

/// 当前时间的 RFC3339 毫秒字符串；时钟异常回退到 epoch
pub fn now_rfc3339_millis() -> String {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(d) => format_rfc3339_millis(d.as_millis() as u64),
        Err(_) => "1970-01-01T00:00:00Z".to_string(),
    }
}

static PROCESS_START_MILLIS: OnceLock<u64> = OnceLock::new();
static REQUEST_COUNTER: AtomicU64 = AtomicU64::new(0);

fn process_start_millis() -> u64 {
    *PROCESS_START_MILLIS.get_or_init(|| match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(d) => d.as_millis() as u64,
        Err(_) => 0,
    })
}

/// 生成新的 request id：进程启动毫秒低 48 位 + 24 位递增计数器
pub fn new_request_id() -> String {
    let start = process_start_millis() & 0x0000_FFFF_FFFF_FFFF;
    let counter = REQUEST_COUNTER.fetch_add(1, Ordering::Relaxed) & 0x00FF_FFFF;
    format!("{:012x}-{:06x}", start, counter)
}

/// 清洗外部传入的 request id：仅保留 ASCII 字母数字与 - _
pub fn sanitize_request_id(raw: &str) -> String {
    let filtered: String = raw
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
        .take(128)
        .collect();
    if filtered.is_empty() {
        new_request_id()
    } else {
        filtered
    }
}

/// 写一行 JSONL 到 stderr
fn emit_json(value: serde_json::Value) {
    let line = value.to_string();
    let mut stderr = std::io::stderr().lock();
    let _ = writeln!(stderr, "{}", line);
}

/// 请求日志中间件：注入 x-request-id，记录一行访问日志
pub async fn request_log_middleware(req: Request, next: Next) -> Response {
    let request_id = req
        .headers()
        .get("x-request-id")
        .and_then(|v| v.to_str().ok())
        .map(sanitize_request_id)
        .unwrap_or_else(new_request_id);

    let method = req.method().to_string();
    let path = req.uri().path().to_string();

    let started = Instant::now();
    let mut response = next.run(req).await;
    let latency_ms = started.elapsed().as_millis() as u64;

    if let Ok(hv) = HeaderValue::from_str(&request_id) {
        response.headers_mut().insert("x-request-id", hv);
    }

    let status = response.status().as_u16();
    emit_json(serde_json::json!({
        "ts": now_rfc3339_millis(),
        "level": "info",
        "request_id": request_id,
        "method": method,
        "path": path,
        "status": status,
        "latency_ms": latency_ms,
    }));

    response
}

/// 打一条事件日志：{"ts":..., "level":"info", "event":..., ...fields}
pub fn log_event(event: &str, fields: serde_json::Value) {
    let mut obj = serde_json::Map::new();
    obj.insert(
        "ts".to_string(),
        serde_json::Value::String(now_rfc3339_millis()),
    );
    obj.insert(
        "level".to_string(),
        serde_json::Value::String("info".to_string()),
    );
    obj.insert(
        "event".to_string(),
        serde_json::Value::String(event.to_string()),
    );

    if let serde_json::Value::Object(extra) = fields {
        for (k, v) in extra {
            obj.insert(k, v);
        }
    }

    emit_json(serde_json::Value::Object(obj));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_millis_pinned() {
        assert_eq!(
            format_rfc3339_millis(1792133085123),
            "2026-10-16T06:44:45.123Z"
        );
        assert_eq!(
            format_rfc3339_millis(1792133085000),
            "2026-10-16T06:44:45Z"
        );
    }

    #[test]
    fn sanitize_strips_control_and_truncates() {
        let raw = "abc\u{0000}\u{0007}def-_.!@#";
        assert_eq!(sanitize_request_id(raw), "abcdef-_");

        let long = "a".repeat(300);
        assert_eq!(sanitize_request_id(&long).len(), 128);

        assert!(!sanitize_request_id("\u{0000}\u{0001}").is_empty());
    }

    #[test]
    fn new_request_id_is_unique() {
        let a = new_request_id();
        let b = new_request_id();
        assert_ne!(a, b);
    }
}
