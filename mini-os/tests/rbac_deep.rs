use mini_os::rbac::{has_permission, require, Permission, Role};

const ALL_PERMISSIONS: [Permission; 5] = [
    Permission::FsRead,
    Permission::FsWrite,
    Permission::ShareCreate,
    Permission::ShareManage,
    Permission::UsersManage,
];

#[test]
fn parse_trims_whitespace_and_ignores_case() {
    assert_eq!(Role::parse("  ADMIN  "), Some(Role::Admin));
    assert_eq!(Role::parse("\tEditor\n"), Some(Role::Editor));
    assert_eq!(Role::parse("Viewer"), Some(Role::Viewer));
    assert_eq!(Role::parse("aDmIn"), Some(Role::Admin));
}

#[test]
fn parse_rejects_illegal_and_edge_strings() {
    assert_eq!(Role::parse(""), None);
    assert_eq!(Role::parse("   "), None);
    assert_eq!(Role::parse("root"), None);
    assert_eq!(Role::parse("admin "), Some(Role::Admin));
    assert_eq!(Role::parse("admin\u{200b}"), None);
    assert_eq!(Role::parse("管理员"), None);
}

#[test]
fn parse_does_not_panic_on_long_or_unicode_input() {
    let long_name = "x".repeat(100_000);
    assert_eq!(Role::parse(&long_name), None);

    let long_valid = format!("  {}admin{}  ", " ".repeat(50_000), " ".repeat(50_000));
    assert_eq!(Role::parse(&long_valid), Some(Role::Admin));

    let chinese = "管".repeat(4096);
    assert_eq!(Role::parse(&chinese), None);
}

#[test]
fn as_str_roundtrip_for_all_roles() {
    for role in [Role::Admin, Role::Editor, Role::Viewer] {
        let s = role.as_str();
        assert_eq!(
            Role::parse(s),
            Some(role),
            "as_str 输出应能被 parse 还原: {s}"
        );
        assert!(
            s.chars().all(|c| c.is_ascii_lowercase()),
            "as_str 必须是纯小写 ASCII: {s}"
        );
    }
    assert_eq!(Role::Admin.as_str(), "admin");
    assert_eq!(Role::Editor.as_str(), "editor");
    assert_eq!(Role::Viewer.as_str(), "viewer");
}

#[test]
fn display_name_is_chinese_for_all_roles_and_permissions() {
    assert_eq!(Role::Admin.display_name(), "管理员");
    assert_eq!(Role::Editor.display_name(), "编辑者");
    assert_eq!(Role::Viewer.display_name(), "只读");

    assert_eq!(Permission::FsRead.display_name(), "文件读取");
    assert_eq!(Permission::FsWrite.display_name(), "文件写入");
    assert_eq!(Permission::ShareCreate.display_name(), "分享创建");
    assert_eq!(Permission::ShareManage.display_name(), "分享管理");
    assert_eq!(Permission::UsersManage.display_name(), "用户管理");
}

#[test]
fn admin_has_every_permission() {
    for perm in ALL_PERMISSIONS.iter() {
        assert!(
            has_permission(&Role::Admin, perm),
            "admin 应拥有权限 {:?}",
            perm
        );
    }
    assert_eq!(ALL_PERMISSIONS.len(), 5);
}

#[test]
fn editor_has_all_except_users_manage() {
    assert!(has_permission(&Role::Editor, &Permission::FsRead));
    assert!(has_permission(&Role::Editor, &Permission::FsWrite));
    assert!(has_permission(&Role::Editor, &Permission::ShareCreate));
    assert!(has_permission(&Role::Editor, &Permission::ShareManage));
    assert!(!has_permission(&Role::Editor, &Permission::UsersManage));
}

#[test]
fn viewer_only_reads_files() {
    assert!(has_permission(&Role::Viewer, &Permission::FsRead));
    assert!(!has_permission(&Role::Viewer, &Permission::FsWrite));
    assert!(!has_permission(&Role::Viewer, &Permission::ShareCreate));
    assert!(!has_permission(&Role::Viewer, &Permission::ShareManage));
    assert!(!has_permission(&Role::Viewer, &Permission::UsersManage));
}

#[test]
fn require_ok_returns_unit_without_error_message() {
    let ok_read = require(&Role::Viewer, &Permission::FsRead);
    assert!(ok_read.is_ok(), "viewer 读文件应通过: {ok_read:?}");

    let ok_admin = require(&Role::Admin, &Permission::UsersManage);
    assert!(ok_admin.is_ok(), "admin 管理用户应通过: {ok_admin:?}");
}

