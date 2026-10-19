//! HTTP 处理器与 WebSocket，包含全部 /api 路由实现。

use std::sync::Arc;

use axum::{
    body::{Body, Bytes},
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Extension, Multipart, Path, Query, State,
    },
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use futures_util::stream;
use rusqlite::{params, OptionalExtension};
use serde::Deserialize;
use serde_json::json;

use crate::auth;
use crate::metrics::Metrics;
use crate::models::{
    AppInfo, CreateNodeRequest, CreateShareRequest, LoginRequest, Node, RegisterRequest,
    SetRoleRequest, SettingRequest, ShareAdminItem, ShareCreated, ShareDirEntry, ShareDirListing,
    ShareInfo, Stats, UpdateNodeRequest, UserInfo, UserWithRole,
};
use crate::plugins;
use crate::AppState;
use rand::TryRngCore;

/// 统一的 API 返回类型别名
type ApiResult = Result<Response, (StatusCode, Json<serde_json::Value>)>;

fn plain_err(status: StatusCode, msg: &str) -> Response {
    (status, msg.to_string()).into_response()
}

/// GET /api/plugins：列出已安装插件。
pub async fn list_plugins(State(state): State<Arc<AppState>>) -> Response {
    match plugins::list_installed(std::path::Path::new(&state.data_dir)) {
        Ok(items) => Json(items).into_response(),
        Err(e) => plain_err(StatusCode::INTERNAL_SERVER_ERROR, &e),
    }
}

/// POST /api/plugins/preview：只解析校验 multipart 上传的 zip，不写盘。
pub async fn preview_plugin(mut multipart: Multipart) -> Response {
    let mut zip_bytes: Option<Vec<u8>> = None;
    loop {
        let field = match multipart.next_field().await {
            Ok(Some(f)) => f,
            Ok(None) => break,
            Err(_) => return plain_err(StatusCode::BAD_REQUEST, "缺少文件字段"),
        };
        if field.name() != Some("file") {
            continue;
        }
        let mut buf: Vec<u8> = Vec::new();
        let mut field = field;
        loop {
            match field.chunk().await {
                Ok(Some(chunk)) => buf.extend_from_slice(&chunk),
                Ok(None) => break,
                Err(_) => return plain_err(StatusCode::BAD_REQUEST, "缺少文件字段"),
            }
        }
        zip_bytes = Some(buf);
        break;
    }
    let bytes = match zip_bytes {
        Some(b) => b,
        None => return plain_err(StatusCode::BAD_REQUEST, "缺少文件字段"),
    };
    match plugins::preview_from_zip(&bytes) {
        Ok(m) => Json(m).into_response(),
        Err(e) => plain_err(StatusCode::BAD_REQUEST, &e),
    }
}

/// POST /api/plugins/install：安装 multipart 上传的 zip。
pub async fn install_plugin(
    State(state): State<Arc<AppState>>,
    mut multipart: Multipart,
) -> Response {
    let mut zip_bytes: Option<Vec<u8>> = None;
    loop {
        let field = match multipart.next_field().await {
            Ok(Some(f)) => f,
            Ok(None) => break,
            Err(_) => return plain_err(StatusCode::BAD_REQUEST, "缺少文件字段"),
        };
        if field.name() != Some("file") {
            continue;
        }
        let mut buf: Vec<u8> = Vec::new();
        let mut field = field;
        loop {
            match field.chunk().await {
                Ok(Some(chunk)) => buf.extend_from_slice(&chunk),
                Ok(None) => break,
                Err(_) => return plain_err(StatusCode::BAD_REQUEST, "缺少文件字段"),
            }
        }
        zip_bytes = Some(buf);
        break;
    }
    let bytes = match zip_bytes {
        Some(b) => b,
        None => return plain_err(StatusCode::BAD_REQUEST, "缺少文件字段"),
    };
    match plugins::install_from_zip(&bytes, std::path::Path::new(&state.data_dir)) {
        Ok(m) => Json(m).into_response(),
        Err(e) => plain_err(StatusCode::BAD_REQUEST, &e),
    }
}

/// DELETE /api/plugins/:id：卸载插件。
pub async fn uninstall_plugin(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
) -> Response {
    match plugins::uninstall(&id, std::path::Path::new(&state.data_dir)) {
        Ok(()) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => {
            let status = if e.contains("未安装") {
                StatusCode::NOT_FOUND
            } else {
                StatusCode::BAD_REQUEST
            };
            plain_err(status, &e)
        }
    }
}

/// 上传接口查询参数
#[derive(Deserialize)]
pub struct UploadQuery {
    pub path: Option<String>,
}

/// 魔数嗅探：返回 (mime, is_executable)。无法识别返回 None。
fn sniff_mime(bytes: &[u8]) -> Option<(&'static str, bool)> {
    if bytes.starts_with(&[0x4D, 0x5A]) {
        return Some(("application/x-msdownload", true));
    }
    if bytes.starts_with(&[0x7F, 0x45, 0x4C, 0x46]) {
        return Some(("application/x-elf", true));
    }
    if bytes.starts_with(&[0xFE, 0xED, 0xFA, 0xCE])
        || bytes.starts_with(&[0xCE, 0xFA, 0xED, 0xFE])
        || bytes.starts_with(&[0xFE, 0xED, 0xFA, 0xCF])
        || bytes.starts_with(&[0xCF, 0xFA, 0xED, 0xFE])
        || bytes.starts_with(&[0xCA, 0xFE, 0xBA, 0xBE])
    {
        return Some(("application/x-mach-binary", true));
    }
    if bytes.starts_with(&[0xD0, 0xCF, 0x11, 0xE0]) {
        return Some(("application/x-ole-storage", true));
    }
    if bytes.starts_with(&[0x23, 0x21]) {
        return Some(("text/x-shellscript", true));
    }
    if bytes.starts_with(&[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) {
        return Some(("image/png", false));
    }
    if bytes.starts_with(&[0xFF, 0xD8, 0xFF]) {
        return Some(("image/jpeg", false));
    }
    if bytes.starts_with(&[0x47, 0x49, 0x46, 0x38]) {
        return Some(("image/gif", false));
    }
    if bytes.starts_with(&[0x25, 0x50, 0x44, 0x46]) {
        return Some(("application/pdf", false));
    }
    if bytes.starts_with(&[0x50, 0x4B, 0x03, 0x04]) {
        return Some(("application/zip", false));
    }
    None
}

/// 下载接口查询参数
#[derive(Deserialize)]
pub struct DownloadQuery {
    pub path: Option<String>,
}

/// 文件名消毒：拒绝非法字符、控制字符、"."/".."、过长名称
fn sanitize_filename(name: &str) -> Result<String, &'static str> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("文件名不能为空");
    }
    if trimmed.contains('/') || trimmed.contains('\\') || trimmed.contains('\0') {
        return Err("文件名含非法字符");
    }
    if trimmed == "." || trimmed == ".." {
        return Err("非法文件名");
    }
    if trimmed.chars().any(|c| c.is_control()) {
        return Err("文件名含非法字符");
    }
    if trimmed.chars().count() > 200 {
        return Err("文件名过长");
    }
    Ok(trimmed.to_string())
}

