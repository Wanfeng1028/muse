// src/metrics.rs
//! Prometheus 文本格式指标：零依赖手写 exposition。
//!
//! 只使用标准库：`Mutex<HashMap<...>>` 存标签计数，`AtomicI64` 存 gauge。

use std::collections::HashMap;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use axum::extract::{MatchedPath, Request, State};
use axum::http::header::CONTENT_TYPE;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};

use crate::AppState;

/// 直方图桶边界（秒），不含 +Inf 桶。
const DURATION_BUCKETS: [f64; 11] = [
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
];

/// 单个请求时长直方图：11 个显式桶 + 1 个 +Inf 桶。
struct Histogram {
    /// 累计桶计数，末位为 +Inf 桶。
    buckets: [u64; 12],
    /// 观测值总和。
    sum: f64,
    /// 观测次数。
    count: u64,
}

/// 指标集合：字段全私有，仅通过方法访问。
pub struct Metrics {
    /// http_requests_total：key 为 (method, route, status)。
    http: Mutex<HashMap<(String, String, u16), u64>>,
    /// vfs_ops_total：key 为 op。
    vfs: Mutex<HashMap<String, u64>>,
    /// auth_ops_total：key 为 op（register/login/logout/migrate_legacy/share_create）。
    auth: Mutex<HashMap<String, u64>>,
    /// ws_connections：当前 WebSocket 连接数。
    ws: AtomicI64,
    /// http_request_duration_seconds：key 为 (method, route)，值为各桶累计计数（末位为 +Inf 桶）与总和/总数。
    durations: Mutex<HashMap<(String, String), Histogram>>,
    /// share_ratelimited：被分享读取限流拒绝的请求总数。
    share_ratelimited: AtomicU64,
}

impl Metrics {
    /// 创建空指标集合。
    pub fn new() -> Self {
        Self {
            http: Mutex::new(HashMap::new()),
            vfs: Mutex::new(HashMap::new()),
            auth: Mutex::new(HashMap::new()),
            ws: AtomicI64::new(0),
            durations: Mutex::new(HashMap::new()),
            share_ratelimited: AtomicU64::new(0),
        }
    }

    /// 累加一次 HTTP 请求计数。
    pub fn inc_http(&self, method: &str, route: &str, status: u16) {
        let mut map = self.http.lock().unwrap();
        let entry = map
            .entry((method.to_string(), route.to_string(), status))
            .or_insert(0);
        *entry += 1;
    }

    /// 累加一次 VFS 操作计数。
    pub fn inc_vfs(&self, op: &str) {
        let mut map = self.vfs.lock().unwrap();
        let entry = map.entry(op.to_string()).or_insert(0);
        *entry += 1;
    }

    /// 累加一次认证操作计数。
    pub fn inc_auth(&self, op: &str) {
        let mut map = self.auth.lock().unwrap();
        let entry = map.entry(op.to_string()).or_insert(0);
        *entry += 1;
    }

    /// 累加一次分享读取限流拒绝计数。
    pub fn inc_share_ratelimited(&self) {
        self.share_ratelimited.fetch_add(1, Ordering::Relaxed);
    }

    /// WebSocket 连接数 +1。
    pub fn ws_inc(&self) {
        self.ws.fetch_add(1, Ordering::SeqCst);
    }

    /// WebSocket 连接数 -1。
    pub fn ws_dec(&self) {
        self.ws.fetch_sub(1, Ordering::SeqCst);
    }

