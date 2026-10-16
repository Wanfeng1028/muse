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
    /// 父节点 id，缺省为根
    pub parent_id: Option<i64>,
    /// 名称
    pub name: String,
    /// 类型：只取 "file" 或 "folder"
    pub kind: String,
    /// 初始内容（可选）
    pub content: Option<String>,
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
    /// 待分享的节点 id
    pub node_id: i64,
}

/// POST /api/shares 响应
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShareCreated {
    /// 分享令牌
    pub token: String,
    /// 分享访问地址
    pub url: String,
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
    /// 字节数
    pub size: i64,
    /// MIME 类型（未设置时为 None）
    pub mime_type: Option<String>,
}
