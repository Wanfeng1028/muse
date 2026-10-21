use axum::body::Body;
use axum::http::{Request, StatusCode};
use serde_json::Value;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::time::timeout;
use tower::ServiceExt;

async fn register(app: &axum::Router, username: &str) -> (StatusCode, Value, String) {
    let body = serde_json::json!({"username": username, "password": "password123"}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    let status = resp.status();
    let cookie = resp
        .headers()
        .get("set-cookie")
        .expect("register should set cookie")
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, value, cookie)
}

async fn build_test_app() -> (axum::Router, String) {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);
    let (status, _v, cookie) = register(&app, "admin").await;
    assert_eq!(status, StatusCode::CREATED);
    (app, cookie)
}

async fn spawn_server(app: axum::Router) -> std::net::SocketAddr {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    addr
}

async fn connect_ws(addr: std::net::SocketAddr, cookie: &str) -> TcpStream {
    let mut stream = TcpStream::connect(addr).await.unwrap();
    let req = format!(
        "GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nCookie: {}\r\n\r\n",
        addr.port(), cookie,
    );
    stream.write_all(req.as_bytes()).await.unwrap();
    let mut buf = Vec::new();
    let mut byte = [0u8; 1];
    loop {
        let n = stream.read(&mut byte).await.unwrap();
        if n == 0 {
            break;
        }
        buf.push(byte[0]);
        if buf.len() >= 4 && &buf[buf.len() - 4..] == b"\r\n\r\n" {
            break;
        }
    }
    let status = String::from_utf8_lossy(&buf);
    assert!(
        status.starts_with("HTTP/1.1 101"),
        "upgrade failed: {}",
        status.lines().next().unwrap_or("")
    );
    stream
}

fn client_frame(opcode: u8, payload: &[u8]) -> Vec<u8> {
    let mut f = vec![0x80 | opcode];
    let n = payload.len();
    if n < 126 {
        f.push(0x80 | n as u8);
    } else if n < 65536 {
        f.push(0x80 | 126);
        f.extend_from_slice(&(n as u16).to_be_bytes());
    } else {
        f.push(0x80 | 127);
        f.extend_from_slice(&(n as u64).to_be_bytes());
    }
    let mask = [0x11u8, 0x22, 0x33, 0x44];
    f.extend_from_slice(&mask);
    f.extend(
        payload
            .iter()
            .enumerate()
            .map(|(i, b)| b ^ mask[i % 4])
            .collect::<Vec<u8>>(),
    );
    f
}

async fn read_frame(stream: &mut TcpStream) -> Option<(u8, Vec<u8>)> {
    let mut header = [0u8; 2];
    let n = stream.read(&mut header).await.ok()?;
    if n == 0 {
        return None;
    }
    if n < 2 {
        let mut rest = [0u8; 1];
        stream.read_exact(&mut rest).await.ok()?;
        header[1] = rest[0];
    }
    let opcode = header[0] & 0x0F;
    let masked = header[1] & 0x80 != 0;
    let mut len = (header[1] & 0x7F) as u64;
    if len == 126 {
        let mut ext = [0u8; 2];
        stream.read_exact(&mut ext).await.ok()?;
        len = u16::from_be_bytes(ext) as u64;
    } else if len == 127 {
        let mut ext = [0u8; 8];
        stream.read_exact(&mut ext).await.ok()?;
        len = u64::from_be_bytes(ext);
    }
    let mut mask = [0u8; 4];
    if masked {
        stream.read_exact(&mut mask).await.ok()?;
    }
    let mut payload = vec![0u8; len as usize];
    if len > 0 {
        stream.read_exact(&mut payload).await.ok()?;
    }
    if masked {
        for (i, b) in payload.iter_mut().enumerate() {
            *b ^= mask[i % 4];
        }
    }
    Some((opcode, payload))
}

async fn read_text_frame(stream: &mut TcpStream) -> Value {
    let (op, payload) = timeout(Duration::from_secs(30), read_frame(stream))
        .await
        .expect("read frame timeout")
        .expect("stream closed");
    assert_eq!(op, 0x1, "expected text frame, got opcode {}", op);
    serde_json::from_slice(&payload).expect("frame payload must be JSON")
}

async fn recv_until(stream: &mut TcpStream, want_type: &str, needle: &str) -> Value {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(30);
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        let (op, payload) = timeout(left, read_frame(stream))
            .await
            .expect("timeout")
            .expect("stream closed");
        if op != 0x1 {
            continue;
        }
        let v: Value = match serde_json::from_slice(&payload) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let t = v.get("type").and_then(|x| x.as_str()).unwrap_or("");
        if t == want_type {
            let s = v.to_string();
            if needle.is_empty() || s.contains(needle) {
                return v;
            }
        }
    }
}

