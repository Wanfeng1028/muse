//! 数据模型定义：与前端 JSON 交互的结构体统一使用 camelCase 命名。

use serde::{Deserialize, Serialize};

/// 虚拟文件系统节点（文件或文件夹）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Node {
    /// 节点主键
    pub id: i64,
    /// 父节点 id，根节点为 None
    pub parent_id: Option<i64>,
    /// 名称
    pub name: String,
    /// 类型：只取 "file" 或 "folder"
    pub kind: String,
    /// 文件内容（文件夹为空字符串；二进制文件在 JSON 中为空串，真实字节走下载接口）
    pub content: String,
    /// 创建时间
    pub created_at: String,
    /// 更新时间
    pub updated_at: String,
    /// 字节数（文件夹为 0）
    pub size: i64,
    /// MIME 类型（未设置时为 None）
    pub mime_type: Option<String>,
}

/// 创建节点请求体
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateNodeRequest {
    /// 父节点 id，缺省为根；与非空 parent 同时指定将返回 400
    pub parent_id: Option<i64>,
    /// 父节点路径（如 "/docs"），仅在 parent_id 缺省时解析
    pub parent: Option<String>,
    /// 名称
    pub name: String,
    /// 类型：只取 "file" 或 "folder"
    pub kind: String,
    /// 初始内容（可选）；与 bytes 同时指定非空内容时返回 400
    pub content: Option<String>,
    /// 二进制内容（JSON 数字数组）；提供时存入 content_blob；与非空 content 同时指定时返回 400，不再静默丢弃 content
    pub bytes: Option<Vec<u8>>,
}

/// 更新节点请求体
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateNodeRequest {
    /// 新名称（可选）
    pub name: Option<String>,
    /// 新内容（可选）
    pub content: Option<String>,
}

/// 设置项请求体
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingRequest {
    /// 设置键
    pub key: String,
    /// 设置值
    pub value: String,
}

/// 应用信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppInfo {
    /// 应用 id
    pub id: String,
    /// 应用名称
    pub name: String,
    /// 应用图标（emoji）
    pub icon: String,
    /// 应用描述
    pub description: String,
}

/// 统计信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Stats {
    /// 文件数量
    pub files: i64,
    /// 文件夹数量
    pub folders: i64,
    /// 所有文件内容总字节数
    pub total_bytes: i64,
}

/// 用户公开信息（永不含 password_hash）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UserInfo {
    /// 用户主键
    pub id: i64,
    /// 用户名
    pub username: String,
    /// 是否管理员
    pub is_admin: bool,
    /// 角色规范值 admin/editor/viewer
    pub role: String,
}

/// POST /api/auth/register 请求
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisterRequest {
    /// 用户名
    pub username: String,
    /// 密码
    pub password: String,
}

/// POST /api/auth/login 请求
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoginRequest {
    /// 用户名
    pub username: String,
    /// 密码
    pub password: String,
}

/// GET /api/auth/setup-needed 响应
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SetupNeededResponse {
    /// 是否需要进行初始设置
    pub needed: bool,
}

/// POST /api/shares 请求
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateShareRequest {
    /// 待分享的节点 id（file 模式必填）
    pub node_id: Option<i64>,
    /// 分享类型："file"（默认）或 "dir"；JSON 字段名为 type
    #[serde(rename = "type", default)]
    pub share_type: Option<String>,
    /// 目录分享时的 VFS 路径，如 "/docs"；dir 模式下 nodeId 与 path 不能同时指定（否则 400）；file 模式下非空 path 返回 400
    #[serde(default)]
    pub path: Option<String>,
    /// 过期时间（unix 秒），None 表示永不过期
    #[serde(default)]
    pub expires_at: Option<i64>,
}

/// POST /api/shares 响应
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShareCreated {
    /// 分享令牌
    pub token: String,
    /// 分享访问地址
    pub url: String,
    /// 过期时间（unix 秒），None 表示永不过期
    pub expires_at: Option<i64>,
}

/// GET /api/s/:token 响应（只读元信息）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShareInfo {
    /// 分享令牌
    pub token: String,
    /// 名称
    pub name: String,
    /// 类型：只取 "file" 或 "folder"
    pub kind: String,
    /// 字节数（目录分享时为子树内所有文件字节数之和）
    pub size: i64,
    /// MIME 类型（未设置时为 None）
    pub mime_type: Option<String>,
    /// 分享类型："file" 或 "dir"
    pub share_type: String,
}

/// GET /api/share/list 条目：目录分享内的一个文件/文件夹
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShareDirEntry {
    /// 名称
    pub name: String,
    /// 类型：只取 "file" 或 "folder"
    pub kind: String,
    /// 字节数（文件夹为 0）
    pub size: i64,
    /// 修改时间（updated_at）
    pub mtime: String,
}

/// GET /api/share/list 响应
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShareDirListing {
    /// 当前相对路径（"" 表示分享根）
    pub path: String,
    /// 条目列表（文件夹在前，各按名称排序）
    pub entries: Vec<ShareDirEntry>,
}

/// 用户管理列表项
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UserWithRole {
    /// 用户主键
    pub id: i64,
    /// 用户名
    pub username: String,
    /// 是否管理员
    pub is_admin: bool,
    /// 角色规范值 admin/editor/viewer
    pub role: String,
    /// 创建时间
    pub created_at: String,
}

/// PUT /api/users/{id}/role 请求体
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SetRoleRequest {
    /// 角色规范值 admin/editor/viewer
    pub role: String,
}

/// 速记便签
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Note {
    pub id: i64,
    pub user_id: i64,
    pub title: String,
    pub body: String,
    /// DB 中为 INTEGER 0/1，读写时用 `r.get::<_, i64>(i)? == 1` 转 bool，写时用 `if pinned {1} else {0}`。
    pub pinned: bool,
    pub updated_at: String,
}

/// 日程事件
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CalEvent {
    pub id: i64,
    pub user_id: i64,
    pub title: String,
    /// ISO8601 本地时间字符串，如 "2026-10-20T09:00:00"
    pub starts_at: String,
    pub ends_at: Option<String>,
    /// DB 中为 INTEGER 0/1，读写时用 `r.get::<_, i64>(i)? == 1` 转 bool，写时用 `if all_day {1} else {0}`。
    pub all_day: bool,
    /// DB 中为 INTEGER 0/1，读写时用 `r.get::<_, i64>(i)? == 1` 转 bool，写时用 `if done {1} else {0}`。
    pub done: bool,
    pub created_at: String,
}

/// GET /api/shares 条目（含归属信息，仅管理员/创建者可见）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShareAdminItem {
    /// 分享行主键
    pub id: i64,
    /// 分享令牌
    pub token: String,
    /// 分享类型 file/dir
    pub share_type: String,
    /// 创建者用户 id
    pub owner_id: i64,
    /// 创建者用户名
    pub owner_username: String,
    /// 被分享节点名
    pub node_name: String,
    /// 创建时间
    pub created_at: String,
    /// 过期时间（unix 秒），None 表示永不过期
    pub expires_at: Option<i64>,
}
