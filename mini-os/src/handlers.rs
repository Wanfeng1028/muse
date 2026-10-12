//! HTTP 处理器与 WebSocket，包含全部 /api 路由实现。

use std::sync::Arc;

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Path, Query, State,
    },
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use rusqlite::{params, OptionalExtension};
use serde::Deserialize;
use serde_json::json;

use crate::models::{AppInfo, CreateNodeRequest, Node, SettingRequest, Stats, UpdateNodeRequest};
use crate::AppState;

/// 统一 API 返回类型别名。
pub type ApiResult = Result<Response, (StatusCode, Json<serde_json::Value>)>;

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
    Json(json!({ "status": "ok", "version": "1.0.0" }))
}

/// GET /api/apps
pub async fn list_apps() -> impl IntoResponse {
    Json(apps_registry())
}

/// 从行构造 Node。
fn row_to_node(row: &rusqlite::Row) -> rusqlite::Result<Node> {
    Ok(Node {
        id: row.get(0)?,
        parent_id: row.get(1)?,
        name: row.get(2)?,
        kind: row.get(3)?,
        content: row.get(4)?,
        created_at: row.get(5)?,
        updated_at: row.get(6)?,
    })
}

/// GET /api/fs?parent_id=...
pub async fn list_fs(
    State(state): State<Arc<AppState>>,
    Query(q): Query<FsQuery>,
) -> ApiResult {
    // 锁中毒直接 unwrap（进程内简单互斥，不做恢复）
    let conn = state.db.lock().unwrap();

    // 文件夹优先，再按名称升序
    let mut nodes: Vec<Node> = Vec::new();

    if let Some(pid) = q.parent_id {
        let mut stmt = conn
            .prepare(
                "SELECT id, parent_id, name, kind, content, created_at, updated_at \
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
                "SELECT id, parent_id, name, kind, content, created_at, updated_at \
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
pub async fn get_fs(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> ApiResult {
    let conn = state.db.lock().unwrap();
    let node = conn
        .query_row(
            "SELECT id, parent_id, name, kind, content, created_at, updated_at \
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
            "SELECT id, parent_id, name, kind, content, created_at, updated_at \
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
            "SELECT id, parent_id, name, kind, content, created_at, updated_at \
             FROM vfs_nodes WHERE id = ?1",
            params![id],
            row_to_node,
        )
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(node).into_response())
}

/// DELETE /api/fs/{id}（级联删除子节点）
pub async fn delete_fs(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> ApiResult {
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

    // 所有文件 content 的字节数之和（NULL 视作 0）
    let total_bytes: i64 = conn
        .query_row(
            "SELECT COALESCE(SUM(LENGTH(CAST(content AS BLOB))), 0) \
             FROM vfs_nodes WHERE kind = 'file'",
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
