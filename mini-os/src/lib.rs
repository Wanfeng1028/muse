// src/lib.rs
pub mod config;
pub mod db;
pub mod handlers;
pub mod log;
pub mod metrics;
pub mod migrate;
pub mod models;

use std::sync::{Arc, Mutex};

use axum::{
    extract::DefaultBodyLimit,
    routing::{get, post, Router},
};
use tower_http::{
    cors::CorsLayer,
    services::{ServeDir, ServeFile},
};

/// 应用共享状态：数据库连接 + 静态资源目录 + 上传大小上限 + 指标集合
pub struct AppState {
    pub db: Mutex<rusqlite::Connection>,
    pub static_dir: String,
    pub max_upload_bytes: u64,
    pub metrics: Arc<crate::metrics::Metrics>,
}

/// 初始化全局状态（指定上传上限）：打开数据库并做种子数据
pub fn init_state_with(
    database_path: &str,
    static_dir: &str,
    max_upload_bytes: u64,
) -> Arc<AppState> {
    let conn = crate::db::open_db(database_path).expect("open_db failed");
    crate::db::seed(&conn).expect("seed failed");
    Arc::new(AppState {
        db: Mutex::new(conn),
        static_dir: static_dir.to_string(),
        max_upload_bytes,
        metrics: Arc::new(crate::metrics::Metrics::new()),
    })
}

/// 初始化全局状态：打开数据库并做种子数据
pub fn init_state(database_path: &str, static_dir: &str) -> Arc<AppState> {
    let max_upload_bytes = crate::config::Config::from_env().upload_max_bytes;
    init_state_with(database_path, static_dir, max_upload_bytes)
}

/// 构建路由
pub fn build_app(state: Arc<AppState>) -> Router {
    let static_dir = state.static_dir.clone();
    let metrics = state.metrics.clone();

    // 静态资源兜底：目录 + index.html fallback
    let serve_dir = ServeDir::new(&static_dir)
        .append_index_html_on_directories(true)
        .fallback(ServeFile::new(format!("{}/index.html", static_dir)));

    Router::new()
        .route("/api/health", get(handlers::health))
        .route("/api/readyz", get(handlers::readyz))
        .route("/api/apps", get(handlers::list_apps))
        .route("/api/fs", get(handlers::list_fs).post(handlers::create_fs))
        .route(
            "/api/fs/:id",
            get(handlers::get_fs)
                .put(handlers::update_fs)
                .delete(handlers::delete_fs),
        )
        .route(
            "/api/settings",
            get(handlers::get_settings).put(handlers::put_setting),
        )
        .route(
            "/api/files/upload",
            post(handlers::upload_file).route_layer(DefaultBodyLimit::disable()),
        )
        .route("/api/files/download", get(handlers::download_file))
        .route("/api/stats", get(handlers::get_stats))
        .route("/ws", get(handlers::ws_handler))
        .route("/metrics", get(crate::metrics::metrics_handler))
        // route_layer 只包装已注册路由，必须在所有 .route() 之后、fallback_service 之前，
        // 这样中间件在路由匹配之后执行，才能拿到 MatchedPath。
        .route_layer(axum::middleware::from_fn_with_state(
            metrics,
            crate::metrics::metrics_middleware,
        ))
        .fallback_service(serve_dir)
        .layer(axum::middleware::from_fn(crate::log::request_log_middleware))
        .layer(CorsLayer::permissive())
        .with_state(state)
}
