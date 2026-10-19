// 测试依据（A 组：安装失败回滚）：
//   install_from_zip / install_from_zip_inner 的真实流程：
//   先扫描（validate_entry_name / 大小 / 数量 / manifest），
//   再检查 target_dir.exists() -> AlreadyInstalled，
//   再建 .tmp-<id>-<pid> 临时目录，解压中途失败走 Io("建目录失败 ...") 等分支并 remove_dir_all(tmp_dir)，
//   最后 rename。
// 测试依据（B 组：恶意 zip 防护）：
//   validate_entry_name（ParentDir / RootDir / Prefix / 盘符 / starts_with('/') / starts_with('\\') / 空 / NUL）
//   与 safe_join 的真实行为；MAX_TOTAL_UNCOMPRESSED = 10 * 1024 * 1024。
//
// 关于 B5 的说明：zip::ZipWriter::start_file 在构造期对含 NUL 的名字会报错，
// 无法构造出含 NUL 条目名的 zip，因此删掉 B5 的测试（见下方注释）。

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

/// 判断 plugins 目录下是否存在以 ".tmp-" 开头的目录/文件。
fn has_tmp_leftover(plugins_root: &Path) -> bool {
    if !plugins_root.exists() {
        return false;
    }
    let rd = match fs::read_dir(plugins_root) {
        Ok(rd) => rd,
        Err(_) => return false,
    };
    for entry in rd {
        let entry = match entry {
            Ok(e) => e,
            Err(_) => continue,
        };
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with(".tmp-") {
            return true;
        }
    }
    false
}

// ---------------------------------------------------------------------------
// A 组：安装失败回滚
// ---------------------------------------------------------------------------

// A1：文件-目录名冲突，解压中途 create_dir_all 失败，走 Io("建目录失败 ...")，
// 随后 remove_dir_all(tmp_dir)。断言没有 plugins/demo，也没有 .tmp- 残留。
#[test]
fn a1_file_dir_conflict_rolls_back() {
    let dir = work_dir("a1_file_dir_conflict");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    // 顺序：先 "a" 写成文件，再 "a/b.js" 需要把 "a" 当目录 → create_dir_all 失败
    let bytes = build_zip_str(&[
        ("a", "x"),
        ("a/b.js", "y"),
        ("plugin.json", manifest.as_str()),
        ("main.js", "console.log('m');"),
    ]);

    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("建目录失败"), "unexpected error: {}", err);

    let plugins_root = dir.join("plugins");
    assert!(
        !plugins_root.join("demo").exists(),
        "plugins/demo should not exist after rollback"
    );
    assert!(
        !has_tmp_leftover(&plugins_root),
        "no .tmp- leftover expected, dir listing: {:?}",
        fs::read_dir(&plugins_root).map(|rd| rd
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect::<Vec<_>>())
    );

    let listed = list_installed(&dir).unwrap();
    assert!(listed.is_empty(), "expected empty, got {:?}", listed);

    cleanup(&dir);
}

// A2：扫描校验发生在 target_dir.exists() 之前。
// 第二次用同 id 但含 "../evil.js" 的包，应报"路径穿越"而不是"已安装"；
// 旧插件目录内容必须原样，且无 .tmp- 残留。
#[test]
fn a2_scan_validation_before_already_installed() {
    let dir = work_dir("a2_scan_before_exists");

    let ok_bytes = demo_zip("demo");
    install_from_zip(&ok_bytes, &dir).expect("first install ok");

    let base = dir.join("plugins").join("demo");
    let main_before = fs::read(base.join("main.js")).unwrap();

    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let bad_bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("../evil.js", "console.log('evil');"),
    ]);
    let err = install_from_zip(&bad_bytes, &dir).unwrap_err();
    assert!(
        err.contains("路径穿越"),
        "expected path traversal error, got: {}",
        err
    );
    assert!(
        !err.contains("已安装"),
        "should not report already installed, got: {}",
        err
    );

    let main_after = fs::read(base.join("main.js")).unwrap();
    assert_eq!(
        main_before, main_after,
        "old plugin main.js must stay untouched"
    );

    let plugins_root = dir.join("plugins");
    assert!(
        !has_tmp_leftover(&plugins_root),
        "no .tmp- leftover expected"
    );

    cleanup(&dir);
}

// A3：重复安装同 id 合法包 → AlreadyInstalled，在建临时目录之前返回，无 .tmp- 残留。
#[test]
fn a3_already_installed_no_tmp_leftover() {
    let dir = work_dir("a3_already_installed");
    let bytes = demo_zip("demo");
    install_from_zip(&bytes, &dir).expect("first install ok");

    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("已安装"), "unexpected error: {}", err);

    let plugins_root = dir.join("plugins");
    assert!(
        !has_tmp_leftover(&plugins_root),
        "no .tmp- leftover expected"
    );

    cleanup(&dir);
}

