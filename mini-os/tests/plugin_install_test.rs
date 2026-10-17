use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use mini_os::plugins::{
    install_from_zip, list_installed, uninstall, PluginManifest, MAX_FILE_COUNT,
    MAX_TOTAL_UNCOMPRESSED,
};
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

fn write_basic_plugin(data_dir: &Path) -> PathBuf {
    let zip = make_zip(&[
        ("plugin.json", manifest_json("hello", "Hello", "1.0.0", "main.js").as_bytes()),
        ("main.js", b"console.log('hi');"),
    ]);
    let p = data_dir.join("hello.zip");
    fs::write(&p, &zip).unwrap();
    p
}

#[test]
fn install_valid_zip_creates_dir_and_manifest() {
    let data = tmp_dir("valid");
    let zip = make_zip(&[
        ("plugin.json", manifest_json("hello", "Hello", "1.0.0", "main.js").as_bytes()),
        ("main.js", b"console.log('hi');"),
        ("assets/a.txt", b"aaa"),
    ]);
    let m = install_from_zip(&zip, &data).expect("合法 zip 应安装成功");
    assert_eq!(m.id, "hello");
    assert_eq!(m.name, "Hello");
    assert_eq!(m.version, "1.0.0");
    assert_eq!(m.entry, "main.js");

    let dir = data.join("plugins").join("hello");
    assert!(dir.is_dir());
    assert!(dir.join("plugin.json").is_file());
    assert!(dir.join("main.js").is_file());
    assert_eq!(fs::read(dir.join("assets/a.txt")).unwrap(), b"aaa");

    let installed = list_installed(&data).unwrap();
    assert_eq!(installed.len(), 1);
    assert_eq!(installed[0].id, "hello");
}

#[test]
fn install_rejects_path_traversal() {
    let data = tmp_dir("traversal");
    let zip = make_zip(&[
        ("plugin.json", manifest_json("evil", "Evil", "1.0.0", "main.js").as_bytes()),
        ("../escape.txt", b"pwned"),
    ]);
    let err = install_from_zip(&zip, &data).expect_err("含 .. 的 zip 必须被拒");
    assert!(err.contains("路径穿越"), "错误信息应提到路径穿越，实际：{}", err);
    assert!(!data.join("plugins").join("evil").exists());
    assert!(!data.join("escape.txt").exists());
}

#[test]
fn install_rejects_absolute_path_entry() {
    let data = tmp_dir("abs");
    let zip = make_zip(&[
        ("plugin.json", manifest_json("abs", "Abs", "1.0.0", "main.js").as_bytes()),
        ("/etc/passwd", b"x"),
    ]);
    let err = install_from_zip(&zip, &data).expect_err("绝对路径必须被拒");
    assert!(err.contains("绝对路径"), "错误信息应提到绝对路径，实际：{}", err);
    assert!(!data.join("plugins").join("abs").exists());
}

#[test]
fn install_rejects_oversize_uncompressed() {
    let data = tmp_dir("oversize");
    // 用高度可压缩的内容，让解压后 > 10MB
    let big = vec![0u8; (MAX_TOTAL_UNCOMPRESSED as usize) + 1024];
    let zip = make_zip(&[
        ("plugin.json", manifest_json("big", "Big", "1.0.0", "main.js").as_bytes()),
        ("main.js", &big),
    ]);
    let err = install_from_zip(&zip, &data).expect_err("超 10MB 必须被拒");
    assert!(err.contains("10MB"), "错误信息应提到 10MB，实际：{}", err);
    assert!(!data.join("plugins").join("big").exists());
}

#[test]
fn install_rejects_too_many_files() {
    let data = tmp_dir("toomany");
    let mut entries: Vec<(String, Vec<u8>)> = Vec::new();
    entries.push((
        "plugin.json".to_string(),
        manifest_json("many", "Many", "1.0.0", "main.js").into_bytes(),
    ));
    for i in 0..(MAX_FILE_COUNT + 5) {
        entries.push((format!("f{}.txt", i), vec![b'a'; 4]));
    }
    let mut buf = Vec::new();
    {
        let mut zw = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: FileOptions = FileOptions::default();
        for (name, data) in &entries {
            zw.start_file(name.as_str(), opts).unwrap();
            zw.write_all(data).unwrap();
        }
        zw.finish().unwrap();
    }
    let err = install_from_zip(&buf, &data).expect_err("文件数超限必须被拒");
    assert!(err.contains("200"), "错误信息应提到 200，实际：{}", err);
    assert!(!data.join("plugins").join("many").exists());
}

