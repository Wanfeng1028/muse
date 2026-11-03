//! A small HTTP/1.1 server on loopback that asks a caller-supplied [`Answerer`] what to send back.
//! It knows nothing about recordings: the caller decides every answer.
//!
//! What a page on the internet can't do to it matters as much as what it serves, so it binds to
//! `127.0.0.1` only, refuses a `Host` that isn't loopback (DNS rebinding) and an `Origin` that isn't
//! a local page. Everything a client controls is bounded: head and body size, header count, time to
//! send a request, and how many connections are open. Every connection closes after one answer.
//! Dropping the [`LoopbackServer`] stops it and frees the port.

use std::io::{ErrorKind, Read, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

/// How often a blocked read wakes to check the time limit and whether the server is stopping.
const READ_SLICE: Duration = Duration::from_millis(100);
const MAX_HEADERS: usize = 128;
const MAX_ALLOW_HEADERS: usize = 1024;

/// One request, already checked. The path and query are exactly as the client sent them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Request {
    pub method: String,
    pub path: String,
    pub query: String,
    pub body: Vec<u8>,
}

/// What to send back. `Content-Length`, `Connection` and CORS headers are set by the server, and a
/// header with an invalid name or value is left out rather than sent.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Response {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Response {
    /// A JSON answer.
    pub fn json(status: u16, value: &serde_json::Value) -> Response {
        Response { status, headers: vec![("Content-Type".into(), "application/json".into())], body: value.to_string().into_bytes() }
    }
}

/// Decides the answer to a checked request. Runs on the connection's own thread.
pub trait Answerer: Send + Sync + 'static {
    fn answer(&self, request: &Request) -> Response;
}

impl<F: Fn(&Request) -> Response + Send + Sync + 'static> Answerer for F {
    fn answer(&self, request: &Request) -> Response {
        self(request)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limits {
    pub max_head_bytes: usize,
    pub max_body_bytes: usize,
    /// How long a client has to send its whole request.
    pub request_time: Duration,
    pub write_time: Duration,
    pub max_connections: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Limits {
            max_head_bytes: 32 * 1024,
            max_body_bytes: 16 * 1024 * 1024,
            request_time: Duration::from_secs(10),
            write_time: Duration::from_secs(20),
            max_connections: 64,
        }
    }
}

/// A running server. Dropping it stops it.
pub struct LoopbackServer {
    pub port: u16,
    stop: Arc<AtomicBool>,
    active: Arc<AtomicUsize>,
    refused: Arc<AtomicU64>,
    accept_thread: Option<JoinHandle<()>>,
}

impl LoopbackServer {
    pub fn url(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }

    /// Requests refused before reaching the answerer (bad host or origin, too large, too slow…).
    pub fn refused(&self) -> u64 {
        self.refused.load(Ordering::Relaxed)
    }
}

impl Drop for LoopbackServer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(t) = self.accept_thread.take() {
            let _ = t.join();
        }
        // Connections notice `stop` within a read slice; a stuck write has its own limit, so this
        // only waits briefly and never holds up whoever dropped the server.
        let until = Instant::now() + Duration::from_secs(1);
        while self.active.load(Ordering::SeqCst) > 0 && Instant::now() < until {
            std::thread::sleep(Duration::from_millis(10));
        }
    }
}

/// Serve on `127.0.0.1:port` (0 picks a free port).
pub fn serve(port: u16, limits: Limits, answerer: Arc<dyn Answerer>) -> std::io::Result<LoopbackServer> {
    let listener = TcpListener::bind(("127.0.0.1", port))?;
    listener.set_nonblocking(true)?;
    let port = listener.local_addr()?.port();
    let stop = Arc::new(AtomicBool::new(false));
    let active = Arc::new(AtomicUsize::new(0));
    let refused = Arc::new(AtomicU64::new(0));
    let shared = Shared { port, limits, answerer, stop: stop.clone(), refused: refused.clone() };
    let counter = active.clone();
    let accept_thread = std::thread::Builder::new().name("loopback-server".into()).spawn(move || accept_loop(&listener, &shared, &counter))?;
    Ok(LoopbackServer { port, stop, active, refused, accept_thread: Some(accept_thread) })
}

