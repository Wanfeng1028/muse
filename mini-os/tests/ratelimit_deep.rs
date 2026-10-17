//! ratelimit 模块深度测试：配置解析、令牌桶边界、并发、错误传播。
//!
//! 该文件为集成测试，通过 `mini_os::ratelimit` 公开 API 访问被测实现。

use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use mini_os::ratelimit::{parse_login_limit, LoginLimitConfig, RateLimiter};

/// 环境变量操作需要串行化，避免并行测试互相污染。
fn env_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: std::sync::OnceLock<std::sync::Mutex<()>> = std::sync::OnceLock::new();
    LOCK.get_or_init(|| std::sync::Mutex::new(()))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
}

/// 在给定环境变量集合下调用 parse_login_limit，随后恢复现场。
fn with_env<F, R>(rps: Option<&str>, burst: Option<&str>, f: F) -> R
where
    F: FnOnce() -> R,
{
    let _guard = env_lock();
    let old_rps = std::env::var("MINIOS_LOGIN_RPS").ok();
    let old_burst = std::env::var("MINIOS_LOGIN_BURST").ok();

    match rps {
        Some(v) => std::env::set_var("MINIOS_LOGIN_RPS", v),
        None => std::env::remove_var("MINIOS_LOGIN_RPS"),
    }
    match burst {
        Some(v) => std::env::set_var("MINIOS_LOGIN_BURST", v),
        None => std::env::remove_var("MINIOS_LOGIN_BURST"),
    }

    let out = f();

    match old_rps {
        Some(v) => std::env::set_var("MINIOS_LOGIN_RPS", v),
        None => std::env::remove_var("MINIOS_LOGIN_RPS"),
    }
    match old_burst {
        Some(v) => std::env::set_var("MINIOS_LOGIN_BURST", v),
        None => std::env::remove_var("MINIOS_LOGIN_BURST"),
    }
    out
}

fn cfg(rps: f64, burst: u64) -> LoginLimitConfig {
    LoginLimitConfig { rps, burst }
}

#[test]
fn parse_login_limit_uses_defaults_when_unset() {
    let r = with_env(None, None, parse_login_limit);
    let parsed = r.expect("未设置环境变量时应使用默认值成功");
    assert_eq!(parsed.rps, 1.0, "默认 rps 应为 1");
    assert_eq!(parsed.burst, 5, "默认 burst 应为 5");
}

#[test]
fn parse_login_limit_rejects_zero_and_negative_rps() {
    let zero = with_env(Some("0"), Some("5"), parse_login_limit);
    let zero_err = zero.expect_err("rps=0 应报错");
    assert!(
        zero_err.contains("MINIOS_LOGIN_RPS"),
        "错误信息应点名 MINIOS_LOGIN_RPS，实际: {}",
        zero_err
    );
    assert!(
        zero_err.contains('0'),
        "错误信息应包含非法值 '0'，实际: {}",
        zero_err
    );

    let neg = with_env(Some("-2.5"), Some("5"), parse_login_limit);
    let neg_err = neg.expect_err("rps=-2.5 应报错");
    assert!(
        neg_err.contains("MINIOS_LOGIN_RPS"),
        "错误信息应点名 MINIOS_LOGIN_RPS，实际: {}",
        neg_err
    );
    assert!(
        neg_err.contains("-2.5"),
        "错误信息应包含非法值 '-2.5'，实际: {}",
        neg_err
    );
}

#[test]
fn parse_login_limit_rejects_nan_and_infinity_and_garbage() {
    let nan = with_env(Some("NaN"), Some("5"), parse_login_limit);
    assert!(
        nan.is_err(),
        "NaN 应被拒绝，但得到: {:?}",
        nan.map(|c| c.rps)
    );

    let inf = with_env(Some("inf"), Some("5"), parse_login_limit);
    assert!(
        inf.is_err(),
        "inf 应被拒绝，但得到: {:?}",
        inf.map(|c| c.rps)
    );

    let garbage = with_env(Some("not-a-number"), Some("5"), parse_login_limit);
    let g_err = garbage.expect_err("非数字应被拒绝");
    assert!(
        g_err.contains("not-a-number"),
        "错误信息应包含原始输入，实际: {}",
        g_err
    );
    assert!(
        g_err.contains("MINIOS_LOGIN_RPS"),
        "错误信息应点名 MINIOS_LOGIN_RPS，实际: {}",
        g_err
    );
}

