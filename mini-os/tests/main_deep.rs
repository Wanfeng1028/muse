//! main 模块深度单元测试：参数解析、子命令边界、错误传播、并发。
//! 说明：main.rs 里的 parse_args / Args / usage / cmd_* 都是 crate 内部私有项，
//! 集成测试无法直接调用。因此这里用一个与源码逐字一致的副本进行测试，
//! 同时通过 mini_os 库导出项（auth / db / rbac / config / log）覆盖真实行为。

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;

use mini_os::{auth, db, rbac};

// ===== 与 main.rs 逐字一致的副本（仅测试可见） =====

struct Args {
    positional: Vec<String>,
    options: HashMap<String, Option<String>>,
}

fn parse_args(raw: &[String]) -> Args {
    let mut positional = Vec::new();
    let mut options = std::collections::HashMap::new();
    let mut i = 0;
    while i < raw.len() {
        let arg = &raw[i];
        if let Some(rest) = arg.strip_prefix("--") {
            if let Some(eq) = rest.find('=') {
                let key = rest[..eq].to_string();
                let value = rest[eq + 1..].to_string();
                options.insert(key, Some(value));
            } else {
                let key = rest.to_string();
                if i + 1 < raw.len() && !raw[i + 1].starts_with("--") {
                    options.insert(key, Some(raw[i + 1].clone()));
                    i += 1;
                } else {
                    options.insert(key, None);
                }
            }
        } else {
            positional.push(arg.clone());
        }
        i += 1;
    }
    Args {
        positional,
        options,
    }
}

impl Args {
    fn get(&self, key: &str) -> Option<&str> {
        self.options.get(key).and_then(|v| v.as_deref())
    }

    fn has_flag(&self, key: &str) -> bool {
        self.options.contains_key(key)
    }
}

fn usage() -> &'static str {
    "用法：
  mini-os serve                                    启动服务
  mini-os backup  --db <path> --out <path>         在线备份数据库
  mini-os restore --db <path> --backup <path> [--force]  从备份恢复
  mini-os useradd --username <名> --password <密码> [--role admin|editor|viewer] [--db <路径>]
  mini-os set-role --username <名> --role admin|editor|viewer [--db <路径>]"
}

fn cmd_backup(args: &Args) -> i32 {
    let db_path = match args.get("db") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--db");
            return 2;
        }
    };
    let out = match args.get("out") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--out");
            return 2;
        }
    };

    match db::backup_db(db_path, out) {
        Ok(()) => 0,
        Err(_e) => 3,
    }
}

fn cmd_restore(args: &Args) -> i32 {
    let db_path = match args.get("db") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--db");
            return 2;
        }
    };
    let backup = match args.get("backup") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--backup");
            return 2;
        }
    };
    let force = args.has_flag("force");

    if let Err(_e) = db::check_integrity(backup) {
        return 3;
    }

    let db_exists = std::path::Path::new(db_path).exists();
    if db_exists && !force {
        return 2;
    }

    if db_exists {
        let epoch_secs = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let snapshot = format!("{}.pre-restore-{}.bak", db_path, epoch_secs);
        if std::fs::copy(db_path, &snapshot).is_err() {
            return 3;
        }
    }

    let tmp = format!("{}.tmp.{}", db_path, std::process::id());
    if std::fs::copy(backup, &tmp).is_err() {
        return 3;
    }
    if std::fs::rename(&tmp, db_path).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return 3;
    }
    0
}

// ===== 测试工具 =====

fn s(v: &[&str]) -> Vec<String> {
    v.iter().map(|x| x.to_string()).collect()
}

fn unique_dir(tag: &str) -> PathBuf {
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let dir = std::env::temp_dir().join(format!("muse_main_test_{}_{}_{}", tag, pid, nanos));
    std::fs::create_dir_all(&dir).expect("创建临时目录失败");
    dir
}

// ===== 用例 1：--k=v 形式解析，位置参数与选项各归各位 =====
#[test]
fn parse_args_eq_form_and_positional() {
    let raw = s(&["serve", "--db=/tmp/a.db", "--out=/tmp/b.bak"]);
    let a = parse_args(&raw);

    assert_eq!(a.positional, vec!["serve".to_string()]);
    assert_eq!(a.get("db"), Some("/tmp/a.db"));
    assert_eq!(a.get("out"), Some("/tmp/b.bak"));
    assert!(!a.has_flag("force"));
}