// A4：manifest 缺 entry 字段 → 扫描阶段 validate_manifest 报 "entry"；
// plugins/demo 不存在，无 .tmp- 残留。
#[test]
fn a4_manifest_missing_entry_no_leftover() {
    let dir = work_dir("a4_missing_entry");
    // 缺 entry 字段
    let manifest = r#"{"id":"demo","name":"Demo","version":"1.0.0"}"#;
    let bytes = build_zip_str(&[("plugin.json", manifest), ("main.js", "console.log('m');")]);

    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("entry"), "unexpected error: {}", err);

    let plugins_root = dir.join("plugins");
    assert!(
        !plugins_root.join("demo").exists(),
        "plugins/demo should not exist"
    );
    assert!(
        !has_tmp_leftover(&plugins_root),
        "no .tmp- leftover expected"
    );

    cleanup(&dir);
}

// ---------------------------------------------------------------------------
// B 组：恶意 zip 防护
// ---------------------------------------------------------------------------

// B1：条目 "../evil.js" 在扫描阶段被 validate_entry_name 拒绝（ParentDir），
// 此时 create_dir_all(plugins_root) 还没执行，plugins 目录根本不存在。
#[test]
fn b1_dotdot_entry_rejected_no_plugins_dir() {
    let dir = work_dir("b1_dotdot");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("../evil.js", "console.log('evil');"),
    ]);

    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("路径穿越"), "unexpected error: {}", err);

    let plugins_root = dir.join("plugins");
    assert!(
        !plugins_root.exists(),
        "plugins dir should not exist, scan rejected before create_dir_all"
    );

    cleanup(&dir);
}

// B2：条目 "a/../../evil.js" 含 ParentDir，validate_entry_name 报"路径穿越"。
#[test]
fn b2_nested_dotdot_entry_rejected() {
    let dir = work_dir("b2_nested_dotdot");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let bytes = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("a/../../evil.js", "console.log('evil');"),
    ]);

    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("路径穿越"), "unexpected error: {}", err);

    cleanup(&dir);
}

// B3：绝对路径 "/abs/x.js" 与 UNC 路径 "\\\\server\\x.js"。
// validate_entry_name 的 raw.starts_with('/') 与 raw.starts_with('\\') 分支分别命中。
#[test]
fn b3_absolute_and_unc_rejected() {
    let dir = work_dir("b3_absolute_unc");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");

    let bytes_abs = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("/abs/x.js", "console.log('x');"),
    ]);
    let err_abs = install_from_zip(&bytes_abs, &dir).unwrap_err();
    assert!(
        err_abs.contains("绝对路径"),
        "unexpected error: {}",
        err_abs
    );

    let bytes_unc = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("\\\\server\\x.js", "console.log('x');"),
    ]);
    let err_unc = install_from_zip(&bytes_unc, &dir).unwrap_err();
    assert!(
        err_unc.contains("绝对路径"),
        "unexpected error: {}",
        err_unc
    );

    cleanup(&dir);
}

// B4：Windows 盘符形如 "C:/x.js" 和 "C:\\x.js"，validate_entry_name 的盘符分支拒绝。
#[test]
fn b4_windows_drive_rejected() {
    let dir = work_dir("b4_drive");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");

    let bytes_fwd = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("C:/x.js", "console.log('x');"),
    ]);
    let err_fwd = install_from_zip(&bytes_fwd, &dir).unwrap_err();
    assert!(
        err_fwd.contains("绝对路径"),
        "unexpected error: {}",
        err_fwd
    );

    let bytes_back = build_zip_str(&[
        ("plugin.json", manifest.as_str()),
        ("C:\\x.js", "console.log('x');"),
    ]);
    let err_back = install_from_zip(&bytes_back, &dir).unwrap_err();
    assert!(
        err_back.contains("绝对路径"),
        "unexpected error: {}",
        err_back
    );

    cleanup(&dir);
}

// B5 删除说明：zip::ZipWriter::start_file 在构造期就拒绝含 NUL 的名字，
// 无法构造出条目名含 NUL 的 zip，因此删掉针对 "a\0b.js" 的测试。

