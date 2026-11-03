//! JEB tools: a small MCP client (Streamable HTTP, JSON-RPC 2.0) for a JEB MCP server the user
//! runs themselves on this machine. The server URL comes from Settings → Engines (`jeb_url`).
//! We never start JEB, never retry, only talk plain HTTP to a loopback address, and bound every
//! exchange by a deadline and a response-size cap.

use crate::tool::{CancelToken, Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use crate::tools::native_common::spec;
use craft_anything_evidence::{
    Authority, Confidence, Coverage, Environment, ErrorCode, EvidenceBuilder, Limitation, Location, Subject, ToolError, host_triple,
};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::{ErrorKind, Read, Write};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr, TcpStream};
use std::time::{Duration, Instant};

/// Biggest HTTP response we accept.
const MAX_RESPONSE: usize = 16 << 20;
/// Biggest upstream payload kept in evidence (serialised bytes).
const MAX_PAYLOAD: usize = 2 << 20;
const PROTOCOL_VERSION: &str = "2025-06-18";

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "engines_jeb_check",
            "Check the JEB connection",
            "Connect to the user-run JEB MCP server set in Settings → Engines (jeb_url, loopback only), report its server information, upstream tools and client information. Never starts JEB.",
            "Check that Craft Anything can talk to your running JEB.",
            Toolset::Android,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<ClientParams>,
            engines_jeb_check,
        ),
        spec(
            "android_jeb_open",
            "Open a file in JEB",
            "Ask the user-run JEB MCP server to open an absolute file path as a project (upstream open_project). Not idempotent: JEB keeps the project open.",
            "Load an app into your running JEB.",
            Toolset::Android,
            Effects::MUTATES_SESSION.union(Effects::ACCESSES_NETWORK),
            Requires::Nothing,
            schema_of::<OpenParams>,
            android_jeb_open,
        ),
        spec(
            "android_jeb_units_browse",
            "List JEB units",
            "List the units of the open JEB project (upstream list_units), optionally under parent_unit_path and filtered, one page at a time (index, count ≤ 100).",
            "See the parts JEB found in the app.",
            Toolset::Android,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<ListParams>,
            android_jeb_units_browse,
        ),
        spec(
            "android_jeb_decompile",
            "Decompile with JEB",
            "Ask JEB to decompile one type or method (upstream decompile_code_item) by item_address, optionally inside unit_path. The output is JEB's, recorded as external evidence.",
            "Ask JEB to turn one class or method back into readable code.",
            Toolset::Android,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<DecompileParams>,
            android_jeb_decompile,
        ),
    ]
}