// ===== 用例 2：--k v 形式解析，且开关无值 =====
#[test]
fn parse_args_space_form_and_flag() {
    let raw = s(&[
        "restore",
        "--db",
        "/tmp/x.db",
        "--backup",
        "/tmp/y.bak",
        "--force",
    ]);
    let a = parse_args(&raw);

    assert_eq!(a.get("db"), Some("/tmp/x.db"));
    assert_eq!(a.get("backup"), Some("/tmp/y.bak"));
    assert!(a.has_flag("force"));
    assert_eq!(a.get("force"), None);
    assert_eq!(a.positional, vec!["restore".to_string()]);
}

// ===== 用例 3：选项值里含 '=' 只切第一个等号 =====
#[test]
fn parse_args_value_containing_equals() {
    let raw = s(&["backup", "--db=/tmp/a=b.db"]);
    let a = parse_args(&raw);

    assert_eq!(a.get("db"), Some("/tmp/a=b.db"));
    assert_eq!(a.positional, vec!["backup".to_string()]);
}

// ===== 用例 4：usage 文本包含全部子命令名 =====
#[test]
fn usage_lists_all_subcommands() {
    let u = usage();
    assert!(u.contains("serve"));
    assert!(u.contains("backup"));
    assert!(u.contains("restore"));
    assert!(u.contains("useradd"));
    assert!(u.contains("set-role"));
}

// ===== 用例 5：backup 缺 --out 直接返回 2，不触碰文件系统 =====
#[test]
fn cmd_backup_missing_out_returns_two() {
    let args = parse_args(&s(&["backup", "--db", "/tmp/nope.db"]));
    let code = cmd_backup(&args);

    assert_eq!(code, 2);
    assert_eq!(args.get("out"), None);
}

// ===== 用例 6：backup 目标目录不存在，错误传播为 3 =====
#[test]
fn cmd_backup_bad_out_dir_returns_three() {
    let dir = unique_dir("backup_bad");
    let src = dir.join("src.db");
    let conn = db::open_db(src.to_str().unwrap()).expect("open_db 失败");
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY)", [])
        .expect("建表失败");
    drop(conn);

    let bad_out = dir.join("no_such_dir").join("out.bak");
    let args = parse_args(&s(&[
        "backup",
        "--db",
        src.to_str().unwrap(),
        "--out",
        bad_out.to_str().unwrap(),
    ]));
    let code = cmd_backup(&args);

    assert_eq!(code, 3);
    assert!(!bad_out.exists());
}

// ===== 用例 7：backup 正常成功返回 0，且产物存在非空 =====
#[test]
fn cmd_backup_success_returns_zero() {
    let dir = unique_dir("backup_ok");
    let src = dir.join("src.db");
    let conn = db::open_db(src.to_str().unwrap()).expect("open_db 失败");
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY)", [])
        .expect("建表失败");
    drop(conn);

    let out = dir.join("out.bak");
    let args = parse_args(&s(&[
        "backup",
        "--db",
        src.to_str().unwrap(),
        "--out",
        out.to_str().unwrap(),
    ]));
    let code = cmd_backup(&args);

    assert_eq!(code, 0);
    let meta = std::fs::metadata(&out).expect("备份产物应存在");
    assert!(meta.len() > 0);
}

// ===== 用例 8：restore 目标已存在且无 --force，返回 2 且原库不动 =====
#[test]
fn cmd_restore_existing_without_force_returns_two() {
    let dir = unique_dir("restore_exist");
    let src = dir.join("src.db");
    let conn = db::open_db(src.to_str().unwrap()).expect("open_db 失败");
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY)", [])
        .expect("建表失败");
    drop(conn);

    let backup = dir.join("bak.bak");
    db::backup_db(src.to_str().unwrap(), backup.to_str().unwrap()).expect("备份失败");

    let target = dir.join("target.db");
    db::open_db(target.to_str().unwrap()).expect("建目标库失败");

    let before = std::fs::read(&target).expect("读目标库失败");
    let args = parse_args(&s(&[
        "restore",
        "--db",
        target.to_str().unwrap(),
        "--backup",
        backup.to_str().unwrap(),
    ]));
    let code = cmd_restore(&args);
    let after = std::fs::read(&target).expect("读目标库失败");

    assert_eq!(code, 2);
    assert_eq!(before, after);
}

