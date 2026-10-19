use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use mini_os::plugins::{
    install_from_zip, list_installed, uninstall, PluginManifest, PluginRegistry,
};

fn work_dir(tag: &str) -> PathBuf {
    let dir =
        std::env::temp_dir().join(format!("mini_os_plug_deep3_{}_{}", std::process::id(), tag));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn cleanup(dir: &Path) {
    let _ = fs::remove_dir_all(dir);
}

fn manifest_json(id: &str, name: &str, version: &str, entry: &str) -> String {
    format!(
        r#"{{"id":"{}","name":"{}","version":"{}","entry":"{}"}}"#,
        id, name, version, entry
    )
}

fn build_zip(files: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = std::io::Cursor::new(Vec::new());
    {
        let mut w = zip::ZipWriter::new(&mut buf);
        for (name, data) in files {
            w.start_file(
                *name,
                zip::write::FileOptions::default()
                    .compression_method(zip::CompressionMethod::Deflated),
            )
            .unwrap();
            w.write_all(data).unwrap();
        }
        w.finish().unwrap();
    }
    buf.into_inner()
}

fn build_zip_str(files: &[(&str, &str)]) -> Vec<u8> {
    let owned: Vec<(&str, &[u8])> = files.iter().map(|(n, s)| (*n, s.as_bytes())).collect();
    build_zip(&owned)
}

fn demo_zip(id: &str) -> Vec<u8> {
    let manifest = manifest_json(id, "Demo", "1.0.0", "main.js");
    build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('hi');"),
    ])
}

#[test]
fn install_success_full_flow() {
    let dir = work_dir("success_flow");
    let manifest = manifest_json("demo1", "Demo One", "1.0.0", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('main');"),
        ("js/util.js", "export const x = 1;"),
    ]);

    let m = install_from_zip(&bytes, &dir).expect("install should succeed");
    assert_eq!(m.id, "demo1");

    let base = dir.join("plugins").join("demo1");
    assert!(base.join("plugin.json").exists());
    assert!(base.join("main.js").exists());
    assert!(base.join("js").join("util.js").exists());

    let listed = list_installed(&dir).unwrap();
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].id, "demo1");

    cleanup(&dir);
}

