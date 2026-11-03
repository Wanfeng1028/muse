//! Web runtime tools over loopback CDP: precise JavaScript coverage, DOM event listeners, and the
//! live-page module-import graph. All attach to a browser (or launch a located Chromium) and bound
//! every exchange.

use super::browser_tools::{self, CaptureFlags};
use super::native_common::spec;
use super::web_common::{self, Browser};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::cdp::{self, CdpClient, Deadline, PAGE_MAX_MESSAGE};
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, EvidenceBuilder, Limitation, Location, Subject, ToolError};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "web_coverage_measure",
            "Measure which code ran",
            "Turn on V8 precise coverage on one page, observe for a window, then report per-script which functions and block ranges ran (UTF-16 offsets, with call counts when available). Changes the page's profiler state and discards coverage data on stop, so it is not idempotent.",
            "See which parts of a web page's code actually run.",
            Toolset::Browser,
            Effects::MUTATES_SESSION
                .union(Effects::MUTATES_TARGET)
                .union(Effects::ACCESSES_NETWORK)
                .union(Effects::MAY_DISCARD_DATA)
                .union(Effects::LAUNCHES_PROCESS),
            Requires::Nothing,
            schema_of::<ExecutionParams>,
            web_coverage_measure,
        ),
        spec(
            "web_listeners_list",
            "List a node's event listeners",
            "Resolve a CSS selector on one page and list the DOM event listeners registered on that element: event type, capture/passive/once flags and the handler's script location (URL, line, column). No handler source is read.",
            "See what events an element on a web page reacts to.",
            Toolset::Browser,
            Effects::NETWORK_EVIDENCE.union(Effects::LAUNCHES_PROCESS),
            Requires::Nothing,
            schema_of::<ListenersParams>,
            web_listeners_list,
        ),
        spec(
            "web_modules_trace",
            "Map a page's module graph",
            "Fetch the scripts a live page has loaded and build their ES module import graph: each script and the specifiers it imports, resolved to URLs where relative, with bare specifiers reported as needing an import map. Static reading of the live sources; nothing is executed.",
            "Map which script imports which on a running web page.",
            Toolset::Browser,
            Effects::NETWORK_EVIDENCE.union(Effects::LAUNCHES_PROCESS),
            Requires::Nothing,
            schema_of::<ModuleImportsParams>,
            web_modules_trace,
        ),
    ]
}

fn d_timeout() -> u64 {
    60
}

fn connect(
    ctx: &Ctx<'_>,
    endpoint: Option<&str>,
    launch: bool,
    headless: bool,
    no_sandbox: bool,
    target_id: Option<&str>,
    dl: &Deadline,
) -> Result<(Browser, CdpClient, String), ToolError> {
    let browser = browser_tools::resolve_browser(ctx, endpoint, launch, headless, no_sandbox, dl)?;
    let targets = cdp::json_list(&browser.endpoint, dl)?;
    let target = web_common::pick_target(&targets, target_id, Some("page"))?;
    let url = web_common::sanitize_url(target.get("url").and_then(Value::as_str).unwrap_or_default());
    let client = web_common::connect_target(&browser, target, PAGE_MAX_MESSAGE, dl)?;
    Ok((browser, client, url))
}

/// Build scriptId → sanitized url map from scriptParsed events gathered during a window.
fn script_urls(events: &[cdp::CdpEvent]) -> std::collections::BTreeMap<String, String> {
    let mut map = std::collections::BTreeMap::new();
    for ev in events.iter().filter(|e| e.method == "Debugger.scriptParsed") {
        if let (Some(id), Some(url)) = (ev.params.get("scriptId").and_then(Value::as_str), ev.params.get("url").and_then(Value::as_str)) {
            if url.is_empty() {
                continue;
            }
            map.insert(id.to_string(), web_common::sanitize_url(url));
        }
    }
    map
}

