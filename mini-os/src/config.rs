use std::env;

/// 应用配置
#[derive(Debug, Clone)]
pub struct Config {
    pub data_dir: String,
    pub port: u16,
    pub database_path: String,
    pub static_dir: String,
    pub upload_max_bytes: u64,
    pub shutdown_timeout_secs: u64,
    pub session_ttl_secs: u64,
    /// 会话滑动续期开关（MINIOS_SESSION_SLIDING），默认开启
    pub session_sliding: bool,
    /// 登录限流：每秒补充的令牌数（来自 MINIOS_LOGIN_RPS）
    pub login_rps: f64,
    /// 登录限流：桶容量/突发上限（来自 MINIOS_LOGIN_BURST）
    pub login_burst: u64,
    /// 分享读取限流：每秒补充的令牌数（来自 MINIOS_SHARE_RPS）
    pub share_read_rps: f64,
    /// 分享读取限流：桶容量/突发上限（来自 MINIOS_SHARE_BURST）
    pub share_read_burst: u64,
    /// 来自 MINIOS_SHARE_RATE_LIMIT_ENABLED，默认开启
    pub share_ratelimit_enabled: bool,
    /// 终端单会话连续输出上限（字节），来自 MINIOS_TERM_OUTPUT_LIMIT，默认 1MiB
    pub term_output_limit: u64,
}

/// 解析会话滑动续期开关原始值：缺省/非法之外的真值表，非法返回 Err。
pub fn parse_session_sliding_raw(raw: Option<&str>) -> Result<bool, String> {
    match raw {
        None => Ok(true),
        Some(s) => match s.trim().to_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Ok(true),
            "0" | "false" | "no" | "off" => Ok(false),
            _ => Err(format!(
                "MINIOS_SESSION_SLIDING 非法：{:?}，只能是 true/false/1/0/yes/no/on/off",
                s
            )),
        },
    }
}

/// 从环境变量读取配置，缺失或解析失败时使用默认值

impl Config {
    pub fn from_env() -> Self {
        let data_dir = compute_data_dir();
        let port = env::var("PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(8090);

        let database_path =
            env::var("DATABASE_PATH").unwrap_or_else(|_| "data/mini-os.db".to_string());

        let static_dir = env::var("STATIC_DIR").unwrap_or_else(|_| "static".to_string());

        let upload_max_bytes = env::var("UPLOAD_MAX_BYTES")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(50 * 1024 * 1024);

        let shutdown_timeout_secs = env::var("SHUTDOWN_TIMEOUT_SECS")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(30);

        let session_ttl_secs = env::var("SESSION_TTL_SECS")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .filter(|&v| v > 0)
            .unwrap_or(604800);

        // 会话滑动续期开关：非法值 fail-fast（与限流配置同规格）。
        let session_sliding =
            match parse_session_sliding_raw(env::var("MINIOS_SESSION_SLIDING").ok().as_deref()) {
                Ok(v) => v,
                Err(msg) => {
                    eprintln!("配置错误：{}", msg);
                    std::process::exit(2);
                }
            };

        // 登录限流配置：非法值 fail-fast（启动即报错退出），符合规格 S3。
        // 注意 from_env 的签名是 -> Self（非 Result），因此这里直接 eprintln + exit(2)。
        let login_limit = match crate::ratelimit::parse_login_limit() {
            Ok(cfg) => cfg,
            Err(msg) => {
                eprintln!("配置错误：{}", msg);
                std::process::exit(2);
            }
        };

        // 分享读取限流配置（v1.8）：MINIOS_SHARE_RPS / MINIOS_SHARE_BURST / MINIOS_SHARE_RATE_LIMIT_ENABLED，非法值同样 fail-fast。
        let share_limit = match crate::ratelimit::parse_share_limit() {
            Ok(cfg) => cfg,
            Err(msg) => {
                eprintln!("配置错误：{}", msg);
                std::process::exit(2);
            }
        };
        // 终端输出背压：MINIOS_TERM_OUTPUT_LIMIT，默认 1MiB，非法值 fail-fast（与限流配置同规格）。
        let term_output_limit = match parse_term_output_limit() {
            Ok(v) => v,
            Err(msg) => {
                eprintln!("配置错误：{}", msg);
                std::process::exit(2);
            }
        };

        Config {
            data_dir,
            port,
            database_path,
            static_dir,
            upload_max_bytes,
            shutdown_timeout_secs,
            session_ttl_secs,
            session_sliding,
            login_rps: login_limit.rps,
            login_burst: login_limit.burst,
            share_read_rps: share_limit.rps,
            share_read_burst: share_limit.burst,
            share_ratelimit_enabled: share_limit.enabled,
            term_output_limit,
        }
    }
}

/// 解析终端输出上限：缺失时默认 1MiB；空串/非数字/0 视为非法。
/// 纯函数（方便单测），from_env 用 env 读取后调它。
fn parse_term_output_limit_raw(raw: Option<&str>) -> Result<u64, String> {
    match raw {
        None => Ok(1024 * 1024),
        Some(s) => {
            let v: u64 = s.trim().parse().map_err(|_| {
                format!(
                    "MINIOS_TERM_OUTPUT_LIMIT 非法：{:?}，必须是正整数（字节）",
                    s
                )
            })?;
            if v == 0 {
                return Err("MINIOS_TERM_OUTPUT_LIMIT 非法：不能为 0".to_string());
            }
            Ok(v)
        }
    }
}
/// 从环境变量读取终端输出上限。
fn parse_term_output_limit() -> Result<u64, String> {
    parse_term_output_limit_raw(std::env::var("MINIOS_TERM_OUTPUT_LIMIT").ok().as_deref())
}

fn compute_data_dir() -> String {
    if let Ok(dir) = std::env::var("MINIOS_DATA_DIR") {
        if !dir.trim().is_empty() {
            return dir;
        }
    }
    if let Ok(db) = std::env::var("DATABASE_PATH") {
        if let Some(parent) = std::path::Path::new(&db).parent() {
            if !parent.as_os_str().is_empty() {
                return parent.to_string_lossy().to_string();
            }
        }
    }
    "data".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn term_output_limit_default() {
        assert_eq!(parse_term_output_limit_raw(None).unwrap(), 1024 * 1024);
    }

    #[test]
    fn term_output_limit_valid() {
        assert_eq!(parse_term_output_limit_raw(Some("65536")).unwrap(), 65536);
        assert_eq!(parse_term_output_limit_raw(Some("  2048  ")).unwrap(), 2048);
    }

    #[test]
    fn term_output_limit_invalid() {
        assert!(parse_term_output_limit_raw(Some("")).is_err());
        assert!(parse_term_output_limit_raw(Some("0")).is_err());
        assert!(parse_term_output_limit_raw(Some("abc")).is_err());
        assert!(parse_term_output_limit_raw(Some("-5")).is_err());
    }
}
