use mini_os::plugins::{PluginManifest, PluginRegistry};

fn manifest(id: &str) -> PluginManifest {
    PluginManifest {
        id: id.to_string(),
        name: format!("n-{}", id),
        version: "1.0.0".to_string(),
        entry: "/static/plugins/index.js".to_string(),
        description: String::new(),
        icon: String::new(),
        permissions: vec!["fs.read".to_string()],
    }
}

#[test]
fn register_ok_and_list() {
    let registry = PluginRegistry::new();
    registry.register(manifest("b-plugin")).unwrap();
    registry.register(manifest("a-plugin")).unwrap();
    let list = registry.list();
    assert_eq!(list.len(), 2);
    assert_eq!(list[0].id, "a-plugin");
    assert_eq!(list[1].id, "b-plugin");
}

#[test]
fn register_duplicate_id_err() {
    let registry = PluginRegistry::new();
    registry.register(manifest("dup")).unwrap();
    let err = registry.register(manifest("dup")).unwrap_err();
    assert!(err.contains("已存在"));
}

#[test]
fn register_invalid_manifest_err() {
    let registry = PluginRegistry::new();
    let mut m = manifest("valid");
    m.id = String::new();
    assert!(registry.register(m).is_err());
}

#[test]
fn unregister_ok_returns_manifest() {
    let registry = PluginRegistry::new();
    registry.register(manifest("target")).unwrap();
    let removed = registry.unregister("target").unwrap();
    assert_eq!(removed.id, "target");
    assert!(registry.list().is_empty());
}

#[test]
fn unregister_unknown_none() {
    let registry = PluginRegistry::new();
    assert!(registry.unregister("nope").is_none());
}

#[test]
fn unregister_twice_second_none() {
    let registry = PluginRegistry::new();
    registry.register(manifest("once")).unwrap();
    assert!(registry.unregister("once").is_some());
    assert!(registry.unregister("once").is_none());
}

#[test]
fn list_empty() {
    let registry = PluginRegistry::new();
    assert!(registry.list().is_empty());
}

#[test]
fn default_same_as_new() {
    let registry = PluginRegistry::default();
    assert!(registry.list().is_empty());
}