#[derive(Clone)]
struct Shared {
    port: u16,
    limits: Limits,
    answerer: Arc<dyn Answerer>,
    stop: Arc<AtomicBool>,
    refused: Arc<AtomicU64>,
}

/// Counts a connection for as long as it lives, even if its thread never starts or panics.
struct Open(Arc<AtomicUsize>);

impl Drop for Open {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

fn accept_loop(listener: &TcpListener, shared: &Shared, active: &Arc<AtomicUsize>) {
    while !shared.stop.load(Ordering::SeqCst) {
        match listener.accept() {
            Ok((stream, peer)) => {
                if !peer.ip().is_loopback() || stream.set_nonblocking(false).is_err() {
                    continue;
                }
                if active.load(Ordering::SeqCst) >= shared.limits.max_connections {
                    shared.refused.fetch_add(1, Ordering::Relaxed);
                    let _ = stream.set_write_timeout(Some(Duration::from_millis(200)));
                    let body = refusal("too_many_connections", "Too many connections are open; try again shortly.");
                    let _ = write_response(&stream, &body, "GET", None);
                    // This thread accepts everyone, so it waits only moments for the rest.
                    let _ = stream.set_read_timeout(Some(Duration::from_millis(5)));
                    drain(&stream, Duration::from_millis(20));
                    continue;
                }
                active.fetch_add(1, Ordering::SeqCst);
                let open = Open(active.clone());
                let conn = shared.clone();
                let _ = std::thread::Builder::new().name("loopback-conn".into()).spawn(move || {
                    let _open = open;
                    handle(stream, &conn);
                });
            }
            Err(e) if e.kind() == ErrorKind::WouldBlock => std::thread::sleep(Duration::from_millis(10)),
            Err(_) => std::thread::sleep(Duration::from_millis(50)),
        }
    }
}

fn refusal(code: &str, message: &str) -> Response {
    let status = match code {
        "bad_request" => 400,
        "not_local" => 403,
        "too_slow" => 408,
        "too_large" => 413,
        "head_too_large" => 431,
        "chunked_not_supported" => 501,
        _ => 503,
    };
    Response::json(status, &serde_json::json!({"error": code, "message": message}))
}

/// The head of a request, parsed and bounded.
struct Head {
    method: String,
    path: String,
    query: String,
    host: Option<String>,
    origin: Option<String>,
    content_length: usize,
    expect_continue: bool,
    preflight_method: bool,
    preflight_headers: Option<String>,
}

fn is_token(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b))
}

fn parse_head(text: &str) -> Result<Head, Response> {
    let bad = |m: &str| refusal("bad_request", m);
    let mut lines = text.split("\r\n");
    let mut first = lines.next().unwrap_or_default().split(' ');
    let (method, target, version) = (first.next().unwrap_or_default(), first.next().unwrap_or_default(), first.next().unwrap_or_default());
    if !is_token(method) || first.next().is_some() || !matches!(version, "HTTP/1.1" | "HTTP/1.0") {
        return Err(bad("The request line isn't HTTP/1.1."));
    }
    // Only a path: an absolute URL here would let a request name a different site.
    if !target.starts_with('/') || target.bytes().any(|b| b.is_ascii_control() || b == b' ') {
        return Err(bad("The request target must be a path starting with /."));
    }
    let target = target.split('#').next().unwrap_or_default();
    let (path, query) = target.split_once('?').unwrap_or((target, ""));
    let mut head = Head {
        method: method.to_string(),
        path: path.to_string(),
        query: query.to_string(),
        host: None,
        origin: None,
        content_length: 0,
        expect_continue: false,
        preflight_method: false,
        preflight_headers: None,
    };
    let (mut hosts, mut origins, mut lengths, mut count) = (0usize, 0usize, 0usize, 0usize);
    for line in lines {
        if line.is_empty() {
            continue;
        }
        count += 1;
        if count > MAX_HEADERS {
            return Err(refusal("head_too_large", "The request has too many headers."));
        }
        let Some((name, value)) = line.split_once(':') else { return Err(bad("A header line has no colon.")) };
        if !is_token(name) {
            return Err(bad("A header name isn't valid."));
        }
        let value = value.trim_matches([' ', '\t']);
        match name.to_ascii_lowercase().as_str() {
            "host" => {
                hosts += 1;
                head.host = Some(value.to_string());
            }
            "origin" => {
                origins += 1;
                head.origin = Some(value.to_string());
            }
            "content-length" => {
                lengths += 1;
                if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
                    return Err(bad("Content-Length isn't a number."));
                }
                // Too many digits for usize is simply too large.
                head.content_length = value.parse().unwrap_or(usize::MAX);
            }
            "transfer-encoding" => {
                return Err(refusal("chunked_not_supported", "Send the body with a Content-Length."));
            }
            "expect" => head.expect_continue = value.eq_ignore_ascii_case("100-continue"),
            "access-control-request-method" => head.preflight_method = true,
            "access-control-request-headers" => head.preflight_headers = Some(value.to_string()),
            _ => {}
        }
    }
    if hosts != 1 || origins > 1 || lengths > 1 {
        return Err(bad("A request needs one Host header, and at most one Origin and Content-Length."));
    }
    Ok(head)
}

