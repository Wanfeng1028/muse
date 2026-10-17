use std::sync::Arc;
use std::thread;

use mini_os::plugins::PluginManifest;
use mini_os::plugins::{PluginRegistry, ALLOWED_PERMISSIONS, ENTRY_PREFIX};

fn manifest(id: &str) -> PluginManifest {
    PluginManifest {
        id: id.to_string(),
        name: "测试插件".to_string(),
        version: "1.0.0".to_string(),
        description: "用于测试的插件".to_string(),
        icon: "puzzle".to_string(),
        entry: "/static/plugins/test.js".to_string(),
        permissions: vec!["fs.read".to_string()],
    }
}

#[test]
fn register_valid_manifest_succeeds() {
    let reg = PluginRegistry::new();
    let m = manifest("hello-world");
    let result = reg.register(m.clone());
    assert!(result.is_ok(), "合法插件应注册成功，实际：{:?}", result);

    let list = reg.list();
    assert_eq!(list.len(), 1, "注册后列表应有 1 个插件");
    assert_eq!(list[0].id, "hello-world");
    assert_eq!(list[0].version, "1.0.0");
    assert_eq!(list[0].entry, "/static/plugins/test.js");
}

#[test]
fn register_empty_id_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("a");
    m.id = "".to_string();
    let err = reg.register(m).unwrap_err();
    assert!(err.contains("长度"), "错误信息应提到长度，实际：{}", err);
    assert_eq!(reg.list().len(), 0, "拒绝后注册表应保持为空");
}

#[test]
fn register_too_long_id_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("a");
    m.id = "a".repeat(33);
    let err = reg.register(m).unwrap_err();
    assert!(err.contains("长度"), "错误信息应提到长度，实际：{}", err);
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_id_with_illegal_char_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("a");
    m.id = "hello_world".to_string();
    let err = reg.register(m).unwrap_err();
    assert!(
        err.contains("只允许字母、数字和连字符"),
        "错误信息应提到字符限制，实际：{}",
        err
    );
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_id_boundary_32_ok() {
    let reg = PluginRegistry::new();
    let mut m = manifest("a");
    m.id = "a".repeat(32);
    assert!(reg.register(m).is_ok(), "32 字符 id 应被接受");
    assert_eq!(reg.list().len(), 1);
}

#[test]
fn register_invalid_version_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("ver-test");
    m.version = "1.0".to_string();
    let err = reg.register(m).unwrap_err();
    assert!(err.contains("semver"), "错误信息应提到 semver，实际：{}", err);
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_version_with_non_digit_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("ver-test");
    m.version = "1.0.x".to_string();
    let err = reg.register(m).unwrap_err();
    assert!(
        err.contains("每段必须是数字"),
        "错误信息应提到每段必须是数字，实际：{}",
        err
    );
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_version_with_leading_zero_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("ver-test");
    m.version = "01.0.0".to_string();
    let err = reg.register(m).unwrap_err();
    assert!(
        err.contains("前导零"),
        "错误信息应提到前导零，实际：{}",
        err
    );
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_invalid_entry_prefix_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("entry-test");
    m.entry = "/other/plugins/x.js".to_string();
    let err = reg.register(m).unwrap_err();
    assert!(
        err.contains(ENTRY_PREFIX),
        "错误信息应包含合法前缀 {}，实际：{}",
        ENTRY_PREFIX,
        err
    );
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_invalid_permission_rejected() {
    let reg = PluginRegistry::new();
    let mut m = manifest("perm-test");
    m.permissions = vec!["net.connect".to_string()];
    let err = reg.register(m).unwrap_err();
    assert!(
        err.contains("权限不合法"),
        "错误信息应提到权限不合法，实际：{}",
        err
    );
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn register_all_allowed_permissions_ok() {
    let reg = PluginRegistry::new();
    let mut m = manifest("perm-all");
    m.permissions = ALLOWED_PERMISSIONS
        .iter()
        .map(|s| s.to_string())
        .collect();
    assert!(reg.register(m).is_ok(), "三种白名单权限应全部接受");
    let list = reg.list();
    assert_eq!(list.len(), 1);
    assert_eq!(list[0].permissions.len(), 3);
}

#[test]
fn register_duplicate_id_rejected() {
    let reg = PluginRegistry::new();
    assert!(reg.register(manifest("dup")).is_ok());
    let err = reg.register(manifest("dup")).unwrap_err();
    assert!(
        err.contains("已存在"),
        "错误信息应提到已存在，实际：{}",
        err
    );
    assert_eq!(reg.list().len(), 1, "重复注册不应增加条目");
}

#[test]
fn unregister_existing_returns_manifest() {
    let reg = PluginRegistry::new();
    assert!(reg.register(manifest("bye")).is_ok());
    let removed = reg.unregister("bye");
    assert!(removed.is_some(), "卸载存在的插件应返回清单");
    assert_eq!(removed.unwrap().id, "bye");
    assert_eq!(reg.list().len(), 0, "卸载后列表应为空");
}

#[test]
fn unregister_missing_returns_none() {
    let reg = PluginRegistry::new();
    let removed = reg.unregister("nope");
    assert!(removed.is_none(), "卸载不存在的插件应返回 None");
    assert_eq!(reg.list().len(), 0);
}

#[test]
fn list_is_sorted_by_id() {
    let reg = PluginRegistry::new();
    assert!(reg.register(manifest("zebra")).is_ok());
    assert!(reg.register(manifest("alpha")).is_ok());
    assert!(reg.register(manifest("mango")).is_ok());
    let list = reg.list();
    assert_eq!(list.len(), 3);
    let ids: Vec<&str> = list.iter().map(|m| m.id.as_str()).collect();
    assert_eq!(ids, vec!["alpha", "mango", "zebra"]);
}

#[test]
fn concurrent_register_same_id_only_one_wins() {
    let reg = Arc::new(PluginRegistry::new());
    let mut handles = Vec::new();
    for _ in 0..8 {
        let reg = Arc::clone(&reg);
        handles.push(thread::spawn(move || reg.register(manifest("race")).is_ok()));
    }
    let mut ok_count = 0;
    for h in handles {
        if h.join().unwrap() {
            ok_count += 1;
        }
    }
    assert_eq!(ok_count, 1, "并发注册同一 id，应恰好一个成功");
    assert_eq!(reg.list().len(), 1, "最终列表应只有 1 个插件");
}

#[test]
fn concurrent_register_distinct_ids_all_succeed() {
    let reg = Arc::new(PluginRegistry::new());
    let mut handles = Vec::new();
    for i in 0..8 {
        let reg = Arc::clone(&reg);
        handles.push(thread::spawn(move || {
            let id = format!("plugin-{}", i);
            reg.register(manifest(&id)).is_ok()
        }));
    }
    for h in handles {
        assert!(h.join().unwrap(), "每个独立 id 都应注册成功");
    }
    assert_eq!(reg.list().len(), 8);
}