#[test]
fn parse_login_limit_rejects_zero_and_non_integer_burst() {
    let zero = with_env(Some("1"), Some("0"), parse_login_limit);
    let z_err = zero.expect_err("burst=0 应被拒绝");
    assert!(
        z_err.contains("MINIOS_LOGIN_BURST"),
        "错误信息应点名 MINIOS_LOGIN_BURST，实际: {}",
        z_err
    );
    assert!(
        z_err.contains('0'),
        "错误信息应包含非法值 '0'，实际: {}",
        z_err
    );

    let frac = with_env(Some("1"), Some("3.5"), parse_login_limit);
    let f_err = frac.expect_err("burst=3.5 非整数应被拒绝");
    assert!(
        f_err.contains("MINIOS_LOGIN_BURST"),
        "错误信息应点名 MINIOS_LOGIN_BURST，实际: {}",
        f_err
    );
    assert!(
        f_err.contains("3.5"),
        "错误信息应包含非法值 '3.5'，实际: {}",
        f_err
    );
}

#[test]
fn burst_is_consumed_then_rejected_and_not_deducted_on_reject() {
    // rps=1，burst=3。同一瞬间连续取 3 次应全部成功，第 4 次拒绝。
    let limiter = RateLimiter::new(&cfg(1.0, 3));
    let now = Instant::now();

    for i in 0..3 {
        let r = limiter.try_acquire_at("1.1.1.1", None, now);
        assert!(r.is_ok(), "第 {} 次应放行，实际: {:?}", i + 1, r);
    }

    let rejected = limiter.try_acquire_at("1.1.1.1", None, now);
    let secs = rejected.expect_err("第 4 次应被拒绝");
    // 令牌为 0，deficit=1，rps=1 → ceil(1/1)=1。
    assert_eq!(secs, 1, "retry_after 应为 1 秒");

    // 拒绝后立即再次尝试，仍应拒绝且秒数不变（说明拒绝未扣桶）。
    let again = limiter.try_acquire_at("1.1.1.1", None, now);
    let secs2 = again.expect_err("拒绝后再次尝试仍应拒绝");
    assert_eq!(secs2, 1, "拒绝路径不得扣减令牌，retry_after 仍为 1");
}

#[test]
fn ip_and_account_dimensions_both_limit() {
    // burst=2，rps=1。IP 维度独立于账号维度。
    let limiter = RateLimiter::new(&cfg(1.0, 2));
    let now = Instant::now();

    assert!(
        limiter.try_acquire_at("10.0.0.1", Some("alice"), now).is_ok(),
        "第 1 次 (alice) 应放行"
    );
    assert!(
        limiter.try_acquire_at("10.0.0.1", Some("bob"), now).is_ok(),
        "第 2 次 (bob) 应放行"
    );

    // IP 桶已空，即便账号 bob 还有余量，也应被 IP 维度拒绝。
    let r = limiter.try_acquire_at("10.0.0.1", Some("bob"), now);
    assert!(
        r.is_err(),
        "IP 桶空时，换账号也不应放行，实际: {:?}",
        r
    );
}

#[test]
fn account_key_none_or_empty_skips_account_bucket() {
    // burst=2，rps=1；账号键为 None 与 "" 都应只走 IP 桶。
    let limiter = RateLimiter::new(&cfg(1.0, 2));
    let now = Instant::now();

    assert!(
        limiter.try_acquire_at("2.2.2.2", None, now).is_ok(),
        "None 账号第 1 次应放行"
    );
    assert!(
        limiter.try_acquire_at("2.2.2.2", Some(""), now).is_ok(),
        "空字符串账号第 2 次应放行"
    );
    let r = limiter.try_acquire_at("2.2.2.2", None, now);
    assert!(r.is_err(), "IP 桶已空，第 3 次应拒绝，实际: {:?}", r);
}

#[test]
fn tokens_refill_over_time_and_capped_at_burst() {
    // rps=2，burst=2。等 1 秒应补 2 个 token，恰好回满。
    let limiter = RateLimiter::new(&cfg(2.0, 2));
    let t0 = Instant::now();

    assert!(limiter.try_acquire_at("3.3.3.3", None, t0).is_ok());
    assert!(limiter.try_acquire_at("3.3.3.3", None, t0).is_ok());
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t0).is_err(),
        "桶空后应立即拒绝"
    );

    let t1 = t0 + Duration::from_secs(1);
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t1).is_ok(),
        "1 秒后应补满并放行"
    );
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t1).is_ok(),
        "补满后有 2 个 token，第 2 次仍应放行"
    );
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t1).is_err(),
        "再次耗尽应拒绝"
    );

    // 等待远超补满时间，token 不应超过 burst。
    let t2 = t1 + Duration::from_secs(100);
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t2).is_ok(),
        "长时间后第 1 次应放行"
    );
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t2).is_ok(),
        "长时间后第 2 次应放行（burst 上限为 2）"
    );
    assert!(
        limiter.try_acquire_at("3.3.3.3", None, t2).is_err(),
        "第 3 次必须拒绝，证明 token 被 burst 截断"
    );
}