/// 把路径解析为文件夹节点 id。None/""/" /" 表示根目录（返回 Ok(None)）。
fn resolve_folder_id(
    conn: &rusqlite::Connection,
    path: Option<&str>,
    user_id: i64,
) -> Result<Option<i64>, &'static str> {
    let raw = match path {
        None => return Ok(None),
        Some(s) => s,
    };
    let trimmed = raw.trim();
    if trimmed.is_empty() || trimmed == "/" {
        return Ok(None);
    }

    let stripped = trimmed.trim_matches('/');
    if stripped.is_empty() {
        return Ok(None);
    }

    let mut parent: Option<i64> = None;
    for seg in stripped.split('/') {
        let seg_trimmed = seg.trim();
        if seg_trimmed.is_empty() || seg_trimmed == "." || seg_trimmed == ".." {
            return Err("非法路径");
        }
        if seg_trimmed.chars().any(|c| c.is_control()) {
            return Err("非法路径");
        }

        let found: Option<i64> = if parent.is_none() {
            conn.query_row(
                "SELECT id FROM vfs_nodes WHERE parent_id IS NULL AND name = ?1 AND kind = 'folder' AND user_id = ?2",
                params![seg_trimmed, user_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(|_| "目录不存在或不是文件夹")?
        } else {
            conn.query_row(
                "SELECT id FROM vfs_nodes WHERE parent_id = ?2 AND name = ?1 AND kind = 'folder' AND user_id = ?3",
                params![seg_trimmed, parent, user_id],
                |row| row.get(0),
            )
            .optional()
            .map_err(|_| "目录不存在或不是文件夹")?
        };

        match found {
            Some(id) => parent = Some(id),
            None => return Err("目录不存在或不是文件夹"),
        }
    }

    Ok(parent)
}

/// percent 编码：保留 [A-Za-z0-9._~-]，其余字节转 %XX 大写
fn percent_encode(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for &b in input.as_bytes() {
        let keep = matches!(b, b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'.' | b'_' | b'~' | b'-');
        if keep {
            out.push(b as char);
        } else {
            out.push('%');
            out.push_str(&format!("{:02X}", b));
        }
    }
    out
}

/// 构造错误响应。
fn err(status: StatusCode, msg: &str) -> (StatusCode, Json<serde_json::Value>) {
    (status, Json(json!({ "error": msg })))
}

/// 构造带 reason 的错误响应：{"error":..., "reason":...}，用于 403 权限拒绝。
fn err_reason(
    status: StatusCode,
    msg: &str,
    reason: &str,
) -> (StatusCode, Json<serde_json::Value>) {
    (status, Json(json!({ "error": msg, "reason": reason })))
}

/// 应用注册表：返回 5 个内置应用。
pub fn apps_registry() -> Vec<AppInfo> {
    vec![
        AppInfo {
            id: "files".to_string(),
            name: "文件管理器".to_string(),
            icon: "📁".to_string(),
            description: "浏览与管理虚拟文件系统".to_string(),
        },
        AppInfo {
            id: "editor".to_string(),
            name: "文本编辑器".to_string(),
            icon: "📝".to_string(),
            description: "创建与编辑文本文件".to_string(),
        },
        AppInfo {
            id: "terminal".to_string(),
            name: "终端".to_string(),
            icon: "🖥️".to_string(),
            description: "简易命令行界面".to_string(),
        },
        AppInfo {
            id: "settings".to_string(),
            name: "设置".to_string(),
            icon: "⚙️".to_string(),
            description: "主题与壁纸设置".to_string(),
        },
        AppInfo {
            id: "about".to_string(),
            name: "关于".to_string(),
            icon: "ℹ️".to_string(),
            description: "系统信息与统计".to_string(),
        },
        AppInfo {
            id: "users".to_string(),
            name: "用户与权限".to_string(),
            icon: "<svg viewBox=\"0 0 24 24\" width=\"24\" height=\"24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 3l7 3v6c0 4.2-2.9 7.5-7 9-4.1-1.5-7-4.8-7-9V6l7-3z\"/><circle cx=\"12\" cy=\"10\" r=\"2.2\"/><path d=\"M8.2 16.4c.7-1.6 2.1-2.5 3.8-2.5s3.1.9 3.8 2.5\"/></svg>".to_string(),
            description: "查看用户列表、调整角色、读懂权限规则".to_string(),
        },
    ]
}

/// GET /api/fs 查询参数。
#[derive(Deserialize)]
pub struct FsQuery {
    pub parent_id: Option<i64>,
}

/// GET /api/health
pub async fn health() -> impl IntoResponse {
    Json(json!({ "status": "ok", "version": env!("CARGO_PKG_VERSION") }))
}

/// GET /api/readyz：就绪探针。DB 真实可查（schema_migrations 表）返回 200，否则 503。
pub async fn readyz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let ok = state
        .db
        .lock()
        .map(|conn| {
            conn.query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
                row.get::<_, i64>(0)
            })
            .is_ok()
        })
        .unwrap_or(false);
    if ok {
        (StatusCode::OK, Json(json!({ "status": "ready" })))
    } else {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "status": "not_ready" })),
        )
    }
}

/// GET /api/apps
pub async fn list_apps() -> impl IntoResponse {
    Json(apps_registry())
}

/// 从行构造 Node。
/// 列顺序固定：id, parent_id, name, kind, content, created_at, updated_at, size, mime_type
fn row_to_node(row: &rusqlite::Row) -> rusqlite::Result<Node> {
    Ok(Node {
        id: row.get(0)?,
        parent_id: row.get(1)?,
        name: row.get(2)?,
        kind: row.get(3)?,
        content: row.get(4)?,
        created_at: row.get(5)?,
        updated_at: row.get(6)?,
        size: row.get(7)?,
        mime_type: row.get(8)?,
    })
}

/// GET /api/fs?parent_id=...
pub async fn list_fs(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Query(q): Query<FsQuery>,
) -> ApiResult {
    // 锁中毒直接 unwrap（进程内简单互斥，不做恢复）
    let conn = state.db.lock().unwrap();

    // 文件夹优先，再按名称升序
    let mut nodes: Vec<Node> = Vec::new();

    if let Some(pid) = q.parent_id {
        let mut stmt = conn
            .prepare(
                "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
                 CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
                 mime_type \
                 FROM vfs_nodes WHERE parent_id = ?1 AND user_id = ?2 \
                 ORDER BY CASE kind WHEN 'folder' THEN 0 ELSE 1 END, name ASC",
            )


            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map(params![pid, user.id], row_to_node)
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        for r in rows {
            nodes.push(r.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?);
        }
    } else {
        let mut stmt = conn
            .prepare(
                "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
                 CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
                 mime_type \
                 FROM vfs_nodes WHERE parent_id IS NULL AND user_id = ?1 \
                 ORDER BY CASE kind WHEN 'folder' THEN 0 ELSE 1 END, name ASC",
            )


            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map(params![user.id], row_to_node)
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        for r in rows {
            nodes.push(r.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?);
        }
    }

    state.metrics.inc_vfs("read");
    Ok(Json(nodes).into_response())
}

/// GET /api/fs/{id}
pub async fn get_fs(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Path(id): Path<i64>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
             CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
             mime_type \
             FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",
            params![id, user.id],
            row_to_node,
        )
        .optional()


        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    match node {
        Some(n) => {
            state.metrics.inc_vfs("read");
            Ok(Json(n).into_response())
        }
        None => Err(err(StatusCode::NOT_FOUND, "节点不存在")),
    }
}

