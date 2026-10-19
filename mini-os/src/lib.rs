// src/lib.rs
pub mod auth;
pub mod config;
pub mod db;
pub mod handlers;
pub mod log;
pub mod metrics;
pub mod migrate;
pub mod models;
pub mod notes;
pub mod plugins;
pub mod ratelimit;
pub mod rbac;
pub mod terminal;

use std::sync::{Arc, Mutex};

use axum::{
    extract::{DefaultBodyLimit, State},
    routing::{delete, get, patch, post, put, Router},
};

use tower_http::{
    cors::CorsLayer,
    services::{ServeDir, ServeFile},
};

/// 应用共享状态：数据库连接 + 静态资源目录 + 上传大小上限 + session 有效期 + 指标集合 + 登录限流器 + 分享读取限流器
pub struct AppState {
    pub db: Mutex<rusqlite::Connection>,
    pub static_dir: String,
    pub max_upload_bytes: u64,
    pub session_ttl_secs: u64,
    pub metrics: Arc<crate::metrics::Metrics>,
    /// 登录限流器（IP + 账号双维度令牌桶）
    pub login_limiter: Arc<crate::ratelimit::RateLimiter>,
    /// 分享读取限流器（IP 单维度令牌桶，与登录桶解耦）
    pub share_limiter: Arc<crate::ratelimit::ShareReadLimiter>,
    /// 分享读限流总开关，来自 MINIOS_SHARE_RATE_LIMIT_ENABLED
    pub share_ratelimit_enabled: bool,
    /// 插件数据目录，插件安装到 <data_dir>/plugins/<id>/
    pub data_dir: String,
    /// 真 PTY 终端会话管理器（按用户隔离）。
    pub terminals: Arc<crate::terminal::TerminalManager>,
}

/// 解析插件数据目录：MINIOS_DATA_DIR 优先，否则 database_path 的父目录，否则 "data"。
pub fn resolve_data_dir(database_path: &str) -> String {
    if let Ok(dir) = std::env::var("MINIOS_DATA_DIR") {
        if !dir.trim().is_empty() {
            return dir;
        }
    }
    if let Some(parent) = std::path::Path::new(database_path).parent() {
        if !parent.as_os_str().is_empty() {
            return parent.to_string_lossy().to_string();
        }
    }
    "data".to_string()
}

/// 初始化全局状态（完整参数版，含分享读取限流配额与总开关）
///
/// 参数多于 clippy 阈值是刻意的：保持与旧 `init_state_with` 的位置参数风格一致，
/// 调用方（测试）按顺序传参可读性更好。
#[allow(clippy::too_many_arguments)]
pub fn init_state_with_full(
    database_path: &str,
    static_dir: &str,
    max_upload_bytes: u64,
    session_ttl_secs: u64,
    login_rps: f64,
    login_burst: u64,
    share_read_rps: f64,
    share_read_burst: u64,
    share_ratelimit_enabled: bool,
) -> Arc<AppState> {
    let conn = crate::db::open_db(database_path).expect("open_db failed");
    crate::db::seed(&conn).expect("seed failed");
    let limiter_cfg = crate::ratelimit::LoginLimitConfig {
        rps: login_rps,
        burst: login_burst,
    };
    let share_limiter_cfg = crate::ratelimit::ShareReadLimitConfig {
        rps: share_read_rps,
        burst: share_read_burst,
        enabled: share_ratelimit_enabled,
    };
    let data_dir = resolve_data_dir(database_path);
    let terminals = Arc::new(crate::terminal::TerminalManager::new(
        data_dir.clone(),
        8,
        1800,
    ));
    terminals.spawn_reaper();
    Arc::new(AppState {
        db: Mutex::new(conn),
        static_dir: static_dir.to_string(),
        max_upload_bytes,
        session_ttl_secs,
        metrics: Arc::new(crate::metrics::Metrics::new()),
        login_limiter: Arc::new(crate::ratelimit::RateLimiter::new(&limiter_cfg)),
        share_limiter: Arc::new(crate::ratelimit::ShareReadLimiter::new(&share_limiter_cfg)),
        share_ratelimit_enabled,
        data_dir,
        terminals,
    })
}

