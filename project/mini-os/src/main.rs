// 程序入口：子命令解析（serve/backup/restore）、优雅关闭、结构化日志
use std::time::Duration;

use mini_os::{
    auth, build_app, config::Config, db, init_state_with, log::log_event, password, rbac,
};

use serde_json::json;

/// 手写参数解析结果：位置参数 + 选项表
struct Args {
    positional: Vec<String>,
    options: std::collections::HashMap<String, Option<String>>,
}

/// 解析 `--k v` 与 `--k=v` 两种形式；布尔型开关（如 --force）值为 None
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
                // 看下一个是否是值（不以 -- 开头）
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
        Ok(()) => {
            log_event("backup_done", json!({ "db": db_path, "out": out }));
            0
        }
        Err(e) => {
            eprintln!("备份失败：{}", e);
            3
        }
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

    if let Err(e) = db::check_integrity(backup) {
        eprintln!("恢复失败：备份文件完整性校验未通过：{}", e);
        return 3;
    }

    let db_exists = std::path::Path::new(db_path).exists();
    if db_exists && !force {
        eprintln!("恢复失败：目标数据库已存在（加 --force 覆盖）");
        return 2;
    }

    if db_exists {
        let epoch_secs = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let snapshot = format!("{}.pre-restore-{}.bak", db_path, epoch_secs);
        if let Err(e) = std::fs::copy(db_path, &snapshot) {
            eprintln!("恢复失败：无法创建快照 {}", e);
            return 3;
        }
    }

    let tmp = format!("{}.tmp.{}", db_path, std::process::id());
    if let Err(e) = std::fs::copy(backup, &tmp) {
        eprintln!("恢复失败：无法写入临时文件 {}", e);
        return 3;
    }
    if let Err(e) = std::fs::rename(&tmp, db_path) {
        eprintln!("恢复失败：无法替换目标数据库 {}", e);
        let _ = std::fs::remove_file(&tmp);
        return 3;
    }

    log_event("restore_done", json!({ "db": db_path, "backup": backup }));
    0
}

/// useradd 子命令：创建用户。首个可登录用户自动设为 admin。
fn cmd_useradd(args: &Args) -> i32 {
    // 必填参数：用户名、密码
    let username = match args.get("username") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--username");
            return 2;
        }
    };
    let password = match args.get("password") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--password");
            return 2;
        }
    };

    // 角色：缺省 editor，非法值直接拒绝
    let role_str = args.get("role").unwrap_or("editor");
    if rbac::Role::parse(role_str).is_none() {
        eprintln!("role 只支持 admin/editor/viewer");
        return 2;
    }

    // 用户名合法性校验
    if let Err(e) = auth::validate_username(username) {
        eprintln!("{}", e);
        return 2;
    }

    // 密码强度策略（与 /api/auth/register 同口径）
    if let Err(msg) = password::validate_password(password, username) {
        eprintln!("{}", msg);
        return 2;
    }

    // 数据库路径：--db 优先，否则取环境配置
    let db_path = match args.get("db") {
        Some(v) => v.to_string(),
        None => Config::from_env().database_path,
    };
    let conn = match db::open_db(&db_path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("打开数据库失败：{}", e);
            return 3;
        }
    };

    // 用户名唯一性检查
    let existing: i64 = match conn.query_row(
        "SELECT COUNT(*) FROM users WHERE username=?1",
        [username],
        |row| row.get(0),
    ) {
        Ok(n) => n,
        Err(e) => {
            eprintln!("查询用户失败：{}", e);
            return 3;
        }
    };
    if existing > 0 {
        eprintln!("用户名已存在");
        return 3;
    }

    // 库中是否已有可登录用户；没有则首个用户强制为 admin
    let loginable: i64 = match conn.query_row(
        "SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL",
        [],
        |row| row.get(0),
    ) {
        Ok(n) => n,
        Err(e) => {
            eprintln!("查询用户失败：{}", e);
            return 3;
        }
    };
    let role = if loginable == 0 {
        eprintln!("首个用户，自动设为 admin");
        rbac::Role::Admin
    } else {
        // 上面已校验，这里必为 Some
        rbac::Role::parse(role_str).unwrap()
    };
    let role_str = role.as_str();
    let is_admin: i64 = if role_str == "admin" { 1 } else { 0 };

    // 哈希密码
    let password_hash = match auth::hash_password(password) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("密码哈希失败：{}", e);
            return 3;
        }
    };

    // 落库
    if let Err(e) = conn.execute(
        "INSERT INTO users(username, password_hash, is_admin, role) VALUES(?1, ?2, ?3, ?4)",
        rusqlite::params![username, password_hash, is_admin, role_str],
    ) {
        eprintln!("创建用户失败：{}", e);
        return 3;
    }
    let id = conn.last_insert_rowid();

    // 成功输出单行 JSON，便于脚本解析
    println!(
        "{{\"id\": {}, \"username\": \"{}\", \"role\": \"{}\"}}",
        id, username, role_str
    );
    0
}