/// POST /api/fs
pub async fn create_fs(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Json(req): Json<CreateNodeRequest>,
) -> ApiResult {
    // 校验名称
    let name = req.name.trim();
    if name.is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "名称不能为空"));
    }
    // 校验 kind
    if req.kind != "file" && req.kind != "folder" {
        return Err(err(StatusCode::BAD_REQUEST, "kind 必须为 file 或 folder"));
    }
    // 内容：bytes（二进制数组）优先存入 content_blob；否则用 content 文本。
    let (content, content_blob): (String, Option<Vec<u8>>) = match req.bytes {
        Some(b) => (String::new(), Some(b)),
        None => (req.content.unwrap_or_default(), None),
    };

    let conn = state.db.lock().unwrap();

    // 父节点：parent_id 优先；否则按 parent 路径解析。
    let parent_id: Option<i64> = if req.parent_id.is_some() {
        req.parent_id
    } else if let Some(p) = req.parent.as_deref() {
        match resolve_folder_id(&conn, Some(p), user.id) {
            Ok(id) => id,
            Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
        }
    } else {
        None
    };

    // 校验父节点存在且为 folder
    if let Some(pid) = parent_id {
        let parent_kind: Option<String> = conn
            .query_row(
                "SELECT kind FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",
                params![pid, user.id],
                |r| r.get(0),
            )
            .optional()
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        match parent_kind {
            None => return Err(err(StatusCode::NOT_FOUND, "父节点不存在")),
            Some(k) if k != "folder" => {
                return Err(err(StatusCode::BAD_REQUEST, "父节点不是文件夹"))
            }
            _ => {}
        }
    }

    // 同级同名检查：同用户、同父目录下不许重名（文件与文件夹互相冲突）。
    let conflict: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE user_id = ?1 AND parent_id IS ?2 AND name = ?3",
            params![user.id, parent_id, name],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    if conflict > 0 {
        return Err(err(StatusCode::CONFLICT, "同名文件已存在"));
    }

    conn.execute(
        "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content, content_blob) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![user.id, parent_id, name, req.kind, content, content_blob],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let id = conn.last_insert_rowid();
    state.metrics.inc_vfs("create");
    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
             CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
             mime_type \
             FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",


            params![id, user.id],
            row_to_node,
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok((StatusCode::CREATED, Json(node)).into_response())
}

/// PUT /api/fs/{id}
pub async fn update_fs(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Path(id): Path<i64>,
    Json(req): Json<UpdateNodeRequest>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();

    // 确认存在
    let exists: Option<i64> = conn
        .query_row(
            "SELECT id FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",
            params![id, user.id],
            |r| r.get(0),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    if exists.is_none() {
        return Err(err(StatusCode::NOT_FOUND, "节点不存在"));
    }

    // 名称校验（如提供）
    if let Some(n) = &req.name {
        if n.trim().is_empty() {
            return Err(err(StatusCode::BAD_REQUEST, "名称不能为空"));
        }
    }

    // 同级同名检查：重命名时若与同父目录下其他节点重名则冲突。
    if let Some(n) = &req.name {
        let trimmed = n.trim();
        let parent_id: Option<i64> = conn
            .query_row(
                "SELECT parent_id FROM vfs_nodes WHERE id = ?1",
                params![id],
                |r| r.get(0),
            )
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let conflict: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM vfs_nodes WHERE user_id = ?1 AND parent_id IS ?2 AND name = ?3 AND id != ?4",
                params![user.id, parent_id, trimmed, id],
                |r| r.get(0),
            )
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        if conflict > 0 {
            return Err(err(StatusCode::CONFLICT, "同名文件已存在"));
        }
    }

    // 分别更新提供的字段
    if let Some(n) = &req.name {
        conn.execute(
            "UPDATE vfs_nodes SET name = ?1, updated_at = datetime('now') WHERE id = ?2",
            params![n.trim(), id],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    }
    if let Some(c) = &req.content {
        conn.execute(
            "UPDATE vfs_nodes SET content = ?1, updated_at = datetime('now') WHERE id = ?2",
            params![c, id],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    }
    // 即使两个字段都为 None，也刷新一次时间戳以保证语义一致
    if req.name.is_none() && req.content.is_none() {
        conn.execute(
            "UPDATE vfs_nodes SET updated_at = datetime('now') WHERE id = ?1",
            params![id],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    }
    state.metrics.inc_vfs("update");

    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
             CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
             mime_type \
             FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",


            params![id, user.id],
            row_to_node,
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(node).into_response())
}

/// DELETE /api/fs/{id}（级联删除子节点）
pub async fn delete_fs(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Path(id): Path<i64>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let affected = conn
        .execute(
            "DELETE FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",
            params![id, user.id],
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    if affected == 0 {
        return Err(err(StatusCode::NOT_FOUND, "节点不存在"));
    }
    state.metrics.inc_vfs("delete");
    Ok(StatusCode::NO_CONTENT.into_response())
}

/// GET /api/settings -> 键值映射
pub async fn get_settings(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<crate::auth::CurrentUser>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let mut stmt = conn
        .prepare("SELECT key, value FROM settings WHERE user_id = ?1")
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let rows = stmt
        .query_map(params![user.id], |r| {
            let k: String = r.get(0)?;
            let v: String = r.get(1)?;
            Ok((k, v))
        })
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let mut map = serde_json::Map::new();
    for r in rows {
        let (k, v) = r.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        map.insert(k, serde_json::Value::String(v));
    }

    Ok(Json(serde_json::Value::Object(map)).into_response())
}

/// PUT /api/settings（upsert）
pub async fn put_setting(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<crate::auth::CurrentUser>,
    Json(req): Json<SettingRequest>,
) -> ApiResult {
    if req.key.trim().is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "key 不能为空"));
    }
    let conn = state.db.lock().unwrap();
    conn.execute(
        "INSERT INTO settings (user_id, key, value) VALUES (?1, ?2, ?3) \
         ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
        params![user.id, req.key, req.value],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(json!({ "key": req.key, "value": req.value })).into_response())
}

