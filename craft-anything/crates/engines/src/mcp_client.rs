//! A small client for external MCP servers, so their tools can be offered as Craft Anything
//! tools. Two transports implement [`Transport`]: a local server over stdio (newline-delimited
//! JSON-RPC 2.0), run through `craft_anything_platform::process` like every external program and
//! killed when the client is dropped; and a remote server over Streamable HTTP (JSON or
//! server-sent events in reply to each POST).

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::{Process, RunningProcess, StdinMode};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::io::{BufRead, Write};
use std::path::PathBuf;
use std::process::ChildStdin;
use std::sync::mpsc::{Receiver, RecvTimeoutError, channel};
use std::time::{Duration, Instant};

/// The protocol version we ask for; servers may answer with an older one they support.
const PROTOCOL: &str = "2025-06-18";
/// Largest single message we accept from a server.
const MAX_LINE: usize = 16 * 1024 * 1024;

/// How to start a local server.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerCommand {
    pub command: String,
    pub args: Vec<String>,
    pub env: BTreeMap<String, String>,
    pub cwd: Option<PathBuf>,
}

/// Where a remote server answers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerUrl {
    /// `https://…`, or `http://` to this computer (`localhost`, `127.0.0.1`, `[::1]`).
    pub url: String,
    /// Sent with every request (e.g. `Authorization`).
    pub headers: BTreeMap<String, String>,
}

/// How to reach a server.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Server {
    Command(ServerCommand),
    Url(ServerUrl),
}

/// One tool a server offers (`tools/list`).
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct RemoteTool {
    pub name: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default, rename = "inputSchema")]
    pub input_schema: Value,
    #[serde(default)]
    pub annotations: Value,
}

/// How JSON-RPC messages reach a server and its answers come back. Implement it for another
/// transport (WebSocket, a pipe…) and pass it to [`McpClient::with_transport`].
pub trait Transport: Send {
    /// Send a notification (no answer expected).
    fn notify(&mut self, msg: &Value) -> Result<(), ToolError>;
    /// Send request `id` and wait (until `deadline`, or `cancelled`) for the message answering it.
    fn request(&mut self, msg: &Value, id: u64, deadline: Instant, cancelled: &dyn Fn() -> bool) -> Result<Value, ToolError>;
}

/// A server, initialized and ready for requests.
pub struct McpClient {
    name: String,
    transport: Box<dyn Transport>,
    next_id: u64,
}

impl McpClient {
    /// Reach the server and complete the MCP handshake (within `timeout`).
    pub fn connect(name: &str, server: &Server, timeout: Duration) -> Result<McpClient, ToolError> {
        let transport: Box<dyn Transport> = match server {
            Server::Command(cmd) => Box::new(Stdio::start(name, cmd)?),
            Server::Url(u) => Box::new(Http::new(name, u)?),
        };
        McpClient::with_transport(name, transport, timeout)
    }

    /// Start a local server and complete the handshake.
    pub fn start(name: &str, cmd: &ServerCommand, timeout: Duration) -> Result<McpClient, ToolError> {
        McpClient::connect(name, &Server::Command(cmd.clone()), timeout)
    }

