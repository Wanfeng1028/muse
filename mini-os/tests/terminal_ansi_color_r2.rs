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

// 测什么：PTY 对 ANSI SGR 颜色转义序列原样透传，不吞不改。
// 为什么：终端模拟器的核心价值就是透传转义序列，前端靠它渲染颜色。
#[test]
fn ansi_color_escape_passthrough() {
    let m = mgr("ansi-color-r2", 4, 3600);
    let uid: i64 = 7_001;
    let sid = m.open(uid, 80, 24).expect("open should succeed");

    m.write(
        uid,
        &sid,
        b"printf '\\e[31mRED-ANSI-1\\e[0m done-color-1\\n'\n",
    )
    .expect("write printf should succeed");

    let out = read_until(&m, uid, &sid, "\u{1b}[31m", Duration::from_secs(10));
    assert!(
        out.contains("\u{1b}[31m"),
        "output must contain the SGR red sequence ESC[31m, got: {:?}",
        out
    );
    assert!(
        out.contains("\u{1b}[0m"),
        "output must contain the SGR reset sequence ESC[0m, got: {:?}",
        out
    );

    m.close(uid, &sid).expect("close should succeed");
    assert_eq!(m.session_count(uid), 0, "session must be gone after close");
    assert_eq!(
        m.close(uid, &sid),
        Err(TermError::NotFound),
        "closing an already closed session must be NotFound"
    );
}

// 测什么：清屏与光标定位序列透传。
// 为什么：全屏应用（vim/htop 类）依赖这些序列，透传是底线。
#[test]
fn ansi_cursor_movement_passthrough() {
    let m = mgr("ansi-cursor-r2", 4, 3600);
    let uid: i64 = 7_002;
    let sid = m.open(uid, 80, 24).expect("open should succeed");

    m.write(uid, &sid, b"printf '\\e[2J\\e[10;20Hpos-ansi-2\\n'\n")
        .expect("write printf should succeed");

    let out = read_until(&m, uid, &sid, "\u{1b}[2J", Duration::from_secs(10));
    assert!(
        out.contains("\u{1b}[2J"),
        "output must contain the clear-screen sequence ESC[2J, got: {:?}",
        out
    );
    assert!(
        out.contains("\u{1b}[10;20H"),
        "output must contain the cursor-position sequence ESC[10;20H, got: {:?}",
        out
    );

    m.close(uid, &sid).expect("close should succeed");
    assert_eq!(m.session_count(uid), 0, "session must be gone after close");
    assert_eq!(
        m.close(uid, &sid),
        Err(TermError::NotFound),
        "closing an already closed session must be NotFound"
    );
}
