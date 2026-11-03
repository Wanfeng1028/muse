//! 终端输出背压测试（TECH_DEBT P1-6）：
//! `cat` 大文件时服务端必须截断推送、提示一次、持续排空 PTY，客户端输入后恢复。

use std::time::{Duration, Instant};

use mini_os::terminal::{ReadOutcome, TerminalManager};

fn mgr(data_suffix: &str) -> TerminalManager {
    let dir = std::env::temp_dir().join(format!(
        "minios-term-bp-{}-{}",
        data_suffix,
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    TerminalManager::new(dir.to_string_lossy().into_owned(), 4, 3600)
}

fn data_dir_of(suffix: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("minios-term-bp-{}-{}", suffix, std::process::id()))
}

/// 测什么：小输出（echo 一行）全部以 Data 转发，不触发截断。
/// 为什么：背压不能误伤正常交互。
#[test]
fn small_output_never_truncated() {
    let m = mgr("small");
    let sid = m.open(1, 80, 24).expect("open");
    m.write(1, &sid, b"echo hello-bp-small\n").expect("write");
    let mut buf = [0u8; 4096];
    let mut acc = Vec::new();
    let mut saw_other = false;
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(15) {
        match m.read_chunk_limited(1, &sid, &mut buf).expect("read") {
            ReadOutcome::Data(n) => {
                acc.extend_from_slice(&buf[..n]);
                if String::from_utf8_lossy(&acc).contains("hello-bp-small") {
                    break;
                }
            }
            _ => {
                saw_other = true;
                break;
            }
        }
    }
    assert!(
        String::from_utf8_lossy(&acc).contains("hello-bp-small"),
        "15s 内未收到回显"
    );
    assert!(!saw_other, "小输出不应触发截断/Drained/Closed");
    assert!(acc.len() < 64 * 1024);
    let _ = m.close(1, &sid);
}

/// 测什么：`cat` 256KB 文件时恰好触发一次 TruncatedNotice，之后只返回 Drained。
/// 为什么：核心语义——提示一次、不 spam、持续排空 PTY。
#[test]
fn flood_triggers_single_truncation_notice() {
    let m = mgr("flood");
    m.set_output_limit(64 * 1024);
    let dir = data_dir_of("flood");
    std::fs::create_dir_all(&dir).expect("mkdir");
    std::fs::write(dir.join("bp-big.txt"), vec![b'A'; 256 * 1024]).expect("write big file");
    let sid = m.open(1, 80, 24).expect("open");
    m.write(1, &sid, b"cat bp-big.txt\n").expect("write cat");
    let mut buf = [0u8; 8192];
    let mut notice = 0u32;
    let mut drained = 0u32;
    let mut data_bytes = 0u64;
    let mut after_notice_not_drained = false;
    let mut noticed = false;
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(30) {
        match m.read_chunk_limited(1, &sid, &mut buf).expect("read") {
            ReadOutcome::Data(n) => {
                data_bytes += n as u64;
                if noticed {
                    after_notice_not_drained = true;
                }
            }
            ReadOutcome::TruncatedNotice => {
                notice += 1;
                noticed = true;
            }
            ReadOutcome::Drained => {
                drained += 1;
                if !noticed {
                    after_notice_not_drained = true;
                }
            }
            ReadOutcome::Closed => break,
        }
        if noticed && drained >= 5 {
            break;
        }
    }
    assert_eq!(notice, 1, "必须恰好触发一次截断提示，实际 {}", notice);
    assert!(
        !after_notice_not_drained,
        "提示之后只允许 Drained（或 Closed 结束）"
    );
    assert!(drained >= 1, "截断后应有持续排空");
    assert!(
        data_bytes <= 64 * 1024 + 8192,
        "转发字节超限：{}",
        data_bytes
    );
    let _ = m.close(1, &sid);
}

/// 测什么：截断后客户端输入新命令，预算重置、输出恢复转发。
/// 为什么：截断是"暂停推送"不是"杀会话"。
#[test]
fn client_input_resets_budget_after_truncation() {
    let m = mgr("reset");
    m.set_output_limit(32 * 1024);
    let dir = data_dir_of("reset");
    std::fs::create_dir_all(&dir).expect("mkdir");
    std::fs::write(dir.join("bp-mid.txt"), vec![b'B'; 128 * 1024]).expect("write mid file");
    let sid = m.open(1, 80, 24).expect("open");
    m.write(1, &sid, b"cat bp-mid.txt\n").expect("write cat");
    let mut buf = [0u8; 8192];
    let start = Instant::now();
    let mut noticed = false;
    while start.elapsed() < Duration::from_secs(20) {
        if matches!(
            m.read_chunk_limited(1, &sid, &mut buf).expect("read"),
            ReadOutcome::TruncatedNotice
        ) {
            noticed = true;
            break;
        }
    }
    assert!(noticed, "20s 内未触发截断");
    m.write(1, &sid, b"echo resumed-ok-bp\n")
        .expect("write echo");
    let mut acc = Vec::new();
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(15) {
        match m.read_chunk_limited(1, &sid, &mut buf).expect("read") {
            ReadOutcome::Data(n) => {
                acc.extend_from_slice(&buf[..n]);
                if String::from_utf8_lossy(&acc).contains("resumed-ok-bp") {
                    break;
                }
            }
            ReadOutcome::Closed => break,
            _ => {}
        }
    }
    assert!(
        String::from_utf8_lossy(&acc).contains("resumed-ok-bp"),
        "输入新命令后输出未恢复"
    );
    let _ = m.close(1, &sid);
}

/// 测什么：截断指标计数与 exposition 渲染。
/// 为什么：可观测性是 DoD 要求，截断次数必须可见。
#[test]
fn truncation_metric_renders() {
    let met = mini_os::metrics::Metrics::new();
    met.term_output_truncated();
    met.term_output_truncated();
    let body = met.render();
    assert!(
        body.contains("minios_term_output_truncated_total 2"),
        "计数应为 2，实际:\n{}",
        body
    );
    assert!(
        body.contains("# TYPE minios_term_output_truncated_total counter"),
        "缺 TYPE 行"
    );
}