    /// Complete the handshake over any transport.
    pub fn with_transport(name: &str, transport: Box<dyn Transport>, timeout: Duration) -> Result<McpClient, ToolError> {
        let mut client = McpClient { name: name.to_string(), transport, next_id: 1 };
        client.request(
            "initialize",
            json!({"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "craft-anything", "version": env!("CARGO_PKG_VERSION")}}),
            timeout,
            &|| false,
        )?;
        client.notify("notifications/initialized", json!({}))?;
        Ok(client)
    }

    /// Every tool the server offers (following pagination, at most 50 pages).
    pub fn list_tools(&mut self, timeout: Duration) -> Result<Vec<RemoteTool>, ToolError> {
        let mut tools = Vec::new();
        let mut cursor: Option<String> = None;
        for _ in 0..50 {
            let params = match &cursor {
                Some(c) => json!({"cursor": c}),
                None => json!({}),
            };
            let r = self.request("tools/list", params, timeout, &|| false)?;
            for t in r.get("tools").and_then(Value::as_array).cloned().unwrap_or_default() {
                if let Ok(t) = serde_json::from_value::<RemoteTool>(t) {
                    tools.push(t);
                }
            }
            cursor = r.get("nextCursor").and_then(Value::as_str).map(str::to_string);
            if cursor.is_none() {
                break;
            }
        }
        Ok(tools)
    }

    /// Call a tool. A result the server marks as an error becomes a `ToolError` with its text.
    pub fn call_tool(&mut self, name: &str, arguments: Value, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Result<Value, ToolError> {
        let r = self.request("tools/call", json!({"name": name, "arguments": arguments}), timeout, cancelled)?;
        if r.get("isError").and_then(Value::as_bool).unwrap_or(false) {
            let text = content_text(&r);
            return Err(ToolError::new(
                ErrorCode::ProgramFailed,
                format!("The {} plugin's {name} failed: {}", self.name, if text.is_empty() { "no details" } else { &text }),
            ));
        }
        Ok(r)
    }

    fn notify(&mut self, method: &str, params: Value) -> Result<(), ToolError> {
        self.transport.notify(&json!({"jsonrpc": "2.0", "method": method, "params": params}))
    }

    fn request(&mut self, method: &str, params: Value, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Result<Value, ToolError> {
        let id = self.next_id;
        self.next_id = self.next_id.saturating_add(1);
        let msg = json!({"jsonrpc": "2.0", "id": id, "method": method, "params": params});
        let answer = match self.transport.request(&msg, id, Instant::now() + timeout, cancelled) {
            Err(e) if e.code == ErrorCode::Cancelled => {
                let _ = self.notify("notifications/cancelled", json!({"requestId": id}));
                return Err(e);
            }
            Err(e) if e.code == ErrorCode::TimedOut => {
                return Err(ToolError::new(ErrorCode::TimedOut, format!("The {} plugin didn't answer {method} in time.", self.name))
                    .with_remediation("Try again; if it keeps happening, check the plugin."));
            }
            r => r?,
        };
        if let Some(err) = answer.get("error") {
            let text = err.get("message").and_then(Value::as_str).unwrap_or("unknown error");
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("The {} plugin refused {method}: {text}", self.name)));
        }
        Ok(answer.get("result").cloned().unwrap_or(Value::Null))
    }
}

/// Whether `msg` is the answer to request `id`.
fn answers(msg: &Value, id: u64) -> bool {
    msg.get("id").and_then(Value::as_u64) == Some(id) && (msg.get("result").is_some() || msg.get("error").is_some())
}

/// A local server over stdio.
struct Stdio {
    name: String,
    process: RunningProcess,
    stdin: ChildStdin,
    lines: Receiver<String>,
}

impl Stdio {
    fn start(name: &str, cmd: &ServerCommand) -> Result<Stdio, ToolError> {
        let (tx, lines) = channel();
        let mut p = Process::new(&cmd.command)
            .args(&cmd.args)
            .stdin(StdinMode::Piped)
            // A server lives as long as the session; it's stopped when the client is dropped.
            .timeout(Duration::from_secs(7 * 24 * 3600))
            .stdout_cap(MAX_LINE)
            .on_stdout_line(move |l| {
                let _ = tx.send(l.to_string());
            })
            .label(format!("the {name} plugin"))
            .remediation(format!("Check the command for the {name} plugin in config.toml ([[plugins.mcp]])."));
        for (k, v) in &cmd.env {
            p = p.env(k, v);
        }
        if let Some(dir) = &cmd.cwd {
            p = p.cwd(dir);
        }
        let mut process = p.spawn()?;
        let stdin = process.take_stdin().ok_or_else(|| ToolError::internal(format!("the {name} plugin has no input pipe")))?;
        Ok(Stdio { name: name.to_string(), process, stdin, lines })
    }

    fn exited(&self) -> ToolError {
        ToolError::new(ErrorCode::EngineMissing, format!("The {} plugin exited.", self.name))
            .with_remediation("Check its command in config.toml ([[plugins.mcp]]).")
    }
}

impl Transport for Stdio {
    fn notify(&mut self, msg: &Value) -> Result<(), ToolError> {
        let mut line = msg.to_string();
        line.push('\n');
        self.stdin
            .write_all(line.as_bytes())
            .and_then(|()| self.stdin.flush())
            .map_err(|e| ToolError::new(ErrorCode::EngineMissing, format!("The {} plugin stopped: {e}", self.name)))
    }

    fn request(&mut self, msg: &Value, id: u64, deadline: Instant, cancelled: &dyn Fn() -> bool) -> Result<Value, ToolError> {
        self.notify(msg)?;
        loop {
            if cancelled() {
                return Err(ToolError::cancelled());
            }
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return Err(ToolError::new(ErrorCode::TimedOut, "no answer in time"));
            }
            let line = match self.lines.recv_timeout(left.min(Duration::from_millis(200))) {
                Ok(l) => l,
                Err(RecvTimeoutError::Timeout) if self.process.is_finished() => return Err(self.exited()),
                Err(RecvTimeoutError::Timeout) => continue,
                Err(RecvTimeoutError::Disconnected) => return Err(self.exited()),
            };
            // Servers may log to stdout or send notifications; only our answer matters.
            if let Ok(msg) = serde_json::from_str::<Value>(line.trim())
                && answers(&msg, id)
            {
                return Ok(msg);
            }
        }
    }
}

impl Drop for Stdio {
    fn drop(&mut self) {
        // Confirmed, not just asked: the session may end (and the process exit) right after.
        self.process.kill_and_wait(Duration::from_secs(5));
    }
}

/// A remote server over Streamable HTTP: each message is POSTed; a request's answer comes back as
/// JSON or as server-sent events. The session id the server gives is sent back with each request.
struct Http {
    name: String,
    url: String,
    headers: BTreeMap<String, String>,
    session: Option<String>,
    initialized: bool,
}

impl Http {
    fn new(name: &str, u: &ServerUrl) -> Result<Http, ToolError> {
        if !url_allowed(&u.url) {
            return Err(ToolError::invalid(format!("The {name} plugin's url must start with https:// (or http:// to this computer).")));
        }
        Ok(Http { name: name.to_string(), url: u.url.clone(), headers: u.headers.clone(), session: None, initialized: false })
    }

