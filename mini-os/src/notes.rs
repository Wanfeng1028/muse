//! 速记便签（notes）与日程（events）的 HTTP 处理器。
//! 全部按 user_id 隔离；时间用 ISO8601 本地字符串，字典序即时间序。

use std::sync::Arc;

use axum::{
    extract::{Extension, Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Deserialize;

use crate::auth::CurrentUser;
use crate::handlers::{err, ApiResult};
use crate::models::{CalEvent, Note};
use crate::AppState;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateNoteRequest {
    pub title: Option<String>,
    pub body: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateNoteRequest {
    pub title: Option<String>,
    pub body: Option<String>,
    pub pinned: Option<bool>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateEventRequest {
    pub title: String,
    pub starts_at: String,
    pub ends_at: Option<String>,
    pub all_day: Option<bool>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateEventRequest {
    pub title: Option<String>,
    pub starts_at: Option<String>,
    pub ends_at: Option<String>,
    pub all_day: Option<bool>,
    pub done: Option<bool>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EventRangeQuery {
    pub from: Option<String>,
    pub to: Option<String>,
}

/// 规范化日期时间字符串：补齐到 "YYYY-MM-DDTHH:MM:SS" 以便字典序比较。
fn norm_dt(s: &str) -> String {
    if s.len() == 10 {
        // YYYY-MM-DD
        let mut out = String::with_capacity(19);
        out.push_str(s);
        out.push_str("T00:00:00");
        out
    } else if s.len() == 16 {
        // YYYY-MM-DDTHH:MM
        let mut out = String::with_capacity(19);
        out.push_str(s);
        out.push_str(":00");
        out
    } else {
        s.to_string()
    }
}

/// 校验并规范化日期时间字符串。返回 Err 消息用于 400。
fn validate_dt(s: &str) -> Result<String, String> {
    let bytes = s.as_bytes();
    let n = bytes.len();
    // 允许长度 10、16、19
    let valid_len = n == 10 || n == 16 || n == 19;
    if !valid_len {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    // 检查位置上的字符类型
    let digits_ok = |i: usize| -> bool { bytes.get(i).is_some_and(|b| b.is_ascii_digit()) };
    // YYYY-MM-DD
    if !(digits_ok(0) && digits_ok(1) && digits_ok(2) && digits_ok(3)) {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if bytes[4] != b'-' {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if !(digits_ok(5) && digits_ok(6)) {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if bytes[7] != b'-' {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if !(digits_ok(8) && digits_ok(9)) {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if n == 10 {
        return Ok(norm_dt(s));
    }
    // T
    if bytes[10] != b'T' {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if !(digits_ok(11) && digits_ok(12)) {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if bytes[13] != b':' {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if !(digits_ok(14) && digits_ok(15)) {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if n == 16 {
        return Ok(norm_dt(s));
    }
    // n == 19
    if bytes[16] != b':' {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    if !(digits_ok(17) && digits_ok(18)) {
        return Err("时间格式不正确，用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM".to_string());
    }
    Ok(norm_dt(s))
}

/// 校验标题：trim 后非空且 <= 200 字符。
fn validate_title(t: &str) -> Result<String, String> {
    let trimmed = t.trim();
    if trimmed.is_empty() {
        return Err("标题不能为空".to_string());
    }
    if trimmed.chars().count() > 200 {
        return Err("标题不能超过 200 字符".to_string());
    }
    Ok(trimmed.to_string())
}

/// 读取整行 note（固定列顺序）。
fn row_to_note(row: &rusqlite::Row<'_>) -> rusqlite::Result<Note> {
    let pinned_i: i64 = row.get(4)?;
    Ok(Note {
        id: row.get(0)?,
        user_id: row.get(1)?,
        title: row.get(2)?,
        body: row.get(3)?,
        pinned: pinned_i == 1,
        updated_at: row.get(5)?,
    })
}

/// 读取整行 event（固定列顺序）。
fn row_to_event(row: &rusqlite::Row<'_>) -> rusqlite::Result<CalEvent> {
    let all_day_i: i64 = row.get(5)?;
    let done_i: i64 = row.get(6)?;
    Ok(CalEvent {
        id: row.get(0)?,
        user_id: row.get(1)?,
        title: row.get(2)?,
        starts_at: row.get(3)?,
        ends_at: row.get(4)?,
        all_day: all_day_i == 1,
        done: done_i == 1,
        created_at: row.get(7)?,
    })
}

/// 查询单条 note 并校验归属。
fn fetch_note(
    conn: &rusqlite::Connection,
    user_id: i64,
    id: i64,
) -> rusqlite::Result<Option<Note>> {
    let mut stmt = conn.prepare(
        "SELECT id, user_id, title, body, pinned, updated_at \
         FROM notes WHERE id = ?1 AND user_id = ?2",
    )?;
    let mut rows = stmt.query(rusqlite::params![id, user_id])?;
    if let Some(r) = rows.next()? {
        Ok(Some(row_to_note(r)?))
    } else {
        Ok(None)
    }
}

/// 查询单条 event 并校验归属。
fn fetch_event(
    conn: &rusqlite::Connection,
    user_id: i64,
    id: i64,
) -> rusqlite::Result<Option<CalEvent>> {
    let mut stmt = conn.prepare(
        "SELECT id, user_id, title, starts_at, ends_at, all_day, done, created_at \
         FROM events WHERE id = ?1 AND user_id = ?2",
    )?;
    let mut rows = stmt.query(rusqlite::params![id, user_id])?;
    if let Some(r) = rows.next()? {
        Ok(Some(row_to_event(r)?))
    } else {
        Ok(None)
    }
}

/// 取当前时间的 SQLite datetime('now') 字符串。
fn now_str(conn: &rusqlite::Connection) -> rusqlite::Result<String> {
    conn.query_row("SELECT datetime('now')", [], |r| r.get::<_, String>(0))
}

pub async fn list_notes(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
) -> ApiResult {
    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let mut stmt = conn
        .prepare(
            "SELECT id, user_id, title, body, pinned, updated_at \
             FROM notes WHERE user_id = ?1 \
             ORDER BY pinned DESC, updated_at DESC",
        )
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?;
    let rows = stmt
        .query_map(rusqlite::params![user.id], row_to_note)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?);
    }
    Ok(Json(out).into_response())
}

pub async fn create_note(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Json(req): Json<CreateNoteRequest>,
) -> ApiResult {
    let title = match req.title {
        Some(t) => validate_title(&t).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?,
        None => "未命名便签".to_string(),
    };
    let body = req.body.unwrap_or_default();

    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let now = now_str(&conn).map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "时间读取失败"))?;
    conn.execute(
        "INSERT INTO notes (user_id, title, body, pinned, updated_at) \
         VALUES (?1, ?2, ?3, 0, ?4)",
        rusqlite::params![user.id, title, body, now],
    )
    .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "写入失败"))?;
    let id = conn.last_insert_rowid();
    let note = fetch_note(&conn, user.id, id)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?
        .ok_or_else(|| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?;
    Ok((StatusCode::CREATED, Json(note)).into_response())
}

pub async fn update_note(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Path(id): Path<i64>,
    Json(req): Json<UpdateNoteRequest>,
) -> ApiResult {
    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let existing = fetch_note(&conn, user.id, id)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?;
    if existing.is_none() {
        return Err(err(StatusCode::NOT_FOUND, "便签不存在"));
    }

    let mut new_title: Option<String> = None;
    if let Some(t) = req.title.as_deref() {
        new_title = Some(validate_title(t).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?);
    }
    let new_body: Option<String> = req.body;
    let new_pinned: Option<i64> = req.pinned.map(|b| if b { 1 } else { 0 });

    let now = now_str(&conn).map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "时间读取失败"))?;

    conn.execute(
        "UPDATE notes SET \
            title = COALESCE(?1, title), \
            body = COALESCE(?2, body), \
            pinned = COALESCE(?3, pinned), \
            updated_at = ?4 \
         WHERE id = ?5 AND user_id = ?6",
        rusqlite::params![new_title, new_body, new_pinned, now, id, user.id],
    )
    .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "更新失败"))?;

    let note = fetch_note(&conn, user.id, id)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "便签不存在"))?;
    Ok(Json(note).into_response())
}

pub async fn delete_note(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Path(id): Path<i64>,
) -> ApiResult {
    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let affected = conn
        .execute(
            "DELETE FROM notes WHERE id = ?1 AND user_id = ?2",
            rusqlite::params![id, user.id],
        )
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "删除失败"))?;
    if affected == 0 {
        return Err(err(StatusCode::NOT_FOUND, "便签不存在"));
    }
    Ok(StatusCode::NO_CONTENT.into_response())
}

pub async fn list_events(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Query(q): Query<EventRangeQuery>,
) -> ApiResult {
    let from_raw = q.from.unwrap_or_else(|| "0000-00-00T00:00:00".to_string());
    let to_raw = q.to.unwrap_or_else(|| "9999-12-31T23:59:59".to_string());
    let from = validate_dt(&from_raw).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?;
    let to = validate_dt(&to_raw).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?;

    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let mut stmt = conn
        .prepare(
            "SELECT id, user_id, title, starts_at, ends_at, all_day, done, created_at \
             FROM events WHERE user_id = ?1 AND starts_at >= ?2 AND starts_at < ?3 \
             ORDER BY starts_at ASC",
        )
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?;
    let rows = stmt
        .query_map(rusqlite::params![user.id, from, to], row_to_event)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "查询失败"))?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?);
    }
    Ok(Json(out).into_response())
}