    /// 渲染为 Prometheus exposition 文本。
    pub fn render(&self) -> String {
        let mut out = String::new();

        // http_requests_total
        out.push_str("# HELP http_requests_total Total number of HTTP requests.\n");
        out.push_str("# TYPE http_requests_total counter\n");
        {
            let map = self.http.lock().unwrap();
            let mut rows: Vec<(&(String, String, u16), &u64)> = map.iter().collect();
            rows.sort_by(|a, b| {
                let ka = (&a.0 .0, &a.0 .1, a.0 .2);
                let kb = (&b.0 .0, &b.0 .1, b.0 .2);
                ka.cmp(&kb)
            });
            for ((method, route, status), count) in rows {
                out.push_str(&format!(
                    "http_requests_total{{method=\"{}\",route=\"{}\",status=\"{}\"}} {}\n",
                    escape_label(method),
                    escape_label(route),
                    status,
                    count
                ));
            }
        }

        // vfs_ops_total
        out.push_str("# HELP vfs_ops_total Total number of VFS operations.\n");
        out.push_str("# TYPE vfs_ops_total counter\n");
        {
            let map = self.vfs.lock().unwrap();
            let mut rows: Vec<(&String, &u64)> = map.iter().collect();
            rows.sort_by(|a, b| a.0.cmp(b.0));
            for (op, count) in rows {
                out.push_str(&format!(
                    "vfs_ops_total{{op=\"{}\"}} {}\n",
                    escape_label(op),
                    count
                ));
            }
        }

        // auth_ops_total
        out.push_str("# HELP auth_ops_total Total number of auth operations.\n");
        out.push_str("# TYPE auth_ops_total counter\n");
        {
            let map = self.auth.lock().unwrap();
            let mut rows: Vec<(&String, &u64)> = map.iter().collect();
            rows.sort_by(|a, b| a.0.cmp(b.0));
            for (op, count) in rows {
                out.push_str(&format!(
                    "auth_ops_total{{op=\"{}\"}} {}\n",
                    escape_label(op),
                    count
                ));
            }
        }

        // minios_share_rate_limited_total
        out.push_str("# HELP minios_share_rate_limited_total Total number of share read requests rejected by rate limiting.\n");
        out.push_str("# TYPE minios_share_rate_limited_total counter\n");
        out.push_str(&format!(
            "minios_share_rate_limited_total {}\n",
            self.share_ratelimited.load(Ordering::Relaxed)
        ));

        // http_request_duration_seconds
        out.push_str("# HELP http_request_duration_seconds HTTP request duration in seconds.\n");
        out.push_str("# TYPE http_request_duration_seconds histogram\n");
        {
            let map = self.durations.lock().unwrap();
            let mut keys: Vec<&(String, String)> = map.keys().collect();
            keys.sort();
            for key in keys {
                let (method, route) = key;
                let h = &map[key];
                let method = escape_label(method);
                let route = escape_label(route);
                for (i, b) in DURATION_BUCKETS.iter().enumerate() {
                    out.push_str(&format!(
                        "http_request_duration_seconds_bucket{{method=\"{}\",route=\"{}\",le=\"{}\"}} {}\n",
                        method, route, b, h.buckets[i]
                    ));
                }
                out.push_str(&format!(
                    "http_request_duration_seconds_bucket{{method=\"{}\",route=\"{}\",le=\"+Inf\"}} {}\n",
                    method, route, h.buckets[DURATION_BUCKETS.len()]
                ));
                out.push_str(&format!(
                    "http_request_duration_seconds_sum{{method=\"{}\",route=\"{}\"}} {}\n",
                    method, route, h.sum
                ));
                out.push_str(&format!(
                    "http_request_duration_seconds_count{{method=\"{}\",route=\"{}\"}} {}\n",
                    method, route, h.count
                ));
            }
        }

        // ws_connections
        out.push_str("# HELP ws_connections Current number of WebSocket connections.\n");
        out.push_str("# TYPE ws_connections gauge\n");
        out.push_str(&format!(
            "ws_connections {}\n",
            self.ws.load(Ordering::SeqCst)
        ));

        out
    }

    /// 记录一次请求时长（秒）：累加直方图。
    pub fn observe_duration(&self, method: &str, route: &str, secs: f64) {
        let secs = if secs.is_finite() && secs >= 0.0 {
            secs
        } else {
            0.0
        };
        let mut map = self.durations.lock().unwrap();
        let h = map
            .entry((method.to_string(), route.to_string()))
            .or_insert_with(|| Histogram {
                buckets: [0; 12],
                sum: 0.0,
                count: 0,
            });
        h.count += 1;
        h.sum += secs;
        // 累计直方图：所有 le >= secs 的桶都 +1（含 +Inf 桶）。
        let mut idx = DURATION_BUCKETS.len();
        for (i, b) in DURATION_BUCKETS.iter().enumerate() {
            if secs <= *b {
                idx = i;
                break;
            }
        }
        for b in h.buckets.iter_mut().skip(idx) {
            *b += 1;
        }
    }

