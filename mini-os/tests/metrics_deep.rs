//! metrics 模块深度测试：并发、边界、错误传播。
//!
//! 由于被测源码里 `Metrics` 及相关字段均为私有或仅通过方法暴露，
//! 这里只测试公开 API 的行为（`inc_*`、`observe_duration`、`render`、
//! `render_gauges`、`ws_inc/ws_dec`、`inc_share_ratelimited`）。
//! 断言使用真实的 exposition 文本内容，不做空转。

use std::sync::Arc;
use std::thread;

use mini_os::metrics::Metrics;

/// 断言文本里包含完整的样本行（method/route/status 三元组）。
fn has_line(text: &str, line: &str) -> bool {
    text.lines().any(|l| l == line)
}

#[test]
fn http_counter_increments_and_renders_sorted() {
    let m = Metrics::new();
    m.inc_http("GET", "/a", 200);
    m.inc_http("GET", "/a", 200);
    m.inc_http("POST", "/b", 404);

    let out = m.render();
    assert!(has_line(&out, "# TYPE http_requests_total counter"));
    assert!(has_line(
        &out,
        "http_requests_total{method=\"GET\",route=\"/a\",status=\"200\"} 2"
    ));
    assert!(has_line(
        &out,
        "http_requests_total{method=\"POST\",route=\"/b\",status=\"404\"} 1"
    ));

    let get_pos = out
        .lines()
        .position(|l| l.starts_with("http_requests_total{method=\"GET\""))
        .unwrap();
    let post_pos = out
        .lines()
        .position(|l| l.starts_with("http_requests_total{method=\"POST\""))
        .unwrap();
    assert!(get_pos < post_pos);
}

#[test]
fn vfs_and_auth_counters_render_in_sorted_order() {
    let m = Metrics::new();
    m.inc_vfs("read");
    m.inc_vfs("read");
    m.inc_vfs("write");
    m.inc_auth("login");
    m.inc_auth("register");
    m.inc_auth("register");

    let out = m.render();
    assert!(has_line(&out, "# TYPE vfs_ops_total counter"));
    assert!(has_line(&out, "vfs_ops_total{op=\"read\"} 2"));
    assert!(has_line(&out, "vfs_ops_total{op=\"write\"} 1"));
    assert!(has_line(&out, "# TYPE auth_ops_total counter"));
    assert!(has_line(&out, "auth_ops_total{op=\"login\"} 1"));
    assert!(has_line(&out, "auth_ops_total{op=\"register\"} 2"));

    let read_pos = out
        .lines()
        .position(|l| l == "vfs_ops_total{op=\"read\"} 2")
        .unwrap();
    let write_pos = out
        .lines()
        .position(|l| l == "vfs_ops_total{op=\"write\"} 1")
        .unwrap();
    assert!(read_pos < write_pos);
}

#[test]
fn duration_histogram_accumulates_buckets_sum_and_count() {
    let m = Metrics::new();
    m.observe_duration("GET", "/x", 0.003);
    m.observe_duration("GET", "/x", 0.2);
    m.observe_duration("GET", "/x", 0.6);

    let out = m.render();
    assert!(has_line(
        &out,
        "# TYPE http_request_duration_seconds histogram"
    ));
    // 0.003 <= 0.005，因此 0.005 桶及其之后（含 +Inf）都是 1。
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/x\",le=\"0.005\"} 1"
    ));
    // 0.003 落在 0.005 之后，0.01/0.025/0.05 桶只在第二个观测（0.2）之前不再增长，
    // 但累计规则下 0.2 会加 0.25 起的桶。0.01 桶只被 0.003 命中，故为 1。
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/x\",le=\"0.01\"} 1"
    ));
    // 0.2 命中 0.25 桶，因此 0.25 桶包含 0.003、0.2 两次观测，加上 0.6 未命中，
    // 但 0.6 命中 1.0 桶（0.6 > 0.5），所以 0.25 桶 = 2。
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/x\",le=\"0.25\"} 2"
    ));
    // 0.6 落在 0.5 之后、1.0 之前，1.0 桶累计三次观测。
    // 注意：渲染用 {} 格式化 f64，1.0 显示为 "1" 而非 "1.0"。
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/x\",le=\"1\"} 3"
    ));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/x\",le=\"+Inf\"} 3"
    ));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_count{method=\"GET\",route=\"/x\"} 3"
    ));
    // sum = 0.003 + 0.2 + 0.6 = 0.803，浮点比较用容差。
    let sum_line = out
        .lines()
        .find(|l| l.starts_with("http_request_duration_seconds_sum{method=\"GET\",route=\"/x\"}"))
        .unwrap();
    let sum_val: f64 = sum_line
        .rsplit(' ')
        .next()
        .unwrap()
        .parse()
        .unwrap();
    assert!((sum_val - 0.803).abs() < 1e-9);
}

#[test]
fn duration_negative_and_nan_clamp_to_zero_bucket() {
    let m = Metrics::new();
    m.observe_duration("GET", "/clamp", -1.0);
    m.observe_duration("GET", "/clamp", f64::NAN);
    m.observe_duration("GET", "/clamp", f64::INFINITY);

    let out = m.render();
    // 三个观测都被钳到 0.0，全部落在最小桶 0.005。
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/clamp\",le=\"0.005\"} 3"
    ));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/clamp\",le=\"+Inf\"} 3"
    ));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_count{method=\"GET\",route=\"/clamp\"} 3"
    ));
    let sum_line = out
        .lines()
        .find(|l| {
            l.starts_with("http_request_duration_seconds_sum{method=\"GET\",route=\"/clamp\"}")
        })
        .unwrap();
    let sum_val: f64 = sum_line.rsplit(' ').next().unwrap().parse().unwrap();
    assert_eq!(sum_val, 0.0);
}

