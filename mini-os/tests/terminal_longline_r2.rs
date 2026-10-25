use std::sync::Arc;
use std::time::{Duration, Instant};

use mini_os::terminal::TerminalManager;

fn mgr(data_suffix: &str, max: usize, idle: u64) -> TerminalManager {
    let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(format!("tmp-term-{}-{}", data_suffix, std::process::id()));
    TerminalManager::new(dir.to_string_lossy().into_owned(), max, idle)
}

#[test]
fn long_line_32k_roundtrip() {
    // 测什么：向 PTY 分块写入 32KB 超长行（外加换行），同时并发读回，
    //         断言累积输出中出现了完整的 32768 个连续 'L' 字符。
    // 为什么：用户粘贴大段文本 / 大数据输出是常态，write_all 的阻塞语义
    //         必须保证字节完整透传，不能被截断或丢失。
    // 就绪等待是必要条件：open 之后 bash 尚未启动完，PTY 从机仍处于内核
    //         行规程的规范模式，规范模式行缓冲上限约 4KB，超出的字节会被
    //         行规程直接丢弃，导致 32768 个连续 'L' 永远凑不齐。必须等
    //         shell 就绪、readline 接管并切换到非规范模式后再开始写。
    // 分块写模拟真实大粘贴：每块 2048 字节、块间 100ms，配合并发读线程
    //         边收边排空，贴近前端实际消费节奏。
    let m = Arc::new(mgr("longline", 4, 3600));
    let sid = m.open(1, 80, 24).expect("open session");

    // 等 shell 就绪，脱离规范模式，避免 4KB 行缓冲丢字节。
    std::thread::sleep(Duration::from_millis(1500));

    let (tx, rx) = std::sync::mpsc::channel::<bool>();
    let reader = {
        let m = Arc::clone(&m);
        let sid = sid.clone();
        std::thread::spawn(move || {
            let needle = "L".repeat(32768);
            let start = Instant::now();
            let timeout = Duration::from_secs(30);
            let mut acc: Vec<u8> = Vec::new();
            let mut buf = [0u8; 8192];
            let mut found = false;
            while start.elapsed() < timeout {
                match m.read_chunk(1, &sid, &mut buf) {
                    Ok(0) => {}
                    Ok(n) => {
                        acc.extend_from_slice(&buf[..n]);
                        if acc.windows(needle.len()).any(|w| w == needle.as_bytes()) {
                            found = true;
                            break;
                        }
                    }
                    Err(e) => panic!(
                        "read_chunk failed: {:?}, accumulated: {} bytes",
                        e,
                        acc.len()
                    ),
                }
            }
            let _ = tx.send(found);
        })
    };

    let payload = "L".repeat(32768);
    assert_eq!(payload.len(), 32768);
    let bytes = payload.as_bytes();
    let chunk_size = 2048;
    let mut offset = 0;
    while offset < bytes.len() {
        let end = std::cmp::min(offset + chunk_size, bytes.len());
        assert_eq!(m.write(1, &sid, &bytes[offset..end]), Ok(()));
        offset = end;
        std::thread::sleep(Duration::from_millis(100));
    }
    assert_eq!(m.write(1, &sid, b"\n"), Ok(()));

    let found = rx
        .recv_timeout(Duration::from_secs(60))
        .expect("reader thread did not report within 60s");
    assert!(
        found,
        "did not observe 32768 consecutive 'L' via concurrent reader"
    );
    reader.join().expect("reader thread panicked");

    assert_eq!(m.session_count(1), 1);
    assert_eq!(m.close(1, &sid), Ok(()));
}

#[test]
fn concurrent_writes_no_panic() {
    // 测什么：8 个线程并发向同一会话各写 200 行，全部 join 之后
    //         断言会话仍然存活（is_alive == Ok(true)）。
    // 为什么：writer 内部是 Mutex 串行化的，前端多路输入（粘贴 + 按键）
    //         并发写同一 PTY 必须安全，不允许 panic 或死锁。
    let m = Arc::new(mgr("concw", 4, 3600));
    let sid = m.open(1, 80, 24).expect("open session");

    let mut handles = Vec::new();
    for i in 0..8 {
        let m = Arc::clone(&m);
        let sid = sid.clone();
        handles.push(std::thread::spawn(move || {
            for j in 0..200 {
                let line = format!("c{i}-{j}\n");
                assert_eq!(m.write(1, &sid, line.as_bytes()), Ok(()));
            }
        }));
    }

    for h in handles {
        h.join().expect("writer thread panicked");
    }

    assert_eq!(m.is_alive(1, &sid), Ok(true));
    assert_eq!(m.close(1, &sid), Ok(()));
}