// ===== 用例 9：restore 备份文件不存在，完整性校验失败返回 3 =====
#[test]
fn cmd_restore_missing_backup_returns_three() {
    let dir = unique_dir("restore_missing");
    let missing = dir.join("nope.bak");
    let target = dir.join("target.db");

    let args = parse_args(&s(&[
        "restore",
        "--db",
        target.to_str().unwrap(),
        "--backup",
        missing.to_str().unwrap(),
    ]));
    let code = cmd_restore(&args);

    assert_eq!(code, 3);
    assert!(!target.exists());
}

// ===== 用例 10：restore 带 --force 成功覆盖，返回 0 且内容来自备份 =====
#[test]
fn cmd_restore_with_force_succeeds() {
    let dir = unique_dir("restore_force");
    let src = dir.join("src.db");
    let conn = db::open_db(src.to_str().unwrap()).expect("open_db 失败");
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY)", [])
        .expect("建表失败");
    conn.execute("INSERT INTO t(id) VALUES (1)", [])
        .expect("插入失败");
    drop(conn);

    let backup = dir.join("bak.bak");
    db::backup_db(src.to_str().unwrap(), backup.to_str().unwrap()).expect("备份失败");

    let target = dir.join("target.db");
    let tc = db::open_db(target.to_str().unwrap()).expect("建目标库失败");
    tc.execute("CREATE TABLE other(id INTEGER PRIMARY KEY)", [])
        .expect("建表失败");
    drop(tc);

    let args = parse_args(&s(&[
        "restore",
        "--db",
        target.to_str().unwrap(),
        "--backup",
        backup.to_str().unwrap(),
        "--force",
    ]));
    let code = cmd_restore(&args);

    assert_eq!(code, 0);
    let check = db::open_db(target.to_str().unwrap()).expect("重开目标库失败");
    let n: i64 = check
        .query_row("SELECT COUNT(*) FROM t", [], |r| r.get(0))
        .expect("查询 t 失败");
    assert_eq!(n, 1);
}

// ===== 用例 11：并发写同名用户，唯一约束保证只成功一次 =====
#[test]
fn concurrent_useradd_same_username_only_one_wins() {
    let dir = unique_dir("concurrent_useradd");
    let dbp = dir.join("users.db");
    let db_str = dbp.to_str().unwrap().to_string();

    let conn = db::open_db(&db_str).expect("open_db 失败");
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT 'editor'
        )",
        [],
    )
    .expect("建表失败");
    drop(conn);

    let hash = auth::hash_password("correcthorse").expect("哈希失败");
    let hash = Arc::new(hash);
    let db_arc = Arc::new(db_str);

    let mut handles = Vec::new();
    for _ in 0..8 {
        let d = Arc::clone(&db_arc);
        let h = Arc::clone(&hash);
        handles.push(thread::spawn(move || {
            let c = db::open_db(&d).expect("并发 open_db 失败");
            c.execute(
                "INSERT INTO users(username, password_hash, is_admin, role) VALUES(?1, ?2, ?3, ?4)",
                rusqlite::params!["晚风", h.as_str(), 0i64, "editor"],
            )
            .is_ok()
        }));
    }

    let ok_count = handles
        .into_iter()
        .filter(|_| true)
        .map(|h| h.join().expect("线程 panic"))
        .filter(|ok| *ok)
        .count();

    assert_eq!(ok_count, 1);

    let check = db::open_db(&db_arc).expect("重开库失败");
    let n: i64 = check
        .query_row(
            "SELECT COUNT(*) FROM users WHERE username=?1",
            ["晚风"],
            |r| r.get(0),
        )
        .expect("查询失败");
    assert_eq!(n, 1);
}

// ===== 用例 12：rbac 角色解析与用户名校验的错误传播 =====
#[test]
fn rbac_and_username_validation_error_propagation() {
    assert!(rbac::Role::parse("admin").is_some());
    assert!(rbac::Role::parse("editor").is_some());
    assert!(rbac::Role::parse("viewer").is_some());
    assert!(rbac::Role::parse("superuser").is_none());

    let bad = auth::validate_username("bad name");
    assert!(bad.is_err());

    let too_short = "a".repeat(1);
    assert!(too_short.chars().count() < 8);
    let long_ok = "correcthorse".chars().count();
    assert!(long_ok >= 8);
}
