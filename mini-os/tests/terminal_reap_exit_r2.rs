use mini_os::terminal::{TermError, TerminalManager};
use std::path::PathBuf;
use std::time::{Duration, Instant};

fn mgr(data_suffix: &str, max: usize, idle: u64) -> TerminalManager {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(format!("tmp-term-{}-{}", data_suffix, std::process::id()));
    TerminalManager::new(dir.to_string_lossy().into_owned(), max, idle)
}

#[allow(dead_code)]
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
                panic!(
                    "read_chunk failed: {:?}, accumulated so far: {:?}",
                    e,
                    String::from_utf8_lossy(&acc)
                );
            }
        }
    }
    panic!(
        "timeout waiting for {:?}, accumulated so far: {:?}",
        needle,
        String::from_utf8_lossy(&acc)
    );
}

// 测什么：子进程通过 write(b"exit\n") 退出后，reap_idle 必须把该会话从表中移除并返回 1，
// 随后 session_count 归零、对已回收 session 的 write 必须返回 NotFound。
// 为什么：用户 exit 后若不回收，僵尸会话会永久占用 max_per_user 配额中的位置；
// reap 是配额防泄漏的第二道防线，必须在子进程退出但未显式 close 时兜底清理。
#[test]
fn reap_reaps_exited_child() {
    let m = mgr("reap-exit", 8, 3600);
    let sid = m.open(1, 80, 24).expect("open session");
    assert_eq!(m.session_count(1), 1);

    m.write(1, &sid, b"exit\n").expect("write exit");

    let deadline = Instant::now() + Duration::from_secs(10);
    let mut alive = true;
    while Instant::now() < deadline {
        match m.is_alive(1, &sid) {
            Ok(false) => {
                alive = false;
                break;
            }
            Ok(true) => {}
            Err(e) => panic!("is_alive errored: {:?}", e),
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(
        !alive,
        "child did not exit within 10s after write(b\"exit\\n\")"
    );

    assert_eq!(
        m.reap_idle(),
        1,
        "exited child session must be reaped exactly once"
    );
    assert_eq!(
        m.session_count(1),
        0,
        "reaped session must not count toward quota"
    );

    match m.write(1, &sid, b"x") {
        Err(TermError::NotFound) => {}
        other => panic!("expected NotFound after reap, got {:?}", other),
    }
}
