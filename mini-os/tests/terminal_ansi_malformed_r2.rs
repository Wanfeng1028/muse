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

// 测什么：向 PTY 写入畸形/超长 CSI 参数序列后，shell 仍存活并能继续执行命令。
// 为什么：恶意或损坏的程序输出（例如 \x1b[9999999999999999m）不能把用户终端搞死，
// 必须验证 line discipline 与 shell 不会被这种垃圾输入击垮。
#[test]
fn malformed_escape_does_not_kill_shell() {
    let m = mgr("malformed-esc", 4, 600);
    let sid = m.open(1, 80, 24).expect("open session");

    m.write(1, &sid, b"\x1b[9999999999999999mbad-esc-3\n")
        .expect("write malformed escape");
    m.write(1, &sid, b"echo after-bad-esc-3\n")
        .expect("write echo command");

    let out = read_until(&m, 1, &sid, "after-bad-esc-3", Duration::from_secs(10));
    assert!(
        out.contains("after-bad-esc-3"),
        "expected echo output after malformed escape, got: {:?}",
        out
    );

    assert_eq!(
        m.is_alive(1, &sid),
        Ok(true),
        "shell must still be alive after malformed escape sequence"
    );

    let _ = m.close(1, &sid);
}

// 测什么：空切片写入的语义——合法会话空写直接 Ok(())，非法会话空写仍先校验归属返回 NotFound。
// 为什么：源码中 write 的空数据分支会先调用 get_session，这个安全细节决定了
// 「不存在的会话」与「他人会话」不会被空写绕过，必须锁死这一行为。
#[test]
fn empty_write_semantics() {
    let m = mgr("empty-write", 4, 600);
    let sid = m.open(1, 80, 24).expect("open session");

    assert_eq!(
        m.write(1, &sid, &[]),
        Ok(()),
        "empty write on a valid owned session must succeed"
    );

    let bogus = "deadbeefdeadbeefdeadbeefdeadbeef";
    assert_eq!(
        m.write(1, bogus, &[]),
        Err(TermError::NotFound),
        "empty write on a nonexistent session must still validate ownership and return NotFound"
    );

    assert_eq!(
        m.write(2, &sid, &[]),
        Err(TermError::Forbidden),
        "empty write from a different user must return Forbidden"
    );

    let _ = m.close(1, &sid);
}