#[test]
fn retry_after_is_rounded_up_to_whole_seconds() {
    // rps=2，burst=1：取完 1 个 token 后，deficit=1，ceil(1/2)=1。
    let limiter = RateLimiter::new(&cfg(2.0, 1));
    let now = Instant::now();
    assert!(limiter.try_acquire_at("4.4.4.4", None, now).is_ok());
    let secs = limiter
        .try_acquire_at("4.4.4.4", None, now)
        .expect_err("桶空应拒绝");
    assert_eq!(secs, 1, "deficit=1，rps=2 → ceil(0.5)=1 秒");

    // rps=0.5，burst=1：deficit=1，ceil(1/0.5)=2。
    let limiter2 = RateLimiter::new(&cfg(0.5, 1));
    let t = Instant::now();
    assert!(limiter2.try_acquire_at("5.5.5.5", None, t).is_ok());
    let secs2 = limiter2
        .try_acquire_at("5.5.5.5", None, t)
        .expect_err("桶空应拒绝");
    assert_eq!(secs2, 2, "deficit=1，rps=0.5 → ceil(2)=2 秒");
}

#[test]
fn concurrent_access_never_exceeds_burst() {
    // 8 线程共享同一限流器，同一 IP，burst=5，rps=1（近似不补充）。
    // 成功次数必须恰好等于 burst，不能超发。
    let limiter = Arc::new(RateLimiter::new(&cfg(1.0, 5)));
    let now = Instant::now();

    let mut handles = Vec::new();
    for _ in 0..8 {
        let l = Arc::clone(&limiter);
        handles.push(thread::spawn(move || {
            l.try_acquire_at("6.6.6.6", None, now).is_ok()
        }));
    }

    let mut ok_count = 0usize;
    let mut err_count = 0usize;
    for h in handles {
        if h.join().expect("线程不应 panic") {
            ok_count += 1;
        } else {
            err_count += 1;
        }
    }

    assert_eq!(ok_count, 5, "并发下成功次数应恰为 burst=5");
    assert_eq!(err_count, 3, "并发下失败次数应为 3");
}

#[test]
fn concurrent_account_and_ip_share_limiter_consistently() {
    // 4 线程同 IP 同账号，burst=3：成功数必须为 3。
    let limiter = Arc::new(RateLimiter::new(&cfg(1.0, 3)));
    let now = Instant::now();

    let mut handles = Vec::new();
    for _ in 0..4 {
        let l = Arc::clone(&limiter);
        handles.push(thread::spawn(move || {
            l.try_acquire_at("7.7.7.7", Some("carol"), now).is_ok()
        }));
    }

    let results: Vec<bool> = handles
        .into_iter()
        .map(|h| h.join().expect("线程不应 panic"))
        .collect();
    let ok = results.iter().filter(|b| **b).count();
    let fail = results.iter().filter(|b| !**b).count();

    assert_eq!(ok, 3, "并发共享 IP+账号桶时成功数应为 burst=3");
    assert_eq!(fail, 1, "并发共享 IP+账号桶时失败数应为 1");
}

#[test]
fn distinct_keys_do_not_share_buckets() {
    // 不同 IP、不同账号各自独立计数。
    let limiter = RateLimiter::new(&cfg(1.0, 1));
    let now = Instant::now();

    assert!(limiter.try_acquire_at("8.8.8.8", Some("u1"), now).is_ok());
    assert!(limiter.try_acquire_at("9.9.9.9", Some("u2"), now).is_ok());
    // 各自桶已空，再次请求应拒绝。
    assert!(
        limiter.try_acquire_at("8.8.8.8", Some("u1"), now).is_err(),
        "同一 IP+账号第二次应拒绝"
    );
    assert!(
        limiter.try_acquire_at("9.9.9.9", Some("u2"), now).is_err(),
        "另一 IP+账号第二次应拒绝"
    );
    // 同一 IP 桶已空时换账号也必须拒绝：IP 桶与账号桶是"与"关系，缺一不可。
    assert!(
        limiter.try_acquire_at("8.8.8.8", Some("u2"), now).is_err(),
        "IP 桶已空时换账号也应拒绝（双桶缺一不可）"
    );
    // 而全新 IP + 全新账号仍能成功，证明桶按 key 隔离。
    assert!(
        limiter.try_acquire_at("7.7.7.7", Some("u3"), now).is_ok(),
        "全新 IP+账号应放行"
    );
}