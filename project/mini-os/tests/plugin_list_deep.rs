use mini_os::plugins::{install_from_zip, list_installed, uninstall};
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

fn manifest_json(id: &str) -> String {
    format!(
        r#"{{"id":"{}","name":"n-{}","version":"1.0.0","entry":"index.js","description":"d","icon":"x","permissions":["fs.read"]}}"#,
        id, id
    )
}

fn install_one(data_dir: &Path, id: &str) {
    let zip = make_zip(&[
        ("plugin.json", manifest_json(id).as_bytes()),
        ("index.js", b"console.log(1);"),
    ]);
    install_from_zip(&zip, data_dir).unwrap();
}

#[test]
fn list_empty_dir() {
    let dir = tmp_dir("list-empty");
    let list = list_installed(&dir).unwrap();
    assert!(list.is_empty());
}

#[test]
fn list_after_install() {
    let dir = tmp_dir("list-after-install");
    install_one(&dir, "alpha");
    install_one(&dir, "beta");
    let list = list_installed(&dir).unwrap();
    assert_eq!(list.len(), 2);
    let ids: Vec<String> = list.iter().map(|m| m.id.clone()).collect();
    assert!(ids.contains(&"alpha".to_string()));
    assert!(ids.contains(&"beta".to_string()));
}

#[test]
fn list_fields_roundtrip() {
    let dir = tmp_dir("list-fields");
    install_one(&dir, "gamma");
    let list = list_installed(&dir).unwrap();
    assert_eq!(list.len(), 1);
    let m = &list[0];
    assert_eq!(m.id, "gamma");
    assert_eq!(m.name, "n-gamma");
    assert_eq!(m.version, "1.0.0");
    assert_eq!(m.entry, "index.js");
    assert_eq!(m.permissions, vec!["fs.read".to_string()]);
}

#[test]
fn uninstall_ok() {
    let dir = tmp_dir("uninstall-ok");
    install_one(&dir, "delta");
    uninstall("delta", &dir).unwrap();
    assert!(!dir.join("plugins").join("delta").exists());
    let list = list_installed(&dir).unwrap();
    assert!(list.is_empty());
}

#[test]
fn uninstall_unknown_err() {
    let dir = tmp_dir("uninstall-unknown");
    let res = uninstall("nope", &dir);
    assert!(res.is_err());
}

#[test]
fn uninstall_twice() {
    let dir = tmp_dir("uninstall-twice");
    install_one(&dir, "epsilon");
    uninstall("epsilon", &dir).unwrap();
    let res = uninstall("epsilon", &dir);
    assert!(res.is_err());
}

#[test]
fn reinstall_after_uninstall() {
    let dir = tmp_dir("reinstall");
    install_one(&dir, "zeta");
    uninstall("zeta", &dir).unwrap();
    install_one(&dir, "zeta");
    let list = list_installed(&dir).unwrap();
    assert_eq!(list.len(), 1);
    assert_eq!(list[0].id, "zeta");
}

#[test]
fn list_ignores_stray() {
    let dir = tmp_dir("list-ignores-stray");
    let plugins_dir = dir.join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    fs::create_dir_all(plugins_dir.join("stray-dir")).unwrap();
    fs::write(plugins_dir.join("stray.txt"), b"hello").unwrap();
    let list = list_installed(&dir).unwrap();
    assert!(list.is_empty());
}