    fn post(&mut self, msg: &Value, timeout: Duration) -> Result<ureq::http::Response<ureq::Body>, ToolError> {
        let agent = ureq::Agent::config_builder()
            .http_status_as_error(false)
            .user_agent("CraftAnything")
            .timeout_connect(Some(Duration::from_secs(20)))
            .timeout_global(Some(timeout.max(Duration::from_secs(1))))
            .build()
            .new_agent();
        let mut req = agent.post(&self.url).header("Content-Type", "application/json").header("Accept", "application/json, text/event-stream");
        if self.initialized {
            req = req.header("MCP-Protocol-Version", PROTOCOL);
        }
        if let Some(s) = &self.session {
            req = req.header("Mcp-Session-Id", s);
        }
        for (k, v) in &self.headers {
            req = req.header(k, v);
        }
        let resp = req.send(msg.to_string()).map_err(|e| {
            let code = if matches!(e, ureq::Error::Timeout(_)) { ErrorCode::TimedOut } else { ErrorCode::EngineMissing };
            ToolError::new(code, format!("Couldn't reach the {} plugin: {e}", self.name))
                .with_remediation("Check its url in config.toml ([[plugins.mcp]]) and your connection.")
        })?;
        if let Some(s) = resp.headers().get("mcp-session-id").and_then(|v| v.to_str().ok()) {
            self.session = Some(s.to_string());
        }
        let status = resp.status().as_u16();
        if !(200..300).contains(&status) {
            let hint = if status == 401 || status == 403 {
                "Check the plugin's headers (its key or token) in config.toml."
            } else {
                "Check its url in config.toml ([[plugins.mcp]])."
            };
            return Err(ToolError::new(ErrorCode::EngineMissing, format!("The {} plugin answered {status}.", self.name)).with_remediation(hint));
        }
        Ok(resp)
    }
}

impl Transport for Http {
    fn notify(&mut self, msg: &Value) -> Result<(), ToolError> {
        self.post(msg, Duration::from_secs(30))?;
        if msg.get("method").and_then(Value::as_str) == Some("notifications/initialized") {
            self.initialized = true;
        }
        Ok(())
    }

