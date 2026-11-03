use std::time::{Duration, Instant};

use mini_os::terminal::{TermError, TerminalManager};

fn mgr(data_suffix: &str, max: usize, idle: u64) -> TerminalManager {
    let dir = std::env::temp_dir().join(format!(
        "minios-term-test-{}-{}",
        data_suffix,
        std::process::id()
    ));
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

/// 测什么：open 返回 32 位 hex id，写入命令后能通过 read_chunk 读到回显与输出。
/// 为什么：验证 PTY 最基本的数据通路（master 写 -> shell 执行 -> slave 读回）。
#[test]
fn open_write_read_echo() {
    let m = mgr("echo", 4, 3600);
    let sid = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open failed: {:?}", e),
    };
    assert_eq!(sid.len(), 32, "session id should be 32 hex chars");
    assert!(sid.chars().all(|c| c.is_ascii_hexdigit()));

    match m.write(1, &sid, b"echo hello-term-it\n") {
        Ok(()) => {}
        Err(e) => panic!("write failed: {:?}", e),
    }

    let out = read_until(&m, 1, &sid, "hello-term-it", Duration::from_secs(10));
    assert!(out.contains("hello-term-it"));

    match m.close(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("close failed: {:?}", e),
    }
}

/// 测什么：会话归属隔离。用户 2 拿到用户 1 的 sid，所有操作都应 Forbidden。
/// 为什么：跨用户访问是安全红线，必须在每个入口都拦住。
#[test]
fn session_isolation() {
    let m = mgr("isolation", 4, 3600);
    let sid = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open failed: {:?}", e),
    };

    assert_eq!(m.write(2, &sid, b"x"), Err(TermError::Forbidden));
    assert_eq!(m.resize(2, &sid, 100, 30), Err(TermError::Forbidden));
    assert_eq!(m.interrupt(2, &sid), Err(TermError::Forbidden));
    let mut buf = [0u8; 64];
    assert_eq!(m.read_chunk(2, &sid, &mut buf), Err(TermError::Forbidden));
    assert_eq!(m.close(2, &sid), Err(TermError::Forbidden));
    assert_eq!(m.is_alive(2, &sid), Err(TermError::Forbidden));

    assert_eq!(m.session_count(1), 1);
    match m.close(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("close failed: {:?}", e),
    }
}

/// 测什么：不存在的 sid 返回 NotFound，而不是别的错误。
/// 为什么：区分 Forbidden（越权）与 NotFound（不存在），错误语义要对。
#[test]
fn unknown_session() {
    let m = mgr("unknown", 4, 3600);
    let bogus = "deadbeefdeadbeefdeadbeefdeadbeef";
    assert_eq!(m.write(1, bogus, b"x"), Err(TermError::NotFound));
}

/// 测什么：每用户限额。用户 7 开满 2 个后第 3 个 LimitReached；用户 8 不受影响。
/// 为什么：限额必须按 user_id 维度计数，不能全局或串号。
#[test]
fn per_user_limit() {
    let m = mgr("limit", 2, 3600);
    let s1 = match m.open(7, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open 1 failed: {:?}", e),
    };
    let s2 = match m.open(7, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open 2 failed: {:?}", e),
    };
    assert_eq!(m.open(7, 80, 24), Err(TermError::LimitReached));
    assert_eq!(m.session_count(7), 2);

    match m.open(8, 80, 24) {
        Ok(_) => {}
        Err(e) => panic!("user 8 open failed: {:?}", e),
    }

    match m.close(7, &s1) {
        Ok(()) => {}
        Err(e) => panic!("close s1 failed: {:?}", e),
    }
    match m.close(7, &s2) {
        Ok(()) => {}
        Err(e) => panic!("close s2 failed: {:?}", e),
    }
    match m.close(
        8,
        &m.open(8, 80, 24)
            .unwrap_or_else(|e| panic!("reopen 8 failed: {:?}", e)),
    ) {
        Ok(()) => {}
        Err(e) => panic!("close user8 failed: {:?}", e),
    }
}