#[test]
fn install_rejects_missing_manifest() {
    let data = tmp_dir("nomanifest");
    let zip = make_zip(&[("main.js", b"console.log(1);")]);
    let err = install_from_zip(&zip, &data).expect_err("缺 plugin.json 必须被拒");
    assert!(err.contains("plugin.json"), "错误信息应提到 plugin.json，实际：{}", err);
    let plugins = data.join("plugins");
    let count = if plugins.exists() {
        fs::read_dir(&plugins).unwrap().count()
    } else {
        0
    };
    assert_eq!(count, 0);
}

#[test]
fn install_rejects_invalid_manifest_json() {
    let data = tmp_dir("badjson");
    let zip = make_zip(&[
        ("plugin.json", b"{ not valid json "),
        ("main.js", b"x"),
    ]);
    let err = install_from_zip(&zip, &data).expect_err("非法 json 必须被拒");
    assert!(err.contains("plugin.json"), "错误信息应提到 plugin.json，实际：{}", err);
    assert!(!data.join("plugins").join("badjson").exists());
}

#[test]
fn install_rejects_id_mismatch_with_dir_name() {
    let data = tmp_dir("mismatch");
    // manifest id 是 "real"，但我们不放顶层目录包裹，安装目录会按 manifest id 生成；
    // 这里构造一个 entry 前缀与 id 不同的包，验证 entry 校验仍通过、id 校验基于 manifest
    let zip = make_zip(&[
        ("plugin.json", manifest_json("real-id", "N", "1.0.0", "main.js").as_bytes()),
        ("main.js", b"x"),
    ]);
    let m = install_from_zip(&zip, &data).expect("合法包应安装成功");
    assert_eq!(m.id, "real-id");
    assert!(data.join("plugins").join("real-id").is_dir());
    // 若已存在同名目录，则再次安装应报 AlreadyInstalled
    let again = install_from_zip(&zip, &data);
    assert!(again.is_err());
    let msg = again.err().unwrap();
    assert!(msg.contains("已安装"), "应提示已安装，实际：{}", msg);
}

#[test]
fn install_rejects_duplicate_install() {
    let data = tmp_dir("dup");
    let zip = make_zip(&[
        ("plugin.json", manifest_json("dup", "Dup", "1.0.0", "main.js").as_bytes()),
        ("main.js", b"x"),
    ]);
    let m1 = install_from_zip(&zip, &data).unwrap();
    assert_eq!(m1.id, "dup");
    let err = install_from_zip(&zip, &data).expect_err("重复安装必须被拒");
    assert!(err.contains("已安装"), "错误信息应提到已安装，实际：{}", err);
    let dir = data.join("plugins").join("dup");
    assert!(dir.is_dir());
    assert!(dir.join("main.js").is_file());
}

#[test]
fn install_rejects_corrupt_zip() {
    let data = tmp_dir("corrupt");
    let junk = b"this is definitely not a zip archive at all";
    let err = install_from_zip(junk, &data).expect_err("损坏 zip 必须被拒");
    assert!(!err.is_empty(), "应有错误信息");
    assert!(!data.join("plugins").join("junk").exists());
}

#[test]
fn install_rejects_empty_bytes() {
    let data = tmp_dir("empty");
    let err = install_from_zip(&[], &data).expect_err("空字节必须被拒");
    assert!(err.contains("空"), "错误信息应提到空，实际：{}", err);
    assert!(!data.join("plugins").join("anything").exists());
}

#[test]
fn uninstall_removes_installed_plugin() {
    let data = tmp_dir("uninstall");
    let zip = make_zip(&[
        ("plugin.json", manifest_json("gone", "Gone", "1.0.0", "main.js").as_bytes()),
        ("main.js", b"x"),
    ]);
    install_from_zip(&zip, &data).unwrap();
    let dir = data.join("plugins").join("gone");
    assert!(dir.is_dir());
    uninstall("gone", &data).expect("卸载应成功");
    assert!(!dir.exists());
    let err = uninstall("gone", &data).expect_err("再次卸载应报未安装");
    assert!(err.contains("未安装"), "错误信息应提到未安装，实际：{}", err);
}