/// GET /api/stats
/// 上传文件：multipart/form-data，字段名固定为 "file"，目标目录由 ?path= 指定
pub async fn upload_file(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Query(q): Query<UploadQuery>,
    mut multipart: Multipart,
) -> ApiResult {
    let mut found_bytes: Option<(String, Option<String>, Vec<u8>)> = None;

    loop {
        let field = match multipart.next_field().await {
            Ok(Some(f)) => f,
            Ok(None) => break,
            Err(_) => return Err(err(StatusCode::BAD_REQUEST, "缺少文件字段")),
        };

        let is_file = field.name() == Some("file");
        let fname_opt = field.file_name().map(|s| s.to_string());
        if !is_file || fname_opt.is_none() {
            continue;
        }

        let fname = fname_opt.unwrap();
        let ctype = field.content_type().map(|m| m.to_string());

        let mut buf: Vec<u8> = Vec::new();
        let mut field = field;
        loop {
            match field.chunk().await {
                Ok(Some(chunk)) => {
                    buf.extend_from_slice(&chunk);
                    if buf.len() as u64 > state.max_upload_bytes {
                        let mb = state.max_upload_bytes / 1024 / 1024;
                        let msg = format!("文件过大，单文件上限为 {} MB", mb);
                        return Err(err(StatusCode::PAYLOAD_TOO_LARGE, &msg));
                    }
                }
                Ok(None) => break,
                Err(_) => return Err(err(StatusCode::BAD_REQUEST, "缺少文件字段")),
            }
        }

        found_bytes = Some((fname, ctype, buf));
        break;
    }

    let (raw_name, ctype, bytes) = match found_bytes {
        Some(v) => v,
        None => return Err(err(StatusCode::BAD_REQUEST, "缺少文件字段")),
    };

    let name = match sanitize_filename(&raw_name) {
        Ok(n) => n,
        Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
    };

    let sniffed = sniff_mime(&bytes);
    if let Some((_, true)) = sniffed {
        return Err(err(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "可执行文件不允许上传",
        ));
    }

    let mime = match sniffed {
        Some((m, _)) => m.to_string(),
        None => match ctype {
            Some(ct) => ct,
            None => mime_guess::from_path(&name)
                .first_or_octet_stream()
                .to_string(),
        },
    };

    let is_utf8 = std::str::from_utf8(&bytes).is_ok();
    let content_text: String = if is_utf8 {
        String::from_utf8_lossy(&bytes).to_string()
    } else {
        String::new()
    };

    let conn = state.db.lock().unwrap();

    let parent_id = match resolve_folder_id(&conn, q.path.as_deref(), user.id) {
        Ok(p) => p,
        Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
    };

    // 同目录同名检查（file 或 folder 任意）
    let exists: Option<i64> = if parent_id.is_none() {
        conn.query_row(
            "SELECT id FROM vfs_nodes WHERE parent_id IS NULL AND name = ?1 AND user_id = ?2",
            params![name, user.id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?
    } else {
        conn.query_row(
            "SELECT id FROM vfs_nodes WHERE parent_id = ?1 AND name = ?2 AND user_id = ?3",
            params![parent_id, name, user.id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?
    };
    if exists.is_some() {
        return Err(err(StatusCode::CONFLICT, "同名文件已存在"));
    }

    // 插入
    let insert_res = if parent_id.is_none() {
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content, content_blob, mime_type) VALUES (?1, NULL, ?2, 'file', ?3, ?4, ?5)",
            params![user.id, name, content_text, bytes, mime],
        )
    } else {
        conn.execute(
            "INSERT INTO vfs_nodes (user_id, parent_id, name, kind, content, content_blob, mime_type) VALUES (?1, ?2, ?3, 'file', ?4, ?5, ?6)",
            params![user.id, parent_id, name, content_text, bytes, mime],
        )
    };
    if insert_res.is_err() {
        return Err(err(StatusCode::INTERNAL_SERVER_ERROR, "写入失败"));
    }
    let new_id = conn.last_insert_rowid();
    state.metrics.inc_vfs("upload");

    let mut stmt = match conn.prepare(
        "SELECT id, parent_id, name, kind, content, created_at, updated_at, CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, mime_type FROM vfs_nodes WHERE id = ?1",
    ) {


        Ok(s) => s,
        Err(_) => return Err(err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败")),
    };

    let node_result: rusqlite::Result<Node> = stmt.query_row(params![new_id], row_to_node);

    match node_result {
        Ok(node) => Ok((StatusCode::CREATED, Json(json!(node))).into_response()),
        Err(_) => Err(err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败")),
    }
}

/// 下载文件：?path= 指定完整文件路径，分块流式返回
/// download_file 内部查询行的类型别名：id, parent_id, name, kind, content, created_at, updated_at, content_blob, mime_type
type FileRow = (
    i64,
    Option<i64>,
    String,
    String,
    String,
    String,
    String,
    Option<Vec<u8>>,
    Option<String>,
);

pub async fn download_file(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Query(q): Query<DownloadQuery>,
) -> ApiResult {
    let raw_path = match q.path.as_deref() {
        Some(p) if !p.trim().is_empty() => p.to_string(),
        _ => return Err(err(StatusCode::BAD_REQUEST, "缺少 path 参数")),
    };

    // 切分路径：最后一段为文件名，其余为目录
    let trimmed = raw_path.trim();
    let stripped = trimmed.trim_matches('/');
    if stripped.is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "缺少 path 参数"));
    }

    let mut segments: Vec<&str> = stripped.split('/').collect();
    let file_seg = segments.pop().unwrap();
    let file_name = match sanitize_filename(file_seg) {
        Ok(n) => n,
        Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
    };

    let dir_path: Option<String> = if segments.is_empty() {
        None
    } else {
        Some(format!("/{}", segments.join("/")))
    };

    let conn = state.db.lock().unwrap();

    let parent_id = match resolve_folder_id(&conn, dir_path.as_deref(), user.id) {
        Ok(p) => p,
        Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
    };

    let query_row: rusqlite::Result<FileRow> = if parent_id.is_none() {
        conn.query_row(
                "SELECT id, parent_id, name, kind, content, created_at, updated_at, content_blob, mime_type FROM vfs_nodes WHERE parent_id IS NULL AND name = ?1 AND user_id = ?2",
                params![file_name, user.id],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                        row.get(6)?,
                        row.get(7)?,
                        row.get(8)?,
                    ))
                },
            )
    } else {
        conn.query_row(
                "SELECT id, parent_id, name, kind, content, created_at, updated_at, content_blob, mime_type FROM vfs_nodes WHERE parent_id = ?1 AND name = ?2 AND user_id = ?3",
                params![parent_id, file_name, user.id],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                        row.get(6)?,
                        row.get(7)?,
                        row.get(8)?,
                    ))
                },
            )
    };

    let (_id, _parent, name, kind, content, _ca, _ua, blob, mime_opt) = match query_row {
        Ok(v) => v,
        Err(rusqlite::Error::QueryReturnedNoRows) => {
            return Err(err(StatusCode::NOT_FOUND, "文件不存在"));
        }
        Err(_) => return Err(err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败")),
    };

    if kind == "folder" {
        return Err(err(StatusCode::BAD_REQUEST, "不能下载目录"));
    }

    let bytes_vec: Vec<u8> = match blob {
        Some(b) => b,
        None => content.into_bytes(),
    };
    let size = bytes_vec.len();

    let mime_str = match mime_opt {
        Some(m) if !m.is_empty() => m,
        _ => mime_guess::from_path(&name)
            .first_or_octet_stream()
            .to_string(),
    };

    // 分块流式
    const CHUNK_SIZE: usize = 65536;
    let mut chunks: Vec<Result<Bytes, std::io::Error>> = Vec::new();
    let mut offset = 0usize;
    while offset < bytes_vec.len() {
        let end = std::cmp::min(offset + CHUNK_SIZE, bytes_vec.len());
        chunks.push(Ok(Bytes::copy_from_slice(&bytes_vec[offset..end])));
        offset = end;
    }
    let body_stream = stream::iter(chunks);

    state.metrics.inc_vfs("download");
    let disposition = format!("attachment; filename*=UTF-8''{}", percent_encode(&name));

    let response = Response::builder()
        .status(StatusCode::OK)
        .header("content-type", mime_str)
        .header("content-disposition", disposition)
        .header("content-length", size.to_string())
        .body(Body::from_stream(body_stream))
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "构造响应失败"))?;

    Ok(response)
}

pub async fn get_stats(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<crate::auth::CurrentUser>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();

    let files: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'file' AND user_id = ?1",
            params![user.id],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let folders: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'folder' AND user_id = ?1",
            params![user.id],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    // 所有文件字节数之和：content_blob 优先，否则 content 文本字节
    let total_bytes: i64 = conn
        .query_row(
            "SELECT COALESCE(SUM(CASE WHEN kind='file' THEN CASE WHEN content_blob IS NOT NULL THEN LENGTH(content_blob) ELSE LENGTH(CAST(content AS BLOB)) END ELSE 0 END), 0) \
             FROM vfs_nodes WHERE user_id = ?1",

            params![user.id],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(Stats {
        files,
        folders,
        total_bytes,
    })
    .into_response())
}

/// GET /ws WebSocket 升级
pub async fn ws_handler(
    State(state): State<Arc<AppState>>,
    ws: WebSocketUpgrade,
) -> impl IntoResponse {
    let metrics = state.metrics.clone();
    ws.on_upgrade(move |socket| handle_socket(socket, metrics))
}

/// Drop guard：确保 WebSocket 退出时连接数一定 -1。
struct WsConnGuard {
    metrics: Arc<Metrics>,
}

impl Drop for WsConnGuard {
    fn drop(&mut self) {
        self.metrics.ws_dec();
    }
}