pub async fn create_event(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Json(req): Json<CreateEventRequest>,
) -> ApiResult {
    let title = validate_title(&req.title).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?;
    let starts_at = validate_dt(&req.starts_at).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?;
    let ends_at: Option<String> = match req.ends_at {
        Some(e) => {
            let v = validate_dt(&e).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?;
            if v.as_str() < starts_at.as_str() {
                return Err(err(StatusCode::BAD_REQUEST, "结束时间不能早于开始时间"));
            }
            Some(v)
        }
        None => None,
    };
    let all_day_i: i64 = if req.all_day.unwrap_or(false) { 1 } else { 0 };

    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let now = now_str(&conn).map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "时间读取失败"))?;
    conn.execute(
        "INSERT INTO events (user_id, title, starts_at, ends_at, all_day, done, created_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6)",
        rusqlite::params![user.id, title, starts_at, ends_at, all_day_i, now],
    )
    .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "写入失败"))?;
    let id = conn.last_insert_rowid();
    let ev = fetch_event(&conn, user.id, id)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?
        .ok_or_else(|| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?;
    Ok((StatusCode::CREATED, Json(ev)).into_response())
}

pub async fn update_event(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Path(id): Path<i64>,
    Json(req): Json<UpdateEventRequest>,
) -> ApiResult {
    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let existing = fetch_event(&conn, user.id, id)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "日程不存在"))?;

    let new_title: Option<String> = match req.title.as_deref() {
        Some(t) => Some(validate_title(t).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?),
        None => None,
    };
    let new_starts: Option<String> = match req.starts_at.as_deref() {
        Some(s) => Some(validate_dt(s).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?),
        None => None,
    };
    let new_ends: Option<String> = match req.ends_at.as_deref() {
        Some(e) => Some(validate_dt(e).map_err(|m| err(StatusCode::BAD_REQUEST, &m))?),
        None => None,
    };
    let new_all_day: Option<i64> = req.all_day.map(|b| if b { 1 } else { 0 });
    let new_done: Option<i64> = req.done.map(|b| if b { 1 } else { 0 });

    // 校验 starts < ends 一致性（使用合并后的值）
    let eff_starts = new_starts
        .clone()
        .unwrap_or_else(|| existing.starts_at.clone());
    let eff_ends = new_ends.clone().or_else(|| existing.ends_at.clone());
    if let Some(e) = eff_ends {
        if e.as_str() < eff_starts.as_str() {
            return Err(err(StatusCode::BAD_REQUEST, "结束时间不能早于开始时间"));
        }
    }

    conn.execute(
        "UPDATE events SET \
            title = COALESCE(?1, title), \
            starts_at = COALESCE(?2, starts_at), \
            ends_at = COALESCE(?3, ends_at), \
            all_day = COALESCE(?4, all_day), \
            done = COALESCE(?5, done) \
         WHERE id = ?6 AND user_id = ?7",
        rusqlite::params![
            new_title,
            new_starts,
            new_ends,
            new_all_day,
            new_done,
            id,
            user.id
        ],
    )
    .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "更新失败"))?;

    let ev = fetch_event(&conn, user.id, id)
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "读取失败"))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "日程不存在"))?;
    Ok(Json(ev).into_response())
}

pub async fn delete_event(
    State(state): State<Arc<AppState>>,
    Extension(user): Extension<CurrentUser>,
    Path(id): Path<i64>,
) -> ApiResult {
    let conn = state
        .db
        .lock()
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "数据库忙"))?;
    let affected = conn
        .execute(
            "DELETE FROM events WHERE id = ?1 AND user_id = ?2",
            rusqlite::params![id, user.id],
        )
        .map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "删除失败"))?;
    if affected == 0 {
        return Err(err(StatusCode::NOT_FOUND, "日程不存在"));
    }
    Ok(StatusCode::NO_CONTENT.into_response())
}