fn d_timeout() -> u64 {
    60
}
fn d_open_timeout() -> u64 {
    300
}
fn d_count() -> u32 {
    100
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClientParams {
    /// Seconds to wait for the whole exchange (1..=600).
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OpenParams {
    /// Absolute path of the file to open in JEB (APK, DEX, …).
    pub path: String,
    /// Seconds to wait for the whole exchange (1..=600).
    #[serde(default = "d_open_timeout")]
    pub timeout_secs: u64,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// Only units whose name or path matches this text.
    #[serde(default)]
    pub filter: Option<String>,
    /// List the children of this unit instead of the project's top-level units.
    #[serde(default)]
    pub parent_unit_path: Option<String>,
    /// First unit of the page.
    #[serde(default)]
    pub index: u32,
    /// Units per page (1..=100).
    #[serde(default = "d_count")]
    pub count: u32,
    /// Seconds to wait for the whole exchange (1..=600).
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ItemKind {
    Type,
    Method,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DecompileParams {
    /// The code unit holding the item; JEB's default when omitted.
    #[serde(default)]
    pub unit_path: Option<String>,
    /// The item's address in JEB's notation, e.g. `Lcom/example/Main;` or `Lcom/example/Main;->onCreate(Landroid/os/Bundle;)V`.
    pub item_address: String,
    /// type or method.
    pub item_kind: ItemKind,
    /// Seconds to wait for the whole exchange (1..=600).
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

// ---------------------------------------------------------------------------------------------
// Endpoint

#[derive(Debug, Clone, PartialEq, Eq)]
struct Endpoint {
    url: String,
    host_header: String,
    addrs: Vec<SocketAddr>,
    path: String,
}

fn config_err(msg: impl Into<String>) -> ToolError {
    ToolError::new(ErrorCode::BadSettings, msg)
        .with_remediation("Set Settings → Engines → jeb_url to the plain-HTTP loopback URL your JEB MCP server prints, e.g. http://127.0.0.1:8425/mcp.")
}

fn parse_endpoint(url: &str) -> Result<Endpoint, ToolError> {
    let u = url.trim();
    if u.contains(['?', '#', '@']) || u.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err(config_err(format!("jeb_url {u:?} must not contain credentials, a query, a fragment or spaces")));
    }
    let Some(rest) = u.strip_prefix("http://") else {
        return Err(config_err(format!("jeb_url {u:?} must start with http:// (a local, plain-HTTP server)")));
    };
    let (authority, path) = match rest.find('/') {
        Some(i) => (rest.get(..i).unwrap_or(""), rest.get(i..).unwrap_or("/")),
        None => (rest, "/"),
    };
    let (host, port) = if let Some(after) = authority.strip_prefix('[') {
        let (h, tail) = after.split_once(']').ok_or_else(|| config_err("jeb_url has an unclosed [ in its host"))?;
        let port = match tail {
            "" => None,
            t => Some(t.strip_prefix(':').ok_or_else(|| config_err("jeb_url has junk after the ] of its host"))?),
        };
        (format!("[{h}]"), port)
    } else {
        match authority.split_once(':') {
            Some((h, p)) => (h.to_string(), Some(p)),
            None => (authority.to_string(), None),
        }
    };
    let port: u16 = match port {
        None => 80,
        Some(p) => p.parse().ok().filter(|p| *p != 0).ok_or_else(|| config_err(format!("jeb_url has an invalid port {p:?}")))?,
    };
    let ips: Vec<IpAddr> = match host.to_ascii_lowercase().as_str() {
        "127.0.0.1" => vec![IpAddr::V4(Ipv4Addr::LOCALHOST)],
        "[::1]" => vec![IpAddr::V6(Ipv6Addr::LOCALHOST)],
        "localhost" => vec![IpAddr::V4(Ipv4Addr::LOCALHOST), IpAddr::V6(Ipv6Addr::LOCALHOST)],
        other => {
            return Err(config_err(format!("jeb_url host {other:?} is not this machine; only 127.0.0.1, [::1] or localhost are allowed")));
        }
    };
    Ok(Endpoint {
        url: u.to_string(),
        host_header: format!("{host}:{port}"),
        addrs: ips.into_iter().map(|ip| SocketAddr::new(ip, port)).collect(),
        path: path.to_string(),
    })
}

fn endpoint_from_settings(ctx: &Ctx<'_>) -> Result<Endpoint, ToolError> {
    match ctx.session.settings.engines.jeb_url.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
        Some(u) => parse_endpoint(u),
        None => Err(ToolError::new(ErrorCode::EngineMissing, "JEB is not configured.")
            .with_remediation("Start the JEB MCP server inside your JEB, then set Settings → Engines → jeb_url (for example http://127.0.0.1:8425/mcp).")),
    }
}

// ---------------------------------------------------------------------------------------------
// HTTP

struct Response {
    status: u16,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

impl Response {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k.eq_ignore_ascii_case(name)).map(|(_, v)| v.as_str())
    }
}

fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
    hay.windows(needle.len()).position(|w| w == needle)
}

/// Decode a chunked body: (data so far, whether the final chunk was seen).
fn dechunk(body: &[u8]) -> (Vec<u8>, bool) {
    let mut out = Vec::new();
    let mut pos = 0usize;
    loop {
        let Some(rest) = body.get(pos..) else { return (out, false) };
        let Some(eol) = find(rest, b"\r\n") else { return (out, false) };
        let line = String::from_utf8_lossy(rest.get(..eol).unwrap_or_default());
        let size_text = line.split(';').next().unwrap_or("").trim();
        let Ok(size) = usize::from_str_radix(size_text, 16) else { return (out, false) };
        let start = pos.saturating_add(eol).saturating_add(2);
        if size == 0 {
            return (out, true);
        }
        let end = start.saturating_add(size);
        match body.get(start..end) {
            Some(d) => out.extend_from_slice(d),
            None => {
                out.extend_from_slice(body.get(start..).unwrap_or_default());
                return (out, false);
            }
        }
        pos = end.saturating_add(2);
    }
}

/// JSON-RPC messages inside a server-sent-event stream.
fn sse_messages(body: &[u8]) -> Vec<Value> {
    let text = String::from_utf8_lossy(body).replace("\r\n", "\n");
    let mut out = Vec::new();
    for event in text.split("\n\n") {
        let data: Vec<&str> = event.lines().filter_map(|l| l.strip_prefix("data:")).map(|d| d.strip_prefix(' ').unwrap_or(d)).collect();
        if data.is_empty() {
            continue;
        }
        if let Ok(v) = serde_json::from_str::<Value>(&data.join("\n")) {
            out.push(v);
        }
    }
    out
}

fn matching(messages: Vec<Value>, id: u64) -> Option<Value> {
    messages.into_iter().find(|m| m.get("id").and_then(Value::as_u64) == Some(id) && (m.get("result").is_some() || m.get("error").is_some()))
}

struct Client {
    ep: Endpoint,
    deadline: Instant,
    cancel: CancelToken,
    session: Option<String>,
    next_id: u64,
}

impl Client {
    fn new(ep: Endpoint, timeout_secs: u64, cancel: CancelToken) -> Result<Self, ToolError> {
        if !(1..=600).contains(&timeout_secs) {
            return Err(ToolError::invalid("timeout_secs must be 1..=600"));
        }
        Ok(Client { ep, deadline: Instant::now() + Duration::from_secs(timeout_secs), cancel, session: None, next_id: 1 })
    }

    fn timeout_err(&self) -> ToolError {
        ToolError::new(ErrorCode::TimedOut, format!("JEB at {} did not answer in time.", self.ep.url))
            .with_remediation("Check JEB is responsive (a long analysis may be running), or raise timeout_secs.")
    }

    fn remaining(&self) -> Result<Duration, ToolError> {
        self.cancel.check()?;
        let r = self.deadline.saturating_duration_since(Instant::now());
        if r.is_zero() { Err(self.timeout_err()) } else { Ok(r) }
    }

    fn connect(&self) -> Result<TcpStream, ToolError> {
        let mut timed_out = false;
        let mut last = String::new();
        for a in &self.ep.addrs {
            let t = self.remaining()?.min(Duration::from_secs(10));
            match TcpStream::connect_timeout(a, t) {
                Ok(s) => return Ok(s),
                Err(e) if matches!(e.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock) => timed_out = true,
                Err(e) => last = e.to_string(),
            }
        }
        if !last.is_empty() || !timed_out {
            let e = ToolError::new(ErrorCode::EngineMissing, format!("Couldn't reach JEB at {} ({last}).", self.ep.url))
                .with_remediation("Start JEB and its MCP server, and check Settings → Engines → jeb_url matches the address it prints.");
            return Err(e);
        }
        Err(self.timeout_err())
    }

    /// POST one JSON-RPC message; for requests (`id` given) wait for the matching response.
    fn post(&mut self, body: &Value, id: Option<u64>) -> Result<Option<Value>, ToolError> {
        let payload = serde_json::to_vec(body).map_err(|e| ToolError::internal(e.to_string()))?;
        let mut stream = self.connect()?;
        let mut req = format!(
            "POST {} HTTP/1.1\r\nHost: {}\r\nUser-Agent: CraftAnything-dev\r\nContent-Type: application/json\r\nAccept: application/json, text/event-stream\r\nMCP-Protocol-Version: {PROTOCOL_VERSION}\r\nContent-Length: {}\r\nConnection: close\r\n",
            self.ep.path,
            self.ep.host_header,
            payload.len()
        );
        if let Some(s) = &self.session {
            req.push_str(&format!("Mcp-Session-Id: {s}\r\n"));
        }
        req.push_str("\r\n");
        let io_err = |c: &Client, e: std::io::Error| -> ToolError {
            if matches!(e.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock) {
                c.timeout_err()
            } else {
                ToolError::new(ErrorCode::EngineMissing, format!("The connection to JEB at {} failed: {e}", c.ep.url))
                    .with_remediation("Check JEB and its MCP server are still running.")
            }
        };
        stream.set_write_timeout(Some(self.remaining()?)).map_err(|e| io_err(self, e))?;
        stream.write_all(req.as_bytes()).and_then(|_| stream.write_all(&payload)).and_then(|_| stream.flush()).map_err(|e| io_err(self, e))?;
        let resp = self.read_response(&mut stream, id)?;
        if let Some(s) = resp.header("mcp-session-id")
            && !s.is_empty()
            && s.len() <= 256
            && s.chars().all(|c| c.is_ascii_graphic())
        {
            self.session = Some(s.to_string());
        }
        if resp.status == 202 || resp.status == 204 {
            return Ok(None);
        }
        if resp.status == 404 && self.session.is_some() && id.is_some() {
            return Err(ToolError::new(ErrorCode::EngineMissing, "JEB ended the MCP session.").with_remediation("Run the tool again."));
        }
        if !(200..300).contains(&resp.status) {
            let snippet: String = String::from_utf8_lossy(&resp.body).chars().take(300).collect();
            let code = if resp.status == 404 { ErrorCode::EngineMissing } else { ErrorCode::ProgramFailed };
            return Err(ToolError::new(code, format!("JEB at {} answered HTTP {}: {snippet}", self.ep.url, resp.status))
                .with_remediation("Check jeb_url points at the JEB MCP endpoint (usually ending in /mcp)."));
        }
        let Some(id) = id else { return Ok(None) };
        let ctype = resp.header("content-type").unwrap_or("").to_ascii_lowercase();
        let msg = if ctype.contains("text/event-stream") {
            matching(sse_messages(&resp.body), id)
        } else {
            match serde_json::from_slice::<Value>(&resp.body) {
                Ok(Value::Array(a)) => matching(a, id),
                Ok(v) => matching(vec![v], id),
                Err(_) => None,
            }
        };
        msg.map(Some).ok_or_else(|| {
            ToolError::new(ErrorCode::GarbledOutput, format!("JEB at {} sent no JSON-RPC response for request {id}", self.ep.url))
                .with_remediation("Check jeb_url points at a JEB MCP server.")
        })
    }

    fn read_response(&self, stream: &mut TcpStream, id: Option<u64>) -> Result<Response, ToolError> {
        let mut buf: Vec<u8> = Vec::new();
        let mut chunk = [0u8; 16 * 1024];
        let mut head: Option<(usize, Response, Option<usize>, bool, bool)> = None;
        loop {
            // Done yet?
            if let Some((start, resp, clen, chunked, sse)) = &head {
                let raw = buf.get(*start..).unwrap_or_default();
                let (body, finished) = if *chunked { dechunk(raw) } else { (raw.to_vec(), clen.is_some_and(|n| raw.len() >= n)) };
                let sse_done = *sse && id.is_some_and(|i| matching(sse_messages(&body), i).is_some());
                if finished || sse_done || (resp.status == 202 && clen.is_none() && !*chunked) {
                    let mut body = body;
                    if let Some(n) = clen {
                        body.truncate(*n);
                    }
                    return Ok(Response { status: resp.status, headers: resp.headers.clone(), body });
                }
            }
            let wait = self.remaining()?.min(Duration::from_millis(250));
            stream.set_read_timeout(Some(wait)).map_err(|e| ToolError::internal(e.to_string()))?;
            match stream.read(&mut chunk) {
                Ok(0) => {
                    // Closed: whatever we have is the response.
                    let Some((start, resp, clen, chunked, _)) = head else {
                        return Err(ToolError::new(ErrorCode::GarbledOutput, format!("JEB at {} closed the connection without answering", self.ep.url)));
                    };
                    let raw = buf.get(start..).unwrap_or_default();
                    let mut body = if chunked { dechunk(raw).0 } else { raw.to_vec() };
                    if let Some(n) = clen {
                        body.truncate(n);
                    }
                    return Ok(Response { status: resp.status, headers: resp.headers, body });
                }
                Ok(n) => {
                    buf.extend_from_slice(chunk.get(..n).unwrap_or_default());
                    if buf.len() > MAX_RESPONSE {
                        return Err(ToolError::new(ErrorCode::OverLimit, format!("JEB's answer is bigger than {MAX_RESPONSE} bytes")));
                    }
                }
                Err(e) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut | ErrorKind::Interrupted) => continue,
                Err(e) => {
                    return Err(ToolError::new(ErrorCode::EngineMissing, format!("Reading from JEB at {} failed: {e}", self.ep.url)));
                }
            }
            if head.is_none()
                && let Some(end) = find(&buf, b"\r\n\r\n")
            {
                let text = String::from_utf8_lossy(buf.get(..end).unwrap_or_default()).into_owned();
                let mut lines = text.split("\r\n");
                let status_line = lines.next().unwrap_or("");
                let status = status_line
                    .split_whitespace()
                    .nth(1)
                    .and_then(|s| s.parse::<u16>().ok())
                    .ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, format!("JEB at {} sent a malformed HTTP status line", self.ep.url)))?;
                let headers: Vec<(String, String)> =
                    lines.filter_map(|l| l.split_once(':')).map(|(k, v)| (k.trim().to_string(), v.trim().to_string())).take(200).collect();
                let resp = Response { status, headers, body: Vec::new() };
                let clen = resp.header("content-length").and_then(|v| v.parse::<usize>().ok());
                if clen.is_some_and(|n| n > MAX_RESPONSE) {
                    return Err(ToolError::new(ErrorCode::OverLimit, format!("JEB's answer is bigger than {MAX_RESPONSE} bytes")));
                }
                let chunked = resp.header("transfer-encoding").is_some_and(|v| v.to_ascii_lowercase().contains("chunked"));
                let sse = resp.header("content-type").is_some_and(|v| v.to_ascii_lowercase().contains("text/event-stream"));
                head = Some((end + 4, resp, clen, chunked, sse));
            }
        }
    }

    fn request(&mut self, method: &str, params: Value) -> Result<Value, ToolError> {
        let id = self.next_id;
        self.next_id += 1;
        let msg = self.post(&json!({"jsonrpc": "2.0", "id": id, "method": method, "params": params}), Some(id))?.unwrap_or(Value::Null);
        if let Some(err) = msg.get("error") {
            let text = err.get("message").and_then(Value::as_str).unwrap_or("unknown error");
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("JEB refused {method}: {text}")).with_details(json!({"error": err})));
        }
        Ok(msg.get("result").cloned().unwrap_or(Value::Null))
    }

    /// initialize + notifications/initialized. Returns the server's initialize result.
    fn initialize(&mut self) -> Result<Value, ToolError> {
        let r = self.request(
            "initialize",
            json!({"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "craft-anything", "version": env!("CARGO_PKG_VERSION")}}),
        )?;
        self.post(&json!({"jsonrpc": "2.0", "method": "notifications/initialized"}), None)?;
        Ok(r)
    }

    /// Call an upstream tool; returns (payload, raw result).
    fn call_tool(&mut self, name: &str, args: Value) -> Result<Value, ToolError> {
        let r = self.request("tools/call", json!({"name": name, "arguments": args}))?;
        let texts: Vec<String> =
            r.get("content").and_then(Value::as_array).into_iter().flatten().filter_map(|c| c.get("text").and_then(Value::as_str).map(String::from)).collect();
        if r.get("isError").and_then(Value::as_bool) == Some(true) {
            let text: String = texts.join("\n").chars().take(2000).collect();
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("JEB's {name} failed: {text}"))
                .with_remediation("Check the arguments (paths, unit paths and item addresses as JEB names them)."));
        }
        if let Some(s) = r.get("structuredContent") {
            return Ok(s.clone());
        }
        let joined = texts.join("\n");
        Ok(serde_json::from_str::<Value>(&joined).unwrap_or(Value::String(joined)))
    }
}