/// 处理单个 WebSocket 连接。
async fn handle_socket(mut socket: WebSocket, metrics: Arc<Metrics>) {
    metrics.ws_inc();
    // guard 在所有退出路径（return / break / panic 展开）上都触发 ws_dec
    let _guard = WsConnGuard { metrics };

    // 连接成功先发送 hello
    let hello = json!({ "type": "hello", "message": "welcome to mini-os" }).to_string();
    if socket.send(Message::Text(hello)).await.is_err() {
        return;
    }

    // 循环处理文本消息，Close/错误则退出
    while let Some(msg) = socket.recv().await {
        match msg {
            Ok(Message::Text(text)) => {
                let echo = json!({ "type": "echo", "message": text }).to_string();
                if socket.send(Message::Text(echo)).await.is_err() {
                    break;
                }
            }
            Ok(Message::Binary(_)) => {
                // 忽略二进制消息
            }
            Ok(Message::Ping(_)) | Ok(Message::Pong(_)) => {
                // 交给底层自动处理
            }
            Ok(Message::Close(_)) => break,
            Err(_) => break,
        }
    }
}

// ================= v1.3 认证端点 =================

/// POST /api/auth/register：注册。首个可登录用户自动成为 admin。
pub async fn register(
    State(state): State<Arc<AppState>>,
    Json(req): Json<RegisterRequest>,
) -> ApiResult {
    if let Err(msg) = auth::validate_username(&req.username) {
        return Err(err(StatusCode::BAD_REQUEST, msg));
    }
    if req.password.chars().count() < 8 {
        return Err(err(StatusCode::BAD_REQUEST, "密码至少 8 个字符"));
    }

    let hash = auth::hash_password(&req.password)
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    let ttl = state.session_ttl_secs;
    let conn = state.db.lock().unwrap();

    // 是否首个可登录用户 → 自动 admin
    let loginable: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL",
            [],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let is_admin = if loginable == 0 { 1 } else { 0 };

    let role = if is_admin == 1 { "admin" } else { "editor" };
    let insert = conn.execute(
        "INSERT INTO users (username, password_hash, is_admin, role) VALUES (?1, ?2, ?3, ?4)",
        params![req.username, hash, is_admin, role],
    );

    if let Err(e) = insert {
        let msg = e.to_string();
        if msg.contains("UNIQUE constraint failed") {
            return Err(err(StatusCode::CONFLICT, "用户名已存在"));
        }
        return Err(err(StatusCode::INTERNAL_SERVER_ERROR, &msg));
    }
    let user_id = conn.last_insert_rowid();

    let token = auth::create_session(&conn, user_id, ttl as i64)
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    state.metrics.inc_auth("register");

    let cookie = auth::set_session_cookie_value(&token, ttl as i64);
    let body = Json(UserInfo {
        id: user_id,
        username: req.username,
        is_admin: is_admin == 1,
        role: role.to_string(),
    });
    Ok((StatusCode::CREATED, [(header::SET_COOKIE, cookie)], body).into_response())
}

/// POST /api/auth/login：登录。失败统一 401，防用户名枚举。
pub async fn login(State(state): State<Arc<AppState>>, Json(req): Json<LoginRequest>) -> ApiResult {
    let ttl = state.session_ttl_secs;
    let conn = state.db.lock().unwrap();

    let row: Option<(i64, Option<String>, i64, String)> = conn
        .query_row(
            "SELECT id, password_hash, is_admin, role FROM users WHERE username = ?1",
            params![req.username],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let bad = || err(StatusCode::UNAUTHORIZED, "用户名或密码错误");
    let (user_id, hash_opt, is_admin, role) = match row {
        Some(v) => v,
        None => return Err(bad()),
    };
    let hash = match hash_opt {
        Some(h) => h,
        None => return Err(bad()), // 占位用户不可登录
    };
    if !auth::verify_password(&req.password, &hash) {
        return Err(bad());
    }

    let token = auth::create_session(&conn, user_id, ttl as i64)
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    state.metrics.inc_auth("login");

    let cookie = auth::set_session_cookie_value(&token, ttl as i64);
    let body = Json(UserInfo {
        id: user_id,
        username: req.username,
        is_admin: is_admin == 1,
        role,
    });
    Ok((StatusCode::OK, [(header::SET_COOKIE, cookie)], body).into_response())
}

/// POST /api/auth/logout：登出（无 session 也返回 200）
pub async fn logout(
    State(state): State<Arc<AppState>>,
    headers: axum::http::HeaderMap,
) -> ApiResult {
    let cookie_header = headers
        .get(axum::http::header::COOKIE)
        .and_then(|v| v.to_str().ok());
    if let Some(token) = auth::extract_session_token(cookie_header) {
        let conn = state.db.lock().unwrap();
        let _ = auth::revoke_session(&conn, &token);
    }
    state.metrics.inc_auth("logout");
    let clear = auth::clear_session_cookie_value();
    Ok((
        StatusCode::OK,
        [(header::SET_COOKIE, clear)],
        Json(json!({"status": "ok"})),
    )
        .into_response())
}

/// GET /api/me：当前登录用户（中间件已鉴权）
pub async fn me(Extension(user): Extension<auth::CurrentUser>) -> ApiResult {
    Ok(Json(UserInfo {
        id: user.id,
        username: user.username,
        is_admin: user.is_admin,
        role: user.role.clone(),
    })
    .into_response())
}

/// GET /api/auth/setup-needed：是否需要初始化（无可登录用户时 true）
pub async fn setup_needed(State(state): State<Arc<AppState>>) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL",
            [],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    Ok(Json(crate::models::SetupNeededResponse { needed: count == 0 }).into_response())
}