fn is_loopback_name(host: &str) -> bool {
    host.eq_ignore_ascii_case("localhost") || host == "127.0.0.1" || host == "[::1]"
}

/// `localhost`, `127.0.0.1` or `[::1]`, with `port` if a port is written and one is given.
pub fn host_is_loopback(host: &str, port: Option<u16>) -> bool {
    let (name, written) = match host.rfind(':') {
        // The colons inside `[::1]` aren't a port separator.
        Some(i) if !host.ends_with(']') => (host.get(..i).unwrap_or_default(), host.get(i + 1..)),
        _ => (host, None),
    };
    if !is_loopback_name(name) {
        return false;
    }
    match (written, port) {
        (None, _) => true,
        (Some(w), Some(p)) => w.parse::<u16>().is_ok_and(|w| w == p),
        (Some(w), None) => w.parse::<u16>().is_ok(),
    }
}

/// A page served from this computer, on any port: what a front end under development is.
pub fn origin_is_local(origin: &str) -> bool {
    let Some((scheme, rest)) = origin.split_once("://") else { return false };
    (scheme.eq_ignore_ascii_case("http") || scheme.eq_ignore_ascii_case("https")) && !rest.contains(['/', '@', '?', '#']) && host_is_loopback(rest, None)
}

enum ReadStep {
    Got(usize),
    Closed,
    TooSlow,
}

/// Read once, waking regularly until the request's time is up or the server stops.
fn read_some(mut stream: &TcpStream, buf: &mut [u8], until: Instant, stop: &AtomicBool) -> ReadStep {
    loop {
        if stop.load(Ordering::SeqCst) {
            return ReadStep::Closed;
        }
        if Instant::now() >= until {
            return ReadStep::TooSlow;
        }
        match stream.read(buf) {
            Ok(0) => return ReadStep::Closed,
            Ok(n) => return ReadStep::Got(n),
            Err(e) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut | ErrorKind::Interrupted) => {}
            Err(_) => return ReadStep::Closed,
        }
    }
}

fn head_end(buf: &[u8], from: usize) -> Option<usize> {
    let start = from.saturating_sub(3);
    buf.get(start..)?.windows(4).position(|w| w == b"\r\n\r\n").map(|p| p + start)
}

