//! The NDJSON client: connects to the bridge socket, authenticates each request with the run
//! token, and reads responses with a deadline and a cancel check so it can never block forever.

use super::protocol::{GhidraError, Request, Response};
use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::net::{SocketAddr, TcpStream};
use std::time::{Duration, Instant};

/// How long one socket read blocks before we re-check the deadline and the cancel flag.
const READ_TICK: Duration = Duration::from_millis(200);

pub struct Client {
    writer: TcpStream,
    reader: BufReader<TcpStream>,
    token: String,
    next_id: u64,
}

impl std::fmt::Debug for Client {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GhidraClient").field("next_id", &self.next_id).finish()
    }
}

impl Client {
    /// Connect to the bridge, retrying until the deadline (the bridge may not be listening yet).
    pub fn connect(addr: SocketAddr, token: &str, deadline: Instant) -> Result<Client, GhidraError> {
        let mut last = String::new();
        loop {
            if Instant::now() >= deadline {
                return Err(GhidraError::Timeout(format!("could not connect to the bridge at {addr}: {last}")));
            }
            match TcpStream::connect_timeout(&addr, Duration::from_millis(500)) {
                Ok(stream) => {
                    stream.set_read_timeout(Some(READ_TICK)).map_err(|e| GhidraError::Connection(e.to_string()))?;
                    let reader = BufReader::new(stream.try_clone().map_err(|e| GhidraError::Connection(e.to_string()))?);
                    return Ok(Client { writer: stream, reader, token: token.to_string(), next_id: 1 });
                }
                Err(e) => {
                    last = e.to_string();
                    std::thread::sleep(Duration::from_millis(100));
                }
            }
        }
    }

    /// Send one request and wait for its reply (bounded by `deadline` and `cancel`).
    pub fn request(&mut self, method: &str, params: Value, cancel: &dyn Fn() -> bool, deadline: Instant) -> Result<Value, GhidraError> {
        let id = self.next_id;
        self.next_id = self.next_id.saturating_add(1);
        let req = Request { id, token: self.token.clone(), method: method.to_string(), params };
        let mut line = serde_json::to_string(&req).map_err(|e| GhidraError::Protocol(e.to_string()))?;
        line.push('\n');
        self.writer.write_all(line.as_bytes()).map_err(|e| GhidraError::Connection(e.to_string()))?;
        self.writer.flush().map_err(|e| GhidraError::Connection(e.to_string()))?;

        loop {
            if cancel() {
                return Err(GhidraError::Cancelled);
            }
            if Instant::now() >= deadline {
                return Err(GhidraError::Timeout(format!("no reply to {method} within the deadline")));
            }
            let mut buf = String::new();
            match self.reader.read_line(&mut buf) {
                Ok(0) => return Err(GhidraError::Connection("the bridge closed the connection".into())),
                Ok(_) => {
                    let trimmed = buf.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    let resp: Response = serde_json::from_str(trimmed).map_err(|e| GhidraError::Protocol(format!("bad response: {e}")))?;
                    if resp.id != id {
                        // Out-of-order frame; keep reading for ours.
                        continue;
                    }
                    if resp.ok {
                        return Ok(resp.result.unwrap_or(Value::Null));
                    }
                    let err = resp.error.unwrap_or(super::protocol::WireError { code: "bridge_error".into(), message: "unknown error".into() });
                    return Err(GhidraError::Bridge { code: err.code, message: err.message });
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock || e.kind() == std::io::ErrorKind::TimedOut => {
                    // Read tick elapsed; loop re-checks deadline and cancel.
                    continue;
                }
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(GhidraError::Connection(e.to_string())),
            }
        }
    }

    /// The handshake: returns the bridge's session info.
    pub fn ping(&mut self, cancel: &dyn Fn() -> bool, deadline: Instant) -> Result<Value, GhidraError> {
        self.request("ping", Value::Null, cancel, deadline)
    }

    /// Best-effort clean shutdown; ignores errors (the process-group kill is the backstop).
    pub fn shutdown(&mut self) {
        let deadline = Instant::now() + Duration::from_secs(10);
        let _ = self.request("shutdown", Value::Null, &|| false, deadline);
    }
}
