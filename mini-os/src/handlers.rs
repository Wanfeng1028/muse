//! HTTP 处理器与 WebSocket，包含全部 /api 路由实现。

use std::sync::Arc;

use axum::{
    body::{Body, Bytes},
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Multipart, Path, Query, State,
    },
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use futures_util::stream;
use rusqlite::{params, OptionalExtension};
use serde::Deserialize;
use serde_json::json;

use crate::models::{AppInfo, CreateNodeRequest, Node, SettingRequest, Stats, UpdateNodeRequest};
use crate::AppState;

/// 统一的 API 返回类型别名
type ApiResult = Result<Response, (StatusCode, Json<serde_json::Value>)>;

/// 上传接口查询参数
#[derive(Deserialize)]
pub struct UploadQuery {
    pub path: Option<String>,
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
                "SELECT id FROM vfs_nodes WHERE parent_id IS NULL AND name = ?1 AND kind = 'folder'",
                params![seg_trimmed],
                |row| row.get(0),
            )
            .optional()
            .map_err(|_| "目录不存在或不是文件夹")?
        } else {
            conn.query_row(
                "SELECT id FROM vfs_nodes WHERE parent_id = ?2 AND name = ?1 AND kind = 'folder'",
                params![seg_trimmed, parent],
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
            conn.query_row(
                "SELECT COUNT(*) FROM schema_migrations",
                [],
                |row| row.get::<_, i64>(0),
            )
            .is_ok()
        })
        .unwrap_or(false);
    if ok {
        (
            StatusCode::OK,
            Json(json!({ "status": "ready" })),
        )
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
pub async fn list_fs(State(state): State<Arc<AppState>>, Query(q): Query<FsQuery>) -> ApiResult {
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
                 FROM vfs_nodes WHERE parent_id = ?1 \
                 ORDER BY CASE kind WHEN 'folder' THEN 0 ELSE 1 END, name ASC",
            )


            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map(params![pid], row_to_node)
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
                 FROM vfs_nodes WHERE parent_id IS NULL \
                 ORDER BY CASE kind WHEN 'folder' THEN 0 ELSE 1 END, name ASC",
            )


            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        let rows = stmt
            .query_map([], row_to_node)
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
        for r in rows {
            nodes.push(r.map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?);
        }
    }

    Ok(Json(nodes).into_response())
}

/// GET /api/fs/{id}
pub async fn get_fs(State(state): State<Arc<AppState>>, Path(id): Path<i64>) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
             CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
             mime_type \
             FROM vfs_nodes WHERE id = ?1",
            params![id],
            row_to_node,
        )
        .optional()


        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    match node {
        Some(n) => Ok(Json(n).into_response()),
        None => Err(err(StatusCode::NOT_FOUND, "节点不存在")),
    }
}

