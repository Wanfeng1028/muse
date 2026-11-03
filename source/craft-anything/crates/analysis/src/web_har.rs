//! Historical network captures (HAR): requests, responses, timings, hosts and an API surface
//! grouped by path template, with privacy built in.
//!
//! What is never kept: cookie values, `Authorization`/`Proxy-Authorization`/API-key style header
//! values, URL user-info, credential-looking query values, and any body value — JSON bodies are
//! reduced to their outline (keys and types). Secrets the caller names are redacted wherever
//! they appear in kept text, in raw, percent-encoded and JSON-escaped spellings; a sensitive value
//! used as a JSON property name drops that property.

use craft_anything_formats::har::{self, HarEntry};
use craft_anything_formats::sourcemap::base64_decode;
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub(crate) const CREDENTIAL_HEADERS: &[&str] = &[
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
    "x-csrf-token",
    "x-xsrf-token",
    "x-amz-security-token",
    "x-goog-api-key",
    "x-session-id",
];

const CREDENTIAL_PARAMS: &[&str] = &[
    "token",
    "access_token",
    "id_token",
    "refresh_token",
    "auth",
    "authorization",
    "key",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "pwd",
    "session",
    "sessionid",
    "sid",
    "sig",
    "signature",
    "code",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-security-token",
];

#[derive(Debug, Clone, Default)]
pub struct HarOptions {
    pub hidden_values: Vec<String>,
    pub offset: usize,
    pub limit: usize,
    /// Only these entries (0-based), in full detail.
    pub record_numbers: Option<Vec<usize>>,
    pub max_entries: usize,
}

pub(crate) struct Redactor {
    /// Every spelling of every declared value, longest first.
    pub(crate) needles: Vec<String>,
    log: Vec<Value>,
}