/// 初始化全局状态（指定上传上限）：打开数据库并做种子数据
/// 分享读取限流配额取环境变量默认值（MINIOS_SHARE_RPS/_BURST/_ENABLED），非法则启动失败。
pub fn init_state_with(
    database_path: &str,
    static_dir: &str,
    max_upload_bytes: u64,
    session_ttl_secs: u64,
    login_rps: f64,
    login_burst: u64,
) -> Arc<AppState> {
    let share_limit = crate::ratelimit::parse_share_limit().expect("parse_share_limit failed");
    init_state_with_full(
        database_path,
        static_dir,
        max_upload_bytes,
        session_ttl_secs,
        login_rps,
        login_burst,
        share_limit.rps,
        share_limit.burst,
        share_limit.enabled,
    )
}

/// 初始化全局状态：打开数据库并做种子数据
pub fn init_state(database_path: &str, static_dir: &str) -> Arc<AppState> {
    let cfg = crate::config::Config::from_env();
    init_state_with_full(
        database_path,
        static_dir,
        cfg.upload_max_bytes,
        cfg.session_ttl_secs,
        cfg.login_rps,
        cfg.login_burst,
        cfg.share_read_rps,
        cfg.share_read_burst,
        cfg.share_ratelimit_enabled,
    )
}

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
            | "/api/share/list"
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

/// 根据 HTTP 方法与匹配到的路由路径，返回该请求所需的 RBAC 权限。
/// 返回 None 表示仅要求登录（或未知路径，由路由层负责 404）。
fn required_permission(
    method: &axum::http::Method,
    matched_path: &str,
) -> Option<crate::rbac::Permission> {
    use crate::rbac::Permission;
    use axum::http::Method;
    match (method, matched_path) {
        (&Method::GET, "/api/fs")
        | (&Method::GET, "/api/fs/search")
        | (&Method::GET, "/api/fs/:id")
        | (&Method::GET, "/api/files/download")
        | (&Method::GET, "/api/settings")
        | (&Method::PUT, "/api/settings")
        | (&Method::GET, "/api/stats") => Some(Permission::FsRead),
        (&Method::POST, "/api/fs")
        | (&Method::PUT, "/api/fs/:id")
        | (&Method::DELETE, "/api/fs/:id")
        | (&Method::PATCH, "/api/fs/:id/move")
        | (&Method::POST, "/api/files/upload") => Some(Permission::FsWrite),
        (&Method::GET, "/api/notes") | (&Method::GET, "/api/events") => Some(Permission::NotesRead),
        (&Method::POST, "/api/notes")
        | (&Method::PUT, "/api/notes/:id")
        | (&Method::DELETE, "/api/notes/:id")
        | (&Method::POST, "/api/events")
        | (&Method::PUT, "/api/events/:id")
        | (&Method::DELETE, "/api/events/:id") => Some(Permission::NotesWrite),
        (&Method::GET, "/api/plugins") => Some(Permission::FsRead),
        (&Method::POST, "/api/plugins/preview")
        | (&Method::POST, "/api/plugins/install")
        | (&Method::DELETE, "/api/plugins/:id") => Some(Permission::PluginManage),
        (&Method::POST, "/api/shares") => Some(Permission::ShareCreate),
        (&Method::GET, "/api/shares") | (&Method::DELETE, "/api/shares/:id") => {
            Some(Permission::ShareManage)
        }
        (&Method::GET, "/api/users") | (&Method::PUT, "/api/users/:id/role") => {
            Some(Permission::UsersManage)
        }
        _ => None,
    }
}

