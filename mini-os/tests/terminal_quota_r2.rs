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
fn open_close_cycle_releases_quota() {
    // 测什么：单用户配额 max=1 时，open 成功后再 open 必须返回 LimitReached，
    // 而 close 成功后再次 open 必须重新成功（配额已被释放）。
    // 为什么：若 close 未从 sessions 表中移除会话，配额会被永久占用，
    // 用户开一个终端后即使关闭也无法再开，属于典型配额泄漏。
    let m = mgr("quota-cycle", 1, 3600);

    let s1 = m.open(1, 80, 24).expect("first open should succeed");
    assert_eq!(m.session_count(1), 1, "after first open, session_count(1) must be 1");

    let second = m.open(1, 80, 24);
    assert_eq!(
        second,
        Err(TermError::LimitReached),
        "second open for same user with max=1 must be LimitReached"
    );
    assert_eq!(m.session_count(1), 1, "failed open must not add a session");

    m.close(1, &s1).expect("close of existing session should succeed");
    assert_eq!(m.session_count(1), 0, "after close, session_count(1) must be 0");

    let s2 = m.open(1, 80, 24).expect("re-open after close should succeed");
    assert_ne!(s1, s2, "re-opened session should get a fresh id");
    assert_eq!(m.session_count(1), 1, "after re-open, session_count(1) must be 1");

    m.close(1, &s2).expect("close of re-opened session should succeed");
    assert_eq!(m.session_count(1), 0, "final close must release quota");
}

#[test]
fn set_last_active_unknown_sid_no_panic() {
    // 测什么：对不存在的 session_id 调用 set_last_active_for_test，
    // 必须静默无操作（不 panic），且不影响任何用户会话计数。
    // 为什么：该测试钩子内部查表失败时应直接返回；若在 None 分支上 unwrap/panic，
    // 会直接拖垮调用它的集成测试进程。
    let m = mgr("last-active-unknown", 4, 3600);

    let unknown_sid = "ffffffffffffffffffffffffffffffff";
    m.set_last_active_for_test(unknown_sid, Instant::now());

    assert_eq!(m.session_count(1), 0, "unknown sid hook call must not create sessions for uid 1");
    assert_eq!(m.session_count(0), 0, "unknown sid hook call must not create sessions for uid 0");

    // 再确认钩子对未知 sid 之后，管理器仍能正常 open，证明状态未被破坏。
    let s = m.open(1, 80, 24).expect("manager must still work after unknown-sid hook call");
    assert_eq!(m.session_count(1), 1, "session_count(1) must be 1 after successful open");
    m.close(1, &s).expect("close should succeed");
}