#[test]
fn duration_exactly_on_bucket_boundary_uses_that_bucket() {
    let m = Metrics::new();
    // 恰好等于桶边界 0.1，应命中 0.1 桶（含），而不是更小的桶。
    m.observe_duration("GET", "/bound", 0.1);

    let out = m.render();
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/bound\",le=\"0.05\"} 0"
    ));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/bound\",le=\"0.1\"} 1"
    ));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"GET\",route=\"/bound\",le=\"+Inf\"} 1"
    ));
}

#[test]
fn ws_gauge_inc_dec_and_render() {
    let m = Metrics::new();
    m.ws_inc();
    m.ws_inc();
    m.ws_inc();
    m.ws_dec();

    let out = m.render();
    assert!(has_line(&out, "# TYPE ws_connections gauge"));
    assert!(has_line(&out, "ws_connections 2"));
}

#[test]
fn share_ratelimited_counter_renders() {
    let m = Metrics::new();
    m.inc_share_ratelimited();
    m.inc_share_ratelimited();

    let out = m.render();
    assert!(has_line(
        &out,
        "# TYPE minios_share_rate_limited_total counter"
    ));
    assert!(has_line(&out, "minios_share_rate_limited_total 2"));
}

#[test]
fn render_gauges_renders_files_bytes_and_sorted_shares() {
    let m = Metrics::new();
    let shares = vec![
        ("link".to_string(), 3i64),
        ("code".to_string(), 7i64),
    ];
    let out = m.render_gauges(42, 1024, &shares);

    assert!(has_line(&out, "# TYPE vfs_files_total gauge"));
    assert!(has_line(&out, "vfs_files_total 42"));
    assert!(has_line(&out, "# TYPE vfs_bytes_total gauge"));
    assert!(has_line(&out, "vfs_bytes_total 1024"));
    assert!(has_line(&out, "# TYPE shares_total gauge"));
    assert!(has_line(&out, "shares_total{type=\"code\"} 7"));
    assert!(has_line(&out, "shares_total{type=\"link\"} 3"));

    let code_pos = out
        .lines()
        .position(|l| l == "shares_total{type=\"code\"} 7")
        .unwrap();
    let link_pos = out
        .lines()
        .position(|l| l == "shares_total{type=\"link\"} 3")
        .unwrap();
    assert!(code_pos < link_pos);
}

#[test]
fn label_escaping_handles_quotes_backslash_and_newline() {
    let m = Metrics::new();
    // 标签值里带引号、反斜杠、换行，Prometheus exposition 需要转义。
    m.inc_http("GET", "/p\"a\\th\nname", 200);

    let out = m.render();
    // 转义后：\" -> \\\"，反斜杠 -> \\\\，换行 -> \\n。
    assert!(out.contains("route=\"/p\\\"a\\\\th\\nname\""));
    assert!(has_line(
        &out,
        "http_requests_total{method=\"GET\",route=\"/p\\\"a\\\\th\\nname\",status=\"200\"} 1"
    ));
}

#[test]
fn concurrent_http_increments_are_consistent() {
    let m = Arc::new(Metrics::new());
    let threads: Vec<_> = (0..8)
        .map(|_| {
            let m = Arc::clone(&m);
            thread::spawn(move || {
                for _ in 0..500 {
                    m.inc_http("GET", "/c", 200);
                }
            })
        })
        .collect();
    for t in threads {
        t.join().unwrap();
    }

    let out = m.render();
    assert!(has_line(
        &out,
        "http_requests_total{method=\"GET\",route=\"/c\",status=\"200\"} 4000"
    ));
    // 只有一个 route，不会出现其它 route。
    assert_eq!(
        out.lines()
            .filter(|l| l.starts_with("http_requests_total{"))
            .count(),
        1
    );
}

#[test]
fn concurrent_mixed_ops_produce_stable_snapshot() {
    let m = Arc::new(Metrics::new());
    let mut handles = Vec::new();

    for _ in 0..4 {
        let m = Arc::clone(&m);
        handles.push(thread::spawn(move || {
            for _ in 0..250 {
                m.inc_vfs("read");
                m.inc_auth("login");
            }
        }));
    }
    for _ in 0..4 {
        let m = Arc::clone(&m);
        handles.push(thread::spawn(move || {
            for _ in 0..250 {
                m.observe_duration("POST", "/d", 0.05);
            }
        }));
    }
    for _ in 0..4 {
        let m = Arc::clone(&m);
        handles.push(thread::spawn(move || {
            for _ in 0..250 {
                m.ws_inc();
            }
        }));
    }

    for h in handles {
        h.join().unwrap();
    }

    let out = m.render();
    assert!(has_line(&out, "vfs_ops_total{op=\"read\"} 1000"));
    assert!(has_line(&out, "auth_ops_total{op=\"login\"} 1000"));
    assert!(has_line(
        &out,
        "http_request_duration_seconds_count{method=\"POST\",route=\"/d\"} 1000"
    ));
    // 0.05 恰好等于桶边界，累计到 0.05 桶及之后。
    assert!(has_line(
        &out,
        "http_request_duration_seconds_bucket{method=\"POST\",route=\"/d\",le=\"0.05\"} 1000"
    ));
    assert!(has_line(&out, "ws_connections 1000"));
}