/// POST /api/auth/migrate-legacy：一次性把 legacy 占位用户的数据转给当前用户
pub async fn migrate_legacy(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let legacy_id: Option<i64> = conn
        .query_row("SELECT id FROM users WHERE username = 'legacy'", [], |r| {
            r.get(0)
        })
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let legacy_id = match legacy_id {
        Some(id) => id,
        None => return Err(err(StatusCode::GONE, "无可迁移数据")),
    };

    // 冲突时当前用户的设置优先：删 legacy 侧与当前用户同 key 的设置，
    // 避免 (user_id,key) 冲突，同时不丢用户刚做的显式设置。
    conn.execute(
        "DELETE FROM settings WHERE user_id = ?1 AND key IN (SELECT key FROM settings WHERE user_id = ?2)",
        params![legacy_id, user.id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    conn.execute(
        "UPDATE vfs_nodes SET user_id = ?1 WHERE user_id = ?2",
        params![user.id, legacy_id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    conn.execute(
        "UPDATE settings SET user_id = ?1 WHERE user_id = ?2",
        params![user.id, legacy_id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    // sessions 表 ON DELETE CASCADE 自动清理 legacy 的 session
    conn.execute("DELETE FROM users WHERE id = ?1", params![legacy_id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    state.metrics.inc_auth("migrate_legacy");
    Ok(Json(json!({"migrated": true})).into_response())
}

// __AUTH_ENDPOINTS_END__

// ================= v1.7 RBAC 用户与分享管理 =================

/// GET /api/users：列出全体用户（需要 UsersManage 权限，由中间件保证）
pub async fn list_users(
    State(state): State<Arc<AppState>>,
    Extension(_user): Extension<auth::CurrentUser>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let mut stmt = conn
        .prepare("SELECT id, username, is_admin, role, created_at FROM users ORDER BY id ASC")
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let rows = stmt
        .query_map([], |r| {
            Ok(UserWithRole {
                id: r.get(0)?,
                username: r.get(1)?,
                is_admin: r.get::<_, i64>(2)? == 1,
                role: r.get(3)?,
                created_at: r.get(4)?,
            })
        })
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?);
    }
    Ok(Json(out).into_response())
}

/// PATCH /api/users/:id/role：修改用户角色（需要 UsersManage 权限，由中间件保证）
pub async fn set_user_role(
    State(state): State<Arc<AppState>>,
    Extension(_user): Extension<auth::CurrentUser>,
    Path(id): Path<i64>,
    Json(req): Json<SetRoleRequest>,
) -> ApiResult {
    let new_role = match crate::rbac::Role::parse(&req.role) {
        Some(r) => r,
        None => {
            return Err(err(
                StatusCode::BAD_REQUEST,
                "role 只支持 admin/editor/viewer",
            ))
        }
    };

    let conn = state.db.lock().unwrap();

    let existing: Option<(i64, String)> = conn
        .query_row(
            "SELECT id, role FROM users WHERE id = ?1",
            params![id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let (_, current_role) = match existing {
        Some(v) => v,
        None => return Err(err(StatusCode::NOT_FOUND, "用户不存在")),
    };

    if current_role == "admin" && new_role.as_str() != "admin" {
        let admin_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM users WHERE role = 'admin'", [], |r| {
                r.get(0)
            })
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        if admin_count == 1 {
            return Err(err_reason(
                StatusCode::FORBIDDEN,
                "权限不足",
                "不能移除最后一个管理员",
            ));
        }
    }

    let is_admin_flag: i64 = if new_role.as_str() == "admin" { 1 } else { 0 };
    conn.execute(
        "UPDATE users SET role = ?1, is_admin = ?2 WHERE id = ?3",
        params![new_role.as_str(), is_admin_flag, id],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    // 角色变更后旧会话必须失效：忽略错误，避免因清理失败阻断成功响应。
    let _ = auth::revoke_all_user_sessions(&conn, id);

    state.metrics.inc_auth("set_role");

    let updated = conn
        .query_row(
            "SELECT id, username, is_admin, role, created_at FROM users WHERE id = ?1",
            params![id],
            |r| {
                Ok(UserWithRole {
                    id: r.get(0)?,
                    username: r.get(1)?,
                    is_admin: r.get::<_, i64>(2)? == 1,
                    role: r.get(3)?,
                    created_at: r.get(4)?,
                })
            },
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(updated).into_response())
}

/// GET /api/shares：列出分享（admin 全部，editor 仅自己创建的）
pub async fn list_shares(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let base = "SELECT s.id, s.token, s.share_type, s.owner_id, u.username, s.created_at, v.name, \
                s.expires_at \
                FROM shares s \
                JOIN users u ON u.id = s.owner_id \
                JOIN vfs_nodes v ON v.id = s.node_id";

    let is_admin = matches!(
        crate::rbac::Role::parse(&user.role),
        Some(crate::rbac::Role::Admin)
    );

    let mut out: Vec<ShareAdminItem> = Vec::new();
    if is_admin {
        let mut stmt = conn
            .prepare(&format!("{} ORDER BY s.id ASC", base))
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map([], |r| {
                Ok(ShareAdminItem {
                    id: r.get(0)?,
                    token: r.get(1)?,
                    share_type: r.get(2)?,
                    owner_id: r.get(3)?,
                    owner_username: r.get(4)?,
                    created_at: r.get(5)?,
                    node_name: r.get(6)?,
                    expires_at: r.get(7)?,
                })
            })
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        for row in rows {
            out.push(row.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?);
        }
    } else {
        let mut stmt = conn
            .prepare(&format!("{} WHERE s.owner_id = ?1 ORDER BY s.id ASC", base))
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map(params![user.id], |r| {
                Ok(ShareAdminItem {
                    id: r.get(0)?,
                    token: r.get(1)?,
                    share_type: r.get(2)?,
                    owner_id: r.get(3)?,
                    owner_username: r.get(4)?,
                    created_at: r.get(5)?,
                    node_name: r.get(6)?,
                    expires_at: r.get(7)?,
                })
            })
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        for row in rows {
            out.push(row.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?);
        }
    }

    Ok(Json(out).into_response())
}

/// DELETE /api/shares/token/:token：按 token 撤销分享（admin 任意，editor 仅自己创建的）
pub async fn revoke_share(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Path(token): Path<String>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();

    let owner_id: i64 = conn
        .query_row(
            "SELECT owner_id FROM shares WHERE token = ?1",
            params![token],
            |r| r.get(0),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "分享不存在"))?;

    let is_admin = matches!(
        crate::rbac::Role::parse(&user.role),
        Some(crate::rbac::Role::Admin)
    );
    if !is_admin && owner_id != user.id {
        return Err(err_reason(
            StatusCode::FORBIDDEN,
            "权限不足",
            "只能管理自己创建的分享",
        ));
    }

    conn.execute("DELETE FROM shares WHERE token = ?1", params![token])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(StatusCode::NO_CONTENT.into_response())
}

/// DELETE /api/shares/:id：删除分享（admin 任意，editor 仅自己创建的）
pub async fn delete_share(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Path(id): Path<i64>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();

    let existing: Option<(i64, i64)> = conn
        .query_row(
            "SELECT id, owner_id FROM shares WHERE id = ?1",
            params![id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let (_, owner_id) = match existing {
        Some(v) => v,
        None => return Err(err(StatusCode::NOT_FOUND, "分享不存在")),
    };

    let is_admin = matches!(
        crate::rbac::Role::parse(&user.role),
        Some(crate::rbac::Role::Admin)
    );
    if !is_admin && owner_id != user.id {
        return Err(err_reason(
            StatusCode::FORBIDDEN,
            "权限不足",
            "只能管理自己创建的分享",
        ));
    }

    conn.execute("DELETE FROM shares WHERE id = ?1", params![id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(StatusCode::NO_CONTENT.into_response())
}

// ================= v1.3 访客只读分享 =================

/// 生成分享 token：16 字节随机 hex
fn new_share_token() -> Result<String, String> {
    let mut buf = [0u8; 16];
    rand::rngs::OsRng
        .try_fill_bytes(&mut buf)
        .map_err(|e| e.to_string())?;
    Ok(hex::encode(buf))
}

/// 分享查询行：(node_id, name, kind, content, content_blob, mime_type, share_type, expires_at)
type ShareRow = (
    i64,
    String,
    String,
    String,
    Option<Vec<u8>>,
    Option<String>,
    String,
    Option<i64>,
);

/// 按 token 查分享及其文件（公开接口用，不做用户隔离）
fn lookup_share(conn: &rusqlite::Connection, token: &str) -> Result<Option<ShareRow>, String> {
    let row: Option<ShareRow> = conn
        .query_row(
            "SELECT v.id, v.name, v.kind, v.content, v.content_blob, v.mime_type, s.share_type, \
             s.expires_at \
             FROM shares s JOIN vfs_nodes v ON v.id = s.node_id WHERE s.token = ?1",
            params![token],
            |r| {
                Ok((
                    r.get(0)?,
                    r.get(1)?,
                    r.get(2)?,
                    r.get(3)?,
                    r.get(4)?,
                    r.get(5)?,
                    r.get(6)?,
                    r.get(7)?,
                ))
            },
        )
        .optional()
        .map_err(|e| e.to_string())?;
    Ok(row)
}

/// 当前 unix 秒
fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// 过期检查：expires_at 非空且 <= now 视为过期
fn is_expired(expires_at: Option<i64>) -> bool {
    match expires_at {
        Some(ts) => ts <= now_unix(),
        None => false,
    }
}

/// 目录解析失败原因（创建分享时用）
enum ShareDirError {
    NotFound,
    NotAFolder,
}

/// 校验单个路径段是否合法（非空、非 . / ..、无控制字符）
fn is_valid_segment(seg: &str) -> bool {
    if seg.is_empty() || seg == "." || seg == ".." {
        return false;
    }
    !seg.chars().any(|c| c.is_control())
}

/// 在用户根下逐级解析目录路径，返回目标目录节点 id
fn resolve_share_dir(
    conn: &rusqlite::Connection,
    path: &str,
    user_id: i64,
) -> Result<i64, ShareDirError> {
    let segments: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(ShareDirError::NotFound);
    }
    for seg in &segments {
        if !is_valid_segment(seg) {
            return Err(ShareDirError::NotFound);
        }
    }

    let mut current: Option<i64> = None;
    for seg in segments {
        let found: Option<(i64, String)> = match current {
            None => conn
                .query_row(
                    "SELECT id, kind FROM vfs_nodes \
                     WHERE parent_id IS NULL AND name = ?1 AND user_id = ?2",
                    params![seg, user_id],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .optional(),
            Some(pid) => conn
                .query_row(
                    "SELECT id, kind FROM vfs_nodes \
                     WHERE parent_id = ?1 AND name = ?2 AND user_id = ?3",
                    params![pid, seg, user_id],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .optional(),
        }
        .map_err(|_| ShareDirError::NotFound)?;

        match found {
            None => return Err(ShareDirError::NotFound),
            Some((id, kind)) => {
                if kind != "folder" {
                    return Err(ShareDirError::NotAFolder);
                }
                current = Some(id);
            }
        }
    }
    current.ok_or(ShareDirError::NotFound)
}

/// 分享内相对路径解析结果
struct ShareFile {
    name: String,
    kind: String,
    content: String,
    blob: Option<Vec<u8>>,
    mime: Option<String>,
}

/// 在目录分享子树内沿相对路径下钻，返回 (节点 id, kind)。
/// allow_empty=true 时空 rel 指向分享根（返回 Ok((root_id, "folder"))）；
/// 否则空 rel 按非法路径 403（保持下载端点现有行为）。
/// 非法段（空/"."/".." /控制字符）→ 403；中途找不到 → 404。
fn walk_share_path(
    conn: &rusqlite::Connection,
    root_id: i64,
    rel: &str,
    allow_empty: bool,
) -> Result<(i64, String), (StatusCode, Json<serde_json::Value>)> {
    let trimmed = rel.trim().trim_start_matches('/');
    let segments: Vec<&str> = trimmed.split('/').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        if allow_empty {
            return Ok((root_id, "folder".to_string()));
        }
        return Err(err(StatusCode::FORBIDDEN, "非法路径"));
    }
    for seg in &segments {
        if !is_valid_segment(seg) {
            return Err(err(StatusCode::FORBIDDEN, "非法路径"));
        }
    }

    let mut current = root_id;
    let mut kind: String = "folder".to_string();
    let last_idx = segments.len() - 1;
    for (i, seg) in segments.iter().enumerate() {
        let found: Option<(i64, String)> = conn
            .query_row(
                "SELECT id, kind FROM vfs_nodes WHERE parent_id = ?1 AND name = ?2",
                params![current, seg],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()
            .map_err(|_| err(StatusCode::NOT_FOUND, "分享不存在或已失效"))?;

        match found {
            None => return Err(err(StatusCode::NOT_FOUND, "分享不存在或已失效")),
            Some((id, k)) => {
                if k != "folder" && i != last_idx {
                    // 中间段是文件：无法继续下钻
                    return Err(err(StatusCode::NOT_FOUND, "分享不存在或已失效"));
                }
                current = id;
                kind = k;
            }
        }
    }
    Ok((current, kind))
}

/// 在目录分享的子树内按相对路径解析节点（访客访问，无用户隔离）
fn resolve_in_share(
    conn: &rusqlite::Connection,
    root_id: i64,
    rel: &str,
) -> Result<ShareFile, (StatusCode, Json<serde_json::Value>)> {
    let trimmed = rel.trim().trim_start_matches('/');
    let segments: Vec<&str> = trimmed.split('/').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return Err(err(StatusCode::FORBIDDEN, "非法路径"));
    }
    for seg in &segments {
        if !is_valid_segment(seg) {
            return Err(err(StatusCode::FORBIDDEN, "非法路径"));
        }
    }

    let (node_id, _kind) = walk_share_path(conn, root_id, rel, false)?;
    let last = segments
        .last()
        .copied()
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "分享不存在或已失效"))?;

    let parent_id: i64 = if segments.len() == 1 {
        root_id
    } else {
        let parent_rel = segments[..segments.len() - 1].join("/");
        let (pid, _) = walk_share_path(conn, root_id, &parent_rel, false)?;
        pid
    };

    conn.query_row(
        "SELECT name, kind, content, content_blob, mime_type FROM vfs_nodes \
         WHERE parent_id = ?1 AND name = ?2 AND id = ?3",
        params![parent_id, last, node_id],
        |r| {
            Ok(ShareFile {
                name: r.get(0)?,
                kind: r.get(1)?,
                content: r.get(2)?,
                blob: r.get(3)?,
                mime: r.get(4)?,
            })
        },
    )
    .optional()
    .map_err(|_| err(StatusCode::NOT_FOUND, "分享不存在或已失效"))?
    .ok_or_else(|| err(StatusCode::NOT_FOUND, "分享不存在或已失效"))
}

/// 目录分享浏览查询参数
#[derive(Deserialize)]
pub struct ShareListQuery {
    pub token: String,
    pub path: Option<String>,
}

/// GET /api/share/list?token=&path=：目录分享浏览（公开，只读）
/// path 为分享根下的相对路径，缺省/"" 为根；返回该目录的直接子条目。
pub async fn list_share(
    State(state): State<Arc<AppState>>,
    Query(q): Query<ShareListQuery>,
) -> ApiResult {
    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "内部错误"))?;

    let row =
        lookup_share(&conn, &q.token).map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    let (root_id, _node_name, _node_kind, _content, _blob, _mime, share_type, expires_at) =
        match row {
            None => return Err(err(StatusCode::NOT_FOUND, "分享不存在或已失效")),
            Some(v) => v,
        };

    if is_expired(expires_at) {
        return Err(err(StatusCode::GONE, "分享已过期"));
    }

    if share_type != "dir" {
        return Err(err(StatusCode::BAD_REQUEST, "仅目录分享支持浏览"));
    }

    let rel = q
        .path
        .as_deref()
        .unwrap_or("")
        .trim()
        .trim_start_matches('/');
    let rel = rel.to_string();

    let (dir_id, kind) = walk_share_path(&conn, root_id, &rel, true)?;
    if kind != "folder" {
        return Err(err(StatusCode::BAD_REQUEST, "path 不是目录"));
    }

    let mut stmt = conn
        .prepare(
            "SELECT name, kind, content, content_blob, updated_at FROM vfs_nodes \
             WHERE parent_id = ?1 ORDER BY kind DESC, name ASC",
        )
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "内部错误"))?;

    let rows = stmt
        .query_map(params![dir_id], |r| {
            let name: String = r.get(0)?;
            let kind: String = r.get(1)?;
            let content: Option<String> = r.get(2)?;
            let blob: Option<Vec<u8>> = r.get(3)?;
            let mtime: String = r.get(4)?;
            let size: i64 = if kind == "folder" {
                0
            } else if let Some(b) = &blob {
                b.len() as i64
            } else if let Some(c) = &content {
                c.len() as i64
            } else {
                0
            };
            Ok(ShareDirEntry {
                name,
                kind,
                size,
                mtime,
            })
        })
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "内部错误"))?;

    let mut entries: Vec<ShareDirEntry> = Vec::new();
    for row in rows {
        entries.push(row.map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "内部错误"))?);
    }

    Ok(Json(ShareDirListing { path: rel, entries }).into_response())
}