/// 测什么：interrupt 只杀前台进程组，shell 本身存活。
/// 原理：interrupt 向 pty master 写 0x03，PTY 的 ISIG 将其转成 SIGINT 发给前台进程组，
/// 因此 sleep 被中断，但 shell 自身不在前台进程组（或被忽略），继续可交互。
/// 断言：中断后再跑 echo 仍能读到输出，且 is_alive 为 true。
#[test]
fn interrupt_kills_foreground_but_keeps_shell() {
    let m = mgr("interrupt", 4, 3600);
    let sid = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open failed: {:?}", e),
    };

    match m.write(1, &sid, b"sleep 30\n") {
        Ok(()) => {}
        Err(e) => panic!("write sleep failed: {:?}", e),
    }
    std::thread::sleep(Duration::from_millis(500));

    match m.interrupt(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("interrupt failed: {:?}", e),
    }

    match m.write(1, &sid, b"echo alive-after-sigint\n") {
        Ok(()) => {}
        Err(e) => panic!("write echo failed: {:?}", e),
    }

    let out = read_until(&m, 1, &sid, "alive-after-sigint", Duration::from_secs(10));
    assert!(out.contains("alive-after-sigint"));

    match m.is_alive(1, &sid) {
        Ok(true) => {}
        other => panic!("expected alive, got {:?}", other),
    }

    match m.close(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("close failed: {:?}", e),
    }
}

/// 测什么：resize 在活动会话上返回 Ok。
/// 为什么：窗口尺寸变更走 ioctl TIOCSWINSZ，成功路径不应报错。
#[test]
fn resize_ok() {
    let m = mgr("resize", 4, 3600);
    let sid = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open failed: {:?}", e),
    };
    assert_eq!(m.resize(1, &sid, 100, 30), Ok(()));
    match m.close(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("close failed: {:?}", e),
    }
}

/// 测什么：close 后会话从计数中移除，重复 close / write 都是 NotFound。
/// 为什么：close 必须幂等地在语义上表现为"已不存在"，且不残留状态。
#[test]
fn close_removes_session() {
    let m = mgr("close", 4, 3600);
    let sid = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open failed: {:?}", e),
    };
    assert_eq!(m.session_count(1), 1);
    match m.close(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("close failed: {:?}", e),
    }
    assert_eq!(m.session_count(1), 0);
    assert_eq!(m.close(1, &sid), Err(TermError::NotFound));
    assert_eq!(m.write(1, &sid, b"x"), Err(TermError::NotFound));
}

/// 测什么：reap_idle 按 idle 超时回收过期会话，不误伤新鲜会话。
/// 为什么：通过 set_last_active_for_test 注入"两小时前活跃"，配合 idle=3600，
/// 应当恰好回收 1 个；新鲜会话保持可用。
#[test]
fn reap_idle_reaps_stale() {
    let m = mgr("reap", 4, 3600);
    let stale = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open stale failed: {:?}", e),
    };
    m.set_last_active_for_test(&stale, Instant::now() - Duration::from_secs(7200));

    let fresh = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open fresh failed: {:?}", e),
    };

    assert_eq!(m.reap_idle(), 1);
    assert_eq!(m.write(1, &stale, b"x"), Err(TermError::NotFound));
    match m.is_alive(1, &fresh) {
        Ok(true) => {}
        other => panic!("expected fresh alive, got {:?}", other),
    }

    match m.close(1, &fresh) {
        Ok(()) => {}
        Err(e) => panic!("close fresh failed: {:?}", e),
    }
}

/// 测什么：shell 真能跑命令，且 open 注入了 MINIOS_TERM=1。
/// 为什么：验证 PTY 背后确实是可用的交互 shell，且环境变量按预期注入。
#[test]
fn shell_runs_real_commands() {
    let m = mgr("realcmds", 4, 3600);
    let sid = match m.open(1, 80, 24) {
        Ok(s) => s,
        Err(e) => panic!("open failed: {:?}", e),
    };

    match m.write(1, &sid, b"pwd\n") {
        Ok(()) => {}
        Err(e) => panic!("write pwd failed: {:?}", e),
    }
    let _ = read_until(&m, 1, &sid, "/", Duration::from_secs(10));

    match m.write(1, &sid, b"echo $MINIOS_TERM\n") {
        Ok(()) => {}
        Err(e) => panic!("write env echo failed: {:?}", e),
    }
    let out = read_until(&m, 1, &sid, "1", Duration::from_secs(10));
    assert!(out.contains("1"));

    match m.close(1, &sid) {
        Ok(()) => {}
        Err(e) => panic!("close failed: {:?}", e),
    }
}
