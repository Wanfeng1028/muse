use std::env;

/// 应用配置
#[derive(Debug, Clone)]
pub struct Config {
    pub port: u16,
    pub database_path: String,
    pub static_dir: String,
    pub upload_max_bytes: u64,
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

        Config {
            port,
            database_path,
            static_dir,
            upload_max_bytes,
        }
    }
}