fn handle(stream: TcpStream, shared: &Shared) {
    if stream.set_read_timeout(Some(READ_SLICE)).is_err() || stream.set_write_timeout(Some(shared.limits.write_time)).is_err() {
        return;
    }
    let until = Instant::now() + shared.limits.request_time;
    let refuse = |response: Response| {
        shared.refused.fetch_add(1, Ordering::Relaxed);
        let _ = write_response(&stream, &response, "GET", None);
        drain(&stream, Duration::from_millis(200));
    };

    // The head.
    let mut buf: Vec<u8> = Vec::with_capacity(4096);
    let mut chunk = [0u8; 4096];
    let end = loop {
        let before = buf.len();
        match read_some(&stream, &mut chunk, until, &shared.stop) {
            ReadStep::Got(n) => buf.extend_from_slice(chunk.get(..n).unwrap_or_default()),
            ReadStep::Closed => return,
            ReadStep::TooSlow => return refuse(refusal("too_slow", "The request took too long to arrive.")),
        }
        if let Some(end) = head_end(&buf, before) {
            break end;
        }
        if buf.len() > shared.limits.max_head_bytes {
            return refuse(refusal("head_too_large", "The request's headers are too large."));
        }
    };
    if end > shared.limits.max_head_bytes {
        return refuse(refusal("head_too_large", "The request's headers are too large."));
    }
    let Some(text) = buf.get(..end).and_then(|b| std::str::from_utf8(b).ok()) else {
        return refuse(refusal("bad_request", "The request's headers aren't text."));
    };
    let head = match parse_head(text) {
        Ok(h) => h,
        Err(r) => return refuse(r),
    };
    if !head.host.as_deref().is_some_and(|h| host_is_loopback(h, Some(shared.port))) {
        return refuse(refusal("not_local", "This server answers only requests addressed to this computer."));
    }
    let origin = head.origin.as_deref();
    if origin.is_some_and(|o| !origin_is_local(o)) {
        return refuse(refusal("not_local", "This server answers only pages served from this computer."));
    }

    // A browser's question before a cross-origin request: answered here, not counted as a request.
    if head.method == "OPTIONS" && head.preflight_method && origin.is_some() {
        let mut headers = vec![("Access-Control-Allow-Methods".to_string(), "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS".to_string())];
        if let Some(h) = head.preflight_headers.as_deref().filter(|h| h.len() <= MAX_ALLOW_HEADERS && h.split(',').all(|p| is_token(p.trim()))) {
            headers.push(("Access-Control-Allow-Headers".to_string(), h.to_string()));
        }
        headers.push(("Access-Control-Max-Age".to_string(), "600".to_string()));
        let _ = write_response(&stream, &Response { status: 204, headers, body: Vec::new() }, &head.method, origin);
        return;
    }

    // The body.
    if head.content_length > shared.limits.max_body_bytes {
        return refuse(refusal("too_large", "The request's body is too large."));
    }
    if head.expect_continue && (&stream).write_all(b"HTTP/1.1 100 Continue\r\n\r\n").is_err() {
        return;
    }
    let mut body = buf.get(end + 4..).unwrap_or_default().to_vec();
    body.truncate(head.content_length);
    while body.len() < head.content_length {
        match read_some(&stream, &mut chunk, until, &shared.stop) {
            ReadStep::Got(n) => {
                let want = head.content_length - body.len();
                body.extend_from_slice(chunk.get(..n.min(want)).unwrap_or_default());
            }
            ReadStep::Closed => return,
            ReadStep::TooSlow => return refuse(refusal("too_slow", "The request took too long to arrive.")),
        }
    }

    let method = head.method;
    let request = Request { method: method.clone(), path: head.path, query: head.query, body };
    let response = shared.answerer.answer(&request);
    let _ = write_response(&stream, &response, &method, head.origin.as_deref());
}

/// After refusing a request whose remainder is still arriving: read a little of it, so closing
/// doesn't reset the connection and lose the answer. Bounded in bytes and time.
fn drain(stream: &TcpStream, time: Duration) {
    let _ = stream.shutdown(Shutdown::Write);
    let until = Instant::now() + time;
    let mut left = 256 * 1024usize;
    let mut chunk = [0u8; 4096];
    let mut reader = stream;
    while left > 0 && Instant::now() < until {
        match reader.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => left = left.saturating_sub(n),
            Err(e) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut | ErrorKind::Interrupted) => {}
            Err(_) => break,
        }
    }
}

fn reason(status: u16) -> &'static str {
    match status {
        200 => "OK",
        201 => "Created",
        202 => "Accepted",
        204 => "No Content",
        301 => "Moved Permanently",
        302 => "Found",
        304 => "Not Modified",
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        408 => "Request Timeout",
        413 => "Content Too Large",
        431 => "Request Header Fields Too Large",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        503 => "Service Unavailable",
        _ => "Status",
    }
}

