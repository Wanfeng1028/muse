// src/lib.rs
pub mod config;
pub mod db;
pub mod handlers;
pub mod models;

use std::sync::{Arc, Mutex};

use axum::{
    routing::{get, Router},
};
use tower_http::{cors::CorsLayer, services::{ServeDir, ServeFile}};

/// 应用共享状态：数据库连接 + 静态资源目录
pub struct AppState {
    pub db: Mutex<rusqlite::Connection>,
    pub static_dir: String,
}

/// 初始化全局状态：打开数据库并做种子数据
pub fn init_state(database_path: &str, static_dir: &str) -> Arc<AppState> {
    let conn = crate::db::open_db(database_path).expect("open_db failed");
    crate::db::seed(&conn).expect("seed failed");
    Arc::new(AppState {
        db: Mutex::new(conn),
        static_dir: static_dir.to_string(),
    })
}

/// 构建路由
pub fn build_app(state: Arc<AppState>) -> Router {
    let static_dir = state.static_dir.clone();

    // 静态资源兜底：目录 + index.html fallback
    let serve_dir = ServeDir::new(&static_dir)
        .append_index_html_on_directories(true)
        .fallback(ServeFile::new(format!("{}/index.html", static_dir)));

    Router::new()
        .route("/api/health", get(handlers::health))
        .route("/api/apps", get(handlers::list_apps))
        .route(
            "/api/fs",
            get(handlers::list_fs).post(handlers::create_fs),
        )
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
        .route("/api/stats", get(handlers::get_stats))
        .route("/ws", get(handlers::ws_handler))
        .fallback_service(serve_dir)
        .layer(CorsLayer::permissive())
        .with_state(state)
}