/// RBAC 鉴权中间件：在 auth 之后执行（依赖 CurrentUser 扩展），在 metrics 之前执行。
/// 未知角色字符串 fail-closed 视为 Viewer。
async fn rbac_middleware(
    req: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    use axum::response::IntoResponse;

    if is_public_path(req.uri().path()) {
        return next.run(req).await;
    }

    let user = match req.extensions().get::<crate::auth::CurrentUser>() {
        Some(u) => u.clone(),
        None => {
            return (
                axum::http::StatusCode::UNAUTHORIZED,
                axum::Json(serde_json::json!({"error": "未登录"})),
            )
                .into_response();
        }
    };

    let role = crate::rbac::Role::parse(&user.role).unwrap_or(crate::rbac::Role::Viewer);

    let matched_path = req
        .extensions()
        .get::<axum::extract::MatchedPath>()
        .map(|m| m.as_str().to_string())
        .unwrap_or_default();

    if let Some(perm) = required_permission(req.method(), &matched_path) {
        if let Err(reason) = crate::rbac::require(&role, &perm) {
            return (
                axum::http::StatusCode::FORBIDDEN,
                axum::Json(serde_json::json!({"error": "权限不足", "reason": reason})),
            )
                .into_response();
        }
    }

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
        .route("/api/fs/search", get(handlers::search_fs))
        .route(
            "/api/notes",
            get(notes::list_notes).post(notes::create_note),
        )
        .route(
            "/api/notes/:id",
            put(notes::update_note).delete(notes::delete_note),
        )
        .route(
            "/api/events",
            get(notes::list_events).post(notes::create_event),
        )
        .route(
            "/api/events/:id",
            put(notes::update_event).delete(notes::delete_event),
        )
        .route(
            "/api/fs/:id",
            get(handlers::get_fs)
                .put(handlers::update_fs)
                .delete(handlers::delete_fs),
        )
        .route("/api/fs/:id/move", patch(handlers::move_fs))
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
        .route("/api/users", get(handlers::list_users))
        .route("/api/users/:id/role", put(handlers::set_user_role))
        .route("/api/plugins", get(handlers::list_plugins))
        .route("/api/plugins/preview", post(handlers::preview_plugin))
        .route("/api/plugins/install", post(handlers::install_plugin))
        .route("/api/plugins/:id", delete(handlers::uninstall_plugin))
        .route(
            "/api/shares",
            post(handlers::create_share).get(handlers::list_shares),
        )
        .route("/api/shares/:id", delete(handlers::delete_share))
        .route("/api/shares/token/:token", delete(handlers::revoke_share))
        .route(
            "/api/s/:token",
            get(handlers::get_share).route_layer(axum::middleware::from_fn_with_state(
                state.clone(),
                crate::ratelimit::share_ratelimit_middleware,
            )),
        )
        .route(
            "/api/s/:token/download",
            get(handlers::download_share).route_layer(axum::middleware::from_fn_with_state(
                state.clone(),
                crate::ratelimit::share_ratelimit_middleware,
            )),
        )
        .route(
            "/api/share/list",
            get(handlers::list_share).route_layer(axum::middleware::from_fn_with_state(
                state.clone(),
                crate::ratelimit::share_ratelimit_middleware,
            )),
        )
        // route_layer 只包装已注册路由，必须在所有 .route() 之后、fallback_service 之前，
        // 这样中间件在路由匹配之后执行，才能拿到 MatchedPath。
        //
        // 三层 route_layer 的执行顺序（后挂载=更外层=先执行）：
        //   1) auth（最外层，先执行）：注入 CurrentUser 扩展；
        //   2) rbac（中间层）：基于 CurrentUser.role 做权限校验；
        //   3) metrics（最内层，最后执行）：仅统计已通过鉴权/授权的请求。
        // 这样 401（未登录）与 403（权限不足）都不会计入 metrics。
        .route_layer(axum::middleware::from_fn_with_state(
            metrics,
            crate::metrics::metrics_middleware,
        ))
        .route_layer(axum::middleware::from_fn(rbac_middleware))
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