    /// 渲染 gauge 段（DB 实时值）；调用方在 DB 可用时拼接在 render() 输出之后。
    pub fn render_gauges(&self, files: i64, bytes: i64, shares: &[(String, i64)]) -> String {
        let mut out = String::new();

        out.push_str("# HELP vfs_files_total Total number of files in the virtual file system.\n");
        out.push_str("# TYPE vfs_files_total gauge\n");
        out.push_str(&format!("vfs_files_total {}\n", files));

        out.push_str(
            "# HELP vfs_bytes_total Total bytes of file content in the virtual file system.\n",
        );
        out.push_str("# TYPE vfs_bytes_total gauge\n");
        out.push_str(&format!("vfs_bytes_total {}\n", bytes));

        out.push_str("# HELP shares_total Total number of shares by type.\n");
        out.push_str("# TYPE shares_total gauge\n");
        let mut sorted: Vec<&(String, i64)> = shares.iter().collect();
        sorted.sort_by(|a, b| a.0.cmp(&b.0));
        for (ty, count) in sorted {
            out.push_str(&format!(
                "shares_total{{type=\"{}\"}} {}\n",
                escape_label(ty),
                count
            ));
        }

        out
    }
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

/// 转义 Prometheus label 值：`\` → `\\`、`"` → `\"`、换行 → `\n`。
fn escape_label(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for ch in value.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            _ => out.push(ch),
        }
    }
    out
}

/// 中间件：统计每个请求的 method / route / status，并记录请求时长。
pub async fn metrics_middleware(
    State(metrics): State<Arc<Metrics>>,
    req: Request,
    next: Next,
) -> Response {
    let method = req.method().to_string();
    let route = req
        .extensions()
        .get::<MatchedPath>()
        .map(|p| p.as_str().to_string())
        .unwrap_or_else(|| "unknown".to_string());

    let start = std::time::Instant::now();
    let resp = next.run(req).await;
    let elapsed = start.elapsed().as_secs_f64();
    let status = resp.status().as_u16();
    metrics.inc_http(&method, &route, status);
    metrics.observe_duration(&method, &route, elapsed);
    resp
}