/// Headers this server sets itself, whatever the answerer says.
fn server_owned(name: &str) -> bool {
    let l = name.to_ascii_lowercase();
    matches!(l.as_str(), "content-length" | "connection" | "transfer-encoding" | "keep-alive" | "upgrade" | "vary") || l.starts_with("access-control-")
}

fn write_response(mut stream: &TcpStream, r: &Response, method: &str, origin: Option<&str>) -> std::io::Result<()> {
    // A status a client could misread as something else (a second head, say) isn't sent.
    let status = if (200..=599).contains(&r.status) { r.status } else { 500 };
    let mut head = format!("HTTP/1.1 {status} {}\r\n", reason(status));
    let mut exposed: Vec<&str> = Vec::new();
    for (k, v) in &r.headers {
        // Header text comes from recordings: nothing in it may start a new header line.
        if is_token(k) && !server_owned(k) && !v.bytes().any(|b| b.is_ascii_control() && b != b'\t') {
            head.push_str(&format!("{k}: {v}\r\n"));
            exposed.push(k);
        } else if k.to_ascii_lowercase().starts_with("access-control-") && is_token(k) && !v.bytes().any(|b| b.is_ascii_control() && b != b'\t') {
            // The preflight answer's own headers, made above.
            head.push_str(&format!("{k}: {v}\r\n"));
        }
    }
    if let Some(o) = origin.filter(|o| origin_is_local(o)) {
        head.push_str(&format!("Access-Control-Allow-Origin: {o}\r\nAccess-Control-Allow-Credentials: true\r\nVary: Origin\r\n"));
        if !exposed.is_empty() {
            head.push_str(&format!("Access-Control-Expose-Headers: {}\r\n", exposed.join(", ")));
        }
    }
    let bodiless = matches!(status, 204 | 304);
    if !bodiless {
        head.push_str(&format!("Content-Length: {}\r\n", r.body.len()));
    }
    head.push_str("Connection: close\r\n\r\n");
    stream.write_all(head.as_bytes())?;
    if !bodiless && method != "HEAD" {
        stream.write_all(&r.body)?;
    }
    stream.flush()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpStream;

    fn echo() -> Arc<dyn Answerer> {
        Arc::new(|r: &Request| {
            if r.path == "/hostile" {
                return Response {
                    status: 200,
                    headers: vec![("X-Good".into(), "yes".into()), ("X-Bad".into(), "a\r\nSet-Cookie: stolen=1".into())],
                    body: b"ok".to_vec(),
                };
            }
            Response::json(200, &serde_json::json!({"method": r.method, "path": r.path, "query": r.query, "body": String::from_utf8_lossy(&r.body)}))
        })
    }

    fn start() -> LoopbackServer {
        serve(0, Limits::default(), echo()).unwrap()
    }

    fn send(port: u16, raw: &[u8]) -> String {
        let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(20))).unwrap();
        s.write_all(raw).unwrap();
        let mut out = Vec::new();
        let _ = s.read_to_end(&mut out);
        String::from_utf8_lossy(&out).into_owned()
    }

    fn get(port: u16, path: &str, extra: &str) -> String {
        send(port, format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{extra}\r\n").as_bytes())
    }

    /// Dropping a server frees its port for the next one. (Another test's listener can be handed
    /// a freed ephemeral port at once, so the port is tried for a moment rather than once.)
    #[test]
    fn dropping_a_server_frees_its_port() {
        let srv = start();
        let port = srv.port;
        assert!(get(port, "/", "").starts_with("HTTP/1.1 200"));
        drop(srv);
        let until = std::time::Instant::now() + Duration::from_secs(2);
        while std::net::TcpListener::bind(("127.0.0.1", port)).is_err() {
            assert!(std::time::Instant::now() < until, "port {port} is still held");
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    #[test]
    fn answers_with_method_path_query_and_body() {
        let srv = start();
        let r = get(srv.port, "/a/b?x=1&y=2", "");
        assert!(r.starts_with("HTTP/1.1 200 OK"), "{r}");
        assert!(r.contains("\"path\":\"/a/b\"") && r.contains("\"query\":\"x=1&y=2\""), "{r}");
        let post = send(srv.port, format!("POST /p HTTP/1.1\r\nHost: localhost:{}\r\nContent-Length: 5\r\n\r\nhello", srv.port).as_bytes());
        assert!(post.contains("\"body\":\"hello\"") && post.contains("\"method\":\"POST\""), "{post}");
    }

    #[test]
    fn head_sends_no_body_but_says_how_long_it_would_be() {
        let srv = start();
        let r = send(srv.port, format!("HEAD /x HTTP/1.1\r\nHost: 127.0.0.1:{}\r\n\r\n", srv.port).as_bytes());
        assert!(r.contains("Content-Length: ") && r.ends_with("\r\n\r\n"), "{r}");
    }

    #[test]
    fn refuses_hosts_that_are_not_loopback() {
        let srv = start();
        for host in ["evil.example", "127.0.0.1.evil.example", "localhost.evil.example:80", "127.0.0.2", "[::2]"] {
            let r = send(srv.port, format!("GET / HTTP/1.1\r\nHost: {host}\r\n\r\n").as_bytes());
            assert!(r.starts_with("HTTP/1.1 403") && r.contains("not_local"), "{host}: {r}");
        }
        // The right name with another port is a request meant for something else.
        let other = srv.port.wrapping_add(1);
        assert!(send(srv.port, format!("GET / HTTP/1.1\r\nHost: localhost:{other}\r\n\r\n").as_bytes()).starts_with("HTTP/1.1 403"));
        assert!(send(srv.port, b"GET / HTTP/1.1\r\n\r\n").starts_with("HTTP/1.1 400"), "no Host at all");
        let twice = "GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nHost: evil.example\r\n\r\n";
        assert!(send(srv.port, twice.as_bytes()).starts_with("HTTP/1.1 400"), "two Hosts");
        assert_eq!(srv.refused(), 8);
        assert!(get(srv.port, "/", "").starts_with("HTTP/1.1 200"));
        assert!(send(srv.port, format!("GET / HTTP/1.1\r\nHost: [::1]:{}\r\n\r\n", srv.port).as_bytes()).starts_with("HTTP/1.1 200"));
    }

    #[test]
    fn refuses_absolute_urls_and_malformed_requests() {
        let srv = start();
        for raw in [
            "GET http://evil.example/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            "GET / HTTP/2\r\nHost: 127.0.0.1\r\n\r\n",
            "GET /a b HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            "G@T / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            "GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nno colon here\r\n\r\n",
            "POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: nope\r\n\r\n",
            "POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\nx",
            "\r\n\r\n",
        ] {
            assert!(send(srv.port, raw.as_bytes()).starts_with("HTTP/1.1 400"), "{raw:?}");
        }
        assert!(send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n").starts_with("HTTP/1.1 501"));
        assert!(send(srv.port, b"\xff\xfe / HTTP/1.1\r\n\r\n").starts_with("HTTP/1.1 400"), "not text");
    }

    #[test]
    fn refuses_oversize_heads_and_bodies() {
        let limits = Limits { max_head_bytes: 512, max_body_bytes: 16, ..Limits::default() };
        let srv = serve(0, limits, echo()).unwrap();
        let huge = format!("GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Big: {}\r\n\r\n", "a".repeat(4096));
        assert!(send(srv.port, huge.as_bytes()).starts_with("HTTP/1.1 431"));
        let many: String = (0..200).map(|i| format!("A{i}: b\r\n")).collect();
        let srv2 = start();
        assert!(send(srv2.port, format!("GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n{many}\r\n").as_bytes()).starts_with("HTTP/1.1 431"), "too many headers");
        let big = send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 17\r\n\r\n12345678901234567");
        assert!(big.starts_with("HTTP/1.1 413"), "{big}");
        let overflow = send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 99999999999999999999999999\r\n\r\n");
        assert!(overflow.starts_with("HTTP/1.1 413"), "{overflow}");
        let fits = send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 16\r\n\r\n1234567890123456");
        assert!(fits.starts_with("HTTP/1.1 200"), "{fits}");
    }

    #[test]
    fn extra_bytes_after_the_body_are_not_part_of_it() {
        let srv = start();
        let r = send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\n\r\nabGET /smuggled HTTP/1.1\r\n\r\n");
        assert!(r.contains("\"body\":\"ab\"") && !r.contains("smuggled"), "{r}");
    }

    #[test]
    fn a_slow_client_times_out_and_does_not_hold_the_server() {
        let limits = Limits { request_time: Duration::from_millis(300), ..Limits::default() };
        let srv = serve(0, limits, echo()).unwrap();
        let mut s = TcpStream::connect(("127.0.0.1", srv.port)).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(10))).unwrap();
        s.write_all(b"GET / HTTP/1.1\r\nHost: 127.").unwrap();
        // A second client is served while the first stalls.
        assert!(get(srv.port, "/", "").starts_with("HTTP/1.1 200"));
        let started = Instant::now();
        let mut out = String::new();
        let _ = s.read_to_string(&mut out);
        assert!(out.starts_with("HTTP/1.1 408"), "{out}");
        assert!(started.elapsed() < Duration::from_secs(5));
        // Trickling bytes doesn't extend the time: the limit covers the whole request.
        let mut t = TcpStream::connect(("127.0.0.1", srv.port)).unwrap();
        t.set_read_timeout(Some(Duration::from_secs(10))).unwrap();
        let started = Instant::now();
        for _ in 0..8 {
            if t.write_all(b"X").is_err() {
                break;
            }
            std::thread::sleep(Duration::from_millis(60));
        }
        let mut out = String::new();
        let _ = t.read_to_string(&mut out);
        assert!(out.starts_with("HTTP/1.1 408") || out.is_empty(), "{out}");
        assert!(started.elapsed() < Duration::from_secs(5));
    }

    #[test]
    fn a_slow_body_times_out_too() {
        let limits = Limits { request_time: Duration::from_millis(200), ..Limits::default() };
        let srv = serve(0, limits, echo()).unwrap();
        let r = send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 10\r\n\r\nabc");
        assert!(r.starts_with("HTTP/1.1 408"), "{r}");
    }

    #[test]
    fn the_connection_cap_refuses_rather_than_queues() {
        let limits = Limits { max_connections: 2, request_time: Duration::from_secs(3), ..Limits::default() };
        let srv = serve(0, limits, echo()).unwrap();
        let held: Vec<TcpStream> = (0..2).map(|_| TcpStream::connect(("127.0.0.1", srv.port)).unwrap()).collect();
        std::thread::sleep(Duration::from_millis(100));
        let r = get(srv.port, "/", "");
        assert!(r.starts_with("HTTP/1.1 503") && r.contains("too_many_connections"), "{r}");
        drop(held);
        let until = Instant::now() + Duration::from_secs(5);
        loop {
            if get(srv.port, "/", "").starts_with("HTTP/1.1 200") {
                break;
            }
            assert!(Instant::now() < until, "a closed connection frees its place");
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    #[test]
    fn cors_allows_local_pages_and_refuses_others() {
        let srv = start();
        let r = get(srv.port, "/", "Origin: http://localhost:5173\r\n");
        assert!(r.contains("Access-Control-Allow-Origin: http://localhost:5173") && r.contains("Vary: Origin"), "{r}");
        for origin in ["https://evil.example", "null", "http://localhost.evil.example", "http://localhost@evil.example", "file://"] {
            let r = get(srv.port, "/", &format!("Origin: {origin}\r\n"));
            assert!(r.starts_with("HTTP/1.1 403") && !r.contains("Access-Control-Allow-Origin"), "{origin}: {r}");
        }
        let pre = send(
            srv.port,
            format!(
                "OPTIONS /api HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:3000\r\nAccess-Control-Request-Method: POST\r\nAccess-Control-Request-Headers: content-type, x-thing\r\n\r\n",
                srv.port
            )
            .as_bytes(),
        );
        assert!(pre.starts_with("HTTP/1.1 204"), "{pre}");
        assert!(pre.contains("Access-Control-Allow-Methods: GET") && pre.contains("Access-Control-Allow-Headers: content-type, x-thing"), "{pre}");
        assert!(pre.contains("Access-Control-Allow-Origin: http://127.0.0.1:3000"), "{pre}");
        let hostile = send(
            srv.port,
            b"OPTIONS /api HTTP/1.1\r\nHost: 127.0.0.1\r\nOrigin: http://localhost\r\nAccess-Control-Request-Method: POST\r\nAccess-Control-Request-Headers: a b:c\r\n\r\n",
        );
        assert!(!hostile.contains("Access-Control-Allow-Headers"), "{hostile}");
    }

    #[test]
    fn a_header_that_would_start_a_new_line_is_not_sent() {
        let srv = start();
        let r = get(srv.port, "/hostile", "");
        assert!(r.contains("X-Good: yes") && !r.contains("stolen") && !r.contains("X-Bad"), "{r}");
    }

    #[test]
    fn expect_continue_gets_its_interim_answer() {
        let srv = start();
        let r = send(srv.port, b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nExpect: 100-continue\r\nContent-Length: 2\r\n\r\nhi");
        assert!(r.starts_with("HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200"), "{r}");
    }

    #[test]
    fn an_answerer_that_panics_only_loses_its_connection() {
        let a: Arc<dyn Answerer> = Arc::new(|r: &Request| {
            assert!(r.path != "/boom", "deliberate");
            Response { status: 200, headers: Vec::new(), body: b"fine".to_vec() }
        });
        let srv = serve(0, Limits::default(), a).unwrap();
        let _ = get(srv.port, "/boom", "");
        assert!(get(srv.port, "/", "").contains("fine"));
    }

    #[test]
    fn a_status_outside_the_normal_range_is_not_sent() {
        let a: Arc<dyn Answerer> =
            Arc::new(|r: &Request| Response { status: r.path.trim_start_matches('/').parse().unwrap_or(200), headers: Vec::new(), body: b"x".to_vec() });
        let srv = serve(0, Limits::default(), a).unwrap();
        assert!(get(srv.port, "/101", "").starts_with("HTTP/1.1 500"));
        assert!(get(srv.port, "/700", "").starts_with("HTTP/1.1 500"));
        let none = get(srv.port, "/204", "");
        assert!(none.starts_with("HTTP/1.1 204") && !none.contains("Content-Length"), "{none}");
    }

    #[test]
    fn dropping_it_frees_the_port_even_with_a_stalled_client() {
        let srv = start();
        let port = srv.port;
        let stalled = TcpStream::connect(("127.0.0.1", port)).unwrap();
        std::thread::sleep(Duration::from_millis(50));
        let started = Instant::now();
        drop(srv);
        assert!(started.elapsed() < Duration::from_secs(3), "shutdown doesn't wait for a client");
        drop(stalled);
        // The same port can be served again straight away.
        let again = serve(port, Limits::default(), echo()).unwrap();
        assert_eq!(again.port, port);
        assert!(get(port, "/", "").starts_with("HTTP/1.1 200"));
    }

    #[test]
    fn a_port_in_use_is_an_error_not_a_panic() {
        let srv = start();
        assert!(serve(srv.port, Limits::default(), echo()).is_err());
    }

    #[test]
    fn host_and_origin_rules() {
        assert!(host_is_loopback("localhost", None) && host_is_loopback("LOCALHOST:80", Some(80)) && host_is_loopback("[::1]", Some(1)));
        assert!(
            !host_is_loopback("localhost:81", Some(80))
                && !host_is_loopback("localhost:x", None)
                && !host_is_loopback("", None)
                && !host_is_loopback(":", None)
        );
        assert!(origin_is_local("http://localhost") && origin_is_local("https://127.0.0.1:8443") && origin_is_local("http://[::1]:3000"));
        assert!(!origin_is_local("ftp://localhost") && !origin_is_local("http://localhost/x") && !origin_is_local("localhost"));
    }
}
