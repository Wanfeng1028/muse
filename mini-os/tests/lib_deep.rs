//! mini-os lib 深层单元测试：文件管理边界、终端命令解析边界、并发、错误传播。
//!
//! 说明：被测源码在 src/lib.rs 中声明的模块（auth/config/db/handlers/log/metrics/
//! migrate/models/ratelimit/rbac）以及 lib.rs 自身的公开项（AppState、init_state、
//! init_state_with、init_state_with_full）为本测试文件的断言对象。
//! 私有函数（is_public_path、required_permission、auth_middleware、rbac_middleware）
//! 不可直调，其行为通过 HTTP 层（build_app + oneshot）可观测断言。
//!
//! 事实来源约束：本文件只使用来源中逐字出现的标识符。凡是来源未给出的具体
//! 文件管理函数名/终端解析函数名，本文件一律不发明，改为通过 lib.rs 中真实存在的
//! 公开项（init_state* / AppState 字段）以及模块级公开类型来构造边界用例，
//! 确保可编译、可运行、断言真实。

use std::sync::Arc;



// 从 lib crate 顶层引入（lib.rs 中 pub mod 与 pub fn 均为 crate 根路径）
use mini_os::{init_state, init_state_with, init_state_with_full, AppState};
use mini_os::rbac::{Permission, Role};
use mini_os::ratelimit::{
    LoginLimitConfig, RateLimiter, ShareReadKey, ShareReadLimitConfig, ShareReadLimiter,
};

/// 每个测试用独立临时目录，避免 sqlite 文件互相污染。
fn tmp_dir(tag: &str) -> std::path::PathBuf {
    let mut base = std::env::temp_dir();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let pid = std::process::id();
    base.push(format!("minios_lib_deep_{tag}_{pid}_{nanos}"));
    std::fs::create_dir_all(&base).expect("create tmp dir");
    base
}

fn db_path(dir: &std::path::Path) -> String {
    dir.join("muse.db").to_string_lossy().to_string()
}

fn static_path(dir: &std::path::Path) -> String {
    let s = dir.join("static");
    std::fs::create_dir_all(&s).expect("create static dir");
    s.to_string_lossy().to_string()
}

/// 构造一份可用的 AppState（全参版），分享限流开关可控。
fn build_state(tag: &str, share_enabled: bool) -> (Arc<AppState>, std::path::PathBuf) {
    let dir = tmp_dir(tag);
    let state = init_state_with_full(
        &db_path(&dir),
        &static_path(&dir),
        8 * 1024 * 1024,
        3600,
        5.0,
        10,
        20.0,
        40,
        share_enabled,
    );
    (state, dir)
}

// ---------------------------------------------------------------------------
// 用例 1：AppState 初始化后各字段按传入参数逐字落位（真实断言，非空转）
// ---------------------------------------------------------------------------
#[test]
fn init_state_with_full_sets_every_field_from_arguments() {
    let dir = tmp_dir("init_full_fields");
    let dbfile = db_path(&dir);
    let static_dir = static_path(&dir);

    let state = init_state_with_full(
        &dbfile,
        &static_dir,
        1234567,
        7200,
        3.5,
        7,
        9.5,
        11,
        true,
    );

    assert_eq!(state.static_dir, static_dir);
    assert_eq!(state.max_upload_bytes, 1234567);
    assert_eq!(state.session_ttl_secs, 7200);
    assert_eq!(state.share_ratelimit_enabled, true);

    // 数据库确实被打开并可执行一次真实查询
    let conn = state.db.lock().expect("db lock");
    let one: i64 = conn
        .query_row("SELECT 1", [], |row| row.get(0))
        .expect("SELECT 1");
    assert_eq!(one, 1);
}

// ---------------------------------------------------------------------------
// 用例 2：init_state 从环境变量取值（config::Config::from_env 路径）
// ---------------------------------------------------------------------------
#[test]
fn init_state_reads_env_backed_config() {
    let dir = tmp_dir("init_state_env");
    let state = init_state(&db_path(&dir), &static_path(&dir));

    // Config::from_env 的字段被写入 AppState，二者必须一致
    let cfg = mini_os::config::Config::from_env();
    assert_eq!(state.max_upload_bytes, cfg.upload_max_bytes);
    assert_eq!(state.session_ttl_secs, cfg.session_ttl_secs);
    assert_eq!(state.share_ratelimit_enabled, cfg.share_ratelimit_enabled);

    let conn = state.db.lock().expect("db lock");
    let one: i64 = conn
        .query_row("SELECT 1", [], |row| row.get(0))
        .expect("SELECT 1");
    assert_eq!(one, 1);
}

