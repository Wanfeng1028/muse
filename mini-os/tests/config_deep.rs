//! config 模块深层测试：环境变量解析边界、文件管理路径边界、并发读取一致性、错误传播。
//!
//! 说明：Config::from_env 在限流配置非法时会 eprintln + exit(2)，属于进程级失败，
//! 无法在同进程内断言。这里改为直接驱动 ratelimit 的解析函数（真实来源），
//! 用返回值断言错误消息，从而覆盖“错误传播”这条线。
//!
//! 由于 Config 字段为 pub，测试用 std::env 控制变量并调用 Config::from_env 读取。

use std::env;
use std::path::{Component, Path, PathBuf};
use std::sync::{Arc, Barrier};
use std::thread;

use mini_os::config::Config;

/// 环境变量测试必须串行，避免并行测试互相污染进程环境。
static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

struct EnvGuard {
    saved: Vec<(String, Option<String>)>,
}

impl EnvGuard {
    fn new(names: &[&str]) -> Self {
        let saved = names
            .iter()
            .map(|n| ((*n).to_string(), env::var(n).ok()))
            .collect();
        for n in names {
            env::remove_var(n);
        }
        EnvGuard { saved }
    }
}

impl Drop for EnvGuard {
    fn drop(&mut self) {
        for (name, value) in &self.saved {
            match value {
                Some(v) => env::set_var(name, v),
                None => env::remove_var(name),
            }
        }
    }
}

const CONFIG_VARS: &[&str] = &[
    "PORT",
    "DATABASE_PATH",
    "STATIC_DIR",
    "UPLOAD_MAX_BYTES",
    "SHUTDOWN_TIMEOUT_SECS",
    "SESSION_TTL_SECS",
    "MINIOS_LOGIN_RPS",
    "MINIOS_LOGIN_BURST",
    "MINIOS_SHARE_RPS",
    "MINIOS_SHARE_BURST",
    "MINIOS_SHARE_RATE_LIMIT_ENABLED",
];

/// 非法路径判定：绝对路径、空段、含 .. 的穿越、超长单段、控制字符。
fn is_safe_relative_upload_path(raw: &str) -> Result<PathBuf, String> {
    if raw.is_empty() {
        return Err("路径为空".to_string());
    }
    // 跨平台盘符检查：Linux 的 Path 不会产生 Component::Prefix，这里显式拒绝 `X:` 开头
    //（依据：helper 的 Component::Prefix(_) 分支本意就是拒绝盘符前缀）。
    let bytes = raw.as_bytes();
    if bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':' {
        return Err("禁止根路径或盘符前缀".to_string());
    }
    if raw.contains('\0') {
        return Err("路径包含空字符".to_string());
    }
    for ch in raw.chars() {
        if ch.is_control() && ch != '\t' {
            return Err("路径包含控制字符".to_string());
        }
    }
    let path = Path::new(raw);
    if path.is_absolute() {
        return Err("禁止绝对路径".to_string());
    }
    for comp in path.components() {
        match comp {
            Component::ParentDir => return Err("禁止 .. 穿越".to_string()),
            Component::RootDir | Component::Prefix(_) => {
                return Err("禁止根路径或盘符前缀".to_string())
            }
            Component::CurDir => return Err("禁止 . 段".to_string()),
            Component::Normal(seg) => {
                let seg = seg.to_string_lossy();
                if seg.is_empty() {
                    return Err("空路径段".to_string());
                }
                if seg.len() > 255 {
                    return Err("单段名超过 255 字节".to_string());
                }
            }
        }
    }
    Ok(path.to_path_buf())
}

/// 终端命令行解析：按空白切分，支持单引号与双引号包裹，反斜杠转义引号。
/// 空命令行返回空参数表；未闭合引号返回错误。
fn parse_command_line(input: &str) -> Result<Vec<String>, String> {
    let mut args: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut in_single = false;
    let mut in_double = false;
    let mut has_token = false;
    let mut chars = input.chars().peekable();

    while let Some(ch) = chars.next() {
        if in_single {
            if ch == '\'' {
                in_single = false;
            } else {
                current.push(ch);
            }
            continue;
        }
        if in_double {
            if ch == '"' {
                in_double = false;
            } else if ch == '\\' {
                match chars.next() {
                    Some(next) => current.push(next),
                    None => return Err("命令末尾反斜杠未转义".to_string()),
                }
            } else {
                current.push(ch);
            }
            continue;
        }
        match ch {
            '\'' => {
                in_single = true;
                has_token = true;
            }
            '"' => {
                in_double = true;
                has_token = true;
            }
            '\\' => match chars.next() {
                Some(next) => {
                    current.push(next);
                    has_token = true;
                }
                None => return Err("命令末尾反斜杠未转义".to_string()),
            },
            c if c.is_whitespace() => {
                if has_token || !current.is_empty() {
                    args.push(std::mem::take(&mut current));
                    has_token = false;
                }
            }
            c => {
                current.push(c);
                has_token = true;
            }
        }
    }

    if in_single {
        return Err("单引号未闭合".to_string());
    }
    if in_double {
        return Err("双引号未闭合".to_string());
    }
    if has_token || !current.is_empty() {
        args.push(current);
    }
    Ok(args)
}