// ---------------------------------------------------------------------------------------------
// web_coverage_measure

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExecutionParams {
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    #[serde(default)]
    pub launch: bool,
    #[serde(default = "yes")]
    pub headless: bool,
    #[serde(default)]
    pub no_sandbox: bool,
    #[serde(default)]
    pub target_id: Option<String>,
    /// How long to let code run while measuring (milliseconds, default 10s).
    #[serde(default = "d_exec_window")]
    pub watch_ms: u64,
    /// First script of the page in the result.
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_limit")]
    pub limit: usize,
    #[serde(default = "d_exec_timeout")]
    pub timeout_secs: u64,
}

fn yes() -> bool {
    true
}
fn d_exec_window() -> u64 {
    10_000
}
fn d_exec_timeout() -> u64 {
    120
}
fn d_limit() -> usize {
    500
}

fn web_coverage_measure(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExecutionParams = parse_params(params)?;
    // A page shows at least one script (#331).
    let limit = p.limit.max(1);
    let dl = deadline(ctx, p.timeout_secs)?;
    let (browser, mut client, page_url) = connect(ctx, p.cdp_endpoint.as_deref(), p.launch, p.headless, p.no_sandbox, p.target_id.as_deref(), &dl)?;
    let result = run_coverage(&mut client, &page_url, p.watch_ms, p.offset, limit, ctx, &dl);
    browser_tools::cleanup(&mut client, &dl);
    let (result, total, covered) = result?;
    let summary = format!("Coverage on {page_url}: {covered} of {total} script(s) executed code during the window.");
    let ev = EvidenceBuilder::new(
        "web_coverage_measure",
        Subject { kind: "website".into(), sha256: None, name: Some(page_url.clone()) },
        browser_tools::browser_env(ctx.session.clean_room(), &browser),
    )
    .params(json!({"endpoint": browser.endpoint.origin, "watch_ms": p.watch_ms, "offset": p.offset, "limit": limit}))
    .result(result)
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OurRun)
    .limitation(Limitation::new(
        "window_only",
        "Coverage reflects only what ran during the observation window; code triggered by later interaction is not counted.",
    ))
    .limitation(Limitation::new(
        "discarded",
        "Precise coverage is reset on read and stopped afterwards, so the measurement is not repeatable from this record.",
    ))
    .coverage(Coverage {
        status: CoverageStatus::Partial,
        examined: Some(total.saturating_sub(p.offset).min(limit) as u64),
        total: Some(total as u64),
        next_offset: None,
    })
    .location(Location::new("url", page_url))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn run_coverage(
    client: &mut CdpClient,
    page_url: &str,
    watch_ms: u64,
    offset: usize,
    limit: usize,
    ctx: &Ctx<'_>,
    dl: &Deadline,
) -> Result<(Value, usize, usize), ToolError> {
    let _ = client.call("Debugger.enable", json!({}), None, dl)?;
    let _ = client.call("Profiler.enable", json!({}), None, dl)?;
    client.call("Profiler.startPreciseCoverage", json!({"callCount": true, "detailed": true}), None, dl)?;
    let window = browser_tools::window_deadline(ctx, watch_ms, dl);
    client.pump_until(&window)?;
    let events = client.take_events();
    let urls = script_urls(&events);
    let taken = client.call("Profiler.takePreciseCoverage", json!({}), None, dl)?;
    let _ = client.call("Profiler.stopPreciseCoverage", json!({}), None, dl);
    let mut scripts: Vec<Value> = Vec::new();
    let mut covered = 0usize;
    for s in taken.get("result").and_then(Value::as_array).into_iter().flatten() {
        let sid = s.get("scriptId").and_then(Value::as_str).unwrap_or_default();
        let url =
            s.get("url").and_then(Value::as_str).filter(|u| !u.is_empty()).map(web_common::sanitize_url).or_else(|| urls.get(sid).cloned()).unwrap_or_default();
        if url.is_empty() {
            continue;
        }
        let mut functions = 0u64;
        let mut functions_run = 0u64;
        let mut ranges = 0u64;
        let mut block_coverage = false;
        for f in s.get("functions").and_then(Value::as_array).into_iter().flatten() {
            functions += 1;
            if f.get("isBlockCoverage").and_then(Value::as_bool) == Some(true) {
                block_coverage = true;
            }
            let mut any = false;
            for r in f.get("ranges").and_then(Value::as_array).into_iter().flatten() {
                ranges += 1;
                if r.get("count").and_then(Value::as_u64).unwrap_or(0) > 0 {
                    any = true;
                }
            }
            if any {
                functions_run += 1;
            }
        }
        if functions_run > 0 {
            covered += 1;
        }
        scripts.push(json!({"url": url, "functions": functions, "functions_executed": functions_run, "ranges": ranges, "is_block_coverage": block_coverage}));
    }
    scripts.sort_by(|a, b| a["url"].as_str().unwrap_or("").cmp(b["url"].as_str().unwrap_or("")));
    let total = scripts.len();
    let page: Vec<Value> = scripts.into_iter().skip(offset).take(limit).collect();
    Ok((json!({"origin": page_url, "scripts": page, "scripts_total": total, "scripts_with_execution": covered}), total, covered))
}