    fn request(&mut self, msg: &Value, id: u64, deadline: Instant, cancelled: &dyn Fn() -> bool) -> Result<Value, ToolError> {
        if cancelled() {
            return Err(ToolError::cancelled());
        }
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return Err(ToolError::new(ErrorCode::TimedOut, "no answer in time"));
        }
        let resp = self.post(msg, left)?;
        let event_stream = resp.headers().get("content-type").and_then(|v| v.to_str().ok()).is_some_and(|t| t.starts_with("text/event-stream"));
        let unreadable =
            |e: &dyn std::fmt::Display| ToolError::new(ErrorCode::GarbledOutput, format!("The {} plugin's answer couldn't be read: {e}", self.name));
        let mut body = resp.into_body();
        if !event_stream {
            let text = body.with_config().limit(MAX_LINE as u64).read_to_string().map_err(|e| unreadable(&e))?;
            let v: Value = serde_json::from_str(&text).map_err(|e| unreadable(&e))?;
            // A batch is allowed too.
            let found = match v {
                Value::Array(items) => items.into_iter().find(|m| answers(m, id)),
                m => Some(m).filter(|m| answers(m, id)),
            };
            return found.ok_or_else(|| unreadable(&"it didn't answer the request"));
        }
        // Server-sent events: `data:` lines make up each event; the one answering us ends it.
        let reader = std::io::BufReader::new(body.with_config().limit(MAX_LINE as u64).reader());
        let mut data = String::new();
        for line in reader.lines() {
            if cancelled() {
                return Err(ToolError::cancelled());
            }
            let line = line.map_err(|e| unreadable(&e))?;
            if let Some(d) = line.strip_prefix("data:") {
                data.push_str(d.strip_prefix(' ').unwrap_or(d));
                data.push('\n');
            } else if line.is_empty() && !data.is_empty() {
                if let Ok(m) = serde_json::from_str::<Value>(data.trim())
                    && answers(&m, id)
                {
                    return Ok(m);
                }
                data.clear();
            }
        }
        match serde_json::from_str::<Value>(data.trim()) {
            Ok(m) if answers(&m, id) => Ok(m),
            _ => Err(unreadable(&"the event stream ended without an answer")),
        }
    }
}

/// `https://`, or `http://` to this computer only (keys must not cross the network in the clear).
pub fn url_allowed(url: &str) -> bool {
    let lower = url.trim().to_ascii_lowercase();
    if lower.starts_with("https://") {
        return lower.len() > "https://".len();
    }
    let Some(rest) = lower.strip_prefix("http://") else { return false };
    let host = rest.split(['/', '?', '#']).next().unwrap_or_default();
    let host = host.rsplit_once('@').map_or(host, |(_, h)| h);
    let host = if host.starts_with('[') {
        host.split(']').next().map(|h| format!("{h}]")).unwrap_or_default()
    } else {
        host.split(':').next().unwrap_or_default().to_string()
    };
    matches!(host.as_str(), "localhost" | "127.0.0.1" | "[::1]")
}

