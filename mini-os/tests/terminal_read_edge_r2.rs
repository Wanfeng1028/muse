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

// 测什么：open 对极端 cols/rows 做 clamp(2, 500)，0/0 与 9999/9999 均返回 Ok。
// 为什么：前端传入非法窗口尺寸不能导致 open 报错或 PTY 崩溃，必须被钳位为合法值。
#[test]
fn open_clamps_dimensions() {
    let m = mgr("open-clamp", 8, 3600);

    let sid1 = m
        .open(1, 0, 0)
        .expect("open with 0x0 must clamp and succeed");
    assert!(!sid1.is_empty(), "session id should be non-empty");
    m.close(1, &sid1).expect("close session1 should succeed");

    let sid2 = m
        .open(1, 9999, 9999)
        .expect("open with 9999x9999 must clamp and succeed");
    assert!(!sid2.is_empty(), "session id should be non-empty");
    m.close(1, &sid2).expect("close session2 should succeed");

    assert_eq!(m.session_count(1), 0, "all sessions should be closed");
}

// 测什么：resize 对极端 cols/rows 同样做 clamp(2, 500)，0/0 与 60000/60000 均返回 Ok(())。
// 为什么：resize 底层走 PTY ioctl，非法尺寸若直透可能返回系统错误；钳位保证语义稳定可预期。
#[test]
fn resize_clamps_dimensions() {
    let m = mgr("resize-clamp", 4, 3600);
    let sid = m.open(1, 80, 24).expect("open session should succeed");

    let r1 = m.resize(1, &sid, 0, 0);
    assert_eq!(r1, Ok(()), "resize with 0x0 must clamp and succeed");

    let r2 = m.resize(1, &sid, 60000, 60000);
    assert_eq!(r2, Ok(()), "resize with 60000x60000 must clamp and succeed");

    m.close(1, &sid).expect("close session should succeed");
    assert_eq!(m.session_count(1), 0, "session should be closed");
}
