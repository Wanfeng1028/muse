use std::time::Duration;

use serde_json::Value;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::time::timeout;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use tower::ServiceExt;

async fn build_test_app() -> (axum::Router, String) {
    let state = mini_os::init_state(":memory:", "static");
    let app = mini_os::build_app(state);

    let body = serde_json::json!({
        "username": "admin",
        "password": "password123",
    })
    .to_string();

    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/register")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();

    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

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

async fn upgrade_ws(addr: std::net::SocketAddr, cookie: Option<&str>) -> TcpStream {
    let mut stream = TcpStream::connect(addr).await.unwrap();

    let cookie_line = match cookie {
        Some(c) => format!("Cookie: {}\r\n", c),
        None => String::new(),
    };

    let req = format!(
        "GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n{}\r\n",
        addr.port(),
        cookie_line,
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

    stream
}

fn read_status_line(buf: &[u8]) -> String {
    let text = String::from_utf8_lossy(buf);
    text.lines().next().unwrap_or("").to_string()
}

async fn read_http_headers(stream: &mut TcpStream) -> Vec<u8> {
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
    buf
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

async fn read_frame_timed(stream: &mut TcpStream) -> Option<(u8, Vec<u8>)> {
    timeout(Duration::from_millis(1500), read_frame(stream))
        .await
        .ok()
        .flatten()
}

#[tokio::test]
async fn ws_hello_frame_is_valid_json() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let headers = read_http_headers(&mut stream).await;
    assert!(
        read_status_line(&headers).starts_with("HTTP/1.1 101"),
        "expected 101 upgrade, got {:?}",
        read_status_line(&headers)
    );

    let (opcode, payload) = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");
    assert_eq!(opcode, 0x1, "hello must be a text frame");

    let json: Value = serde_json::from_slice(&payload).expect("hello must be valid JSON");
    assert_eq!(json["type"], "hello");
    assert_eq!(json["message"], "welcome to mini-os");
}

#[tokio::test]
async fn ws_echo_text_roundtrip() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let _ = read_http_headers(&mut stream).await;
    let _hello = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");

    stream
        .write_all(&client_frame(0x1, b"hello-ws-123"))
        .await
        .unwrap();

    let (opcode, payload) = read_frame_timed(&mut stream)
        .await
        .expect("expected echo frame");
    assert_eq!(opcode, 0x1);

    let json: Value = serde_json::from_slice(&payload).expect("echo must be valid JSON");
    assert_eq!(json["type"], "echo");
    assert_eq!(json["message"], "hello-ws-123");
}

#[tokio::test]
async fn ws_echo_unicode() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let _ = read_http_headers(&mut stream).await;
    let _hello = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");

    let text = "你好世界🎉";
    stream
        .write_all(&client_frame(0x1, text.as_bytes()))
        .await
        .unwrap();

    let (opcode, payload) = read_frame_timed(&mut stream)
        .await
        .expect("expected echo frame");
    assert_eq!(opcode, 0x1);

    let json: Value = serde_json::from_slice(&payload).expect("echo must be valid JSON");
    assert_eq!(json["type"], "echo");
    assert_eq!(json["message"], text);
}

#[tokio::test]
async fn ws_echo_empty_text() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let _ = read_http_headers(&mut stream).await;
    let _hello = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");

    stream.write_all(&client_frame(0x1, b"")).await.unwrap();

    let (opcode, payload) = read_frame_timed(&mut stream)
        .await
        .expect("expected echo frame");
    assert_eq!(opcode, 0x1);

    let json: Value = serde_json::from_slice(&payload).expect("echo must be valid JSON");
    assert_eq!(json["type"], "echo");
    assert_eq!(json["message"], "");
}

#[tokio::test]
async fn ws_echo_20kb_uses_extended_length() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let _ = read_http_headers(&mut stream).await;
    let _hello = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");

    let big = "x".repeat(20000);
    stream
        .write_all(&client_frame(0x1, big.as_bytes()))
        .await
        .unwrap();

    let (opcode, payload) = read_frame_timed(&mut stream)
        .await
        .expect("expected echo frame");
    assert_eq!(opcode, 0x1);

    let json: Value = serde_json::from_slice(&payload).expect("echo must be valid JSON");
    assert_eq!(json["type"], "echo");
    let msg = json["message"].as_str().expect("message must be string");
    assert_eq!(msg.len(), 20000);
    assert_eq!(msg, big);
}

#[tokio::test]
async fn ws_binary_ignored_then_still_alive() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let _ = read_http_headers(&mut stream).await;
    let _hello = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");

    stream
        .write_all(&client_frame(0x2, &[1, 2, 3, 4]))
        .await
        .unwrap();

    let no_frame = timeout(Duration::from_millis(400), read_frame(&mut stream)).await;
    assert!(
        no_frame.is_err(),
        "binary message must be ignored (no frame within 400ms)"
    );

    stream
        .write_all(&client_frame(0x1, b"still-here"))
        .await
        .unwrap();

    let (opcode, payload) = read_frame_timed(&mut stream)
        .await
        .expect("expected echo frame after binary");
    assert_eq!(opcode, 0x1);

    let json: Value = serde_json::from_slice(&payload).expect("echo must be valid JSON");
    assert_eq!(json["type"], "echo");
    assert_eq!(json["message"], "still-here");
}

#[tokio::test]
async fn ws_close_frame_terminates() {
    let (app, cookie) = build_test_app().await;
    let addr = spawn_server(app).await;
    let mut stream = upgrade_ws(addr, Some(&cookie)).await;

    let _ = read_http_headers(&mut stream).await;
    let _hello = read_frame_timed(&mut stream)
        .await
        .expect("expected hello frame");

    let close_payload = [0x03u8, 0xE8];
    stream
        .write_all(&client_frame(0x8, &close_payload))
        .await
        .unwrap();

    let result = timeout(Duration::from_millis(1500), read_frame(&mut stream)).await;
    match result {
        Ok(Some((opcode, _payload))) => {
            assert_eq!(opcode, 0x8, "expected close frame from server");
        }
        Ok(None) => {
            // EOF: server closed the connection
        }
        Err(_) => {
            // 若底层直接断开而没有 close 帧回显，需要确认读取会 EOF
            let mut buf = [0u8; 1];
            let n = timeout(Duration::from_millis(1500), stream.read(&mut buf))
                .await
                .expect("expected close or EOF")
                .unwrap_or(0);
            assert_eq!(n, 0, "expected EOF after close");
        }
    }
}

#[tokio::test]
async fn ws_unauthenticated_upgrade_401() {
    let (app, _cookie) = build_test_app().await;
    let addr = spawn_server(app).await;

    let mut stream = TcpStream::connect(addr).await.unwrap();

    let req = format!(
        "GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n",
        addr.port(),
    );
    stream.write_all(req.as_bytes()).await.unwrap();

    let headers = read_http_headers(&mut stream).await;
    let status = read_status_line(&headers);
    assert!(
        status.starts_with("HTTP/1.1 401"),
        "expected 401 for unauthenticated upgrade, got {:?}",
        status
    );
}