#[tokio::test]
async fn ws_reconnect_after_drop() {
    // 测什么：连接断开后重连，hello 与 term_open 均正常。
    // 为什么：网络抖动/前端刷新后重连是常态，服务端不能因旧连接残留状态而拒绝新连接。
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;

    let mut s1 = connect_ws(addr, &cookie).await;
    let hello1 = read_text_frame(&mut s1).await;
    assert_eq!(hello1.get("type").and_then(|v| v.as_str()), Some("hello"));
    assert_eq!(
        hello1.get("message").and_then(|v| v.as_str()),
        Some("welcome to mini-os")
    );
    assert_eq!(hello1.get("term").and_then(|v| v.as_str()), Some("v1"));

    s1.write_all(&client_frame(0x8, b"")).await.unwrap();
    drop(s1);

    tokio::time::sleep(Duration::from_millis(300)).await;

    let mut s2 = connect_ws(addr, &cookie).await;
    let hello2 = read_text_frame(&mut s2).await;
    assert_eq!(hello2.get("type").and_then(|v| v.as_str()), Some("hello"));
    assert_eq!(
        hello2.get("message").and_then(|v| v.as_str()),
        Some("welcome to mini-os")
    );
    assert_eq!(hello2.get("term").and_then(|v| v.as_str()), Some("v1"));

    let open = serde_json::json!({"type": "term_open", "cols": 80, "rows": 24}).to_string();
    s2.write_all(&client_frame(0x1, open.as_bytes()))
        .await
        .unwrap();

    let ready = recv_until(&mut s2, "term_ready", "").await;
    assert_eq!(
        ready.get("type").and_then(|v| v.as_str()),
        Some("term_ready")
    );
    let sid = ready
        .get("session_id")
        .and_then(|v| v.as_str())
        .expect("session_id present");
    assert_eq!(
        sid.len(),
        32,
        "session_id should be 32 hex chars, got {:?}",
        sid
    );
    assert!(
        sid.chars().all(|c| c.is_ascii_hexdigit()),
        "session_id must be hex, got {:?}",
        sid
    );
}

#[tokio::test]
async fn ws_ping_gets_pong() {
    // 测什么：ping/pong 心跳链路通。
    // 为什么：前端靠心跳判断连接存活，底层自动回 pong 是不断线的保障。
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;

    let mut stream = connect_ws(addr, &cookie).await;
    let hello = read_text_frame(&mut stream).await;
    assert_eq!(hello.get("type").and_then(|v| v.as_str()), Some("hello"));

    stream
        .write_all(&client_frame(0x9, b"ping-22"))
        .await
        .unwrap();

    let (op, payload) = timeout(Duration::from_secs(5), read_frame(&mut stream))
        .await
        .expect("pong read timeout")
        .expect("stream closed before pong");
    assert_eq!(op, 0xA, "expected pong opcode 0xA, got 0x{:X}", op);
    assert_eq!(payload, b"ping-22", "pong payload must echo ping payload");
}

#[tokio::test]
async fn ws_echo_preserves_order() {
    // 测什么：服务端按序回 echo，消息不乱序不丢失。
    // 为什么：WS 是有序可靠通道，乱序会破坏终端交互与所有上层协议。
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;

    let mut stream = connect_ws(addr, &cookie).await;
    let hello = read_text_frame(&mut stream).await;
    assert_eq!(hello.get("type").and_then(|v| v.as_str()), Some("hello"));

    stream
        .write_all(&client_frame(0x1, b"ord-1"))
        .await
        .unwrap();
    stream
        .write_all(&client_frame(0x1, b"ord-2"))
        .await
        .unwrap();
    stream
        .write_all(&client_frame(0x1, b"ord-3"))
        .await
        .unwrap();

    let f1 = read_text_frame(&mut stream).await;
    assert_eq!(f1.get("type").and_then(|v| v.as_str()), Some("echo"));
    assert_eq!(f1.get("message").and_then(|v| v.as_str()), Some("ord-1"));

    let f2 = read_text_frame(&mut stream).await;
    assert_eq!(f2.get("type").and_then(|v| v.as_str()), Some("echo"));
    assert_eq!(f2.get("message").and_then(|v| v.as_str()), Some("ord-2"));

    let f3 = read_text_frame(&mut stream).await;
    assert_eq!(f3.get("type").and_then(|v| v.as_str()), Some("echo"));
    assert_eq!(f3.get("message").and_then(|v| v.as_str()), Some("ord-3"));
}
