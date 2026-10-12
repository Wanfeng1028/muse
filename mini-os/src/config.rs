use std::env;

/// 应用配置
#[derive(Debug, Clone)]
pub struct Config {
    pub port: u16,
    pub database_path: String,
    pub static_dir: String,
}

impl Config {
    /// 从环境变量读取配置，缺失或解析失败时使用默认值
    pub fn from_env() -> Self {
        let port = env::var("PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(8090);

        let database_path = env::var("DATABASE_PATH").unwrap_or_else(|_| "data/mini-os.db".to_string());

        let static_dir = env::var("STATIC_DIR").unwrap_or_else(|_| "static".to_string());

        Config {
            port,
            database_path,
            static_dir,
        }
    }
}