/// handler：渲染指标文本。
pub async fn metrics_handler(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let mut body = state.metrics.render();
    // gauge：DB 实时值；锁失败则跳过（不让 /metrics 挂掉）。
    if let Ok(conn) = state.db.lock() {
        let files: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'file'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let bytes: i64 = conn
            .query_row(
                "SELECT COALESCE(SUM(COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)))), 0) FROM vfs_nodes WHERE kind = 'file'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let mut shares: Vec<(String, i64)> = vec![];
        if let Ok(mut stmt) = conn.prepare(
            "SELECT share_type, COUNT(*) FROM shares GROUP BY share_type ORDER BY share_type",
        ) {
            if let Ok(rows) =
                stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)))
            {
                for row in rows.flatten() {
                    shares.push(row);
                }
            }
        }
        body.push_str(&state.metrics.render_gauges(files, bytes, &shares));
    }
    ([(CONTENT_TYPE, "text/plain; version=0.0.4")], body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn render_contains_help_type_before_samples() {
        let m = Metrics::new();
        m.inc_http("GET", "/api/fs/:id", 200);
        m.inc_vfs("read");
        m.ws_inc();

        let text = m.render();
        for name in ["http_requests_total", "vfs_ops_total", "ws_connections"] {
            let help = format!("# HELP {}", name);
            let typ = format!("# TYPE {}", name);
            assert!(text.contains(&help), "missing HELP for {}", name);
            assert!(text.contains(&typ), "missing TYPE for {}", name);
            let help_pos = text.find(&help).unwrap();
            let typ_pos = text.find(&typ).unwrap();
            assert!(help_pos < typ_pos, "HELP must precede TYPE for {}", name);
            // TYPE 行必须在样本行之前：样本行不以 '# ' 开头且包含指标名
            let sample_marker = format!("\n{} ", name);
            if let Some(sample_pos) = text.find(&sample_marker) {
                assert!(
                    typ_pos < sample_pos,
                    "TYPE must precede sample for {}",
                    name
                );
            }
            if let Some(sample_pos) = text.find(&format!("\n{}{{", name)) {
                assert!(
                    typ_pos < sample_pos,
                    "TYPE must precede sample for {}",
                    name
                );
            }
        }
    }

    #[test]
    fn inc_http_same_key_accumulates() {
        let m = Metrics::new();
        m.inc_http("GET", "/x", 200);
        m.inc_http("GET", "/x", 200);
        let text = m.render();
        assert!(text.contains("http_requests_total{method=\"GET\",route=\"/x\",status=\"200\"} 2"));
    }

    #[test]
    fn inc_vfs_accumulates() {
        let m = Metrics::new();
        m.inc_vfs("create");
        m.inc_vfs("create");
        let text = m.render();
        assert!(text.contains("vfs_ops_total{op=\"create\"} 2"));
    }

    #[test]
    fn ws_gauge_counts() {
        let m = Metrics::new();
        m.ws_inc();
        m.ws_inc();
        m.ws_dec();
        let text = m.render();
        assert!(text.contains("ws_connections 1"));
    }

    #[test]
    fn label_values_escaped() {
        let m = Metrics::new();
        m.inc_http("GET", "/a\"b\\c", 200);
        let text = m.render();
        assert!(text.contains("route=\"/a\\\"b\\\\c\""));
    }

    #[test]
    fn inc_auth_accumulates() {
        let m = Metrics::new();
        m.inc_auth("login");
        m.inc_auth("login");
        let text = m.render();
        assert!(text.contains(r#"auth_ops_total{op="login"} 2"#));
    }

    #[test]
    fn duration_histogram_buckets_are_cumulative() {
        let m = Metrics::new();
        m.observe_duration("GET", "/api/health", 0.003);
        m.observe_duration("GET", "/api/health", 0.02);
        m.observe_duration("GET", "/api/health", 30.0);
        let text = m.render();
        assert!(text.contains(
            r#"http_request_duration_seconds_bucket{method="GET",route="/api/health",le="0.005"} 1"#
        ));
        assert!(text.contains(
            r#"http_request_duration_seconds_bucket{method="GET",route="/api/health",le="0.025"} 2"#
        ));
        assert!(text.contains(
            r#"http_request_duration_seconds_bucket{method="GET",route="/api/health",le="+Inf"} 3"#
        ));
        assert!(text.contains(
            r#"http_request_duration_seconds_count{method="GET",route="/api/health"} 3"#
        ));
        assert!(text.contains(
            r#"http_request_duration_seconds_sum{method="GET",route="/api/health"} 30.023"#
        ));
    }

    #[test]
    fn duration_unknown_route_label() {
        let m = Metrics::new();
        m.observe_duration("GET", "unknown", 0.1);
        let text = m.render();
        assert!(text.contains(r#"route="unknown""#));
    }

    #[test]
    fn render_gauges_format() {
        let m = Metrics::new();
        let text = m.render_gauges(
            42,
            12345,
            &[("dir".to_string(), 2), ("file".to_string(), 7)],
        );
        assert!(text.contains(
            "# HELP vfs_files_total Total number of files in the virtual file system.\n"
        ));
        assert!(text.contains("# TYPE vfs_files_total gauge\n"));
        assert!(text.contains("vfs_files_total 42\n"));
        assert!(text.contains(
            "# HELP vfs_bytes_total Total bytes of file content in the virtual file system.\n"
        ));
        assert!(text.contains("# TYPE vfs_bytes_total gauge\n"));
        assert!(text.contains("vfs_bytes_total 12345\n"));
        assert!(text.contains("# HELP shares_total Total number of shares by type.\n"));
        assert!(text.contains("# TYPE shares_total gauge\n"));
        assert!(text.contains(r#"shares_total{type="dir"} 2"#));
        assert!(text.contains(r#"shares_total{type="file"} 7"#));
        let help_pos = text.find("# HELP vfs_files_total").unwrap();
        let type_pos = text.find("# TYPE vfs_files_total").unwrap();
        let sample_pos = text.find("vfs_files_total 42").unwrap();
        assert!(help_pos < type_pos);
        assert!(type_pos < sample_pos);
    }

    #[test]
    fn render_gauges_escapes_type() {
        let m = Metrics::new();
        let text = m.render_gauges(0, 0, &[("a\"b".to_string(), 1)]);
        assert!(text.contains(r#"shares_total{type="a\"b"} 1"#));
    }
}
