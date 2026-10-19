//! RBAC：角色（admin/editor/viewer）与权限矩阵。

/// 系统角色。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    /// 管理员
    Admin,
    /// 编辑者
    Editor,
    /// 只读
    Viewer,
}

impl Role {
    /// 解析 DB/接口中的 role 字符串；大小写不敏感；非法返回 None。
    pub fn parse(s: &str) -> Option<Role> {
        match s.trim().to_ascii_lowercase().as_str() {
            "admin" => Some(Role::Admin),
            "editor" => Some(Role::Editor),
            "viewer" => Some(Role::Viewer),
            _ => None,
        }
    }

    /// 存 DB 的规范值："admin" | "editor" | "viewer"
    pub fn as_str(&self) -> &'static str {
        match self {
            Role::Admin => "admin",
            Role::Editor => "editor",
            Role::Viewer => "viewer",
        }
    }

    /// 中文展示名："管理员" | "编辑者" | "只读"
    pub fn display_name(&self) -> &'static str {
        match self {
            Role::Admin => "管理员",
            Role::Editor => "编辑者",
            Role::Viewer => "只读",
        }
    }
}

/// 系统权限项。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Permission {
    /// 文件读取
    FsRead,
    /// 文件写入
    FsWrite,
    /// 分享创建
    ShareCreate,
    /// 分享管理
    ShareManage,
    /// 用户管理
    UsersManage,
    /// 插件管理
    PluginManage,
}

impl Permission {
    /// 中文展示名："文件读取" | "文件写入" | "分享创建" | "分享管理" | "用户管理"
    pub fn display_name(&self) -> &'static str {
        match self {
            Permission::FsRead => "文件读取",
            Permission::FsWrite => "文件写入",
            Permission::ShareCreate => "分享创建",
            Permission::ShareManage => "分享管理",
            Permission::UsersManage => "用户管理",
            Permission::PluginManage => "插件管理",
        }
    }
}

/// 权限矩阵：Admin 有全部五项；Editor 有 FsRead、FsWrite、ShareCreate、ShareManage（仅自己创建的分享，
/// 归属校验在 handler 层做）；Viewer 仅 FsRead。
/// 说明：/api/settings 是按 user_id 隔离的个人设置（主题/壁纸），视为 FsRead 级，全体角色可读写自己的；
/// UsersManage 保留给未来的系统级设置与用户管理接口。
pub fn has_permission(role: &Role, perm: &Permission) -> bool {
    match role {
        Role::Admin => matches!(
            perm,
            Permission::FsRead
                | Permission::FsWrite
                | Permission::ShareCreate
                | Permission::ShareManage
                | Permission::UsersManage
                | Permission::PluginManage
        ),
        Role::Editor => matches!(
            perm,
            Permission::FsRead
                | Permission::FsWrite
                | Permission::ShareCreate
                | Permission::ShareManage
                | Permission::PluginManage
        ),
        Role::Viewer => matches!(perm, Permission::FsRead),
    }
}

/// 校验；Err 为中文 reason，格式示例：「需要「文件写入」权限，当前角色为「只读」」
pub fn require(role: &Role, perm: &Permission) -> Result<(), String> {
    if has_permission(role, perm) {
        Ok(())
    } else {
        Err(format!(
            "需要「{}」权限，当前角色为「{}」",
            perm.display_name(),
            role.display_name()
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ALL_PERMISSIONS: [Permission; 6] = [
        Permission::FsRead,
        Permission::FsWrite,
        Permission::ShareCreate,
        Permission::ShareManage,
        Permission::UsersManage,
        Permission::PluginManage,
    ];

    #[test]
    fn matrix_admin_has_all() {
        for perm in ALL_PERMISSIONS.iter() {
            assert!(
                has_permission(&Role::Admin, perm),
                "admin 应拥有权限 {:?}",
                perm
            );
        }
    }

    #[test]
    fn matrix_editor() {
        assert!(has_permission(&Role::Editor, &Permission::FsRead));
        assert!(has_permission(&Role::Editor, &Permission::FsWrite));
        assert!(has_permission(&Role::Editor, &Permission::ShareCreate));
        assert!(has_permission(&Role::Editor, &Permission::ShareManage));
        assert!(!has_permission(&Role::Editor, &Permission::UsersManage));
    }

    #[test]
    fn matrix_viewer() {
        assert!(has_permission(&Role::Viewer, &Permission::FsRead));
        assert!(!has_permission(&Role::Viewer, &Permission::FsWrite));
        assert!(!has_permission(&Role::Viewer, &Permission::ShareCreate));
        assert!(!has_permission(&Role::Viewer, &Permission::ShareManage));
        assert!(!has_permission(&Role::Viewer, &Permission::UsersManage));
    }

    #[test]
    fn parse_roundtrip() {
        assert_eq!(Role::parse("admin"), Some(Role::Admin));
        assert_eq!(Role::parse("editor"), Some(Role::Editor));
        assert_eq!(Role::parse("viewer"), Some(Role::Viewer));
        assert_eq!(Role::parse("ADMIN"), Some(Role::Admin));
        assert_eq!(Role::parse("boss"), None);
        assert_eq!(Role::parse(""), None);

        assert_eq!(Role::Admin.as_str(), "admin");
        assert_eq!(Role::Editor.as_str(), "editor");
        assert_eq!(Role::Viewer.as_str(), "viewer");
    }

    #[test]
    fn require_reason_mentions_permission_and_role() {
        let err_viewer =
            require(&Role::Viewer, &Permission::FsWrite).expect_err("viewer 不应拥有 FsWrite 权限");
        assert!(err_viewer.contains("文件写入"), "实际信息: {err_viewer}");
        assert!(err_viewer.contains("只读"), "实际信息: {err_viewer}");

        let err_editor = require(&Role::Editor, &Permission::UsersManage)
            .expect_err("editor 不应拥有 UsersManage 权限");
        assert!(err_editor.contains("用户管理"), "实际信息: {err_editor}");
        assert!(err_editor.contains("编辑者"), "实际信息: {err_editor}");
    }
}