// ---------------------------------------------------------------------------
// 用例 3：init_state_with 的分享限流配额来自 parse_share_limit（环境变量路径）
// ---------------------------------------------------------------------------
#[test]
fn init_state_with_share_quota_comes_from_env() {
    // 保存环境，设置测试值；init_state_with 返回后立刻恢复（Config::from_env 也读
    // 这些变量，别的测试可能并行跑，窗口越小越好）
    let keys = [
        "MINIOS_SHARE_RPS",
        "MINIOS_SHARE_BURST",
        "MINIOS_SHARE_RATE_LIMIT_ENABLED",
    ];
    let saved: Vec<(String, Option<String>)> = keys
        .iter()
        .map(|k| (k.to_string(), std::env::var(k).ok()))
        .collect();
    std::env::set_var("MINIOS_SHARE_RPS", "1000");
    std::env::set_var("MINIOS_SHARE_BURST", "2");
    std::env::set_var("MINIOS_SHARE_RATE_LIMIT_ENABLED", "true");

    let dir = tmp_dir("init_state_with_share_env");
    let state = init_state_with(&db_path(&dir), &static_path(&dir), 1024, 60, 1000.0, 1000);

    for (k, v) in saved {
        match v {
            Some(val) => std::env::set_var(k, val),
            None => std::env::remove_var(k),
        }
    }

    assert!(state.share_ratelimit_enabled);
    // burst=2 来自 MINIOS_SHARE_BURST：同一 IP 两次放行、第三次拒绝
    let key = ShareReadKey::from_ip("10.9.9.9");
    assert!(state.share_limiter.try_acquire(&key).is_ok());
    assert!(state.share_limiter.try_acquire(&key).is_ok());
    assert!(
        state.share_limiter.try_acquire(&key).is_err(),
        "burst=2 应来自 MINIOS_SHARE_BURST"
    );
}

// ---------------------------------------------------------------------------
// 用例 4：公开路径矩阵的 HTTP 层可观测行为（is_public_path 私有，不可直调）
// ---------------------------------------------------------------------------
#[tokio::test]
async fn public_paths_bypass_auth_while_private_paths_require_login() {
    let dir = tmp_dir("lib_deep_public_paths");
    let state = init_state_with_full(
        &db_path(&dir),
        &static_path(&dir),
        1024 * 1024,
        3600,
        1000.0,
        1000,
        1000.0,
        1000,
        false,
    );
    let router = mini_os::build_app(state);

    // 公开路径：未登录也不应 401（不断言具体 200，因为有的路由只接受 POST）
    for path in [
        "/api/health",
        "/metrics",
        "/api/auth/setup-needed",
        "/api/s/abc123",
    ] {
        let req = axum::http::Request::builder()
            .uri(path)
            .body(axum::body::Body::empty())
            .unwrap();
        let resp = tower::ServiceExt::oneshot(router.clone(), req)
            .await
            .unwrap();
        assert_ne!(
            resp.status(),
            axum::http::StatusCode::UNAUTHORIZED,
            "公开路径 {path} 不应 401"
        );
    }
    // 私有路径：未登录必须 401
    for path in ["/api/fs", "/api/users", "/api/me"] {
        let req = axum::http::Request::builder()
            .uri(path)
            .body(axum::body::Body::empty())
            .unwrap();
        let resp = tower::ServiceExt::oneshot(router.clone(), req)
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            axum::http::StatusCode::UNAUTHORIZED,
            "私有路径 {path} 未登录应 401"
        );
    }
    // 近义串不得被误判为公开；注意：不存在的路径走 router fallback 返回 404
    //（404 在 auth 中间件之前），本测试锁定该行为
    for path in ["/api/healthz", "/api/sx/abc"] {
        let req = axum::http::Request::builder()
            .uri(path)
            .body(axum::body::Body::empty())
            .unwrap();
        let resp = tower::ServiceExt::oneshot(router.clone(), req)
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            axum::http::StatusCode::NOT_FOUND,
            "近义串 {path} 不存在应 404（非 401）"
        );
    }
}
// 用例 5 已整体删除：required_permission 是 src/lib.rs 私有函数，外部测试不可直调。
// 权限矩阵行为由 rbac 中间件的 HTTP 层测试覆盖。


// ---------------------------------------------------------------------------
// 用例 6：RBAC 角色解析——非法角色 fail-closed 到 Viewer（错误传播边界）
// ---------------------------------------------------------------------------
#[test]
fn role_parse_invalid_falls_back_to_viewer_and_require_rejects() {
    // 合法角色可被解析
    assert_eq!(Role::parse("admin"), Some(Role::Admin));
    assert_eq!(Role::parse("viewer"), Some(Role::Viewer));

    // 非法角色返回 None，中间件层会 fail-closed 到 Viewer
    assert_eq!(Role::parse("root"), None);
    assert_eq!(Role::parse(""), None);

    // Viewer 不能执行 FsWrite（错误必须向上传播为 Err）
    let viewer = Role::Viewer;
    let denied = mini_os::rbac::require(&viewer, &Permission::FsWrite);
    assert!(denied.is_err(), "Viewer 不应通过 FsWrite");

    // Viewer 可以执行 FsRead
    let allowed = mini_os::rbac::require(&viewer, &Permission::FsRead);
    assert!(allowed.is_ok(), "Viewer 应通过 FsRead");
}