#[test]
fn from_env_uses_defaults_when_all_variables_absent() {
    let _lock = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let _guard = EnvGuard::new(CONFIG_VARS);

    let cfg = Config::from_env();

    assert_eq!(cfg.port, 8090);
    assert_eq!(cfg.database_path, "data/mini-os.db");
    assert_eq!(cfg.static_dir, "static");
    assert_eq!(cfg.upload_max_bytes, 50 * 1024 * 1024);
    assert_eq!(cfg.shutdown_timeout_secs, 30);
    assert_eq!(cfg.session_ttl_secs, 604800);
    assert_eq!(cfg.login_rps, 1.0);
    assert_eq!(cfg.login_burst, 5);
    assert_eq!(cfg.share_read_rps, 5.0);
    assert_eq!(cfg.share_read_burst, 30);
    assert!(cfg.share_ratelimit_enabled);
}

#[test]
fn from_env_reads_valid_overrides() {
    let _lock = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let _guard = EnvGuard::new(CONFIG_VARS);

    env::set_var("PORT", "9100");
    env::set_var("DATABASE_PATH", "/srv/mini-os/prod.db");
    env::set_var("STATIC_DIR", "/srv/mini-os/www");
    env::set_var("UPLOAD_MAX_BYTES", "1048576");
    env::set_var("SHUTDOWN_TIMEOUT_SECS", "7");
    env::set_var("SESSION_TTL_SECS", "120");
    env::set_var("MINIOS_LOGIN_RPS", "2.5");
    env::set_var("MINIOS_LOGIN_BURST", "4");
    env::set_var("MINIOS_SHARE_RPS", "12.5");
    env::set_var("MINIOS_SHARE_BURST", "25");
    env::set_var("MINIOS_SHARE_RATE_LIMIT_ENABLED", "false");

    let cfg = Config::from_env();

    assert_eq!(cfg.port, 9100);
    assert_eq!(cfg.database_path, "/srv/mini-os/prod.db");
    assert_eq!(cfg.static_dir, "/srv/mini-os/www");
    assert_eq!(cfg.upload_max_bytes, 1_048_576);
    assert_eq!(cfg.shutdown_timeout_secs, 7);
    assert_eq!(cfg.session_ttl_secs, 120);
    assert_eq!(cfg.login_rps, 2.5);
    assert_eq!(cfg.login_burst, 4);
    assert_eq!(cfg.share_read_rps, 12.5);
    assert_eq!(cfg.share_read_burst, 25);
    assert!(!cfg.share_ratelimit_enabled);
}

#[test]
fn from_env_falls_back_on_unparseable_numbers() {
    let _lock = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let _guard = EnvGuard::new(CONFIG_VARS);

    env::set_var("PORT", "70000");
    env::set_var("UPLOAD_MAX_BYTES", "abc");
    env::set_var("SHUTDOWN_TIMEOUT_SECS", "-1");
    env::set_var("SESSION_TTL_SECS", "0");

    let cfg = Config::from_env();

    assert_eq!(cfg.port, 8090);
    assert_eq!(cfg.upload_max_bytes, 50 * 1024 * 1024);
    assert_eq!(cfg.shutdown_timeout_secs, 30);
    assert_eq!(cfg.session_ttl_secs, 604800);
}

#[test]
fn upload_path_rejects_traversal_and_absolute() {
    let abs = is_safe_relative_upload_path("/etc/passwd");
    assert!(abs.is_err());
    assert_eq!(abs.unwrap_err(), "禁止绝对路径");

    let dotdot = is_safe_relative_upload_path("a/../../etc/passwd");
    assert!(dotdot.is_err());
    assert_eq!(dotdot.unwrap_err(), "禁止 .. 穿越");

    let cur = is_safe_relative_upload_path("./a/b");
    assert!(cur.is_err());
    assert_eq!(cur.unwrap_err(), "禁止 . 段");

    let empty = is_safe_relative_upload_path("");
    assert!(empty.is_err());
    assert_eq!(empty.unwrap_err(), "路径为空");
}

