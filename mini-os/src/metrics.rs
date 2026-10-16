// src/metrics.rs
//! Prometheus 文本格式指标：零依赖手写 exposition。
//!
//! 只使用标准库：`Mutex<HashMap<...>>` 存标签计数，`AtomicI64` 存 gauge。

use std::collections::HashMap;
use std::sync::atomic::{AtomicI64, Ordering};
use std::sync::{Arc, Mutex};

use axum::extract::{MatchedPath, Request, State};
use axum::http::header::CONTENT_TYPE;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};

use crate::AppState;

/// 指标集合：字段全私有，仅通过方法访问。
pub struct Metrics {
    /// http_requests_total：key 为 (method, route, status)。
    http: Mutex<HashMap<(String, String, u16), u64>>,
    /// vfs_ops_total：key 为 op。
    vfs: Mutex<HashMap<String, u64>>,
    /// ws_connections：当前 WebSocket 连接数。
    ws: AtomicI64,
}

impl Metrics {
    /// 创建空指标集合。
    pub fn new() -> Self {
        Self {
            http: Mutex::new(HashMap::new()),
            vfs: Mutex::new(HashMap::new()),
            ws: AtomicI64::new(0),
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

        // ws_connections
        out.push_str("# HELP ws_connections Current number of WebSocket connections.\n");
        out.push_str("# TYPE ws_connections gauge\n");
        out.push_str(&format!(
            "ws_connections {}\n",
            self.ws.load(Ordering::SeqCst)
        ));

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

/// 中间件：统计每个请求的 method / route / status。
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
        .unwrap_or_else(|| req.uri().path().to_string());

    let resp = next.run(req).await;
    let status = resp.status().as_u16();
    metrics.inc_http(&method, &route, status);
    resp
}

/// handler：渲染指标文本。
pub async fn metrics_handler(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let body = state.metrics.render();
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
                assert!(typ_pos < sample_pos, "TYPE must precede sample for {}", name);
            }
            if let Some(sample_pos) = text.find(&format!("\n{}{{", name)) {
                assert!(typ_pos < sample_pos, "TYPE must precede sample for {}", name);
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
}