#[test]
fn install_empty_bytes_err() {
    let dir = work_dir("empty_bytes");
    let err = install_from_zip(b"", &dir).unwrap_err();
    assert!(err.contains("空"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_garbage_bytes_err() {
    let dir = work_dir("garbage_bytes");
    let result = install_from_zip(b"not-a-zip-at-all-not-a-zip-at-all", &dir);
    assert!(result.is_err());
    cleanup(&dir);
}

#[test]
fn install_missing_manifest_err() {
    let dir = work_dir("missing_manifest");
    let bytes = build_zip_str(&[("main.js", "console.log('x');")]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(
        err.contains("缺少 plugin.json"),
        "unexpected error: {}",
        err
    );
    cleanup(&dir);
}

#[test]
fn install_manifest_invalid_json_err() {
    let dir = work_dir("invalid_json");
    let bytes = build_zip_str(&[("plugin.json", "{bad json")]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("解析失败"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_manifest_id_with_slash_err() {
    let dir = work_dir("id_slash");
    let manifest = manifest_json("a/b", "Bad", "1.0.0", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('x');"),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("非法字符"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_manifest_id_with_dotdot_err() {
    let dir = work_dir("id_dotdot");
    let manifest = manifest_json("a..b", "Bad", "1.0.0", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('x');"),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("非法字符"), "unexpected error: {}", err);

    // 对照组：id "a.b" 正常安装成功
    let ok_manifest = manifest_json("a.b", "Ok", "1.0.0", "main.js");
    let ok_bytes = build_zip_str(&[
        ("plugin.json", ok_manifest.as_str()),
        ("main.js", "console.log('x');"),
    ]);
    let m = install_from_zip(&ok_bytes, &dir).expect("a.b should install");
    assert_eq!(m.id, "a.b");

    cleanup(&dir);
}

#[test]
fn install_manifest_empty_name_err() {
    let dir = work_dir("empty_name");
    let manifest = manifest_json("demo", "", "1.0.0", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('x');"),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("name"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_manifest_empty_version_err() {
    let dir = work_dir("empty_version");
    let manifest = manifest_json("demo", "Demo", "", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('x');"),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("version"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_manifest_empty_entry_err() {
    let dir = work_dir("empty_entry");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('x');"),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("entry"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_entry_dotdot_err() {
    let dir = work_dir("entry_dotdot");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "../evil.js");
    let bytes = build_zip_str(&[("plugin.json", manifest.as_str())]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("路径穿越"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_entry_absolute_err() {
    let dir = work_dir("entry_absolute");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "/abs.js");
    let bytes = build_zip_str(&[("plugin.json", manifest.as_str())]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("绝对路径"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_entry_windows_drive_err() {
    let dir = work_dir("entry_drive");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "C:/evil.js");
    let bytes = build_zip_str(&[("plugin.json", manifest.as_str())]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("绝对路径"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_entry_backslash_single_component_ok() {
    // 文档化平台行为：在 Linux 上 "a\\b.js" 是单个 Normal 分量，因此可正常安装。
    let dir = work_dir("entry_backslash");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "a\\b.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("a\\b.js", "console.log('x');"),
    ]);
    let m = install_from_zip(&bytes, &dir).expect("single backslash component ok");
    assert_eq!(m.id, "demo");
    let base = dir.join("plugins").join("demo");
    assert!(base.join("a\\b.js").exists());
    cleanup(&dir);
}

#[test]
fn install_entry_dot_segments_ok() {
    let dir = work_dir("entry_dot_segments");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "./x.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("./x.js", "console.log('x');"),
        ("sub/./y.js", "console.log('y');"),
    ]);
    let m = install_from_zip(&bytes, &dir).expect("dot segments ok");
    assert_eq!(m.id, "demo");
    let base = dir.join("plugins").join("demo");
    assert!(base.join("x.js").exists());
    assert!(base.join("sub").join("y.js").exists());
    cleanup(&dir);
}

#[test]
fn install_too_many_files_err() {
    let dir = work_dir("too_many_files");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let mut files: Vec<(String, String)> = Vec::new();
    files.push(("plugin.json".to_string(), manifest.clone()));
    for i in 0..201 {
        files.push((format!("f{}.js", i), "x".to_string()));
    }
    let owned: Vec<(&str, &[u8])> = files
        .iter()
        .map(|(n, s)| (n.as_str(), s.as_bytes()))
        .collect();
    let bytes = build_zip(&owned);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("200"), "unexpected error: {}", err);

    // 对照组：199 个小文件 + plugin.json = 200 文件 → Ok
    let dir2 = work_dir("exactly_max_files");
    let mut files2: Vec<(String, String)> = Vec::new();
    files2.push(("plugin.json".to_string(), manifest.clone()));
    for i in 0..199 {
        files2.push((format!("f{}.js", i), "x".to_string()));
    }
    let owned2: Vec<(&str, &[u8])> = files2
        .iter()
        .map(|(n, s)| (n.as_str(), s.as_bytes()))
        .collect();
    let bytes2 = build_zip(&owned2);
    let m = install_from_zip(&bytes2, &dir2).expect("200 files should succeed");
    assert_eq!(m.id, "demo");

    cleanup(&dir);
    cleanup(&dir2);
}

#[test]
fn install_oversize_err() {
    let dir = work_dir("oversize");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let big = vec![0u8; 10 * 1024 * 1024 + 1];
    let bytes = build_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("big.bin", big.as_slice()),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("10MB"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn install_twice_second_already_installed() {
    let dir = work_dir("install_twice");
    let bytes = demo_zip("demo1");
    install_from_zip(&bytes, &dir).expect("first install ok");
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("已安装"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn uninstall_success() {
    let dir = work_dir("uninstall_ok");
    let bytes = demo_zip("demo1");
    install_from_zip(&bytes, &dir).expect("install ok");
    assert!(dir.join("plugins").join("demo1").exists());

    uninstall("demo1", &dir).expect("uninstall ok");
    assert!(!dir.join("plugins").join("demo1").exists());

    let listed = list_installed(&dir).unwrap();
    assert!(listed.is_empty());
    cleanup(&dir);
}

#[test]
fn uninstall_not_installed_err() {
    let dir = work_dir("uninstall_missing");
    fs::create_dir_all(dir.join("plugins")).unwrap();
    let err = uninstall("ghost", &dir).unwrap_err();
    assert!(err.contains("未安装"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn uninstall_illegal_id_err() {
    let dir = work_dir("uninstall_illegal");
    fs::create_dir_all(dir.join("plugins")).unwrap();

    let err1 = uninstall("../x", &dir).unwrap_err();
    assert!(err1.contains("非法"), "unexpected error: {}", err1);

    let err2 = uninstall("", &dir).unwrap_err();
    assert!(err2.contains("非法"), "unexpected error: {}", err2);

    cleanup(&dir);
}

#[test]
fn list_installed_empty_when_no_plugins_dir() {
    let dir = work_dir("list_empty");
    let listed = list_installed(&dir).unwrap();
    assert!(listed.is_empty());
    cleanup(&dir);
}

#[test]
fn list_installed_skips_tmp_and_broken() {
    let dir = work_dir("list_skip");
    let root = dir.join("plugins");
    fs::create_dir_all(&root).unwrap();

    // .tmp-xyz 目录：含合法 plugin.json，但应被跳过
    let tmp = root.join(".tmp-xyz");
    fs::create_dir_all(&tmp).unwrap();
    let good = manifest_json("xyz", "Tmp", "1.0.0", "main.js");
    fs::write(tmp.join("plugin.json"), good).unwrap();

    // broken 目录：无 plugin.json
    fs::create_dir_all(root.join("broken")).unwrap();

    // 普通文件
    fs::write(root.join("x.txt"), b"hello").unwrap();

    let listed = list_installed(&dir).unwrap();
    assert!(listed.is_empty(), "expected empty, got {:?}", listed);

    cleanup(&dir);
}

#[test]
fn registry_register_list_unregister() {
    let reg = PluginRegistry::new();
    assert!(reg.list().is_empty());

    let m = PluginManifest {
        id: "demo".into(),
        name: "Demo".into(),
        version: "1.0.0".into(),
        entry: "/static/plugins/demo/main.js".into(),
        description: String::new(),
        icon: String::new(),
        permissions: vec![],
    };
    reg.register(m.clone()).expect("register ok");
    let listed = reg.list();
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].id, "demo");

    let err = reg.register(m.clone()).unwrap_err();
    assert!(err.contains("已存在"), "unexpected error: {}", err);

    let removed = reg.unregister("demo");
    assert_eq!(removed, Some(m));
    assert!(reg.list().is_empty());

    assert_eq!(reg.unregister("demo"), None);
}

#[test]
fn manifest_optional_fields_default() {
    let dir = work_dir("optional_default");
    let bytes = demo_zip("demo1");
    let m = install_from_zip(&bytes, &dir).expect("install ok");
    assert_eq!(m.description, "");
    assert_eq!(m.icon, "");
    assert!(m.permissions.is_empty());
    cleanup(&dir);
}

#[test]
fn install_entry_uppercase_js_err() {
    // 文档化大小写敏感：entry 必须以小写 ".js" 结尾。
    let dir = work_dir("entry_uppercase");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "MAIN.JS");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("MAIN.JS", "console.log('x');"),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains(".js"), "unexpected error: {}", err);
    cleanup(&dir);
}

#[test]
fn uninstall_then_reinstall_ok() {
    let dir = work_dir("reinstall");
    let bytes = demo_zip("demo1");
    install_from_zip(&bytes, &dir).expect("first install ok");
    uninstall("demo1", &dir).expect("uninstall ok");

    let m = install_from_zip(&bytes, &dir).expect("reinstall ok");
    assert_eq!(m.id, "demo1");
    let listed = list_installed(&dir).unwrap();
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].id, "demo1");

    cleanup(&dir);
}
