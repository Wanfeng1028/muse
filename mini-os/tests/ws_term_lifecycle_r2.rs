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

async fn send_text(stream: &mut TcpStream, v: &Value) {
    let payload = v.to_string();
    stream
        .write_all(&client_frame(0x1, payload.as_bytes()))
        .await
        .unwrap();
}

#[tokio::test]
async fn ws_sigint_kills_sleep_keeps_shell() {
    // 测什么：通过 WS 发 term_signal signal="int" 中断前台 sleep 30 后，shell 仍然存活并响应后续输入。
    // 为什么：Ctrl+C 是终端最高频操作，WS 层的 interrupt 必须走 0x03 真 PTY 语义而不是 kill 进程，
    // 否则 shell 会一起死掉，后续 echo 就不会产生 term_output。
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut ws = connect_ws(addr, &cookie).await;

    let hello = read_text_frame(&mut ws).await;
    assert_eq!(hello.get("type").and_then(|v| v.as_str()), Some("hello"));
    assert_eq!(
        hello.get("message").and_then(|v| v.as_str()),
        Some("welcome to mini-os")
    );
    assert_eq!(hello.get("term").and_then(|v| v.as_str()), Some("v1"));

    send_text(
        &mut ws,
        &serde_json::json!({"type": "term_open", "cols": 80, "rows": 24}),
    )
    .await;
    let ready = recv_until(&mut ws, "term_ready", "").await;
    let sid = ready
        .get("session_id")
        .and_then(|v| v.as_str())
        .expect("term_ready must carry session_id")
        .to_string();
    assert_eq!(
        sid.len(),
        32,
        "session_id must be 32 hex chars, got {}",
        sid
    );
    assert!(
        sid.chars().all(|c| c.is_ascii_hexdigit()),
        "session_id must be hex, got {}",
        sid
    );

    send_text(
        &mut ws,
        &serde_json::json!({
            "type": "term_input",
            "session_id": sid,
            "data": "sleep 30\n"
        }),
    )
    .await;

    tokio::time::sleep(Duration::from_millis(600)).await;

    send_text(
        &mut ws,
        &serde_json::json!({
            "type": "term_signal",
            "session_id": sid,
            "signal": "int"
        }),
    )
    .await;

    send_text(
        &mut ws,
        &serde_json::json!({
            "type": "term_input",
            "session_id": sid,
            "data": "echo ws-alive-21\n"
        }),
    )
    .await;

    let out = recv_until(&mut ws, "term_output", "ws-alive-21").await;
    assert_eq!(
        out.get("type").and_then(|v| v.as_str()),
        Some("term_output")
    );
    assert_eq!(
        out.get("session_id").and_then(|v| v.as_str()),
        Some(sid.as_str())
    );
    let data = out
        .get("data")
        .and_then(|v| v.as_str())
        .expect("term_output must carry data");
    assert!(
        data.contains("ws-alive-21"),
        "term_output data must contain echoed marker, got {:?}",
        data
    );
}

#[tokio::test]
async fn ws_close_then_input_not_found() {
    // 测什么：term_close 关闭会话后，再用同一 session_id 发 term_input，必须返回 term_error 且 message 为「会话不存在」。
    // 为什么：关闭语义必须干净，不能留下可写但无 reader 的半吊子会话，否则后续写入会静默丢弃数据。
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut ws = connect_ws(addr, &cookie).await;

    let hello = read_text_frame(&mut ws).await;
    assert_eq!(hello.get("type").and_then(|v| v.as_str()), Some("hello"));

    send_text(
        &mut ws,
        &serde_json::json!({"type": "term_open", "cols": 80, "rows": 24}),
    )
    .await;
    let ready = recv_until(&mut ws, "term_ready", "").await;
    let sid = ready
        .get("session_id")
        .and_then(|v| v.as_str())
        .expect("term_ready must carry session_id")
        .to_string();
    assert_eq!(sid.len(), 32);

    send_text(
        &mut ws,
        &serde_json::json!({
            "type": "term_close",
            "session_id": sid
        }),
    )
    .await;

    send_text(
        &mut ws,
        &serde_json::json!({
            "type": "term_input",
            "session_id": sid,
            "data": "echo x\n"
        }),
    )
    .await;

    let err = recv_until(&mut ws, "term_error", "").await;
    assert_eq!(err.get("type").and_then(|v| v.as_str()), Some("term_error"));
    assert_eq!(
        err.get("session_id").and_then(|v| v.as_str()),
        Some(sid.as_str())
    );
    assert_eq!(
        err.get("message").and_then(|v| v.as_str()),
        Some("会话不存在")
    );
}