/// Cap a payload for evidence.
fn capped(v: Value) -> (Value, bool) {
    let text = serde_json::to_string(&v).unwrap_or_default();
    if text.len() <= MAX_PAYLOAD {
        return (v, false);
    }
    let mut end = MAX_PAYLOAD;
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    (json!({"truncated_json": text.get(..end).unwrap_or("")}), true)
}

fn jeb_env(server: &Value) -> Environment {
    Environment {
        clean_room: false,
        engine: "jeb".into(),
        engine_version: server.pointer("/serverInfo/version").and_then(Value::as_str).map(String::from),
        host: host_triple(),
        language_id: None,
    }
}

fn evidence(op: &str, subject: Subject, server: &Value, ep: &Endpoint, params: Value) -> EvidenceBuilder {
    EvidenceBuilder::new(op, subject, jeb_env(server))
        .params(params)
        .authority(Authority::OutsideService)
        .location(Location::new("url", ep.url.clone()).with_label("JEB MCP server"))
}

fn server_subject(ep: &Endpoint) -> Subject {
    Subject { kind: "jeb-server".into(), sha256: None, name: Some(ep.url.clone()) }
}

fn finish(b: EvidenceBuilder, payload: Value, mut result: Value, summary: String, confidence: Confidence) -> Result<ToolOutput, ToolError> {
    let (payload, truncated) = capped(payload);
    result["payload"] = payload;
    result["payload_truncated"] = json!(truncated);
    let mut b = b.result(result).summary(summary).confidence(confidence).coverage(if truncated {
        crate::tools::static_input::partial(1)
    } else {
        Coverage::complete(1)
    });
    if truncated {
        b = b.limitation(Limitation::new("payload_truncated", format!("JEB's answer was cut to {MAX_PAYLOAD} bytes")));
    }
    b = b.limitation(Limitation::new("external_engine", "This came from JEB, a third-party engine the user runs; it is not a clean-room result."));
    Ok(ToolOutput::evidence(b.build()?))
}

