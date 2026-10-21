use mini_os::plugins::{install_from_zip, list_installed, uninstall, PluginManifest};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use zip::write::FileOptions;

fn tmp_dir(tag: &str) -> PathBuf {
    let base = std::env::temp_dir().join(format!(
        "mini-os-plugin-test-{}-{}-{}",
        tag,
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&base).unwrap();
    base
}

fn make_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut zw = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: FileOptions =
            FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, data) in entries {
            zw.start_file(*name, opts).unwrap();
            zw.write_all(data).unwrap();
        }
        zw.finish().unwrap();
    }
    buf
}

fn manifest_json(id: &str, name: &str, version: &str, entry: &str) -> String {
    format!(
        r#"{{"id":"{}","name":"{}","version":"{}","entry":"{}","description":"demo","icon":"x","permissions":["fs.read"]}}"#,
        id, name, version, entry
    )
}

#[test]
fn install_basic_ok() {
    let dir = tmp_dir("basic");
    let manifest = manifest_json("test-plugin", "Test Plugin", "1.0.0", "index.js");
    let zip = make_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("index.js", b"console.log('hello');"),
    ]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_ok());
    let m = res.unwrap();
    assert_eq!(m.id, "test-plugin");
    let entry_path = dir.join("plugins").join("test-plugin").join("index.js");
    assert!(entry_path.exists());
}

#[test]
fn install_empty_zip_err() {
    let dir = tmp_dir("empty");
    let zip: Vec<u8> = Vec::new();
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_no_manifest_err() {
    let dir = tmp_dir("no-manifest");
    let zip = make_zip(&[("index.js", b"console.log('hello');")]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_bad_manifest_json_err() {
    let dir = tmp_dir("bad-json");
    let zip = make_zip(&[
        ("plugin.json", b"{not json"),
        ("index.js", b"console.log('hello');"),
    ]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_duplicate_id_err() {
    let dir = tmp_dir("dup-id");
    let manifest = manifest_json("test-plugin", "Test Plugin", "1.0.0", "index.js");
    let zip = make_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("index.js", b"console.log('hello');"),
    ]);
    let res1 = install_from_zip(&zip, &dir);
    assert!(res1.is_ok());
    let res2 = install_from_zip(&zip, &dir);
    assert!(res2.is_err());
    let err = res2.unwrap_err();
    assert!(err.contains("已安装") || err.contains("test-plugin"));
}

#[test]
fn install_id_with_slash_err() {
    let dir = tmp_dir("id-slash");
    let manifest = manifest_json("../evil", "Evil", "1.0.0", "index.js");
    let zip = make_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("index.js", b"console.log('hello');"),
    ]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_entry_not_js_err() {
    let dir = tmp_dir("entry-not-js");
    let manifest = manifest_json("test-plugin", "Test Plugin", "1.0.0", "index.html");
    let zip = make_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("index.html", b"<html></html>"),
    ]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_bad_permission_err() {
    let dir = tmp_dir("bad-perm");
    let manifest = r#"{"id":"test-plugin","name":"Test Plugin","version":"1.0.0","entry":"index.js","description":"demo","icon":"x","permissions":["root.access"]}"#;
    let zip = make_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("index.js", b"console.log('hello');"),
    ]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_duplicate_permission_err() {
    let dir = tmp_dir("dup-perm");
    let manifest = r#"{"id":"test-plugin","name":"Test Plugin","version":"1.0.0","entry":"index.js","description":"demo","icon":"x","permissions":["fs.read","fs.read"]}"#;
    let zip = make_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("index.js", b"console.log('hello');"),
    ]);
    let res = install_from_zip(&zip, &dir);
    assert!(res.is_err());
}

#[test]
fn install_missing_entry_file_currently_ok() {
    let dir = tmp_dir("missing-entry");
    let manifest = manifest_json("test-plugin", "Test Plugin", "1.0.0", "index.js");
    let zip = make_zip(&[("plugin.json", manifest.as_bytes())]);
    let res = install_from_zip(&zip, &dir);
    // 已知缺口：安装时不校验 entry 文件是否存在，缺失要到运行时才暴露
    assert!(res.is_ok());
}
