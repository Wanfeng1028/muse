use std::path::PathBuf;
use std::time::{Duration, Instant};
use mini_os::terminal::{TermError, TerminalManager};

fn mgr(data_suffix: &str, max: usize, idle: u64) -> TerminalManager {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(format!("tmp-term-{}-{}", data_suffix, std::process::id()));
    TerminalManager::new(dir.to_string_lossy().into_owned(), max, idle)
}

fn read_until(m: &TerminalManager, uid: i64, sid: &str, needle: &str, timeout: Duration) -> String {
    let start = Instant::now();
    let mut acc: Vec<u8> = Vec::new();
    let mut buf = [0u8; 4096];
    while start.elapsed() < timeout {
        match m.read_chunk(uid, sid, &mut buf) {
            Ok(0) => {}
            Ok(n) => {
                acc.extend_from_slice(&buf[..n]);
                if let Ok(s) = std::str::from_utf8(&acc) {
                    if s.contains(needle) {
                        return s.to_string();
                    }
                }
            }
            Err(e) => {
                panic!("read_chunk failed: {:?}, accumulated so far: {:?}", e, String::from_utf8_lossy(&acc));
            }
        }
    }
    panic!("timeout waiting for {:?}, accumulated so far: {:?}", needle, String::from_utf8_lossy(&acc));
}

// 测什么：在空行处写入 Ctrl+D（0x04，EOF），bash 收到 EOF 后应退出，
// 随后 is_alive 必须在 15 秒内由 Ok(true) 翻转为 Ok(false)。
// 为什么：Ctrl+D 是用户最常用的退出方式之一，is_alive 必须如实反映子进程
// 已退出；reap_idle 依赖 try_wait 探测到已退出进程来回收会话（联动语义）。
// 断言必须具体：先验证 write 返回 Ok(())，再轮询 is_alive 直到 Ok(false)，
// 最后再断言一次终态为 Ok(false)，且中途不允许出现 Err。
#[test]
fn ctrld_eof_terminates_shell() {
    let m = mgr("ctrld-r2", 4, 3600);
    let sid = m.open(1, 80, 24).expect("open should succeed");

    // 初始必须为存活状态，否则后续断言失去意义。
    match m.is_alive(1, &sid) {
        Ok(true) => {}
        other => panic!("expected initial is_alive Ok(true), got {:?}", other),
    }

    // 等 shell 初始化完成（readline 接管前发 EOF 会被错误时机消耗）：实测 1.5s 后发送可稳定复现退出。
    std::thread::sleep(Duration::from_millis(1500));
    // 写入 Ctrl+D（EOF）。空切片以外的写入会走 write_all + flush。
    let w = m.write(1, &sid, &[0x04u8]);
    assert!(w.is_ok(), "write Ctrl+D should be Ok, got {:?}", w);

    // 轮询 is_alive，最多 15 秒，每 100ms 一次；一旦 Ok(false) 立即成功返回。
    let deadline = Instant::now() + Duration::from_secs(15);
    let mut observed_dead = false;
    let mut last: Option<Result<bool, TermError>> = None;
    while Instant::now() < deadline {
        let cur = m.is_alive(1, &sid);
        match cur {
            Ok(true) => {
                last = Some(Ok(true));
                std::thread::sleep(Duration::from_millis(100));
            }
            Ok(false) => {
                last = Some(Ok(false));
                observed_dead = true;
                break;
            }
            Err(e) => {
                panic!("is_alive returned Err while polling: {:?}", e);
            }
        }
    }

    assert!(
        observed_dead,
        "shell did not terminate within 15s after Ctrl+D; last is_alive = {:?}",
        last
    );

    // 终态断言：必须稳定返回 Ok(false)。
    match m.is_alive(1, &sid) {
        Ok(false) => {}
        other => panic!("expected final is_alive Ok(false), got {:?}", other),
    }
}