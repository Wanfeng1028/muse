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

#[test]
fn interrupt_on_idle_shell_is_harmless() {
    // 测什么：在一个空闲的交互 shell 上调用 interrupt(1, &sid)，应返回 Ok(())、
    // 会话仍然存活，并且随后还能正常 write/read 回显 "idle-ctrlc-4"。
    // 为什么：前端"中断"按钮可能被误触；空闲 shell 无前台进程时，Ctrl+C 只是
    // 触发一次 SIGINT，不应杀掉用户 shell，也不能破坏后续交互能力。
    let m = mgr("ctrlc-idle-r2", 4, 3600);
    let sid = m.open(1, 80, 24).expect("open session for user 1");

    // 空转 shell 上发 Ctrl+C：不应报错。
    let r = m.interrupt(1, &sid);
    assert_eq!(r, Ok(()), "interrupt on idle shell must succeed, got {:?}", r);

    // 会话必须仍然存活。
    let alive = m.is_alive(1, &sid);
    assert_eq!(alive, Ok(true), "session must stay alive after idle Ctrl+C, got {:?}", alive);

    // 之后仍可交互：写入命令并读回回显。
    m.write(1, &sid, b"echo idle-ctrlc-4\n").expect("write after idle interrupt");
    let out = read_until(&m, 1, &sid, "idle-ctrlc-4", Duration::from_secs(10));
    assert!(
        out.contains("idle-ctrlc-4"),
        "expected shell to still echo idle-ctrlc-4 after idle Ctrl+C, got {:?}",
        out
    );

    // 收尾：会话仍在计数中，close 后计数归零。
    assert_eq!(m.session_count(1), 1, "session should still be tracked");
    m.close(1, &sid).expect("close session");
    assert_eq!(m.session_count(1), 0, "session count should drop to zero after close");
}