/// 统计目录子树内所有文件字节数之和（迭代栈）
fn subtree_bytes(conn: &rusqlite::Connection, root_id: i64) -> Result<i64, String> {
    let mut total: i64 = 0;
    let mut stack: Vec<i64> = vec![root_id];
    while let Some(id) = stack.pop() {
        let mut stmt = conn
            .prepare("SELECT id, kind, content, content_blob FROM vfs_nodes WHERE parent_id = ?1")
            .map_err(|e| e.to_string())?;
        let mut rows = stmt.query(params![id]).map_err(|e| e.to_string())?;
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            let child_id: i64 = row.get(0).map_err(|e| e.to_string())?;
            let kind: String = row.get(1).map_err(|e| e.to_string())?;
            if kind == "folder" {
                stack.push(child_id);
            } else {
                let content: String = row.get(2).map_err(|e| e.to_string())?;
                let blob: Option<Vec<u8>> = row.get(3).map_err(|e| e.to_string())?;
                total += blob.as_ref().map(|b| b.len()).unwrap_or(content.len()) as i64;
            }
        }
    }
    Ok(total)
}

/// 构造文件下载响应（分块流式，两处复用）
fn file_download_response(name: &str, bytes_vec: Vec<u8>, mime_opt: Option<String>) -> ApiResult {
    let mime_str = mime_opt.filter(|m| !m.is_empty()).unwrap_or_else(|| {
        mime_guess::from_path(name)
            .first_or_octet_stream()
            .to_string()
    });

    // 分块流式
    const CHUNK_SIZE: usize = 65536;
    let mut chunks: Vec<Result<Bytes, std::io::Error>> = Vec::new();
    let mut offset = 0usize;
    while offset < bytes_vec.len() {
        let end = std::cmp::min(offset + CHUNK_SIZE, bytes_vec.len());
        chunks.push(Ok(Bytes::copy_from_slice(&bytes_vec[offset..end])));
        offset = end;
    }
    let body_stream = stream::iter(chunks);

    let disposition = format!("attachment; filename*=UTF-8''{}", percent_encode(name));
    let response = Response::builder()
        .status(StatusCode::OK)
        .header("content-type", mime_str)
        .header("content-disposition", disposition)
        .header("content-length", bytes_vec.len().to_string())
        .body(Body::from_stream(body_stream))
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "构造响应失败"))?;
    Ok(response)
}