/// The text parts of a tool result (`content: [{type: "text", text}]`), joined.
pub fn content_text(result: &Value) -> String {
    result
        .get("content")
        .and_then(Value::as_array)
        .map(|parts| parts.iter().filter_map(|p| p.get("text").and_then(Value::as_str)).collect::<Vec<_>>().join("\n"))
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn results_read_their_text_and_tools_parse_loosely() {
        let r = json!({"content": [{"type": "text", "text": "one"}, {"type": "image", "data": "…"}, {"type": "text", "text": "two"}]});
        assert_eq!(content_text(&r), "one\ntwo");
        assert_eq!(content_text(&json!({})), "");
        let t: RemoteTool = serde_json::from_value(json!({"name": "echo", "inputSchema": {"type": "object"}, "extra": 1})).unwrap();
        assert_eq!(t.name, "echo");
        assert!(t.annotations.is_null());
    }

    #[test]
    fn a_missing_server_is_a_clear_error() {
        let cmd = ServerCommand { command: "craft-anything-no-such-server".into(), args: vec![], env: BTreeMap::new(), cwd: None };
        let err = McpClient::start("demo", &cmd, Duration::from_secs(5)).err().unwrap();
        assert!(err.remediation.unwrap_or_default().contains("plugins.mcp"));
    }

    #[test]
    fn only_https_or_this_computer() {
        assert!(url_allowed("https://mcp.example.com/mcp"));
        assert!(url_allowed("http://localhost:8080/mcp") && url_allowed("http://127.0.0.1/mcp") && url_allowed("http://[::1]:9000/mcp"));
        assert!(!url_allowed("http://example.com/mcp") && !url_allowed("http://localhost.evil.com/") && !url_allowed("http://evil.com@x/"));
        assert!(!url_allowed("ftp://x") && !url_allowed("https://"));
    }

    /// A tiny Streamable HTTP server on loopback: JSON for initialize (with a session id), 202 for
    /// notifications, an event stream for tools/list, JSON for tools/call. It checks the headers.
    fn http_server() -> (String, std::thread::JoinHandle<Vec<String>>) {
        use std::io::Read;
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/mcp", listener.local_addr().unwrap());
        let handle = std::thread::spawn(move || {
            let mut seen = Vec::new();
            for _ in 0..4 {
                let (mut s, _) = listener.accept().unwrap();
                let mut buf = Vec::new();
                let mut chunk = [0u8; 4096];
                let (head, body) = loop {
                    let n = s.read(&mut chunk).unwrap();
                    buf.extend_from_slice(&chunk[..n]);
                    let text = String::from_utf8_lossy(&buf).to_string();
                    if let Some((h, b)) = text.split_once("\r\n\r\n") {
                        let len: usize =
                            h.lines().find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:").map(|v| v.trim().parse().unwrap())).unwrap_or(0);
                        if b.len() >= len {
                            break (h.to_string(), b.to_string());
                        }
                    }
                };
                let msg: Value = serde_json::from_str(&body).unwrap();
                let method = msg["method"].as_str().unwrap_or_default().to_string();
                let lower = head.to_ascii_lowercase();
                seen.push(format!("{method} session={} auth={}", lower.contains("mcp-session-id: s-1"), lower.contains("authorization: bearer t")));
                let id = msg.get("id").cloned().unwrap_or(Value::Null);
                let json_reply = |result: Value, extra: &str| {
                    let body = json!({"jsonrpc": "2.0", "id": id, "result": result}).to_string();
                    format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n{extra}Content-Length: {}\r\n\r\n{body}", body.len())
                };
                let reply = match method.as_str() {
                    "initialize" => json_reply(json!({"protocolVersion": PROTOCOL, "capabilities": {}}), "Mcp-Session-Id: s-1\r\n"),
                    "notifications/initialized" => "HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n".to_string(),
                    "tools/list" => {
                        // A notification first, then the answer, as an event stream.
                        let ev = json!({"jsonrpc": "2.0", "id": id, "result": {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}});
                        let body = format!("event: message\ndata: {{\"jsonrpc\":\"2.0\",\"method\":\"notifications/progress\"}}\n\ndata: {ev}\n\n");
                        format!("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: {}\r\n\r\n{body}", body.len())
                    }
                    _ => json_reply(json!({"content": [{"type": "text", "text": "hi"}]}), ""),
                };
                s.write_all(reply.as_bytes()).unwrap();
            }
            seen
        });
        (url, handle)
    }

    #[test]
    fn a_remote_server_answers_over_http() {
        let (url, server) = http_server();
        let headers = BTreeMap::from([("Authorization".to_string(), "Bearer t".to_string())]);
        let mut c = McpClient::connect("remote", &Server::Url(ServerUrl { url, headers }), Duration::from_secs(10)).unwrap();
        let tools = c.list_tools(Duration::from_secs(10)).unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "echo");
        let r = c.call_tool("echo", json!({}), Duration::from_secs(10), &|| false).unwrap();
        assert_eq!(content_text(&r), "hi");
        let seen = server.join().unwrap();
        assert_eq!(seen[0], "initialize session=false auth=true");
        assert!(seen[1..].iter().all(|s| s.ends_with("session=true auth=true")), "the session id goes back with every later message: {seen:?}");
        let err =
            McpClient::connect("remote", &Server::Url(ServerUrl { url: "http://example.com/mcp".into(), headers: BTreeMap::new() }), Duration::from_secs(1))
                .err()
                .unwrap();
        assert!(err.message.contains("https://"));
    }
}