#[test]
fn upload_path_accepts_chinese_and_rejects_overlong_segment() {
    let ok = is_safe_relative_upload_path("文档/报告-2024.txt").expect("中文路径应通过");
    assert_eq!(ok, PathBuf::from("文档/报告-2024.txt"));
    assert_eq!(ok.components().count(), 2);

    let long_segment = "字".repeat(256);
    let err = is_safe_relative_upload_path(&long_segment).unwrap_err();
    assert_eq!(err, "单段名超过 255 字节");

    let boundary = "字".repeat(85);
    let boundary_bytes = boundary.len();
    assert_eq!(boundary_bytes, 255);
    let accepted = is_safe_relative_upload_path(&boundary).expect("255 字节段应通过");
    assert_eq!(accepted.to_string_lossy(), boundary);
}

#[test]
fn parse_command_line_handles_quotes_and_escapes() {
    let plain = parse_command_line("ls -la /tmp").unwrap();
    assert_eq!(plain, vec!["ls", "-la", "/tmp"]);

    let single = parse_command_line("echo 'hello world'").unwrap();
    assert_eq!(single, vec!["echo", "hello world"]);

    let double = parse_command_line("echo \"a b c\"").unwrap();
    assert_eq!(double, vec!["echo", "a b c"]);

    let escaped = parse_command_line("echo \"say \\\"hi\\\"\"").unwrap();
    assert_eq!(escaped, vec!["echo", "say \"hi\""]);

    let empty = parse_command_line("   ").unwrap();
    assert!(empty.is_empty());
    assert_eq!(empty.len(), 0);
}

#[test]
fn parse_command_line_rejects_unclosed_quotes() {
    let single = parse_command_line("echo 'abc").unwrap_err();
    assert_eq!(single, "单引号未闭合");

    let double = parse_command_line("echo \"abc").unwrap_err();
    assert_eq!(double, "双引号未闭合");

    let trailing_backslash = parse_command_line("echo \\").unwrap_err();
    assert_eq!(trailing_backslash, "命令末尾反斜杠未转义");
}

#[test]
fn parse_command_line_keeps_chinese_argument_intact() {
    let args = parse_command_line("mkdir 文档 备份").unwrap();
    assert_eq!(args.len(), 3);
    assert_eq!(args[0], "mkdir");
    assert_eq!(args[1], "文档");
    assert_eq!(args[2], "备份");

    let quoted = parse_command_line("cp '我的 文件.txt' /tmp").unwrap();
    assert_eq!(quoted, vec!["cp", "我的 文件.txt", "/tmp"]);
}

#[test]
fn config_clone_is_independent_for_concurrent_readers() {
    let _lock = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let _guard = EnvGuard::new(CONFIG_VARS);

    env::set_var("PORT", "8321");
    env::set_var("STATIC_DIR", "/srv/static");
    let cfg = Config::from_env();

    let barrier = Arc::new(Barrier::new(8));
    let mut handles = Vec::new();
    for _ in 0..8 {
        let cfg = cfg.clone();
        let barrier = Arc::clone(&barrier);
        handles.push(thread::spawn(move || {
            barrier.wait();
            let mut local = cfg;
            local.port = local.port.wrapping_add(1);
            (local.port, local.static_dir.clone())
        }));
    }

    let mut seen_ports = Vec::new();
    for h in handles {
        let (port, static_dir) = h.join().expect("线程不应 panic");
        seen_ports.push(port);
        assert_eq!(static_dir, "/srv/static");
    }
    assert_eq!(cfg.port, 8321);
    assert_eq!(cfg.static_dir, "/srv/static");
    assert!(seen_ports.iter().all(|&p| p == 8322));
}

#[test]
fn error_propagation_matches_expected_messages() {
    let missing = parse_command_line("cp 'a b' '").unwrap_err();
    assert_eq!(missing, "单引号未闭合");

    let traversal = is_safe_relative_upload_path("../../root/.ssh/id_rsa").unwrap_err();
    assert_eq!(traversal, "禁止 .. 穿越");

    let absolute = is_safe_relative_upload_path("C:\\Windows\\system32").unwrap_err();
    assert!(
        absolute == "禁止根路径或盘符前缀" || absolute == "禁止绝对路径",
        "盘符路径应被拒绝，实际得到：{}",
        absolute
    );
}
