// src/lib.rs
pub mod auth;
pub mod config;
pub mod db;
pub mod handlers;
pub mod log;
pub mod metrics;
pub mod migrate;
pub mod models;
pub mod ratelimit;

use std::sync::{Arc, Mutex};

use axum::{
    extract::{DefaultBodyLimit, State},
    routing::{get, post, Router},
};
use tower_http::{
    cors::CorsLayer,
    services::{ServeDir, ServeFile},
};

/// 应用共享状态：数据库连接 + 静态资源目录 + 上传大小上限 + session 有效期 + 指标集合 + 登录限流器
pub struct AppState {
    pub db: Mutex<rusqlite::Connection>,
    pub static_dir: String,
    pub max_upload_bytes: u64,
    pub session_ttl_secs: u64,
    pub metrics: Arc<crate::metrics::Metrics>,
    /// 登录限流器（IP + 账号双维度令牌桶）
    pub login_limiter: Arc<crate::ratelimit::RateLimiter>,
}

/// 初始化全局状态（指定上传上限）：打开数据库并做种子数据
pub fn init_state_with(
    database_path: &str,
    static_dir: &str,
    max_upload_bytes: u64,
    session_ttl_secs: u64,
    login_rps: f64,
    login_burst: u64,
) -> Arc<AppState> {
    let conn = crate::db::open_db(database_path).expect("open_db failed");
    crate::db::seed(&conn).expect("seed failed");
    let limiter_cfg = crate::ratelimit::LoginLimitConfig {
        rps: login_rps,
        burst: login_burst,
    };
    Arc::new(AppState {
        db: Mutex::new(conn),
        static_dir: static_dir.to_string(),
        max_upload_bytes,
        session_ttl_secs,
        metrics: Arc::new(crate::metrics::Metrics::new()),
        login_limiter: Arc::new(crate::ratelimit::RateLimiter::new(&limiter_cfg)),
    })
}

/// 初始化全局状态：打开数据库并做种子数据
pub fn init_state(database_path: &str, static_dir: &str) -> Arc<AppState> {
    let cfg = crate::config::Config::from_env();
    init_state_with(
        database_path,
        static_dir,
        cfg.upload_max_bytes,
        cfg.session_ttl_secs,
        cfg.login_rps,
        cfg.login_burst,
    )
}

/// 构建路由
/// 无需登录的公开路径。
fn is_public_path(path: &str) -> bool {
    matches!(
        path,
        "/api/health"
            | "/api/readyz"
            | "/metrics"
            | "/api/auth/register"
            | "/api/auth/login"
            | "/api/auth/logout"
            | "/api/auth/setup-needed"
    ) || path.starts_with("/api/s/")
}

/// 鉴权中间件：除公开路径外，要求有效 session；通过则注入 CurrentUser 扩展。
async fn auth_middleware(
    State(state): State<Arc<AppState>>,
    req: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    use axum::response::IntoResponse;

    if is_public_path(req.uri().path()) {
        return next.run(req).await;
    }

    let cookie = req
        .headers()
        .get(axum::http::header::COOKIE)
        .and_then(|v| v.to_str().ok());

    let user = match crate::auth::extract_session_token(cookie) {
        Some(token) => {
            let conn = match state.db.lock() {
                Ok(c) => c,
                Err(_) => {
                    return (
                        axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                        axum::Json(serde_json::json!({"error": "数据库锁不可用"})),
                    )
                        .into_response();
                }
            };
            match crate::auth::verify_session(&conn, &token) {
                Ok(Some(u)) => u,
                Ok(None) => {
                    return (
                        axum::http::StatusCode::UNAUTHORIZED,
                        axum::Json(serde_json::json!({"error": "未登录"})),
                    )
                        .into_response();
                }
                Err(e) => {
                    return (
                        axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                        axum::Json(serde_json::json!({"error": e})),
                    )
                        .into_response();
                }
            }
        }
        None => {
            return (
                axum::http::StatusCode::UNAUTHORIZED,
                axum::Json(serde_json::json!({"error": "未登录"})),
            )
                .into_response();
        }
    };

    let mut req = req;
    req.extensions_mut().insert(user);
    next.run(req).await
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
        .route("/api/auth/register", post(handlers::register))
        .route(
            "/api/auth/login",
            post(handlers::login).route_layer(axum::middleware::from_fn_with_state(
                state.clone(),
                crate::ratelimit::login_ratelimit_middleware,
            )),
        )
        .route("/api/auth/logout", post(handlers::logout))
        .route("/api/auth/migrate-legacy", post(handlers::migrate_legacy))
        .route("/api/me", get(handlers::me))
        .route("/api/auth/setup-needed", get(handlers::setup_needed))
        .route("/api/shares", post(handlers::create_share))
        .route("/api/s/:token", get(handlers::get_share))
        .route("/api/s/:token/download", get(handlers::download_share))
        // route_layer 只包装已注册路由，必须在所有 .route() 之后、fallback_service 之前，
        // 这样中间件在路由匹配之后执行，才能拿到 MatchedPath。
        .route_layer(axum::middleware::from_fn_with_state(
            metrics,
            crate::metrics::metrics_middleware,
        ))
        // auth 中间件在 metrics 之后（更外层）：未登录的 401 请求不计入 metrics。
        .route_layer(axum::middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .fallback_service(serve_dir)
        .layer(axum::middleware::from_fn(
            crate::log::request_log_middleware,
        ))
        .layer(CorsLayer::permissive())
        .with_state(state)
}