// ---------------------------------------------------------------------------------------------
// web_listeners_list

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListenersParams {
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    #[serde(default)]
    pub launch: bool,
    #[serde(default = "yes")]
    pub headless: bool,
    #[serde(default)]
    pub no_sandbox: bool,
    #[serde(default)]
    pub target_id: Option<String>,
    /// A CSS selector identifying the element.
    pub selector: String,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn web_listeners_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListenersParams = parse_params(params)?;
    if p.selector.trim().is_empty() || p.selector.len() > 2048 {
        return Err(ToolError::invalid("selector must be 1..=2048 characters"));
    }
    let dl = deadline(ctx, p.timeout_secs)?;
    let (browser, mut client, page_url) = connect(ctx, p.cdp_endpoint.as_deref(), p.launch, p.headless, p.no_sandbox, p.target_id.as_deref(), &dl)?;
    let listeners = gather_listeners(&mut client, &p.selector, &dl);
    browser_tools::cleanup(&mut client, &dl);
    let listeners = listeners?;
    let summary = format!("Element {:?} on {page_url} has {} event listener(s).", p.selector, listeners.len());
    let ev = EvidenceBuilder::new(
        "web_listeners_list",
        Subject { kind: "website".into(), sha256: None, name: Some(page_url.clone()) },
        browser_tools::browser_env(ctx.session.clean_room(), &browser),
    )
    .params(json!({"endpoint": browser.endpoint.origin, "selector": p.selector}))
    .result(json!({"origin": page_url, "selector": p.selector, "listeners": listeners}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::EarlierRecord)
    .limitation(Limitation::new("handler_not_read", "Only the listener's type, flags and script location are kept; the handler source is not read."))
    .coverage(Coverage::complete(listeners.len() as u64))
    .location(Location::new("url", page_url))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn gather_listeners(client: &mut CdpClient, selector: &str, dl: &Deadline) -> Result<Vec<Value>, ToolError> {
    let _ = client.call("DOM.enable", json!({}), None, dl);
    let _ = client.call("Debugger.enable", json!({}), None, dl);
    let events = client.take_events();
    let urls = script_urls(&events);
    let node = browser_tools::query_node(client, selector, dl)?;
    let resolved = client.call("DOM.resolveNode", json!({"nodeId": node}), None, dl)?;
    let object_id = resolved
        .pointer("/object/objectId")
        .and_then(Value::as_str)
        .ok_or_else(|| ToolError::new(craft_anything_evidence::ErrorCode::ProgramFailed, "could not resolve the element"))?;
    let got = client.call("DOMDebugger.getEventListeners", json!({"objectId": object_id, "depth": 1}), None, dl)?;
    let mut out = Vec::new();
    for l in got.get("listeners").and_then(Value::as_array).into_iter().flatten().take(2000) {
        let sid = l.get("scriptId").and_then(Value::as_str).unwrap_or_default();
        out.push(json!({
            "type": l.get("type").and_then(Value::as_str).unwrap_or_default(),
            "use_capture": l.get("useCapture").and_then(Value::as_bool).unwrap_or(false),
            "passive": l.get("passive").and_then(Value::as_bool).unwrap_or(false),
            "once": l.get("once").and_then(Value::as_bool).unwrap_or(false),
            "script_url": urls.get(sid).cloned().unwrap_or_default(),
            "line": l.get("lineNumber").and_then(Value::as_u64),
            "column": l.get("columnNumber").and_then(Value::as_u64),
        }));
    }
    Ok(out)
}

// ---------------------------------------------------------------------------------------------
// web_modules_trace

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ModuleImportsParams {
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    #[serde(default)]
    pub launch: bool,
    #[serde(default = "yes")]
    pub headless: bool,
    #[serde(default)]
    pub no_sandbox: bool,
    #[serde(default)]
    pub target_id: Option<String>,
    #[serde(default = "d_window")]
    pub watch_ms: u64,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_limit")]
    pub limit: usize,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn d_window() -> u64 {
    500
}

fn web_modules_trace(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ModuleImportsParams = parse_params(params)?;
    let limit = p.limit.max(1);
    let dl = deadline(ctx, p.timeout_secs)?;
    let (browser, mut client, page_url) = connect(ctx, p.cdp_endpoint.as_deref(), p.launch, p.headless, p.no_sandbox, p.target_id.as_deref(), &dl)?;
    let flags = CaptureFlags { script_sources: true, ..CaptureFlags::default() };
    let mut secrets = web_common::Secrets::new(&[]);
    let cap = browser_tools::capture_page(&mut client, &page_url, flags, p.watch_ms, &mut secrets, ctx, &dl);
    browser_tools::cleanup(&mut client, &dl);
    let cap = cap?;

    let limits = craft_anything_js::Limits::default();
    let mut nodes: Vec<Value> = Vec::new();
    let mut edges: Vec<Value> = Vec::new();
    let mut unresolved: Vec<Value> = Vec::new();
    for s in &cap.scripts {
        ctx.cancel.check()?;
        let Some(text) = &s.text else { continue };
        let a = craft_anything_js::analyze(&s.url, text, &limits);
        let san = web_common::sanitize_url(&s.url);
        let mut imports = 0u64;
        for imp in &a.facts.imports {
            if !matches!(imp.kind.as_str(), "import" | "dynamic-import" | "re-export" | "modulepreload") {
                continue;
            }
            if !imp.literal {
                unresolved.push(json!({"from": san.clone(), "specifier": imp.specifier.clone(), "reason": "non-literal specifier"}));
                continue;
            }
            imports += 1;
            match resolve_specifier(&s.url, &imp.specifier) {
                Some(to) => edges.push(json!({"from": san.clone(), "to": web_common::sanitize_url(&to), "specifier": imp.specifier, "kind": imp.kind})),
                None => unresolved.push(json!({"from": san.clone(), "specifier": imp.specifier.clone(), "reason": "bare specifier needs an import map"})),
            }
        }
        nodes.push(json!({"url": san, "source_kind": a.facts.source_kind, "import_count": imports}));
    }
    nodes.sort_by(|a, b| a["url"].as_str().unwrap_or("").cmp(b["url"].as_str().unwrap_or("")));
    edges.sort_by(|a, b| (a["from"].as_str(), a["to"].as_str()).cmp(&(b["from"].as_str(), b["to"].as_str())));
    let total_nodes = nodes.len();
    let total_edges = edges.len();
    let node_page: Vec<Value> = nodes.into_iter().skip(p.offset).take(limit).collect();
    let summary = format!("Module graph of {page_url}: {total_nodes} script(s), {total_edges} import edge(s), {} unresolved.", unresolved.len());
    let ev = EvidenceBuilder::new("web_modules_trace", Subject { kind: "website".into(), sha256: None, name: Some(page_url.clone()) }, browser_tools::browser_env(ctx.session.clean_room(), &browser))
        .params(json!({"endpoint": browser.endpoint.origin, "offset": p.offset, "limit": limit}))
        .result(json!({"origin": page_url, "nodes": node_page, "nodes_total": total_nodes, "edges": edges, "unresolved": unresolved}))
        .summary(summary)
        .confidence(Confidence::Derived)
        .authority(Authority::EarlierRecord)
        .limitation(Limitation::new("static_resolution", "Imports are read statically from the live sources; relative specifiers are resolved by URL, bare specifiers need the page's import map, and computed imports are reported as non-literal."))
        .limitation(Limitation::new("live_subset", "Only scripts the page had loaded during the window are included."))
        .coverage(if p.offset == 0 && limit >= total_nodes { Coverage::complete(total_nodes as u64) } else { Coverage::page(limit.min(total_nodes.saturating_sub(p.offset)) as u64, total_nodes as u64, p.offset as u64) })
        .location(Location::new("url", page_url))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

/// Resolve a relative/absolute module specifier against the importing script's URL. Bare
/// specifiers (no `.` or `/` start) return `None` — they need an import map we do not have.
fn resolve_specifier(base_url: &str, specifier: &str) -> Option<String> {
    if specifier.starts_with("http://") || specifier.starts_with("https://") || specifier.starts_with("file://") {
        return Some(specifier.to_string());
    }
    if specifier.starts_with('/') {
        // Root-relative: keep scheme+host of the base.
        let scheme_host = base_url.find("://").and_then(|i| base_url.get(..i + 3).map(|s| (s, base_url.get(i + 3..).unwrap_or(""))));
        if let Some((scheme, rest)) = scheme_host {
            let host = rest.split('/').next().unwrap_or("");
            return Some(format!("{scheme}{host}{specifier}"));
        }
        return None;
    }
    if specifier.starts_with("./") || specifier.starts_with("../") {
        return join_url(base_url, specifier);
    }
    None
}

/// Join a relative reference onto a base URL path (no query/fragment handling needed here).
fn join_url(base_url: &str, rel: &str) -> Option<String> {
    let scheme_end = base_url.find("://")? + 3;
    let (prefix, after) = base_url.split_at(scheme_end);
    let host_end = after.find('/').unwrap_or(after.len());
    let host = after.get(..host_end).unwrap_or("");
    let path = after.get(host_end..).unwrap_or("/");
    let base_dir = path.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
    let mut segments: Vec<&str> = base_dir.split('/').filter(|s| !s.is_empty()).collect();
    for seg in rel.split('/') {
        match seg {
            "" | "." => {}
            ".." => {
                segments.pop();
            }
            s => segments.push(s),
        }
    }
    Some(format!("{prefix}{host}/{}", segments.join("/")))
}

fn deadline(ctx: &Ctx<'_>, timeout_secs: u64) -> Result<Deadline, ToolError> {
    if !(1..=600).contains(&timeout_secs) {
        return Err(ToolError::invalid("timeout_secs must be 1..=600"));
    }
    Ok(Deadline::new(Duration::from_secs(timeout_secs), ctx.cancel.clone()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn specifier_resolution() {
        assert_eq!(resolve_specifier("https://x.test/a/b.js", "./c.js").as_deref(), Some("https://x.test/a/c.js"));
        assert_eq!(resolve_specifier("https://x.test/a/b.js", "../d/e.js").as_deref(), Some("https://x.test/d/e.js"));
        assert_eq!(resolve_specifier("https://x.test/a/b.js", "/root.js").as_deref(), Some("https://x.test/root.js"));
        assert_eq!(resolve_specifier("https://x.test/a/b.js", "https://y.test/z.js").as_deref(), Some("https://y.test/z.js"));
        assert_eq!(resolve_specifier("https://x.test/a/b.js", "lodash"), None);
    }
}
