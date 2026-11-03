use std::sync::Mutex;

use mini_os::ratelimit::{parse_share_limit, ShareReadLimitConfig};

static ENV_LOCK: Mutex<()> = Mutex::new(());

const ENV_SHARE_RPS: &str = "MINIOS_SHARE_RPS";
const ENV_SHARE_BURST: &str = "MINIOS_SHARE_BURST";
const ENV_SHARE_ENABLED: &str = "MINIOS_SHARE_RATE_LIMIT_ENABLED";
const ENV_LEGACY_SHARE_RPM: &str = "MINIOS_SHARE_READ_RPM";
const ENV_LEGACY_SHARE_BURST: &str = "MINIOS_SHARE_READ_BURST";

fn all_vars() -> [&'static str; 5] {
    [
        ENV_SHARE_RPS,
        ENV_SHARE_BURST,
        ENV_SHARE_ENABLED,
        ENV_LEGACY_SHARE_RPM,
        ENV_LEGACY_SHARE_BURST,
    ]
}

fn with_vars<F: FnOnce()>(pairs: &[(&str, Option<&str>)], f: F) {
    let mut backup: Vec<(&'static str, Option<String>)> = Vec::new();
    for name in all_vars() {
        backup.push((name, std::env::var(name).ok()));
    }
    for name in all_vars() {
        std::env::remove_var(name);
    }
    for (name, value) in pairs {
        match value {
            Some(v) => std::env::set_var(name, v),
            None => std::env::remove_var(name),
        }
    }

    f();

    for (name, value) in backup {
        match value {
            Some(v) => std::env::set_var(name, v),
            None => std::env::remove_var(name),
        }
    }
}

fn expect_ok(result: Result<ShareReadLimitConfig, String>) -> ShareReadLimitConfig {
    match result {
        Ok(cfg) => cfg,
        Err(e) => panic!("expected Ok, got Err: {}", e),
    }
}

fn expect_err(result: Result<ShareReadLimitConfig, String>) -> String {
    match result {
        Ok(_) => panic!("expected Err, got Ok"),
        Err(e) => e,
    }
}

#[test]
fn parse_share_limit_defaults() {
    let _guard = ENV_LOCK.lock().unwrap();
    with_vars(&[], || {
        let cfg = expect_ok(parse_share_limit());
        assert_eq!(cfg.rps, 5.0);
        assert_eq!(cfg.burst, 30);
        assert!(cfg.enabled);
    });
}

#[test]
fn parse_share_limit_rejects_bad_rps() {
    let _guard = ENV_LOCK.lock().unwrap();
    for raw in ["0", "-2", "NaN", "inf", "abc"] {
        with_vars(&[(ENV_SHARE_RPS, Some(raw))], || {
            let err = expect_err(parse_share_limit());
            assert!(
                err.contains(ENV_SHARE_RPS),
                "error should mention {}: {}",
                ENV_SHARE_RPS,
                err
            );
            assert!(
                err.contains("期望正的有限数"),
                "error should mention 期望正的有限数: {}",
                err
            );
        });
    }
}

#[test]
fn parse_share_limit_rejects_bad_burst() {
    let _guard = ENV_LOCK.lock().unwrap();
    for raw in ["0", "3.5", "-1", "abc"] {
        with_vars(&[(ENV_SHARE_BURST, Some(raw))], || {
            let err = expect_err(parse_share_limit());
            assert!(
                err.contains(ENV_SHARE_BURST),
                "error should mention {}: {}",
                ENV_SHARE_BURST,
                err
            );
            assert!(
                err.contains("期望大于 0 的整数"),
                "error should mention 期望大于 0 的整数: {}",
                err
            );
        });
    }
}

#[test]
fn parse_share_limit_enabled_values() {
    let _guard = ENV_LOCK.lock().unwrap();

    for raw in ["1", "true", "yes", "on", " TRUE "] {
        with_vars(&[(ENV_SHARE_ENABLED, Some(raw))], || {
            let cfg = expect_ok(parse_share_limit());
            assert!(cfg.enabled, "expected enabled=true for {:?}", raw);
        });
    }

    for raw in ["0", "false", "no", "off", "Off"] {
        with_vars(&[(ENV_SHARE_ENABLED, Some(raw))], || {
            let cfg = expect_ok(parse_share_limit());
            assert!(!cfg.enabled, "expected enabled=false for {:?}", raw);
        });
    }

    for raw in ["maybe", "2", ""] {
        with_vars(&[(ENV_SHARE_ENABLED, Some(raw))], || {
            let err = expect_err(parse_share_limit());
            assert!(
                err.contains(ENV_SHARE_ENABLED),
                "error should mention {}: {}",
                ENV_SHARE_ENABLED,
                err
            );
        });
    }
}

#[test]
fn parse_share_limit_rejects_legacy_vars() {
    let _guard = ENV_LOCK.lock().unwrap();

    with_vars(&[(ENV_LEGACY_SHARE_RPM, Some("60"))], || {
        let err = expect_err(parse_share_limit());
        assert!(
            err.contains("已废弃"),
            "error should mention 已废弃: {}",
            err
        );
        assert!(
            err.contains(ENV_LEGACY_SHARE_RPM),
            "error should mention {}: {}",
            ENV_LEGACY_SHARE_RPM,
            err
        );
        assert!(
            err.contains(ENV_SHARE_RPS),
            "error should mention {}: {}",
            ENV_SHARE_RPS,
            err
        );
    });

    with_vars(&[(ENV_LEGACY_SHARE_BURST, Some("10"))], || {
        let err = expect_err(parse_share_limit());
        assert!(
            err.contains("已废弃"),
            "error should mention 已废弃: {}",
            err
        );
        assert!(
            err.contains(ENV_LEGACY_SHARE_BURST),
            "error should mention {}: {}",
            ENV_LEGACY_SHARE_BURST,
            err
        );
        assert!(
            err.contains(ENV_SHARE_BURST),
            "error should mention {}: {}",
            ENV_SHARE_BURST,
            err
        );
    });
}

#[test]
fn parse_share_limit_accepts_valid_custom() {
    let _guard = ENV_LOCK.lock().unwrap();
    with_vars(
        &[
            (ENV_SHARE_RPS, Some("2.5")),
            (ENV_SHARE_BURST, Some("10")),
            (ENV_SHARE_ENABLED, Some("off")),
        ],
        || {
            let cfg = expect_ok(parse_share_limit());
            assert_eq!(cfg.rps, 2.5);
            assert_eq!(cfg.burst, 10);
            assert!(!cfg.enabled);
        },
    );
}