fn percent_encode(s: &str) -> String {
    let mut out = String::new();
    for b in s.bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'~') {
            out.push(char::from(b));
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

impl Redactor {
    pub(crate) fn new(values: &[String]) -> Self {
        let mut needles: Vec<String> = Vec::new();
        for v in values.iter().filter(|v| !v.is_empty()) {
            let json_escaped = serde_json::to_string(v).ok().and_then(|q| q.get(1..q.len().saturating_sub(1)).map(String::from)).unwrap_or_default();
            for form in [v.clone(), percent_encode(v), percent_encode(v).to_ascii_lowercase(), json_escaped, v.replace(' ', "+")] {
                if !form.is_empty() && !needles.contains(&form) {
                    needles.push(form);
                }
            }
        }
        needles.sort_by_key(|n| std::cmp::Reverse(n.len()));
        Redactor { needles, log: Vec::new() }
    }

    fn contains(&self, s: &str) -> bool {
        self.needles.iter().any(|n| s.contains(n.as_str()))
    }

    /// Replace declared values in kept text.
    fn text(&mut self, pointer: &str, s: &str) -> String {
        if !self.contains(s) {
            return s.to_string();
        }
        let mut out = s.to_string();
        for n in &self.needles {
            out = out.replace(n.as_str(), "[redacted]");
        }
        self.log.push(json!({"pointer": pointer, "reason": "secret-value"}));
        out
    }
}

/// Split a URL, dropping user-info. Returns (scheme, host, path, query pairs, had_userinfo).
pub(crate) fn split_url(url: &str) -> (String, String, String, Vec<(String, String)>, bool) {
    let (scheme, rest) = url.split_once("://").unwrap_or(("", url));
    let rest = rest.split('#').next().unwrap_or(rest);
    let (authority, path_q) = match rest.find(['/', '?', '#']) {
        Some(i) => (rest.get(..i).unwrap_or(""), rest.get(i..).unwrap_or("/")),
        None => (rest, "/"),
    };
    let (userinfo, host) = match authority.rsplit_once('@') {
        Some((_, h)) => (true, h),
        None => (false, authority),
    };
    let (path, query) = path_q.split_once('?').unwrap_or((path_q, ""));
    let pairs = query
        .split('&')
        .filter(|p| !p.is_empty())
        .take(200)
        .map(|p| {
            let (k, v) = p.split_once('=').unwrap_or((p, ""));
            (k.to_string(), v.to_string())
        })
        .collect();
    (scheme.to_ascii_lowercase(), host.to_ascii_lowercase(), if path.is_empty() { "/".into() } else { path.to_string() }, pairs, userinfo)
}

pub(crate) fn is_credential_param(k: &str) -> bool {
    let l = k.to_ascii_lowercase();
    CREDENTIAL_PARAMS.contains(&l.as_str()) || l.ends_with("_token") || l.ends_with("token") || l.contains("password") || l.contains("secret")
}

/// Rebuild a safe URL: no user-info, credential query values replaced.
fn safe_url(url: &str, pointer: &str, red: &mut Redactor) -> (String, Vec<String>) {
    let (scheme, host, path, pairs, userinfo) = split_url(url);
    if userinfo {
        red.log.push(json!({"pointer": pointer, "reason": "url-userinfo"}));
    }
    let mut q = Vec::new();
    let mut names = Vec::new();
    for (k, v) in pairs {
        names.push(k.clone());
        if is_credential_param(&k) && !v.is_empty() {
            red.log.push(json!({"pointer": pointer, "reason": "credential-parameter", "parameter": k}));
            q.push(format!("{k}=[redacted]"));
        } else {
            q.push(if v.is_empty() { k } else { format!("{k}={v}") });
        }
    }
    let base = if scheme.is_empty() { format!("{host}{path}") } else { format!("{scheme}://{host}{path}") };
    let full = if q.is_empty() { base } else { format!("{base}?{}", q.join("&")) };
    (red.text(pointer, &full), names)
}

/// Path template: numeric → {n}, uuid → {uuid}, long hex → {hex}, ISO date → {date}.
pub fn path_template(path: &str) -> String {
    path.split('/')
        .map(|seg| {
            let s = seg;
            if !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()) {
                "{n}".to_string()
            } else if is_uuid(s) {
                "{uuid}".to_string()
            } else if s.len() >= 32 && s.bytes().all(|b| b.is_ascii_hexdigit()) {
                "{hex}".to_string()
            } else if is_iso_date(s) {
                "{date}".to_string()
            } else {
                s.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("/")
}

pub(crate) fn is_uuid(s: &str) -> bool {
    let parts: Vec<&str> = s.split('-').collect();
    parts.len() == 5 && parts.iter().zip([8, 4, 4, 4, 12]).all(|(p, n)| p.len() == n && p.bytes().all(|b| b.is_ascii_hexdigit()))
}

fn is_iso_date(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() >= 10
        && b.get(4) == Some(&b'-')
        && b.get(7) == Some(&b'-')
        && b.iter().take(4).all(u8::is_ascii_digit)
        && b.get(5..7).is_some_and(|m| m.iter().all(u8::is_ascii_digit))
}

/// The outline of a JSON value: types only, never values.
pub fn json_outline(v: &Value, depth: usize, red: &mut OutlineRedactions<'_>, pointer: &str) -> Value {
    if depth > 8 {
        return json!("…");
    }
    match v {
        Value::Null => json!("null"),
        Value::Bool(_) => json!("boolean"),
        Value::Number(n) => json!(if n.is_i64() || n.is_u64() { "integer" } else { "number" }),
        Value::String(_) => json!("string"),
        Value::Array(a) => {
            let mut items: Option<Value> = None;
            for (i, x) in a.iter().take(20).enumerate() {
                let s = json_outline(x, depth + 1, red, &format!("{pointer}/{i}"));
                items = Some(match items {
                    None => s,
                    Some(prev) => merge_outlines(prev, s),
                });
            }
            json!({"type": "array", "items": items.unwrap_or(json!("unknown")), "length": a.len()})
        }
        Value::Object(o) => {
            let mut props = Map::new();
            for (k, x) in o.iter().take(200) {
                if red.names_hit(k) {
                    red.log.push(json!({"pointer": pointer, "reason": "secret-value", "scope": "property-name"}));
                    continue;
                }
                let child = format!("{pointer}/{}", k.replace('~', "~0").replace('/', "~1"));
                props.insert(k.clone(), json_outline(x, depth + 1, red, &child));
            }
            json!({"type": "object", "properties": props})
        }
    }
}

/// Redaction context for outlines (only property names can leak).
pub struct OutlineRedactions<'r> {
    needles: &'r [String],
    pub log: Vec<Value>,
}

impl OutlineRedactions<'_> {
    fn names_hit(&self, k: &str) -> bool {
        self.needles.iter().any(|n| k.contains(n.as_str()))
    }
}

fn merge_outlines(a: Value, b: Value) -> Value {
    if a == b {
        return a;
    }
    match (a, b) {
        (Value::Object(mut x), Value::Object(y)) if x.get("type") == Some(&json!("object")) && y.get("type") == Some(&json!("object")) => {
            let mut props = x.remove("properties").and_then(|p| if let Value::Object(m) = p { Some(m) } else { None }).unwrap_or_default();
            if let Some(Value::Object(yp)) = y.get("properties") {
                for (k, v) in yp {
                    let merged = match props.remove(k) {
                        Some(old) => merge_outlines(old, v.clone()),
                        None => v.clone(),
                    };
                    props.insert(k.clone(), merged);
                }
            }
            json!({"type": "object", "properties": props})
        }
        (Value::Object(x), other) | (other, Value::Object(x)) if x.contains_key("one_of") => {
            let mut list = x.get("one_of").and_then(Value::as_array).cloned().unwrap_or_default();
            if !list.contains(&other) && list.len() < 6 {
                list.push(other);
            }
            json!({"one_of": list})
        }
        (a, b) => json!({"one_of": [a, b]}),
    }
}

fn body_outline(
    mime: Option<&str>,
    text: Option<&str>,
    encoding: Option<&str>,
    params: &[(String, Option<String>)],
    red: &mut Redactor,
    pointer: &str,
) -> Value {
    let mime_l = mime.unwrap_or("").to_ascii_lowercase();
    let decoded: Option<String> = match (text, encoding) {
        (Some(t), Some("base64")) => base64_decode(t).map(|b| String::from_utf8_lossy(&b).into_owned()),
        (Some(t), _) => Some(t.to_string()),
        _ => None,
    };
    let bytes = decoded.as_ref().map_or(0, String::len);
    let json_like = mime_l.contains("json") || decoded.as_deref().is_some_and(|t| t.trim_start().starts_with('{') || t.trim_start().starts_with('['));
    if json_like && let Some(v) = decoded.as_deref().and_then(|t| serde_json::from_str::<Value>(t).ok()) {
        let mut sr = OutlineRedactions { needles: &red.needles, log: Vec::new() };
        let outline = json_outline(&v, 0, &mut sr, pointer);
        red.log.extend(sr.log);
        return json!({"kind": "json", "bytes": bytes, "outline": outline});
    }
    if mime_l.contains("x-www-form-urlencoded") {
        let names: Vec<String> = if params.is_empty() {
            decoded.as_deref().unwrap_or("").split('&').filter_map(|p| p.split('=').next()).filter(|k| !k.is_empty()).map(String::from).take(200).collect()
        } else {
            params.iter().map(|(k, _)| k.clone()).take(200).collect()
        };
        let names: Vec<String> = names.into_iter().filter(|n| !red.contains(n)).collect();
        return json!({"kind": "form", "bytes": bytes, "fields": names});
    }
    if mime_l.contains("multipart") {
        return json!({"kind": "multipart", "bytes": bytes, "fields": params.iter().map(|(k, _)| k.clone()).filter(|n| !red.contains(n)).take(200).collect::<Vec<_>>()});
    }
    if decoded.is_none() {
        return Value::Null;
    }
    json!({"kind": if mime_l.is_empty() { "unknown".to_string() } else { mime_l }, "bytes": bytes})
}

fn headers_view(h: &[(String, String)], pointer: &str, red: &mut Redactor) -> Vec<Value> {
    h.iter()
        .take(200)
        .enumerate()
        .map(|(i, (n, v))| {
            let l = n.to_ascii_lowercase();
            let p = format!("{pointer}/{i}/value");
            if CREDENTIAL_HEADERS.contains(&l.as_str()) {
                red.log.push(json!({"pointer": p, "reason": "auth-header"}));
                json!({"name": n, "value": null, "redacted": "auth-header"})
            } else if matches!(l.as_str(), "referer" | "origin" | "location") {
                let (u, _) = safe_url(v, &p, red);
                json!({"name": n, "value": u})
            } else {
                json!({"name": n, "value": red.text(&p, v)})
            }
        })
        .collect()
}

fn entry_view(e: &HarEntry, red: &mut Redactor) -> Value {
    let base = format!("/log/entries/{}", e.ordinal);
    let (url, query_names) = safe_url(&e.request.url, &format!("{base}/request/url"), red);
    let (_, host, path, _, _) = split_url(&e.request.url);
    let req_body =
        e.request.post.as_ref().map(|p| body_outline(p.mime.as_deref(), p.text.as_deref(), None, &p.params, red, &format!("{base}/request/postData")));
    let res_body =
        body_outline(e.response.mime.as_deref(), e.response.text.as_deref(), e.response.encoding.as_deref(), &[], red, &format!("{base}/response/content"));
    let redirect = e.response.redirect_url.as_deref().map(|u| safe_url(u, &format!("{base}/response/redirectURL"), red).0);
    if !e.request.cookie_names.is_empty() || !e.response.cookie_names.is_empty() {
        red.log.push(json!({"pointer": format!("{base}/cookies"), "reason": "auth-header"}));
    }
    json!({
        "ordinal": e.ordinal,
        "started": e.started,
        "time_ms": e.time_ms,
        "resource_type": e.resource_type,
        "method": e.request.method,
        "url": url,
        "host": host,
        "path_template": path_template(&path),
        "query_parameters": query_names,
        "http_version": e.request.http_version,
        "status": e.response.status,
        "status_text": e.response.status_text,
        "request_headers": headers_view(&e.request.headers, &format!("{base}/request/headers"), red),
        "response_headers": headers_view(&e.response.headers, &format!("{base}/response/headers"), red),
        "request_cookie_names": e.request.cookie_names.iter().filter(|n| !red.contains(n)).collect::<Vec<_>>(),
        "response_cookie_names": e.response.cookie_names.iter().filter(|n| !red.contains(n)).collect::<Vec<_>>(),
        "request_body": req_body,
        "response_body": res_body,
        "response_mime": e.response.mime,
        "response_bytes": e.response.content_size,
        "redirect_url": redirect,
        "timings": e.timings.iter().map(|(k, v)| (k.clone(), json!(v))).collect::<Map<String, Value>>(),
    })
}

/// Inspect a HAR capture.
pub fn inspect_har(bytes: &[u8], opts: &HarOptions) -> Result<Value, String> {
    let har = har::parse(bytes, opts.max_entries.max(1)).map_err(|e| e.to_string())?;
    let mut red = Redactor::new(&opts.hidden_values);
    let mut methods: BTreeMap<String, usize> = BTreeMap::new();
    let mut statuses: BTreeMap<String, usize> = BTreeMap::new();
    let mut hosts: BTreeMap<String, usize> = BTreeMap::new();
    let mut mimes: BTreeMap<String, usize> = BTreeMap::new();
    let mut total_bytes: i64 = 0;
    let mut first: Option<String> = None;
    let mut last: Option<String> = None;
    let mut slowest: Vec<(f64, usize)> = Vec::new();
    let mut surface: BTreeMap<String, Value> = BTreeMap::new();
    let mut views = Vec::new();
    for e in &har.entries {
        let view = entry_view(e, &mut red);
        *methods.entry(e.request.method.to_ascii_uppercase()).or_default() += 1;
        *statuses.entry(format!("{}xx", e.response.status / 100)).or_default() += 1;
        let host = view["host"].as_str().unwrap_or("").to_string();
        *hosts.entry(red.text("/hosts", &host)).or_default() += 1;
        let mime = e.response.mime.as_deref().unwrap_or("").split(';').next().unwrap_or("").trim().to_string();
        *mimes.entry(mime.clone()).or_default() += 1;
        total_bytes = total_bytes.saturating_add(e.response.body_size.unwrap_or(0).max(e.response.content_size.unwrap_or(0)).max(0));
        if let Some(s) = &e.started {
            if first.as_ref().is_none_or(|f| s < f) {
                first = Some(s.clone());
            }
            if last.as_ref().is_none_or(|l| s > l) {
                last = Some(s.clone());
            }
        }
        if let Some(t) = e.time_ms {
            slowest.push((t, e.ordinal));
        }
        // API surface.
        let (scheme, _, _, _, _) = split_url(&e.request.url);
        let key = format!("{} {}://{}{}", e.request.method.to_ascii_uppercase(), scheme, host, view["path_template"].as_str().unwrap_or(""));
        let key = red.text("/api_surface", &key);
        let g = surface.entry(key.clone()).or_insert_with(|| json!({"operation": key, "count": 0, "statuses": [], "query_parameters": [], "request_outline": null, "response_outline": null, "response_mimes": []}));
        if let Some(o) = g.as_object_mut() {
            let c = o.get("count").and_then(Value::as_u64).unwrap_or(0) + 1;
            o.insert("count".into(), json!(c));
            add_unique(o, "statuses", json!(e.response.status));
            for q in view["query_parameters"].as_array().into_iter().flatten() {
                add_unique(o, "query_parameters", q.clone());
            }
            add_unique(o, "response_mimes", json!(mime));
            for (field, src) in [("request_outline", &view["request_body"]), ("response_outline", &view["response_body"])] {
                if let Some(outline) = src.get("outline") {
                    let merged = match o.get(field).cloned() {
                        Some(Value::Null) | None => outline.clone(),
                        Some(prev) => merge_outlines(prev, outline.clone()),
                    };
                    o.insert(field.into(), merged);
                }
            }
        }
        views.push(view);
    }
    slowest.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    let slowest: Vec<Value> = slowest
        .iter()
        .take(5)
        .filter_map(|(t, i)| views.get(*i).map(|v| json!({"ordinal": i, "time_ms": t, "method": v["method"], "url": v["url"]})))
        .collect();
    let selected: Vec<Value> = match &opts.record_numbers {
        Some(ords) => views.iter().filter(|v| v["ordinal"].as_u64().is_some_and(|o| ords.contains(&(o as usize)))).cloned().collect(),
        None => views.iter().skip(opts.offset).take(opts.limit.max(1)).cloned().collect(),
    };
    let ops: Vec<Value> = surface.into_values().collect();
    let mut redactions = red.log;
    redactions.truncate(5000);
    Ok(json!({
        "format": "har",
        "har_version": har.version,
        "creator": har.creator,
        "pages": har.pages,
        "summary": {
            "entries": har.entries.len(),
            "declared_entries": har.declared_entries,
            "methods": methods, "statuses": statuses, "hosts": hosts, "response_mimes": mimes,
            "response_body_bytes": total_bytes, "first_request": first, "last_request": last, "slowest": slowest,
        },
        "api_surface": ops,
        "entries": selected,
        "entries_total": views.len(),
        "redactions": redactions,
        "sensitive_value_declarations": opts.hidden_values.len(),
        "truncated": har.truncated,
    }))
}

fn add_unique(o: &mut Map<String, Value>, key: &str, v: Value) {
    if let Some(Value::Array(a)) = o.get_mut(key)
        && !a.contains(&v)
        && a.len() < 64
    {
        a.push(v);
    }
}

/// Every set of distinct values seen for a key in a JSON tree — used by tests to prove nothing leaks.
pub fn all_strings(v: &Value, out: &mut BTreeSet<String>) {
    match v {
        Value::String(s) => {
            out.insert(s.clone());
        }
        Value::Array(a) => a.iter().for_each(|x| all_strings(x, out)),
        Value::Object(o) => o.iter().for_each(|(k, x)| {
            out.insert(k.clone());
            all_strings(x, out);
        }),
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_url_authority_cases() {
        let mut failures = Vec::new();
        for (row, url, host, path, userinfo) in [
            ("at in path", "https://example.test/@profile", "example.test", "/@profile", false),
            ("at in file name", "https://cdn.example.test/icon@2x.png", "cdn.example.test", "/icon@2x.png", false),
            ("at in query", "https://example.test/?q=a@b", "example.test", "/", false),
            ("at in fragment", "https://example.test/#a@b", "example.test", "/", false),
            ("user-info and at in path", "https://user:pw@example.test/@x", "example.test", "/@x", true),
            ("IPv6 and port", "https://[::1]:8080/@x", "[::1]:8080", "/@x", false),
            ("query with slash, no path", "https://example.test?q=a/b@c", "example.test", "/", false),
            ("port and at in path", "http://example.test:8080/a@b", "example.test:8080", "/a@b", false),
            ("fragment, no path", "https://example.test#a@b", "example.test", "/", false),
            ("user-info only", "https://user@example.test/p", "example.test", "/p", true),
            ("plain", "https://example.test/path", "example.test", "/path", false),
            ("percent-encoded at in user-info", "https://u%40x:pw@example.test/", "example.test", "/", true),
            ("two at signs in user-info", "https://a@b@EXAMPLE.test/p", "example.test", "/p", true),
        ] {
            let (_, actual_host, actual_path, _, actual_userinfo) = split_url(url);
            let actual = (actual_host.as_str(), actual_path.as_str(), actual_userinfo);
            let expected = (host, path, userinfo);
            if actual != expected {
                failures.push(format!("{row}: expected {expected:?}, got {actual:?}"));
            }
        }
        assert!(failures.is_empty(), "{}", failures.join("\n"));
    }

    const HAR: &str = r#"{"log":{"version":"1.2","creator":{"name":"t","version":"1"},"entries":[
      {"startedDateTime":"2026-01-01T00:00:00Z","time":120,
       "request":{"method":"GET","url":"https://bob:hunter2@api.example.test/v1/users/42?access_token=SECRET123&page=2","headers":[{"name":"Authorization","value":"Bearer SECRET123"},{"name":"Accept","value":"application/json"},{"name":"X-Trace","value":"trace-hunter2"}],"cookies":[{"name":"sid","value":"COOKIEVAL"}]},
       "response":{"status":200,"headers":[{"name":"Set-Cookie","value":"sid=COOKIEVAL"}],"content":{"size":40,"mimeType":"application/json","text":"{\"id\":42,\"name\":\"Ann\",\"tags\":[\"a\"],\"hunter2\":true}"}},"timings":{"wait":100}},
      {"startedDateTime":"2026-01-01T00:00:01Z","time":30,
       "request":{"method":"GET","url":"https://api.example.test/v1/users/7","headers":[]},
       "response":{"status":404,"headers":[],"content":{"size":2,"mimeType":"application/json","text":"eyJlcnJvciI6Im5vIn0=","encoding":"base64"}},"timings":{}},
      {"startedDateTime":"2026-01-01T00:00:02Z","time":5,
       "request":{"method":"POST","url":"https://api.example.test/v1/login","headers":[],"postData":{"mimeType":"application/x-www-form-urlencoded","text":"user=ann&password=hunter2"}},
       "response":{"status":302,"headers":[{"name":"Location","value":"https://u:p@api.example.test/home"}],"content":{"size":0,"mimeType":""},"redirectURL":"https://api.example.test/home?token=abc"},"timings":{}}
    ]}}"#;

    fn run(sensitive: &[&str]) -> Value {
        inspect_har(
            HAR.as_bytes(),
            &HarOptions { hidden_values: sensitive.iter().map(|s| s.to_string()).collect(), limit: 50, max_entries: 1000, ..Default::default() },
        )
        .unwrap()
    }

    #[test]
    fn nothing_secret_survives() {
        let v = run(&["hunter2"]);
        let mut all = BTreeSet::new();
        all_strings(&v, &mut all);
        for s in &all {
            for secret in ["SECRET123", "COOKIEVAL", "hunter2", "bob:", "u:p@", "Ann"] {
                assert!(!s.contains(secret), "{secret} leaked in {s:?}");
            }
        }
        assert_eq!(v["summary"]["entries"], 3);
        assert_eq!(v["summary"]["methods"]["GET"], 2);
        assert_eq!(v["entries"][0]["url"], "https://api.example.test/v1/users/42?access_token=[redacted]&page=2");
        assert_eq!(v["entries"][0]["request_headers"][0]["value"], Value::Null);
        assert_eq!(v["entries"][0]["request_headers"][2]["value"], "trace-[redacted]");
        assert_eq!(v["entries"][2]["request_body"]["fields"], json!(["user", "password"]));
        let outline = &v["entries"][0]["response_body"]["outline"];
        assert_eq!(outline["properties"]["id"], "integer");
        assert!(outline["properties"].get("hunter2").is_none(), "sensitive property name dropped");
        assert_eq!(v["entries"][1]["response_body"]["outline"]["properties"]["error"], "string");
    }

    #[test]
    fn api_surface_groups_by_template() {
        let v = run(&[]);
        let ops = v["api_surface"].as_array().unwrap();
        let users = ops.iter().find(|o| o["operation"] == "GET https://api.example.test/v1/users/{n}").unwrap();
        assert_eq!(users["count"], 2);
        assert_eq!(users["statuses"], json!([200, 404]));
        assert_eq!(path_template("/a/123e4567-e89b-12d3-a456-426614174000/2026-01-02/deadbeefdeadbeefdeadbeefdeadbeef"), "/a/{uuid}/{date}/{hex}");
    }

    #[test]
    fn encoded_forms_are_redacted() {
        let r = Redactor::new(&["a b/c\"".into()]);
        assert!(r.needles.iter().any(|n| n == "a%20b%2Fc%22"));
        assert!(r.needles.iter().any(|n| n == "a b/c\\\""));
        let mut r = r;
        assert_eq!(r.text("/x", "q=a%20b%2Fc%22"), "q=[redacted]");
        assert!(inspect_har(b"not json", &HarOptions::default()).is_err());
    }
}