fn engines_jeb_check(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ClientParams = parse_params(params)?;
    let ep = endpoint_from_settings(ctx)?;
    let mut c = Client::new(ep.clone(), p.timeout_secs, ctx.cancel.clone())?;
    let server = c.initialize()?;
    let tools = c.request("tools/list", json!({})).unwrap_or(Value::Null);
    let names: Vec<String> = tools
        .get("tools")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|t| t.get("name").and_then(Value::as_str).map(String::from))
        .take(500)
        .collect();
    let required = ["get_client_information", "open_project", "list_units", "decompile_code_item"];
    let missing: Vec<&str> = required.iter().copied().filter(|r| !names.iter().any(|n| n == r)).collect();
    let info = c.call_tool("get_client_information", json!({}))?;
    let name = server.pointer("/serverInfo/name").and_then(Value::as_str).unwrap_or("JEB MCP server");
    let summary = format!(
        "Connected to {name}{} at {}; {} upstream tools{}.",
        server.pointer("/serverInfo/version").and_then(Value::as_str).map(|v| format!(" {v}")).unwrap_or_default(),
        ep.url,
        names.len(),
        if missing.is_empty() { String::new() } else { format!(", missing {}", missing.join(", ")) }
    );
    let b = evidence("engines_jeb_check", server_subject(&ep), &server, &ep, json!({}));
    let result = json!({
        "url": ep.url,
        "connected": true,
        "protocol_version": server.get("protocolVersion"),
        "server_info": server.get("serverInfo"),
        "capabilities": server.get("capabilities"),
        "upstream_tools": names,
        "missing_tools": missing,
        "session": c.session.is_some(),
    });
    finish(b, info, result, summary, Confidence::Observed)
}

