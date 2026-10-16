use std::env;

/// 应用配置
#[derive(Debug, Clone)]
pub struct Config {
    pub port: u16,
    pub database_path: String,
    pub static_dir: String,
    pub upload_max_bytes: u64,
    pub shutdown_timeout_secs: u64,
    pub session_ttl_secs: u64,
    /// 登录限流：每秒补充的令牌数（来自 MINIOS_LOGIN_RPS）
    pub login_rps: f64,
    /// 登录限流：桶容量/突发上限（来自 MINIOS_LOGIN_BURST）
    pub login_burst: u64,
}

impl Config {
    /// 从环境变量读取配置，缺失或解析失败时使用默认值
    pub fn from_env() -> Self {
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

        // 登录限流配置：非法值 fail-fast（启动即报错退出），符合规格 S3。
        // 注意 from_env 的签名是 -> Self（非 Result），因此这里直接 eprintln + exit(2)。
        let login_limit = match crate::ratelimit::parse_login_limit() {
            Ok(cfg) => cfg,
            Err(msg) => {
                eprintln!("配置错误：{}", msg);
                std::process::exit(2);
            }
        };

        Config {
            port,
            database_path,
            static_dir,
            upload_max_bytes,
            shutdown_timeout_secs,
            session_ttl_secs,
            login_rps: login_limit.rps,
            login_burst: login_limit.burst,
        }
    }
}
