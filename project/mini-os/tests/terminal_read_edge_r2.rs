use mini_os::terminal::{TermError, TerminalManager};
use std::path::PathBuf;

fn mgr(data_suffix: &str, max: usize, idle: u64) -> TerminalManager {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(format!("tmp-term-{}-{}", data_suffix, std::process::id()));
    TerminalManager::new(dir.to_string_lossy().into_owned(), max, idle)
}

// 测什么：零长度缓冲 read_chunk 返回 Ok(0)，且空 buf 路径依然校验会话归属（未知 id 返回 NotFound）。
// 为什么：调用方传空 buf 不应阻塞在 PTY 读上；同时归属校验不能被空 buf 绕过，否则可探测他人会话存在性。
#[test]
fn read_empty_buf_returns_zero() {
    let m = mgr("read-empty-buf", 4, 3600);
    let sid = m.open(1, 80, 24).expect("open session should succeed");

    let mut buf = [0u8; 0];
    let r = m.read_chunk(1, &sid, &mut buf);
    assert_eq!(r, Ok(0), "empty buffer read must return Ok(0)");

    let r2 = m.read_chunk(1, "deadbeefdeadbeefdeadbeefdeadbeef", &mut buf);
    assert_eq!(
        r2,
        Err(TermError::NotFound),
        "empty buffer read must still validate session ownership"
    );

    m.close(1, &sid).expect("close session should succeed");
}

// 测什么：open 遇到越界 cols/rows 返回 Err(TermError::InvalidSize)，合法范围 2..=500。
// 为什么：调用方必须传合法尺寸；坏尺寸不建会话。
#[test]
fn open_rejects_invalid_dimensions() {
    let m = mgr("open-clamp", 8, 3600);

    assert_eq!(m.open(1, 0, 0), Err(TermError::InvalidSize));
    assert_eq!(m.open(1, 9999, 9999), Err(TermError::InvalidSize));
    assert_eq!(
        m.session_count(1),
        0,
        "invalid dimensions must not create sessions"
    );

    let sid = m
        .open(1, 2, 2)
        .expect("open with boundary 2x2 should succeed");
    assert!(!sid.is_empty(), "session id should be non-empty");
    m.close(1, &sid).expect("close session should succeed");
}

// 测什么：resize 遇到越界 cols/rows 返回 Err(TermError::InvalidSize)，合法范围 2..=500。
// 为什么：调用方必须传合法尺寸；坏尺寸不改会话尺寸。
#[test]
fn resize_rejects_invalid_dimensions() {
    let m = mgr("resize-clamp", 4, 3600);
    let sid = m.open(1, 80, 24).expect("open session should succeed");

    assert_eq!(m.resize(1, &sid, 0, 0), Err(TermError::InvalidSize));
    assert_eq!(m.resize(1, &sid, 60000, 60000), Err(TermError::InvalidSize));
    assert_eq!(m.resize(1, &sid, 500, 500), Ok(()));

    m.close(1, &sid).expect("close session should succeed");
    assert_eq!(m.session_count(1), 0, "session should be closed");
}
