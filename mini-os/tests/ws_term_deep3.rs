use mini_os::terminal::{ReadOutcome, TerminalManager};
use std::time::{Duration, Instant};

fn mgr(data_suffix: &str) -> TerminalManager {
    let dir = std::env::temp_dir().join(format!(
        "minios-term-d3-{}-{}",
        data_suffix,
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    TerminalManager::new(dir.to_string_lossy().into_owned(), 4, 3600)
}

#[test]
fn test_open_returns_non_empty_session_id_and_alive() {
    let m = mgr("t1");
    let sid = m.open(1, 80, 24).unwrap();
    assert!(!sid.is_empty());
    assert!(m.is_alive(1, &sid).unwrap());
    assert_eq!(m.session_count(1), 1);
}

#[test]
fn test_max_per_user_limit() {
    let m = mgr("t2");
    for _ in 0..4 {
        m.open(1, 80, 24).unwrap();
    }
    assert_eq!(m.session_count(1), 4);
    let err = m.open(1, 80, 24);
    assert!(err.is_err());
    assert_eq!(m.session_count(1), 4);
}

#[test]
fn test_close_marks_not_alive_and_decrements_count() {
    let m = mgr("t3");
    let sid = m.open(1, 80, 24).unwrap();
    assert_eq!(m.session_count(1), 1);
    m.close(1, &sid).unwrap();
    assert!(m.is_alive(1, &sid).is_err());
    assert_eq!(m.session_count(1), 0);
}

#[test]
fn test_close_nonexistent_session_returns_err() {
    let m = mgr("t4");
    let res = m.close(1, "nonexistent-session-id");
    assert!(res.is_err());
}

#[test]
fn test_write_to_nonexistent_session_returns_err() {
    let m = mgr("t5");
    let res = m.write(1, "nonexistent-session-id", b"hello");
    assert!(res.is_err());
}

#[test]
fn test_resize_valid_and_invalid() {
    let m = mgr("t6");
    let sid = m.open(1, 80, 24).unwrap();
    assert!(m.resize(1, &sid, 100, 30).is_ok());
    assert!(m.resize(1, "nonexistent-session-id", 100, 30).is_err());
}

#[test]
fn test_interrupt_valid_session() {
    let m = mgr("t7");
    let sid = m.open(1, 80, 24).unwrap();
    assert!(m.interrupt(1, &sid).is_ok());
}

#[test]
fn test_output_limit_setter_getter() {
    let m = mgr("t8");
    m.set_output_limit(1024);
    assert_eq!(m.output_limit(), 1024);
}

#[test]
fn test_read_chunk_limited_returns_data() {
    let m = mgr("t9");
    let sid = m.open(1, 80, 24).unwrap();
    m.write(1, &sid, b"echo hello\n").unwrap();
    let mut buf = [0u8; 4096];
    let start = Instant::now();
    let mut got_data = false;
    while start.elapsed() < Duration::from_secs(15) {
        match m.read_chunk_limited(1, &sid, &mut buf) {
            Ok(ReadOutcome::Data(n)) => {
                assert!(n > 0);
                got_data = true;
                break;
            }
            Ok(_) => {}
            Err(_) => {}
        }
    }
    assert!(got_data, "expected Data outcome within 15 seconds");
}

#[test]
fn test_session_count_per_user_isolation() {
    let m = mgr("t10");
    m.open(1, 80, 24).unwrap();
    m.open(1, 80, 24).unwrap();
    m.open(2, 80, 24).unwrap();
    assert_eq!(m.session_count(1), 2);
    assert_eq!(m.session_count(2), 1);
}

#[test]
fn test_write_with_wrong_user_id_returns_err() {
    let m = mgr("t11");
    let sid = m.open(1, 80, 24).unwrap();
    let res = m.write(2, &sid, b"hello");
    assert!(res.is_err());
}

#[test]
fn test_reap_idle_with_active_sessions_returns_zero() {
    let m = mgr("t12");
    m.open(1, 80, 24).unwrap();
    assert_eq!(m.reap_idle(), 0);
}