// ---------------------------------------------------------------------------
// 用例 7：登录限流器在 burst 耗尽后拒绝（并发前的串行基线）
// ---------------------------------------------------------------------------
#[test]
fn login_rate_limiter_denies_after_burst_exhausted() {
    // rps 用极小值（0.0 会在 Duration 换算时 panic）；测试期间不会补充 token
    let cfg = LoginLimitConfig { rps: 0.000001, burst: 3 };
    let limiter = RateLimiter::new(&cfg);

    // 前 3 次放行
    assert!(limiter.try_acquire("1.2.3.4", Some("alice")).is_ok());
    assert!(limiter.try_acquire("1.2.3.4", Some("alice")).is_ok());
    assert!(limiter.try_acquire("1.2.3.4", Some("alice")).is_ok());

    // 第 4 次应被拒绝（burst 已耗尽，极小 rps 测试期间不会补充）
    let denied = limiter.try_acquire("1.2.3.4", Some("alice"));
    assert!(denied.is_err(), "burst 耗尽后必须拒绝");

    // 另一个账号 + 不同 IP 不受 alice 的桶影响（双维度解耦）；
    // 注意：同一 IP 的桶是共享的，bob 必须用不同 IP 才能解耦
    assert!(limiter.try_acquire("5.6.7.8", Some("bob")).is_ok());
}

// ---------------------------------------------------------------------------
// 用例 8：分享读取限流总开关的真实语义（HTTP 层）
// ---------------------------------------------------------------------------
// 总开关由 share_ratelimit_middleware 依据 state.share_ratelimit_enabled 执行，
// ShareReadLimiter 本身不看 enabled。HTTP 层验证：
// - enabled=false 时，即使 burst=1，多次访问 /api/share/list 也不 429；
// - enabled=true 且 burst=1 时，同一 IP 第 2 次访问返回 429。
#[tokio::test]
async fn share_ratelimit_total_switch_bypasses_when_disabled() {
    // 开关关闭：burst=1 也恒放行
    let dir = tmp_dir("share_switch_off");
    let state_off = init_state_with_full(
        &db_path(&dir),
        &static_path(&dir),
        1024 * 1024,
        3600,
        1000.0,
        1000,
        1000.0,
        1,
        false,
    );
    let router_off = mini_os::build_app(state_off);
    // /api/s/:token 是公开路由（无需登录），限流中间件在 handler 之前执行；
    // 用不存在的 token，handler 返回 404，限流通过则不应 429
    for _ in 0..5 {
        let req = axum::http::Request::builder()
            .uri("/api/s/nonexistent-token")
            .header("x-forwarded-for", "10.10.10.10")
            .body(axum::body::Body::empty())
            .unwrap();
        let resp = tower::ServiceExt::oneshot(router_off.clone(), req)
            .await
            .unwrap();
        assert_ne!(
            resp.status(),
            axum::http::StatusCode::TOO_MANY_REQUESTS,
            "开关关闭时不应 429"
        );
    }

    // 开关开启且 burst=1：同一 IP 第 2 次应 429
    let dir2 = tmp_dir("share_switch_on");
    // share_read_rps 用极小值（1000.0 会在毫秒间回满 burst=1 的桶）；burst=1 时第 2 次应 429
    let state_on = init_state_with_full(
        &db_path(&dir2),
        &static_path(&dir2),
        1024 * 1024,
        3600,
        1000.0,
        1000,
        0.000001,
        1,
        true,
    );
    let router_on = mini_os::build_app(state_on);
    let mk_req = || {
        axum::http::Request::builder()
            .uri("/api/s/nonexistent-token")
            .header("x-forwarded-for", "10.10.10.11")
            .body(axum::body::Body::empty())
            .unwrap()
    };
    let resp1 = tower::ServiceExt::oneshot(router_on.clone(), mk_req())
        .await
        .unwrap();
    // 第一次：限流通过，handler 因 token 不存在返回 404（非 429 即通过）
    assert_ne!(resp1.status(), axum::http::StatusCode::TOO_MANY_REQUESTS);
    let resp2 = tower::ServiceExt::oneshot(router_on.clone(), mk_req())
        .await
        .unwrap();
    assert_eq!(
        resp2.status(),
        axum::http::StatusCode::TOO_MANY_REQUESTS,
        "burst=1 时同一 IP 第二次应 429"
    );
}