/// POST /api/shares：创建只读分享（需登录；file 或 dir 类型）
pub async fn create_share(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<auth::CurrentUser>,
    Json(req): Json<CreateShareRequest>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let stype = req.share_type.as_deref().unwrap_or("file");
    if stype != "file" && stype != "dir" {
        return Err(err(StatusCode::BAD_REQUEST, "type 只支持 file 或 dir"));
    }

    let node_id: i64 = if stype == "dir" {
        let path = req.path.as_deref().unwrap_or("");
        if path.trim().is_empty() {
            return Err(err(StatusCode::BAD_REQUEST, "目录分享需要 path 参数"));
        }
        match resolve_share_dir(&conn, path, user.id) {
            Ok(id) => id,
            Err(ShareDirError::NotFound) => return Err(err(StatusCode::NOT_FOUND, "目录不存在")),
            Err(ShareDirError::NotAFolder) => {
                return Err(err(StatusCode::BAD_REQUEST, "path 不是目录"))
            }
        }
    } else {
        let node_id = match req.node_id {
            Some(id) => id,
            None => return Err(err(StatusCode::BAD_REQUEST, "文件分享需要 node_id")),
        };
        let kind: Option<String> = conn
            .query_row(
                "SELECT kind FROM vfs_nodes WHERE id = ?1 AND user_id = ?2",
                params![node_id, user.id],
                |r| r.get(0),
            )
            .optional()
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        match kind.as_deref() {
            None => return Err(err(StatusCode::NOT_FOUND, "节点不存在")),
            Some(k) if k != "file" => return Err(err(StatusCode::BAD_REQUEST, "仅支持分享文件")),
            _ => {}
        }
        node_id
    };

    let expires_at = match req.expires_at {
        Some(ts) => {
            if ts <= now_unix() {
                return Err(err(StatusCode::BAD_REQUEST, "过期时间必须是未来时间"));
            }
            Some(ts)
        }
        None => None,
    };

    // token 碰撞重试 3 次（概率极低，防御性）
    let mut token = String::new();
    let mut ok = false;
    for _ in 0..3 {
        token = new_share_token().map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
        let res = conn.execute(
            "INSERT INTO shares (token, node_id, owner_id, share_type, expires_at) \
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![token, node_id, user.id, stype, expires_at],
        );
        match res {
            Ok(_) => {
                ok = true;
                break;
            }
            Err(e) if e.to_string().contains("UNIQUE constraint failed") => continue,
            Err(e) => return Err(err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string())),
        }
    }
    if !ok {
        return Err(err(
            StatusCode::INTERNAL_SERVER_ERROR,
            "分享创建失败，请重试",
        ));
    }

    state.metrics.inc_auth("share_create");
    Ok((
        StatusCode::CREATED,
        Json(ShareCreated {
            token: token.clone(),
            url: format!("/share.html?token={}", token),
            expires_at,
        }),
    )
        .into_response())
}

/// GET /api/s/:token：分享元信息（公开，只读）
pub async fn get_share(State(state): State<Arc<AppState>>, Path(token): Path<String>) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let row =
        lookup_share(&conn, &token).map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    match row {
        None => Err(err(StatusCode::NOT_FOUND, "分享不存在或已失效")),
        Some((node_id, name, kind, content, blob, mime, share_type, expires_at)) => {
            if is_expired(expires_at) {
                return Err(err(StatusCode::GONE, "分享已过期"));
            }
            if share_type == "dir" {
                let size = subtree_bytes(&conn, node_id)
                    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
                Ok(Json(ShareInfo {
                    token,
                    name,
                    kind: "folder".to_string(),
                    size,
                    mime_type: None,
                    share_type: "dir".to_string(),
                })
                .into_response())
            } else {
                let size = blob.as_ref().map(|b| b.len()).unwrap_or(content.len()) as i64;
                // mime_type 为空时按文件名兜底推断（与 file_download_response 同模式），
                // 保证分享元信息的 mimeType 始终有值。
                let mime_type = mime.filter(|m|!m.is_empty()).unwrap_or_else(|| {
                    mime_guess::from_path(&name)
                        .first_or_octet_stream()
                        .to_string()
                });
                Ok(Json(ShareInfo {
                    token,
                    name,
                    kind,
                    size,
                    mime_type: Some(mime_type),
                    share_type: "file".to_string(),
                })
                .into_response())
            }
        }
    }
}

/// GET /api/s/:token/download：分享文件下载（公开，只读，流式）
pub async fn download_share(
    State(state): State<Arc<AppState>>,
    Path(token): Path<String>,
    Query(q): Query<DownloadQuery>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let row =
        lookup_share(&conn, &token).map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e))?;
    let (root_id, name, kind, content, blob, mime_opt, share_type, expires_at) = match row {
        None => return Err(err(StatusCode::NOT_FOUND, "分享不存在或已失效")),
        Some(v) => v,
    };

    if is_expired(expires_at) {
        return Err(err(StatusCode::GONE, "分享已过期"));
    }

    if share_type == "dir" {
        let rel = q.path.as_deref().unwrap_or("");
        if rel.trim().is_empty() {
            return Err(err(StatusCode::BAD_REQUEST, "目录分享下载需要 path 参数"));
        }
        let f = resolve_in_share(&conn, root_id, rel)?;
        if f.kind == "folder" {
            return Err(err(StatusCode::BAD_REQUEST, "不能下载目录"));
        }
        let bytes_vec: Vec<u8> = f.blob.unwrap_or_else(|| f.content.into_bytes());
        return file_download_response(&f.name, bytes_vec, f.mime);
    }

    if kind == "folder" {
        return Err(err(StatusCode::BAD_REQUEST, "不能下载目录"));
    }
    let bytes_vec: Vec<u8> = blob.unwrap_or_else(|| content.into_bytes());
    file_download_response(&name, bytes_vec, mime_opt)
}

// __SHARES_END__
