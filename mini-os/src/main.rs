// 程序入口：子命令解析（serve/backup/restore）、优雅关闭、结构化日志
use std::time::Duration;

use mini_os::{build_app, config::Config, db, init_state_with, log::log_event};
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
  mini-os restore --db <path> --backup <path> [--force]  从备份恢复"
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
    );

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
        other => {
            eprintln!("未知子命令：{}", other);
            eprintln!("{}", usage());
            2
        }
    };

    std::process::exit(code);
}