fn file_sha256(path: &std::path::Path, cancel: &CancelToken) -> Result<String, ToolError> {
    use sha2::{Digest, Sha256};
    let mut f = std::fs::File::open(path).map_err(|e| ToolError::io(path.display(), e))?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut n_read = 0u64;
    loop {
        let n = f.read(&mut buf).map_err(|e| ToolError::io(path.display(), e))?;
        if n == 0 {
            break;
        }
        h.update(buf.get(..n).unwrap_or_default());
        n_read += n as u64;
        if n_read.is_multiple_of(64 << 20) {
            cancel.check()?;
        }
    }
    Ok(hex::encode(h.finalize()))
}

fn android_jeb_open(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OpenParams = parse_params(params)?;
    let path = std::path::PathBuf::from(&p.path);
    if !path.is_absolute() {
        return Err(ToolError::invalid(format!("path {:?} must be absolute", p.path)));
    }
    if !path.is_file() {
        return Err(ToolError::new(ErrorCode::NotFound, format!("{} is not a file", path.display())));
    }
    let ep = endpoint_from_settings(ctx)?;
    let sha = file_sha256(&path, &ctx.cancel)?;
    let mut c = Client::new(ep.clone(), p.timeout_secs, ctx.cancel.clone())?;
    let server = c.initialize()?;
    ctx.report(None, "JEB is opening the file");
    let payload = c.call_tool("open_project", json!({"path": p.path}))?;
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned());
    let subject = Subject { kind: "file".into(), sha256: Some(sha), name: name.clone() };
    let b = evidence("android_jeb_open", subject, &server, &ep, json!({"path": p.path})).location(Location::new("path", p.path.clone()));
    let summary = format!("JEB opened {}.", name.unwrap_or_else(|| p.path.clone()));
    finish(b, payload, json!({"url": ep.url, "path": p.path}), summary, Confidence::Observed)
}