/// set-role 子命令：变更用户角色。角色变更后旧会话必须失效。
fn cmd_set_role(args: &Args) -> i32 {
    // 必填参数：用户名、角色
    let username = match args.get("username") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--username");
            return 2;
        }
    };
    let role_str = match args.get("role") {
        Some(v) => v,
        None => {
            eprintln!("缺少参数：--role");
            return 2;
        }
    };
    let new_role = match rbac::Role::parse(role_str) {
        Some(r) => r,
        None => {
            eprintln!("role 只支持 admin/editor/viewer");
            return 2;
        }
    };
    let new_role_str = new_role.as_str();

    // 数据库路径：--db 优先，否则取环境配置
    let db_path = match args.get("db") {
        Some(v) => v.to_string(),
        None => Config::from_env().database_path,
    };
    let conn = match db::open_db(&db_path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("打开数据库失败：{}", e);
            return 3;
        }
    };

    // 查目标用户当前角色
    let (id, cur_role): (i64, String) = match conn.query_row(
        "SELECT id, role FROM users WHERE username=?1",
        [username],
        |row| Ok((row.get(0)?, row.get(1)?)),
    ) {
        Ok(v) => v,
        Err(rusqlite::Error::QueryReturnedNoRows) => {
            eprintln!("用户不存在");
            return 3;
        }
        Err(e) => {
            eprintln!("查询用户失败：{}", e);
            return 3;
        }
    };

    // 保护：不能把最后一个 admin 降级
    if cur_role == "admin" && new_role_str != "admin" {
        let admin_count: i64 =
            match conn.query_row("SELECT COUNT(*) FROM users WHERE role='admin'", [], |row| {
                row.get(0)
            }) {
                Ok(n) => n,
                Err(e) => {
                    eprintln!("查询管理员数量失败：{}", e);
                    return 3;
                }
            };
        if admin_count == 1 {
            eprintln!("拒绝：不能移除最后一个管理员");
            return 3;
        }
    }

    let is_admin: i64 = if new_role_str == "admin" { 1 } else { 0 };
    if let Err(e) = conn.execute(
        "UPDATE users SET role=?1, is_admin=?2 WHERE id=?3",
        rusqlite::params![new_role_str, is_admin, id],
    ) {
        eprintln!("更新角色失败：{}", e);
        return 3;
    }

    // 角色变更后旧会话必须失效：撤销该用户全部会话。失败只告警，不影响返回码。
    if let Err(e) = auth::revoke_all_user_sessions(&conn, id) {
        eprintln!("警告：撤销用户会话失败：{}", e);
    }

    // 成功输出单行 JSON，便于脚本解析
    println!(
        "{{\"id\": {}, \"username\": \"{}\", \"role\": \"{}\"}}",
        id, username, new_role_str
    );
    0
}

/// 等待系统关闭信号：Ctrl+C 或（unix）SIGTERM。只等信号本身，不含超时。
async fn os_signal() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };

    #[cfg(unix)]
    let terminate = async {
        if let Ok(mut sig) =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        {
            sig.recv().await;
        }
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}

async fn cmd_serve(config: Config) -> i32 {
    let state = init_state_with(
        &config.database_path,
        &config.static_dir,
        config.upload_max_bytes,
        config.session_ttl_secs,
        config.login_rps,
        config.login_burst,
    );
    // 终端输出背压上限走 MINIOS_TERM_OUTPUT_LIMIT（默认 1MiB，非法值已在 from_env fail-fast）。
    state.terminals.set_output_limit(config.term_output_limit);

    let app = build_app(state);

    let addr = format!("0.0.0.0:{}", config.port);
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("无法绑定监听地址");

    log_event(
        "service_started",
        json!({ "addr": addr, "db": config.database_path }),
    );

    let timeout_secs = config.shutdown_timeout_secs;

    // 服务跑在独立 task 里：with_graceful_shutdown 在收到 shutdown_rx 后停止接受新连接并排空在途请求。
    // 主 task 先等系统信号（正常运行阶段不计时），信号到达后才对"排空阶段"计时，避免超时掐断正常服务。
    let (shutdown_tx, shutdown_rx) = tokio::sync::oneshot::channel::<()>();
    let server_task = tokio::spawn(async move {
        axum::serve(listener, app)
            .with_graceful_shutdown(async move {
                let _ = shutdown_rx.await;
            })
            .await
    });

    os_signal().await;
    log_event("shutdown_signal_received", json!({}));
    let _ = shutdown_tx.send(());

    match tokio::time::timeout(Duration::from_secs(timeout_secs), server_task).await {
        Ok(Ok(Ok(()))) => {
            log_event("service_stopped", json!({}));
            0
        }
        Ok(Ok(Err(e))) => {
            eprintln!("服务运行失败：{}", e);
            1
        }
        Ok(Err(e)) => {
            eprintln!("服务任务异常结束：{}", e);
            1
        }
        Err(_) => {
            log_event("shutdown_timeout", json!({ "timeout_secs": timeout_secs }));
            1
        }
    }
}

#[tokio::main]
async fn main() {
    let raw: Vec<String> = std::env::args().skip(1).collect();
    let args = parse_args(&raw);

    let sub = args
        .positional
        .first()
        .map(|s| s.as_str())
        .unwrap_or("serve");

    let code = match sub {
        "serve" => {
            let config = Config::from_env();
            cmd_serve(config).await
        }
        "backup" => cmd_backup(&args),
        "restore" => cmd_restore(&args),
        "useradd" => cmd_useradd(&args),
        "set-role" => cmd_set_role(&args),
        other => {
            eprintln!("未知子命令：{}", other);
            eprintln!("{}", usage());
            2
        }
    };

    std::process::exit(code);
}