// B6：zip 炸弹 —— 单个 10MB+1 字节文件触发 UncompressedTooLarge；
// 对照组恰好 10*1024*1024 字节通过（代码是 > 才拒绝）。
#[test]
fn b6_zip_bomb_rejected_exact_size_ok() {
    let dir = work_dir("b6_bomb");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let big = vec![0u8; 10 * 1024 * 1024 + 1];
    let bytes = build_zip(&[
        ("plugin.json", manifest.as_bytes()),
        ("big.bin", big.as_slice()),
    ]);
    let err = install_from_zip(&bytes, &dir).unwrap_err();
    assert!(err.contains("10MB"), "unexpected error: {}", err);

    // 对照组：恰好上限字节数
    let dir2 = work_dir("b6_exact_size");
    let manifest2 = manifest_json("demo2", "Demo Two", "1.0.0", "main.js");
    // 计算：plugin.json 本身也占大小，需要把总量控制在 10*1024*1024 以内，
    // 用 manifest2 字节数从 big2 里扣掉。
    let manifest_bytes = manifest2.as_bytes();
    let payload_len = 10 * 1024 * 1024 - manifest_bytes.len();
    let big2 = vec![0u8; payload_len];
    let bytes2 = build_zip(&[
        ("plugin.json", manifest_bytes),
        ("big.bin", big2.as_slice()),
    ]);
    let m = install_from_zip(&bytes2, &dir2).expect("exact total size should succeed");
    assert_eq!(m.id, "demo2");

    cleanup(&dir);
    cleanup(&dir2);
}

// B7：symlink 条目被中和成普通文件。
// 实现里解压只用 fs::write，从不调用 symlink 创建 API，
// 所以即便 zip 里标了 symlink 位，落盘也是普通文件，内容是写入的字节。
#[test]
fn b7_symlink_entry_neutralized_to_regular_file() {
    let dir = work_dir("b7_symlink");

    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");
    let mut buf = std::io::Cursor::new(Vec::new());
    {
        let mut w = zip::ZipWriter::new(&mut buf);
        w.start_file(
            "plugin.json",
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )
        .unwrap();
        w.write_all(manifest.as_bytes()).unwrap();

        w.start_file(
            "main.js",
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )
        .unwrap();
        w.write_all(b"console.log('m');").unwrap();

        // symlink 位 0o120777
        w.start_file(
            "link",
            zip::write::FileOptions::default()
                .compression_method(zip::CompressionMethod::Deflated)
                .unix_permissions(0o120777),
        )
        .unwrap();
        w.write_all(b"/etc/passwd").unwrap();

        w.finish().unwrap();
    }
    let bytes = buf.into_inner();

    let m = install_from_zip(&bytes, &dir).expect("install should succeed");
    assert_eq!(m.id, "demo");

    let link_path = dir.join("plugins").join("demo").join("link");
    let meta = fs::symlink_metadata(&link_path).unwrap();
    assert!(
        !meta.file_type().is_symlink(),
        "symlink entry must be neutralized into a regular file"
    );
    assert!(meta.file_type().is_file(), "link should be a regular file");
    let content = fs::read(&link_path).unwrap();
    assert_eq!(content, b"/etc/passwd");

    cleanup(&dir);
}

// B8：目录条目 "../" 在扫描循环与解压循环里都因 entry.is_dir() 被 continue，
// 不经过 validate_entry_name，因此不影响安装成功。
#[test]
fn b8_dir_entry_dotdot_skipped_install_ok() {
    let dir = work_dir("b8_dir_dotdot");
    let manifest = manifest_json("demo", "Demo", "1.0.0", "main.js");

    let mut buf = std::io::Cursor::new(Vec::new());
    {
        let mut w = zip::ZipWriter::new(&mut buf);
        // 目录条目 "../"：is_dir() 为 true
        w.add_directory(
            "../",
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored),
        )
        .unwrap();

        w.start_file(
            "plugin.json",
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )
        .unwrap();
        w.write_all(manifest.as_bytes()).unwrap();

        w.start_file(
            "main.js",
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )
        .unwrap();
        w.write_all(b"console.log('m');").unwrap();

        w.finish().unwrap();
    }
    let bytes = buf.into_inner();

    let m = install_from_zip(&bytes, &dir).expect("dir entry is skipped, install ok");
    assert_eq!(m.id, "demo");
    assert!(dir.join("plugins").join("demo").join("main.js").exists());

    cleanup(&dir);
}

// 缺口清单：
// - 实现里 install_from_zip_inner 没有对 zip 条目声明大小与实际解压字节做二次校验以外的
//   "目录条目名"检查；B8 依赖 entry.is_dir() continue 的行为，目前无防护，是文档化测试。
// - 实现里解压只用 fs::write，从不创建符号链接；B7 属行为文档化，当前无专门防护。
// - 实现里未对 NUL 字节做专门的 zip 构造侧测试（B5 因 ZipWriter 构造期拒绝而删除）。
// 以上缺口是否补实现由 Phase B 决定；本文件仅记录当前实现的真实行为。
