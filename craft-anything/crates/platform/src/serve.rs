//! A tiny static file server on loopback, for previewing and checking a built website.
//!
//! GET/HEAD only, one short-lived connection at a time per request thread, paths confined to the
//! root (no `..`, symlinks resolved and re-checked), unknown extension-less paths fall back to
//! `index.html` (single-page apps). It stops when the [`StaticServer`] is dropped.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

pub struct StaticServer {
    pub port: u16,
    pub root: PathBuf,
    stop: Arc<AtomicBool>,
}

impl StaticServer {
    pub fn url(&self) -> String {
        format!("http://127.0.0.1:{}/", self.port)
    }
}

impl Drop for StaticServer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}

/// Serve `root` on `127.0.0.1` at a free port.
pub fn serve_dir(root: &Path) -> std::io::Result<StaticServer> {
    let root = std::fs::canonicalize(root)?;
    let listener = TcpListener::bind("127.0.0.1:0")?;
    listener.set_nonblocking(true)?;
    let port = listener.local_addr()?.port();
    let stop = Arc::new(AtomicBool::new(false));
    let (r, s) = (root.clone(), stop.clone());
    std::thread::Builder::new().name("static-server".into()).spawn(move || {
        while !s.load(Ordering::SeqCst) {
            match listener.accept() {
                Ok((stream, _)) => {
                    let r = r.clone();
                    let _ = std::thread::Builder::new().name("static-conn".into()).spawn(move || {
                        let _ = handle(stream, &r);
                    });
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => std::thread::sleep(Duration::from_millis(15)),
                Err(_) => std::thread::sleep(Duration::from_millis(50)),
            }
        }
    })?;
    Ok(StaticServer { port, root, stop })
}

fn content_type(p: &Path) -> &'static str {
    match p.extension().and_then(|e| e.to_str()).map(str::to_ascii_lowercase).as_deref() {
        Some("html" | "htm") => "text/html; charset=utf-8",
        Some("js" | "mjs") => "text/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("json" | "map") => "application/json",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("gif") => "image/gif",
        Some("webp") => "image/webp",
        Some("avif") => "image/avif",
        Some("ico") => "image/x-icon",
        Some("woff") => "font/woff",
        Some("woff2") => "font/woff2",
        Some("ttf") => "font/ttf",
        Some("otf") => "font/otf",
        Some("wasm") => "application/wasm",
        Some("txt") => "text/plain; charset=utf-8",
        Some("mp4") => "video/mp4",
        Some("webm") => "video/webm",
        _ => "application/octet-stream",
    }
}

fn percent_decode(s: &str) -> Option<String> {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        match b.get(i) {
            Some(b'%') => {
                let hex = s.get(i + 1..i + 3)?;
                out.push(u8::from_str_radix(hex, 16).ok()?);
                i += 3;
            }
            Some(c) => {
                out.push(*c);
                i += 1;
            }
            None => break,
        }
    }
    String::from_utf8(out).ok()
}

/// Map a request path to a file under `root`, or `None` when it is outside or missing.
pub fn resolve(root: &Path, url_path: &str) -> Option<PathBuf> {
    let path = url_path.split(['?', '#']).next().unwrap_or("/");
    let decoded = percent_decode(path)?;
    let mut rel = PathBuf::new();
    for c in Path::new(decoded.trim_start_matches('/')).components() {
        match c {
            Component::Normal(n) => rel.push(n),
            Component::CurDir => {}
            _ => return None,
        }
    }
    let mut candidate = root.join(&rel);
    if candidate.is_dir() {
        candidate = candidate.join("index.html");
    }
    // A static export may write a page as `about.html` (Next.js without trailing slashes).
    if !candidate.is_file() && rel.extension().is_none() {
        let page = root.join(&rel).with_extension("html");
        candidate = if !rel.as_os_str().is_empty() && page.is_file() { page } else { root.join("index.html") };
    }
    let real = std::fs::canonicalize(&candidate).ok()?;
    (real.starts_with(root) && real.is_file()).then_some(real)
}

fn handle(mut stream: TcpStream, root: &Path) -> std::io::Result<()> {
    stream.set_nonblocking(false)?;
    stream.set_read_timeout(Some(Duration::from_secs(5)))?;
    stream.set_write_timeout(Some(Duration::from_secs(20)))?;
    let mut reader = BufReader::new((&stream).take(16 * 1024));
    let mut line = String::new();
    reader.read_line(&mut line)?;
    // Drain the headers (bounded by `take`).
    let mut h = String::new();
    while reader.read_line(&mut h)? > 2 {
        h.clear();
    }
    let mut parts = line.split_whitespace();
    let (method, target) = (parts.next().unwrap_or_default(), parts.next().unwrap_or("/"));
    if method != "GET" && method != "HEAD" {
        return stream.write_all(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
    }
    match resolve(root, target).and_then(|p| std::fs::read(&p).ok().map(|b| (p, b))) {
        Some((p, body)) => {
            let head = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
                content_type(&p),
                body.len()
            );
            stream.write_all(head.as_bytes())?;
            if method == "GET" {
                stream.write_all(&body)?;
            }
            Ok(())
        }
        None => stream.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot found"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn get(port: u16, path: &str) -> String {
        let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
        s.write_all(format!("GET {path} HTTP/1.1\r\nHost: x\r\n\r\n").as_bytes()).unwrap();
        let mut out = String::new();
        s.read_to_string(&mut out).unwrap();
        out
    }

    #[test]
    fn serves_files_spa_fallback_and_refuses_escapes() {
        let dir = tempfile::tempdir().unwrap();
        let site = dir.path().join("dist");
        std::fs::create_dir_all(site.join("assets")).unwrap();
        std::fs::write(site.join("index.html"), "<h1>home</h1>").unwrap();
        std::fs::write(site.join("assets/app.js"), "console.log(1)").unwrap();
        std::fs::write(dir.path().join("secret.txt"), "nope").unwrap();
        let srv = serve_dir(&site).unwrap();
        assert!(get(srv.port, "/").contains("<h1>home</h1>"));
        let js = get(srv.port, "/assets/app.js?v=1");
        assert!(js.contains("text/javascript") && js.contains("console.log(1)"));
        assert!(get(srv.port, "/pricing").contains("<h1>home</h1>"), "client-side routes fall back to index.html");
        std::fs::write(site.join("about.html"), "<h1>about</h1>").unwrap();
        assert!(get(srv.port, "/about").contains("<h1>about</h1>") && get(srv.port, "/about/").contains("<h1>about</h1>"), "an exported page");
        assert!(get(srv.port, "/missing.png").starts_with("HTTP/1.1 404"));
        for bad in ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"] {
            assert!(!get(srv.port, bad).contains("nope"), "{bad}");
        }
        let url = srv.url();
        drop(srv);
        assert!(url.starts_with("http://127.0.0.1:"));
    }
}