/// POST /api/fs
pub async fn create_fs(
    State(state): State<Arc<AppState>>,
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
    let content = req.content.unwrap_or_default();

    let conn = state.db.lock().unwrap();

    // 校验父节点存在且为 folder
    if let Some(pid) = req.parent_id {
        let parent_kind: Option<String> = conn
            .query_row(
                "SELECT kind FROM vfs_nodes WHERE id = ?1",
                params![pid],
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

    conn.execute(
        "INSERT INTO vfs_nodes (parent_id, name, kind, content) VALUES (?1, ?2, ?3, ?4)",
        params![req.parent_id, name, req.kind, content],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    let id = conn.last_insert_rowid();
    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
             CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
             mime_type \
             FROM vfs_nodes WHERE id = ?1",


            params![id],
            row_to_node,
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok((StatusCode::CREATED, Json(node)).into_response())
}

/// PUT /api/fs/{id}
pub async fn update_fs(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
    Json(req): Json<UpdateNodeRequest>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();

    // 确认存在
    let exists: Option<i64> = conn
        .query_row("SELECT id FROM vfs_nodes WHERE id = ?1", params![id], |r| {
            r.get(0)
        })
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

    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at, \
             CASE WHEN kind='folder' THEN 0 ELSE COALESCE(LENGTH(content_blob), LENGTH(CAST(content AS BLOB)), 0) END AS size, \
             mime_type \
             FROM vfs_nodes WHERE id = ?1",


            params![id],
            row_to_node,
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(node).into_response())
}

/// DELETE /api/fs/{id}（级联删除子节点）
pub async fn delete_fs(State(state): State<Arc<AppState>>, Path(id): Path<i64>) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let affected = conn
        .execute("DELETE FROM vfs_nodes WHERE id = ?1", params![id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    if affected == 0 {
        return Err(err(StatusCode::NOT_FOUND, "节点不存在"));
    }
    Ok(StatusCode::NO_CONTENT.into_response())
}

/// GET /api/settings -> 键值映射
pub async fn get_settings(State(state): State<Arc<AppState>>) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let mut stmt = conn
        .prepare("SELECT key, value FROM settings")
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let rows = stmt
        .query_map([], |r| {
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
    Json(req): Json<SettingRequest>,
) -> ApiResult {
    if req.key.trim().is_empty() {
        return Err(err(StatusCode::BAD_REQUEST, "key 不能为空"));
    }
    let conn = state.db.lock().unwrap();
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?1, ?2) \
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        params![req.key, req.value],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(json!({ "key": req.key, "value": req.value })).into_response())
}

/// GET /api/stats
/// 上传文件：multipart/form-data，字段名固定为 "file"，目标目录由 ?path= 指定
pub async fn upload_file(
    State(state): State<Arc<AppState>>,
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

    let mime = match ctype {
        Some(ct) => ct,
        None => mime_guess::from_path(&name)
            .first_or_octet_stream()
            .to_string(),
    };

    let is_utf8 = std::str::from_utf8(&bytes).is_ok();
    let content_text: String = if is_utf8 {
        String::from_utf8_lossy(&bytes).to_string()
    } else {
        String::new()
    };

    let conn = state.db.lock().unwrap();

    let parent_id = match resolve_folder_id(&conn, q.path.as_deref()) {
        Ok(p) => p,
        Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
    };

    // 同目录同名检查（file 或 folder 任意）
    let exists: Option<i64> = if parent_id.is_none() {
        conn.query_row(
            "SELECT id FROM vfs_nodes WHERE parent_id IS NULL AND name = ?1",
            params![name],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?
    } else {
        conn.query_row(
            "SELECT id FROM vfs_nodes WHERE parent_id = ?1 AND name = ?2",
            params![parent_id, name],
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
            "INSERT INTO vfs_nodes (parent_id, name, kind, content, content_blob, mime_type) VALUES (NULL, ?1, 'file', ?2, ?3, ?4)",
            params![name, content_text, bytes, mime],
        )
    } else {
        conn.execute(
            "INSERT INTO vfs_nodes (parent_id, name, kind, content, content_blob, mime_type) VALUES (?1, ?2, 'file', ?3, ?4, ?5)",
            params![parent_id, name, content_text, bytes, mime],
        )
    };
    if insert_res.is_err() {
        return Err(err(StatusCode::INTERNAL_SERVER_ERROR, "写入失败"));
    }
    let new_id = conn.last_insert_rowid();

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

    let parent_id = match resolve_folder_id(&conn, dir_path.as_deref()) {
        Ok(p) => p,
        Err(msg) => return Err(err(StatusCode::BAD_REQUEST, msg)),
    };

    let query_row: rusqlite::Result<FileRow> = if parent_id.is_none() {
        conn.query_row(
                "SELECT id, parent_id, name, kind, content, created_at, updated_at, content_blob, mime_type FROM vfs_nodes WHERE parent_id IS NULL AND name = ?1",
                params![file_name],
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
                "SELECT id, parent_id, name, kind, content, created_at, updated_at, content_blob, mime_type FROM vfs_nodes WHERE parent_id = ?1 AND name = ?2",
                params![parent_id, file_name],
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

pub async fn get_stats(State(state): State<Arc<AppState>>) -> ApiResult {
    let conn = state.db.lock().unwrap();

    let files: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'file'",
            [],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    let folders: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM vfs_nodes WHERE kind = 'folder'",
            [],
            |r| r.get(0),
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    // 所有文件字节数之和：content_blob 优先，否则 content 文本字节
    let total_bytes: i64 = conn
        .query_row(
            "SELECT COALESCE(SUM(CASE WHEN kind='file' THEN CASE WHEN content_blob IS NOT NULL THEN LENGTH(content_blob) ELSE LENGTH(CAST(content AS BLOB)) END ELSE 0 END), 0) \
             FROM vfs_nodes",

            [],
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
pub async fn ws_handler(ws: WebSocketUpgrade) -> impl IntoResponse {
    ws.on_upgrade(handle_socket)
}

/// 处理单个 WebSocket 连接。
async fn handle_socket(mut socket: WebSocket) {
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