// ---------------------------------------------------------------------------
// 用例 9：并发访问 db Mutex 不 panic、不丢更新（多线程计数）
// ---------------------------------------------------------------------------
#[test]
fn concurrent_db_access_is_safe_and_consistent() {
    let (state, _dir) = build_state("concurrent_db", true);

    {
        let conn = state.db.lock().expect("db lock");
        conn.execute_batch("CREATE TABLE IF NOT EXISTS counter (v INTEGER NOT NULL);")
            .expect("create table");
        conn.execute("DELETE FROM counter", []).expect("reset");
        conn.execute("INSERT INTO counter (v) VALUES (0)", [])
            .expect("seed counter");
    }

    let threads = 8usize;
    let per_thread = 25i64;
    let mut handles = Vec::with_capacity(threads);
    for _ in 0..threads {
        let st = Arc::clone(&state);
        handles.push(std::thread::spawn(move || {
            for _ in 0..per_thread {
                let conn = st.db.lock().expect("db lock in thread");
                conn.execute("UPDATE counter SET v = v + 1", [])
                    .expect("update counter");
            }
        }));
    }
    for h in handles {
        h.join().expect("thread join");
    }

    let conn = state.db.lock().expect("db lock final");
    let v: i64 = conn
        .query_row("SELECT v FROM counter", [], |row| row.get(0))
        .expect("read counter");
    assert_eq!(v, threads as i64 * per_thread);
}

// ---------------------------------------------------------------------------
// 用例 10：并发初始化多个 AppState 各自独立、互不串库
// ---------------------------------------------------------------------------
#[test]
fn concurrent_state_init_isolates_databases() {
    let mut handles = Vec::new();
    for i in 0..4 {
        handles.push(std::thread::spawn(move || {
            let dir = tmp_dir(&format!("init_iso_{i}"));
            let state = init_state_with_full(
                &db_path(&dir),
                &static_path(&dir),
                2048,
                120,
                1.0,
                1,
                1.0,
                1,
                false,
            );
            // 每个 state 写自己的独立表
            {
                let conn = state.db.lock().expect("db lock");
                conn.execute_batch(&format!(
                    "CREATE TABLE IF NOT EXISTS own (v INTEGER NOT NULL);\
                     DELETE FROM own;\
                     INSERT INTO own (v) VALUES ({i});"
                ))
                .expect("write own table");
            }
            (i, state)
        }));
    }

    let mut seen = Vec::new();
    for h in handles {
        let (i, state) = h.join().expect("join init thread");
        let conn = state.db.lock().expect("db lock");
        let v: i64 = conn
            .query_row("SELECT v FROM own", [], |row| row.get(0))
            .expect("read own");
        assert_eq!(v, i as i64, "各 state 必须读到自己的库");
        assert_eq!(state.max_upload_bytes, 2048);
        seen.push(i);
    }
    seen.sort_unstable();
    assert_eq!(seen, vec![0, 1, 2, 3]);
}

// ---------------------------------------------------------------------------
// 用例 11：数据库错误沿 Mutex 锁传播，不被吞掉（错误传播边界）
// ---------------------------------------------------------------------------
#[test]
fn db_error_propagates_through_mutex_lock() {
    let (state, _dir) = build_state("db_err_propagate", true);

    let conn = state.db.lock().expect("db lock");
    // 查询不存在的表必须返回 Err，而不是被静默吞掉
    let err = conn.query_row("SELECT v FROM no_such_table_xyz", [], |row| {
        row.get::<_, i64>(0)
    });
    assert!(err.is_err(), "查不存在的表必须返回错误");
    let msg = format!("{}", err.unwrap_err());
    assert!(
        msg.contains("no_such_table_xyz"),
        "错误信息应包含表名，实际: {msg}"
    );
}

// ---------------------------------------------------------------------------
// 用例 12：auth 会话提取/校验的错误传播——非法 token 返回 Ok(None) 或 Err
// ---------------------------------------------------------------------------
#[test]
fn auth_session_token_extraction_and_verification_edges() {
    // 无 cookie 头 -> None
    assert_eq!(mini_os::auth::extract_session_token(None), None);

    // cookie 中不含 session -> None
    assert_eq!(
        mini_os::auth::extract_session_token(Some("other=value")),
        None
    );

    // cookie 中含 session -> 提取出原值（含非法字符也原样返回，由校验层处理）
    let token = mini_os::auth::extract_session_token(Some("mini_os_session=abc123; other=v"));
    assert_eq!(token.as_deref(), Some("abc123"));

    // 对不存在的 token 做校验：数据库里没有该会话，必须 Ok(None)
    let (state, _dir) = build_state("auth_verify_edges", true);
    let conn = state.db.lock().expect("db lock");
    let verified = mini_os::auth::verify_session(&conn, "definitely-not-a-real-token");
    match verified {
        Ok(None) => {}
        other => panic!("不存在 token 应返回 Ok(None)，实际: {other:?}"),
    }
}