#[test]
fn require_error_message_names_permission_and_role() {
    let err_viewer =
        require(&Role::Viewer, &Permission::FsWrite).expect_err("viewer 不应拥有 FsWrite 权限");
    assert_eq!(err_viewer, "需要「文件写入」权限，当前角色为「只读」");

    let err_editor = require(&Role::Editor, &Permission::UsersManage)
        .expect_err("editor 不应拥有 UsersManage 权限");
    assert_eq!(err_editor, "需要「用户管理」权限，当前角色为「编辑者」");

    let err_viewer_share =
        require(&Role::Viewer, &Permission::ShareCreate).expect_err("viewer 不应拥有 ShareCreate");
    assert!(err_viewer_share.contains("分享创建"));
    assert!(err_viewer_share.contains("只读"));
}

#[test]
fn permission_matrix_is_consistent_between_has_permission_and_require() {
    let roles = [Role::Admin, Role::Editor, Role::Viewer];
    for role in roles.iter() {
        for perm in ALL_PERMISSIONS.iter() {
            let allowed = has_permission(role, perm);
            let checked = require(role, perm);
            assert_eq!(
                allowed,
                checked.is_ok(),
                "has_permission 与 require 结果必须一致 role={:?} perm={:?}",
                role,
                perm
            );
            if let Err(reason) = checked {
                assert!(
                    reason.contains(perm.display_name()),
                    "错误信息应包含权限名 {:?}: {reason}",
                    perm
                );
                assert!(
                    reason.contains(role.display_name()),
                    "错误信息应包含角色名 {:?}: {reason}",
                    role
                );
            }
        }
    }
}

#[test]
fn concurrent_permission_checks_are_stable() {
    use std::sync::Arc;
    use std::thread;

    let roles: Arc<Vec<Role>> = Arc::new(vec![Role::Admin, Role::Editor, Role::Viewer]);
    let mut handles = Vec::new();

    for _ in 0..8 {
        let roles = Arc::clone(&roles);
        handles.push(thread::spawn(move || {
            let mut results = Vec::new();
            for _ in 0..1000 {
                for role in roles.iter() {
                    for perm in ALL_PERMISSIONS.iter() {
                        results.push((*role, *perm, has_permission(role, perm)));
                    }
                }
            }
            results
        }));
    }

    let mut all = Vec::new();
    for handle in handles {
        let batch = handle.join().expect("线程不应 panic");
        all.push(batch);
    }

    for batch in all.iter() {
        for (role, perm, allowed) in batch.iter() {
            let expected = match role {
                Role::Admin => true,
                Role::Editor => !matches!(perm, Permission::UsersManage),
                Role::Viewer => matches!(perm, Permission::FsRead),
            };
            assert_eq!(
                *allowed, expected,
                "并发下权限结果应稳定 role={:?} perm={:?}",
                role, perm
            );
        }
    }
}

#[test]
fn concurrent_parse_and_require_share_one_source_of_truth() {
    use std::sync::Arc;
    use std::thread;

    let inputs: Arc<Vec<String>> = Arc::new(vec![
        "admin".to_string(),
        "  EDITOR ".to_string(),
        "Viewer".to_string(),
        "root".to_string(),
        "".to_string(),
        "管".repeat(64),
    ]);

    let mut handles = Vec::new();
    for _ in 0..6 {
        let inputs = Arc::clone(&inputs);
        handles.push(thread::spawn(move || {
            let mut parsed = Vec::new();
            for s in inputs.iter() {
                parsed.push((s.clone(), Role::parse(s)));
            }
            parsed
        }));
    }

    for handle in handles {
        let parsed = handle.join().expect("线程不应 panic");
        for (raw, role) in parsed.iter() {
            match role {
                Some(Role::Admin) => assert_eq!(Role::parse(raw), Some(Role::Admin)),
                Some(Role::Editor) => assert_eq!(Role::parse(raw), Some(Role::Editor)),
                Some(Role::Viewer) => assert_eq!(Role::parse(raw), Some(Role::Viewer)),
                None => assert!(Role::parse(raw).is_none(), "非法输入应稳定返回 None"),
            }
            if let Some(r) = role {
                let check = require(r, &Permission::FsRead);
                assert!(
                    check.is_ok(),
                    "任何合法角色都能读文件 role={:?} raw={raw}",
                    r
                );
            }
        }
    }
}