fn android_jeb_units_browse(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    if !(1..=100).contains(&p.count) {
        return Err(ToolError::invalid("count must be 1..=100"));
    }
    let ep = endpoint_from_settings(ctx)?;
    let mut c = Client::new(ep.clone(), p.timeout_secs, ctx.cancel.clone())?;
    let server = c.initialize()?;
    let mut args = json!({"index": p.index, "count": p.count});
    if let Some(f) = &p.filter {
        args["filter"] = json!(f);
    }
    if let Some(u) = &p.parent_unit_path {
        args["parent_unit_path"] = json!(u);
    }
    let payload = c.call_tool("list_units", args.clone())?;
    let n = payload.get("units").and_then(Value::as_array).map(Vec::len).or_else(|| payload.as_array().map(Vec::len));
    let summary = match n {
        Some(n) => format!("JEB listed {n} unit(s) from index {}.", p.index),
        None => format!("JEB answered list_units from index {}.", p.index),
    };
    let b = evidence("android_jeb_units_browse", server_subject(&ep), &server, &ep, args);
    finish(b, payload, json!({"url": ep.url, "index": p.index, "count": p.count, "units_returned": n}), summary, Confidence::Observed)
}

fn android_jeb_decompile(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DecompileParams = parse_params(params)?;
    if p.item_address.trim().is_empty() || p.item_address.len() > 4096 {
        return Err(ToolError::invalid("item_address must be 1..=4096 characters"));
    }
    let ep = endpoint_from_settings(ctx)?;
    let mut c = Client::new(ep.clone(), p.timeout_secs, ctx.cancel.clone())?;
    let server = c.initialize()?;
    let kind = match p.item_kind {
        ItemKind::Type => "type",
        ItemKind::Method => "method",
    };
    let mut args = json!({"item_address": p.item_address, "item_kind": kind});
    if let Some(u) = &p.unit_path {
        args["unit_path"] = json!(u);
    }
    let payload = c.call_tool("decompile_code_item", args.clone())?;
    let summary = format!("JEB decompiled {kind} {}.", p.item_address);
    let b = evidence("android_jeb_decompile", server_subject(&ep), &server, &ep, args)
        .location(Location::new(if kind == "type" { "class" } else { "method" }, p.item_address.clone()))
        .limitation(Limitation::new("decompiler_output", "Decompiled source is a reconstruction; it may not compile or match the original exactly."));
    finish(b, payload, json!({"url": ep.url, "item_address": p.item_address, "item_kind": kind}), summary, Confidence::Derived)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Engine};
    use craft_anything_platform::sync::Mutex;
    use std::io::BufRead;
    use std::net::TcpListener;
    use std::sync::Arc;

    fn engine(url: Option<String>) -> Engine {
        let mut s = crate::testing::session();
        s.settings.engines.jeb_url = url;
        Engine::new(s)
    }

    fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
        e.call(id, p, CallOptions::new(Caller::Mcp)).map(|o| o.to_json())
    }

    /// A fake JEB MCP server. Returns its URL and the session ids it saw on tool calls.
    fn fake_server(sse: bool) -> (String, Arc<Mutex<Vec<String>>>) {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://127.0.0.1:{}/mcp", l.local_addr().unwrap().port());
        let seen = Arc::new(Mutex::new(Vec::new()));
        let seen2 = seen.clone();
        std::thread::spawn(move || {
            for s in l.incoming() {
                let Ok(mut s) = s else { break };
                let mut r = std::io::BufReader::new(s.try_clone().unwrap());
                let mut len = 0usize;
                let mut sid = None;
                loop {
                    let mut line = String::new();
                    if r.read_line(&mut line).unwrap_or(0) == 0 {
                        break;
                    }
                    let l = line.trim_end().to_string();
                    if l.is_empty() {
                        break;
                    }
                    let lower = l.to_ascii_lowercase();
                    if let Some(v) = lower.strip_prefix("content-length:") {
                        len = v.trim().parse().unwrap();
                    }
                    if lower.starts_with("mcp-session-id:") {
                        sid = Some(l.split_once(':').unwrap().1.trim().to_string());
                    }
                }
                let mut body = vec![0u8; len];
                r.read_exact(&mut body).unwrap();
                let req: Value = serde_json::from_slice(&body).unwrap();
                let method = req["method"].as_str().unwrap_or("").to_string();
                let id = req["id"].clone();
                let result = match method.as_str() {
                    "initialize" => {
                        json!({"protocolVersion": PROTOCOL_VERSION, "serverInfo": {"name": "jeb-mcp", "version": "1.3.0"}, "capabilities": {"tools": {}}})
                    }
                    "notifications/initialized" => {
                        s.write_all(b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n").unwrap();
                        continue;
                    }
                    "tools/list" => {
                        json!({"tools": [{"name": "get_client_information"}, {"name": "open_project"}, {"name": "list_units"}, {"name": "decompile_code_item"}]})
                    }
                    "tools/call" => {
                        seen2.lock().unwrap().push(sid.clone().unwrap_or_default());
                        let name = req["params"]["name"].as_str().unwrap_or("");
                        match name {
                            "get_client_information" => json!({"content": [{"type": "text", "text": "{\"jeb_version\":\"5.48\"}"}]}),
                            "list_units" => {
                                json!({"content": [], "structuredContent": {"units": [{"path": "Bytecode"}, {"path": "Manifest"}], "args": req["params"]["arguments"]}})
                            }
                            "decompile_code_item" if req["params"]["arguments"]["item_address"] == "Lbad;" => {
                                json!({"isError": true, "content": [{"type": "text", "text": "no such item"}]})
                            }
                            "decompile_code_item" => json!({"content": [{"type": "text", "text": "public class Main {}"}]}),
                            "open_project" => json!({"content": [{"type": "text", "text": "{\"opened\":true}"}]}),
                            _ => json!({"isError": true, "content": []}),
                        }
                    }
                    _ => json!({}),
                };
                let msg = serde_json::to_string(&json!({"jsonrpc": "2.0", "id": id, "result": result})).unwrap();
                let resp = if sse && method == "tools/call" {
                    // Chunked event stream with a notification first.
                    let events = format!(
                        "event: message\r\ndata: {{\"jsonrpc\":\"2.0\",\"method\":\"notifications/progress\"}}\r\n\r\nevent: message\r\ndata: {msg}\r\n\r\n"
                    );
                    let half = events.len() / 2;
                    format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\nMcp-Session-Id: sess-1\r\n\r\n{:x}\r\n{}\r\n{:x}\r\n{}\r\n0\r\n\r\n",
                        half,
                        &events[..half],
                        events.len() - half,
                        &events[half..]
                    )
                } else {
                    format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nMcp-Session-Id: sess-1\r\nContent-Length: {}\r\n\r\n{msg}", msg.len())
                };
                let _ = s.write_all(resp.as_bytes());
            }
        });
        (url, seen)
    }

    #[test]
    fn talks_to_a_json_server() {
        let (url, seen) = fake_server(false);
        let e = engine(Some(url.clone()));
        let v = call(&e, "engines_jeb_check", json!({})).unwrap();
        assert_eq!(v["environment"]["engine"], "jeb");
        assert_eq!(v["environment"]["clean_room"], false);
        assert_eq!(v["environment"]["engine_version"], "1.3.0");
        assert_eq!(v["result"]["payload"]["jeb_version"], "5.48");
        assert!(v["result"]["missing_tools"].as_array().unwrap().is_empty());
        let d = call(&e, "android_jeb_decompile", json!({"item_address": "LMain;", "item_kind": "type"})).unwrap();
        assert_eq!(d["result"]["payload"], "public class Main {}");
        let err = call(&e, "android_jeb_decompile", json!({"item_address": "Lbad;", "item_kind": "method"})).unwrap_err();
        assert_eq!(err.code, ErrorCode::ProgramFailed);
        assert!(err.message.contains("no such item"));
        let f = craft_anything_testkit::temp_file("x.apk", b"PK\x05\x06");
        let o = call(&e, "android_jeb_open", json!({"path": f})).unwrap();
        assert_eq!(o["result"]["payload"]["opened"], true);
        assert_eq!(o["subject"]["sha256"].as_str().unwrap().len(), 64);
        assert!(seen.lock().unwrap().iter().all(|s| s == "sess-1"));
    }

    #[test]
    fn talks_to_an_sse_server() {
        let (url, _) = fake_server(true);
        let e = engine(Some(url));
        let v = call(&e, "android_jeb_units_browse", json!({"filter": "Byte", "index": 2, "count": 5})).unwrap();
        assert_eq!(v["result"]["units_returned"], 2);
        assert_eq!(v["result"]["payload"]["args"]["filter"], "Byte");
        assert_eq!(v["result"]["payload"]["args"]["index"], 2);
        assert!(call(&e, "android_jeb_units_browse", json!({"count": 101})).is_err());
    }

    #[test]
    fn not_configured_refused_and_remote_urls() {
        let e = engine(None);
        let err = call(&e, "engines_jeb_check", json!({})).unwrap_err();
        assert_eq!(err.code, ErrorCode::EngineMissing);
        assert!(err.message.contains("not configured"));
        assert!(err.remediation.unwrap().contains("jeb_url"));
        let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let e = engine(Some(format!("http://127.0.0.1:{port}/mcp")));
        assert_eq!(call(&e, "engines_jeb_check", json!({})).unwrap_err().code, ErrorCode::EngineMissing);
        for bad in [
            "http://10.0.0.1:8425/mcp",
            "https://127.0.0.1/mcp",
            "http://user:pw@127.0.0.1/mcp",
            "http://127.0.0.1/mcp?x=1",
            "http://127.0.0.1:0/",
            "ftp://localhost",
        ] {
            let e = engine(Some(bad.into()));
            assert_eq!(call(&e, "android_jeb_units_browse", json!({})).unwrap_err().code, ErrorCode::BadSettings, "{bad}");
        }
    }

    #[test]
    fn slow_server_times_out() {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://127.0.0.1:{}/mcp", l.local_addr().unwrap().port());
        std::thread::spawn(move || {
            let mut held = Vec::new();
            for s in l.incoming().take(2) {
                held.push(s);
                std::thread::sleep(Duration::from_secs(3));
            }
        });
        let e = engine(Some(url));
        let started = Instant::now();
        let err = call(&e, "engines_jeb_check", json!({"timeout_secs": 1})).unwrap_err();
        assert_eq!(err.code, ErrorCode::TimedOut);
        assert!(started.elapsed() < Duration::from_secs(3));
    }

    #[test]
    fn endpoint_parsing_and_framing() {
        let ep = parse_endpoint("http://[::1]:9000/mcp").unwrap();
        assert_eq!(ep.host_header, "[::1]:9000");
        assert_eq!(ep.path, "/mcp");
        assert_eq!(parse_endpoint("http://localhost").unwrap().addrs.len(), 2);
        let (b, done) = dechunk(b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n");
        assert_eq!((b.as_slice(), done), (&b"abcde"[..], true));
        assert!(!dechunk(b"5\r\nab").1);
        assert!(!dechunk(b"zz\r\n").1);
        let msgs = sse_messages(b"data: {\"id\":1,\"result\":2}\n\ndata: junk\n\n");
        assert_eq!(matching(msgs, 1).unwrap()["result"], 2);
        for seed in 0..50 {
            let n = craft_anything_testkit::noise(seed, 300);
            let _ = dechunk(&n);
            let _ = sse_messages(&n);
            let _ = parse_endpoint(&String::from_utf8_lossy(&n));
        }
    }
}
