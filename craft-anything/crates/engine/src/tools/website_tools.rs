//! Websites as targets: `web_site_open` starts a private browser owned by the session and loads a
//! page; every other browser tool then looks at that page by default (see
//! [`super::web_common::Browser::resolve`]). `web_site_capture` records what a rebuild needs —
//! full-page screenshots at several widths, the rendered HTML, design tokens, a layout outline,
//! assets, links and form outlines — into a folder. `web_site_close` ends the browser.
//!
//! Data minimisation: form field values, cookies and storage are never read; the capture holds
//! what any visitor sees on the page.

use super::artifact_tools::{create_absent_dir, write_new_file};
use super::browser_tools::{browser_env, cleanup, deadline};
use super::native_common::spec;
use super::web_common::{self, Browser, LaunchOptions};
use crate::tool::{Caller, Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::cdp::{self, CdpClient, CdpEvent, Deadline, Endpoint, PAGE_MAX_MESSAGE};
use craft_anything_evidence::{Authority, Confidence, Coverage, ErrorCode, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex};
use craft_anything_platform::sync::Mutex;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "web_site_open",
            "Open a website",
            "Load a web page (http/https) in a private browser owned by this session (fresh profile, no history or logins) at a chosen window size, wait for it to finish loading, and report its final address, title and size. Every browser tool then inspects this page unless given another endpoint. Runs the site's scripts, so it needs your approval.",
            "Open a website in a private, hidden browser so it can be studied.",
            Toolset::Browser,
            Effects::EVIDENCE.union(Effects::EXECUTES_FOREIGN_CODE).union(Effects::ACCESSES_NETWORK).union(Effects::LAUNCHES_PROCESS),
            Requires::Engine("chromium"),
            schema_of::<OpenParams>,
            web_site_open,
        ),
        spec(
            "web_site_capture",
            "Capture a website for rebuilding",
            "Record the open website into a new folder: full-page PNG screenshots at each requested width, the rendered HTML, design tokens (fonts, sizes, weights, text and background colours as hex, radii, shadows, spacing, content widths, CSS custom properties), the widths its CSS switches layout at, the layout at each width (page width, heading and text sizes, each section's padding, gap, content column and items per row), a layout outline of visible landmarks, headings, controls and images with positions, asset lists (images, stylesheets, scripts, font files, the requests it made), links and form outlines (never values). Writes capture.json and a README.md summary.",
            "Save pictures and a blueprint of a web page so it can be rebuilt.",
            Toolset::Browser,
            Effects::EVIDENCE.union(Effects::WRITES_FILESYSTEM).union(Effects::ACCESSES_NETWORK),
            Requires::Engine("chromium"),
            schema_of::<CaptureParams>,
            web_site_capture,
        ),
        spec(
            "web_page_states_capture",
            "Capture menus, dialogs and tabs",
            "On the open website, open up to max_states of its visible menus, pop-ups, tabs and collapsed sections (aria-expanded, aria-haspopup, unselected tabs, <summary>; never form controls or submit buttons) one at a time: click it, take a screenshot, record what changed (expanded, a dialog appeared, the tab or the address changed), then put the page back. Writes state-<n>.png and states.json into a new folder. Clicking runs the site's own code, so it needs your approval.",
            "Open the site's menus, pop-ups and tabs and photograph each, so a rebuild can match them too.",
            Toolset::Browser,
            Effects::EVIDENCE.union(Effects::WRITES_FILESYSTEM).union(Effects::EXECUTES_FOREIGN_CODE).union(Effects::ACCESSES_NETWORK),
            Requires::Engine("chromium"),
            schema_of::<StatesParams>,
            web_page_states_capture,
        ),
        spec(
            "web_site_close",
            "Close the website",
            "Close the private browser started by web_site_open and delete its temporary profile.",
            "Close the hidden browser.",
            Toolset::Browser,
            Effects::MUTATES_SESSION.union(Effects::IDEMPOTENT),
            Requires::Engine("chromium"),
            schema_of::<CloseParams>,
            web_site_close,
        ),
    ]
}

/// The session's website browser. The process lives as long as this slot (it is killed and its
/// profile removed when the last handle drops).
pub struct SiteBrowser {
    pub endpoint: Endpoint,
    pub product: String,
    pub version: String,
    pub url: Mutex<String>,
    /// What went wrong while the last page opened ([`page_health`]); web_site_capture records it.
    pub health: Mutex<Value>,
    _owner: Mutex<Browser>,
}

impl SiteBrowser {
    /// A non-owning handle for the shared browser helpers.
    fn handle(&self) -> Browser {
        Browser::attached(&self.endpoint, &self.product, &self.version)
    }
}

// ---------------------------------------------------------------------------------------------
// web_site_open

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OpenParams {
    /// The page to open (http or https).
    pub url: String,
    /// Window width in CSS pixels (320..=3840, default 1440).
    #[serde(default = "d_width")]
    pub width: u32,
    /// Window height in CSS pixels (320..=4000, default 900).
    #[serde(default = "d_height")]
    pub height: u32,
    /// Extra time to let late content settle after the load event, in milliseconds (default 2000).
    #[serde(default = "d_settle")]
    pub settle_ms: u64,
    /// Run the browser without a window (default true).
    #[serde(default = "yes")]
    pub headless: bool,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn d_width() -> u32 {
    1440
}
fn d_height() -> u32 {
    900
}
fn d_settle() -> u64 {
    2000
}
fn d_timeout() -> u64 {
    90
}
fn yes() -> bool {
    true
}

/// Only http(s) pages; never local files or browser-internal schemes.
pub fn check_url(url: &str) -> Result<&str, ToolError> {
    let u = url.trim();
    let rest = u.strip_prefix("https://").or_else(|| u.strip_prefix("http://"));
    match rest {
        Some(r) if !r.is_empty() && !r.starts_with('/') && !u.chars().any(char::is_whitespace) => Ok(u),
        _ => Err(ToolError::invalid(format!("{url:?} is not a web address")).with_remediation("Give a full address such as https://example.com.")),
    }
}

/// A URL as shown in evidence and summaries: no credentials, query or fragment.
fn shown_url(url: &str) -> String {
    web_common::sanitize_url(url).split(['?', '#']).next().unwrap_or_default().to_string()
}

fn web_site_open(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OpenParams = parse_params(params)?;
    let url = check_url(&p.url)?.to_string();
    if !(320..=3840).contains(&p.width) || !(320..=4000).contains(&p.height) {
        return Err(ToolError::invalid("width must be 320..=3840 and height 320..=4000"));
    }
    let dl = deadline(ctx, p.timeout_secs)?;
    let site = match live_site(ctx, &dl) {
        Some(s) => s,
        None => {
            ctx.report(None, "Starting a private browser…");
            let opts = LaunchOptions { allow_launch: true, headless: p.headless, no_sandbox: false, startup_secs: 30 };
            let b = Browser::launch(ctx, &opts, &dl)?;
            let site = Arc::new(SiteBrowser {
                endpoint: b.endpoint.clone(),
                product: b.product.clone(),
                version: b.version.clone(),
                url: Mutex::new(String::new()),
                health: Mutex::new(Value::Null),
                _owner: Mutex::new(b),
            });
            ctx.session.ext.insert(site.clone());
            site
        }
    };
    ctx.report(None, format!("Loading {url}…"));
    let mut client = page_client(&site, &dl)?;
    let r = navigate(&mut client, &url, p.width, p.height, p.settle_ms, &dl).and_then(|health| Ok((health, page_facts(&mut client, &dl)?)));
    cleanup(&mut client, &dl);
    let (health, facts) = r?;
    let final_url = facts.get("url").and_then(Value::as_str).unwrap_or(&url).to_string();
    if let Ok(mut u) = site.url.lock() {
        u.clone_from(&final_url);
    }
    if let Ok(mut h) = site.health.lock() {
        h.clone_from(&health);
    }
    // Clean room keeps what a visitor sees: not the page's load errors, failed requests or size in elements.
    let (visitor, mut facts) = (ctx.session.clean_room(), facts);
    let health = if visitor {
        if let Some(f) = facts.as_object_mut() {
            f.remove("elements");
        }
        Value::Null
    } else {
        health
    };
    let title = facts.get("title").and_then(Value::as_str).unwrap_or_default().to_string();
    let shown = shown_url(&final_url);
    let opened = if title.is_empty() { format!("Opened {shown}.") } else { format!("Opened {shown}: \"{title}\".") };
    let count = |k: &str| health.get(k).and_then(Value::as_array).map_or(0, Vec::len);
    let summary = match (count("errors"), count("failed_requests")) {
        (0, 0) => opened,
        (e, f) => format!("{opened} While loading: {e} error(s), {f} failed request(s)."),
    };
    let browser = site.handle();
    let ev = EvidenceBuilder::new(
        "web_site_open",
        Subject { kind: "website".into(), sha256: None, name: Some(shown.clone()) },
        browser_env(ctx.session.clean_room(), &browser),
    )
    .params(json!({"url": shown, "width": p.width, "height": p.height}))
    .result(json!({"url": final_url, "title": title, "facts": facts, "health": health, "browser": site.product}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OurRun)
    .limitation(Limitation::new("private_profile", "A fresh private browser: pages behind a login show their signed-out state."))
    .coverage(Coverage::complete(1))
    .location(Location::new("url", shown))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

/// The session's website browser when it is still answering; a dead one is dropped.
fn live_site(ctx: &mut Ctx<'_>, dl: &Deadline) -> Option<Arc<SiteBrowser>> {
    let site = ctx.session.ext.get::<SiteBrowser>()?;
    if cdp::json_version(&site.endpoint, dl).is_ok() {
        return Some(site);
    }
    ctx.session.ext.remove::<SiteBrowser>();
    None
}

/// The site `web_site_open` opened in this session. Each CLI command is a session of its own, and
/// its browser closes when the command ends, so from the CLI the steps belong in one session (#153).
fn open_site(ctx: &mut Ctx<'_>, dl: &Deadline) -> Result<Arc<SiteBrowser>, ToolError> {
    live_site(ctx, dl).ok_or_else(|| {
        let fix = match ctx.caller {
            Caller::Cli => {
                "Each CLI command starts its own browser and closes it when it ends, so a site opened by an earlier command isn't open here. Run web_site_open and the tools that use the page in one session: an MCP client (`craft-anything-cli mcp`), the app, or `craft-anything-cli rebuild`."
            }
            _ => "Open one first with web_site_open.",
        };
        ToolError::new(ErrorCode::NotFound, "no website is open").with_remediation(fix)
    })
}

fn page_client(site: &SiteBrowser, dl: &Deadline) -> Result<CdpClient, ToolError> {
    let b = site.handle();
    let targets = cdp::json_list(&site.endpoint, dl)?;
    let target = web_common::pick_target(&targets, None, Some("page"))?;
    web_common::connect_target(&b, target, PAGE_MAX_MESSAGE, dl)
}

/// Size the page and pin light mode, so captures don't depend on this computer's theme.
fn set_viewport(client: &mut CdpClient, width: u32, height: u32, dl: &Deadline) -> Result<(), ToolError> {
    client.call("Emulation.setDeviceMetricsOverride", json!({"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600}), None, dl)?;
    let _ = client.call("Emulation.setEmulatedMedia", json!({"features": [{"name": "prefers-color-scheme", "value": "light"}]}), None, dl);
    Ok(())
}

/// Open `url` and wait for it to settle; returns what went wrong while it loaded ([`page_health`]).
fn navigate(client: &mut CdpClient, url: &str, width: u32, height: u32, settle_ms: u64, dl: &Deadline) -> Result<Value, ToolError> {
    client.call("Page.enable", json!({}), None, dl)?;
    // Errors and failed requests are read from the browser's own events; a browser that refuses
    // one of these still loads the page.
    for domain in ["Runtime.enable", "Log.enable", "Network.enable"] {
        let _ = client.call(domain, json!({}), None, dl);
    }
    set_viewport(client, width, height, dl)?;
    let r = client.call("Page.navigate", json!({"url": url}), None, dl)?;
    if let Some(err) = r.get("errorText").and_then(Value::as_str).filter(|s| !s.is_empty()) {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("the page didn't load: {err}"))
            .with_remediation("Check the address and your internet connection, then try again."));
    }
    // Wait for the load event (bounded by the overall deadline), then let late content settle.
    let loaded = Deadline::new(Duration::from_secs(45), crate::tool::CancelToken::default());
    let mut done = false;
    let mut seen: Vec<CdpEvent> = Vec::new();
    let mut keep = |events: Vec<CdpEvent>| {
        let wanted = events.into_iter().filter(|e| e.method.starts_with("Runtime.") || e.method.starts_with("Log.") || e.method.starts_with("Network."));
        seen.extend(wanted.take(MAX_HEALTH_EVENTS.saturating_sub(seen.len())));
    };
    while !done && !loaded.expired() && !dl.expired() {
        let slice = Deadline::new(Duration::from_millis(250), crate::tool::CancelToken::default());
        client.pump_until(&slice)?;
        let events = client.take_events();
        done = events.iter().any(|e| e.method == "Page.loadEventFired");
        keep(events);
    }
    let settle = Deadline::new(Duration::from_millis(settle_ms.min(30_000)), crate::tool::CancelToken::default());
    client.pump_until(&settle)?;
    keep(client.take_events());
    for domain in ["Network.disable", "Log.disable"] {
        let _ = client.call(domain, json!({}), None, dl);
    }
    Ok(page_health(&seen))
}

/// Most browser events read for a page's health (a busy page sends thousands of network events).
const MAX_HEALTH_EVENTS: usize = 20_000;

/// What went wrong while a page loaded, from the browser's events: `errors` (uncaught script
/// errors, console errors and error log entries, each text once) and `failed_requests` (answers
/// of 400 or more, and loads that failed). Texts are cut to one line of 300 characters and
/// addresses lose their query strings, so ids in them aren't kept.
pub fn page_health(events: &[CdpEvent]) -> Value {
    let line = |s: &str| s.lines().next().unwrap_or_default().chars().take(300).collect::<String>();
    let str_at = |v: &Value, p: &str| v.pointer(p).and_then(Value::as_str).unwrap_or_default().to_string();
    let mut urls: std::collections::HashMap<String, String> = std::collections::HashMap::new();
    let mut errors: Vec<Value> = Vec::new();
    let mut failed: Vec<Value> = Vec::new();
    let mut add_error = |kind: &str, text: String, url: String| {
        if !text.is_empty() && errors.len() < 30 && !errors.iter().any(|e| e["text"] == text.as_str()) {
            errors.push(json!({"kind": kind, "text": text, "url": shown_url(&url)}));
        }
    };
    for e in events {
        let p = &e.params;
        match e.method.as_str() {
            "Network.requestWillBeSent" => {
                urls.insert(str_at(p, "/requestId"), str_at(p, "/request/url"));
            }
            "Runtime.exceptionThrown" => {
                let d = &p["exceptionDetails"];
                let text = Some(str_at(d, "/exception/description")).filter(|t| !t.is_empty()).unwrap_or_else(|| str_at(d, "/text"));
                add_error("script", line(&text), str_at(d, "/url"));
            }
            "Runtime.consoleAPICalled" if matches!(p["type"].as_str(), Some("error" | "assert")) => {
                let parts: Vec<String> = p["args"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|a| a.get("value").and_then(Value::as_str).or_else(|| a.get("description").and_then(Value::as_str)).map(String::from))
                    .collect();
                add_error("console", line(&parts.join(" ")), String::new());
            }
            // A failed load is also logged by the browser; the network events say it better.
            "Log.entryAdded" if p.pointer("/entry/level") == Some(&json!("error")) && p.pointer("/entry/source") != Some(&json!("network")) => {
                add_error("log", line(&str_at(p, "/entry/text")), str_at(p, "/entry/url"));
            }
            "Network.responseReceived" => {
                let status = p.pointer("/response/status").and_then(Value::as_u64).unwrap_or(0);
                if status >= 400 && failed.len() < 50 {
                    failed.push(json!({"url": shown_url(&str_at(p, "/response/url")), "status": status, "type": p["type"]}));
                }
            }
            "Network.loadingFailed" if p["canceled"] != true && failed.len() < 50 => {
                let url = urls.get(&str_at(p, "/requestId")).cloned().unwrap_or_default();
                failed.push(json!({"url": shown_url(&url), "error": p["errorText"], "type": p["type"]}));
            }
            _ => {}
        }
    }
    json!({"errors": errors, "failed_requests": failed})
}

/// Evaluate one of our own read-only scripts in the page and return its JSON value.
fn eval(client: &mut CdpClient, script: &str, dl: &Deadline) -> Result<Value, ToolError> {
    let r = client.call("Runtime.evaluate", json!({"expression": script, "returnByValue": true, "awaitPromise": true}), None, dl)?;
    if let Some(ex) = r.get("exceptionDetails") {
        let m = ex.pointer("/exception/description").or_else(|| ex.get("text")).and_then(Value::as_str).unwrap_or("script error");
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("reading the page failed: {}", m.lines().next().unwrap_or(m))));
    }
    Ok(r.pointer("/result/value").cloned().unwrap_or(Value::Null))
}

fn page_facts(client: &mut CdpClient, dl: &Deadline) -> Result<Value, ToolError> {
    eval(
        client,
        "({url: location.href, title: document.title, ready: document.readyState, lang: document.documentElement.lang || '', \
          width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, \
          elements: document.getElementsByTagName('*').length, images: document.images.length, links: document.links.length, \
          forms: document.forms.length})",
        dl,
    )
}

// ---------------------------------------------------------------------------------------------
// web_page_states_capture

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StatesParams {
    /// Absolute path of a folder that does not exist yet; the states are written there.
    pub output_directory: String,
    /// Most controls to open (1..=8, default 4).
    #[serde(default = "d_states")]
    pub max_states: usize,
    /// Page width in CSS pixels (320..=3840, default 1440).
    #[serde(default = "d_state_width")]
    pub width: u32,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn d_states() -> usize {
    4
}
fn d_state_width() -> u32 {
    1440
}

/// Marks the visible toggles (`data-craft-state="<n>"`) and lists them, after dropping the marks
/// an earlier call left (they'd name a control hidden at this width, #339). `__MAX__` is replaced.
const FIND_STATES_JS: &str = r#"(() => {
  for (const old of document.querySelectorAll('[data-craft-state]')) old.removeAttribute('data-craft-state');
  const cap = (s, n) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const shown = el => { const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none'; };
  const sel = '[aria-expanded="false"], [aria-haspopup]:not([aria-haspopup="false"]), [role="tab"][aria-selected="false"], details:not([open]) > summary';
  const out = [];
  for (const el of document.querySelectorAll(sel)) {
    if (out.length >= __MAX__) break;
    if (!shown(el) || el.closest('form') || el.matches('[type="submit"]')) continue;
    const pop = el.getAttribute('aria-haspopup');
    const kind = el.matches('summary') ? 'section' : el.getAttribute('role') === 'tab' ? 'tab' : pop === 'dialog' ? 'dialog' : 'menu';
    el.setAttribute('data-craft-state', String(out.length));
    out.push({index: out.length, kind, label: cap(el.innerText || el.getAttribute('aria-label') || el.getAttribute('title'), 80)});
  }
  return out;
})()"#;

/// What the page looks like around control `__I__` now.
const STATE_JS: &str = r#"(() => {
  const el = document.querySelector('[data-craft-state="__I__"]');
  const seen = d => { const r = d.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], dialog[open], [aria-modal="true"]')).filter(seen).length;
  const details = el && el.parentElement && el.parentElement.tagName === 'DETAILS' ? el.parentElement.open : null;
  return {present: !!el, expanded: el ? el.getAttribute('aria-expanded') : null, selected: el ? el.getAttribute('aria-selected') : null, open: details, dialogs, url: location.href};
})()"#;

const CLICK_STATE_JS: &str = r#"(() => { const el = document.querySelector('[data-craft-state="__I__"]'); if (!el) return false; el.scrollIntoView({block: 'center'}); el.click(); return true; })()"#;

/// Before tab `__I__` is clicked: mark the tab its list has selected now, to select it again after (#335).
const REMEMBER_TAB_JS: &str = r#"(() => {
  const el = document.querySelector('[data-craft-state="__I__"]');
  if (!el || el.getAttribute('role') !== 'tab') return false;
  const list = el.closest('[role="tablist"]') || el.parentElement;
  const was = list && Array.from(list.querySelectorAll('[role="tab"][aria-selected="true"]')).find(t => t !== el);
  if (!was) return false;
  was.setAttribute('data-craft-tab-was', '__I__');
  return true;
})()"#;

const RESELECT_TAB_JS: &str = r#"(() => { const el = document.querySelector('[data-craft-tab-was="__I__"]'); if (!el) return false; el.removeAttribute('data-craft-tab-was'); el.click(); return true; })()"#;

fn press_escape(client: &mut CdpClient, dl: &Deadline) {
    for kind in ["keyDown", "keyUp"] {
        let _ = client.call("Input.dispatchKeyEvent", json!({"type": kind, "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27}), None, dl);
    }
}

fn settle(client: &mut CdpClient, ms: u64) -> Result<(), ToolError> {
    let d = Deadline::new(Duration::from_millis(ms), crate::tool::CancelToken::default());
    client.pump_until(&d)?;
    let _ = client.take_events();
    Ok(())
}

/// What a click changed, in plain words, from the state before and after.
fn state_change(before: &Value, after: &Value) -> Vec<&'static str> {
    let mut out = Vec::new();
    if after["expanded"] == "true" && before["expanded"] != "true" {
        out.push("expanded");
    }
    if after["selected"] == "true" && before["selected"] != "true" {
        out.push("tab selected");
    }
    if after["open"] == true && before["open"] != true {
        out.push("section opened");
    }
    if after["dialogs"].as_u64().unwrap_or(0) > before["dialogs"].as_u64().unwrap_or(0) {
        out.push("dialog appeared");
    }
    if after["url"] != before["url"] {
        out.push("address changed");
    }
    out
}

fn web_page_states_capture(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StatesParams = parse_params(params)?;
    if !(1..=8).contains(&p.max_states) {
        return Err(ToolError::invalid("max_states must be 1..=8"));
    }
    if !(320..=3840).contains(&p.width) {
        return Err(ToolError::invalid("width must be 320..=3840"));
    }
    let dl = deadline(ctx, p.timeout_secs.max(30))?;
    let site = open_site(ctx, &dl)?;
    let out = create_absent_dir(&p.output_directory)?;
    let mut client = page_client(&site, &dl)?;
    let r = (|| -> Result<(String, Vec<Value>, usize), ToolError> {
        client.call("Page.enable", json!({}), None, &dl)?;
        set_viewport(&mut client, p.width, 900, &dl)?;
        settle(&mut client, 500)?;
        let start = eval(&mut client, "location.href", &dl)?.as_str().unwrap_or_default().to_string();
        let found = eval(&mut client, &FIND_STATES_JS.replace("__MAX__", &p.max_states.to_string()), &dl)?;
        let found = found.as_array().cloned().unwrap_or_default();
        let mut states = Vec::new();
        for (n, c) in found.iter().enumerate() {
            if dl.expired() {
                break;
            }
            let i = c.get("index").and_then(Value::as_u64).unwrap_or(n as u64).to_string();
            ctx.report(Some(n as f32 / found.len().max(1) as f32), format!("Opening {}…", c.get("label").and_then(Value::as_str).unwrap_or("a control")));
            let before = eval(&mut client, &STATE_JS.replace("__I__", &i), &dl)?;
            let _ = eval(&mut client, &REMEMBER_TAB_JS.replace("__I__", &i), &dl);
            if eval(&mut client, &CLICK_STATE_JS.replace("__I__", &i), &dl)? != true {
                continue;
            }
            settle(&mut client, 700)?;
            let after = eval(&mut client, &STATE_JS.replace("__I__", &i), &dl).unwrap_or(Value::Null);
            let changed = state_change(&before, &after);
            let mut row = json!({"index": n, "kind": c.get("kind"), "label": c.get("label"), "changed": changed});
            if !changed.contains(&"address changed") {
                let shot = client.call("Page.captureScreenshot", json!({"format": "png"}), None, &dl)?;
                if let Some(data) = shot.get("data").and_then(Value::as_str) {
                    let bytes = web_common::b64_decode(data)?;
                    let name = format!("state-{}.png", n + 1);
                    write_new_file(&out, std::slice::from_ref(&name), &bytes).map_err(ToolError::invalid)?;
                    row["file"] = json!(name);
                    row["sha256"] = json!(sha256_hex(&bytes));
                }
            }
            // Put the page back for the next one: close what opened, or go back to where it was.
            press_escape(&mut client, &dl);
            if after["url"].as_str().is_some_and(|u| u != start) {
                let _ = navigate(&mut client, &start, p.width, 900, 800, &dl)?;
                // The page reloaded: its marks are gone, so mark the toggles again.
                let _ = eval(&mut client, &FIND_STATES_JS.replace("__MAX__", &p.max_states.to_string()), &dl);
            } else if after["expanded"] == "true" || after["open"] == true {
                let _ = eval(&mut client, &CLICK_STATE_JS.replace("__I__", &i), &dl);
            } else if changed.contains(&"tab selected") {
                let _ = eval(&mut client, &RESELECT_TAB_JS.replace("__I__", &i), &dl);
            }
            settle(&mut client, 300)?;
            states.push(row);
        }
        Ok((start, states, found.len()))
    })();
    cleanup(&mut client, &dl);
    let (start, states, found) = r?;
    let json_bytes = serde_json::to_vec_pretty(&json!({"url": start, "width": p.width, "states": states})).map_err(|e| ToolError::internal(e.to_string()))?;
    write_new_file(&out, &["states.json".into()], &json_bytes).map_err(ToolError::invalid)?;
    let shown = shown_url(&start);
    let pictured = states.iter().filter(|s| s.get("file").is_some()).count();
    let summary = if found == 0 {
        format!("{shown} has no menus, pop-ups, tabs or collapsed sections to open.")
    } else {
        format!("Opened {} of {found} control(s) on {shown}; {pictured} pictured in {}.", states.len(), out.display())
    };
    let browser = site.handle();
    let ev = EvidenceBuilder::new(
        "web_page_states_capture",
        Subject { kind: "website".into(), sha256: None, name: Some(shown.clone()) },
        browser_env(ctx.session.clean_room(), &browser),
    )
    .params(json!({"max_states": p.max_states, "width": p.width}))
    .result(json!({"url": start, "found": found, "states": states, "folder": out.display().to_string()}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OurRun)
    .limitation(Limitation::new("first_controls", "Only the first controls found are opened, one at a time; menus inside menus and hover-only menus are not."))
    .coverage(Coverage::complete(states.len() as u64))
    .location(Location::new("url", start))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// web_site_capture

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CaptureParams {
    /// Absolute path of a folder that does not exist yet; the capture is written there.
    pub output_directory: String,
    /// Page widths to screenshot, in CSS pixels (1..=4 widths, each 320..=3840). Default: desktop and phone.
    #[serde(default = "d_widths")]
    pub widths: Vec<u32>,
    /// Tallest screenshot in CSS pixels; longer pages are cut here (600..=20000, default 12000).
    #[serde(default = "d_max_height")]
    pub max_height: u32,
    /// Keep the rendered HTML (default true).
    #[serde(default = "yes")]
    pub include_html: bool,
    /// Photograph each width a second time a moment later and save the parts that changed by
    /// themselves (carousels, videos, animations) as noise-<width>.png, white where it changed,
    /// so comparisons can leave them out (default false).
    #[serde(default)]
    pub noise_pass: bool,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn d_widths() -> Vec<u32> {
    vec![1440, 390]
}
fn d_max_height() -> u32 {
    12_000
}

const MAX_HTML_BYTES: usize = 4 << 20;

/// Our read-only blueprint script. Counts styles, outlines visible structure and lists assets;
/// form fields contribute only their type, name, label and placeholder.
const BLUEPRINT_JS: &str = r#"(() => {
  const cap = (s, n) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const box = el => { const r = el.getBoundingClientRect(); return {x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height)}; };
  const shown = el => { const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const tally = (m, k) => { if (k) m[k] = (m[k] || 0) + 1; };
  const top = (m, n) => Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, n).map(([value, count]) => ({value, count}));
  const fonts = {}, sizes = {}, weights = {}, colors = {}, backgrounds = {}, radii = {}, shadows = {}, bgImages = {}, spacing = {}, maxWidths = {};
  // Colours as #rrggbb(aa), whatever notation the CSS used. Computed rgb()/rgba() is read as numbers: a canvas read
  // can be off by one per channel (Brave adds noise to it, #154). Anything else (oklch, color()…) is painted on a 1×1
  // canvas and read back.
  const cv = document.createElement('canvas'); cv.width = cv.height = 1; const g = cv.getContext('2d', {willReadFrequently: true}); const seenHex = {};
  const hex = c => { if (!c) return c; if (c in seenHex) return seenHex[c]; const h2 = x => x.toString(16).padStart(2, '0'); const m = /^rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)$/.exec(c); if (m) { const a = m[4] === undefined ? 1 : +m[4]; return seenHex[c] = '#' + h2(+m[1]) + h2(+m[2]) + h2(+m[3]) + (a < 1 ? h2(Math.round(a * 255)) : ''); } if (!g) return c; g.clearRect(0, 0, 1, 1); g.fillStyle = '#000'; g.fillStyle = c; g.fillRect(0, 0, 1, 1); const d = g.getImageData(0, 0, 1, 1).data; return seenHex[c] = '#' + h2(d[0]) + h2(d[1]) + h2(d[2]) + (d[3] < 255 ? h2(d[3]) : ''); };
  const els = [document.documentElement, document.body, ...Array.from(document.querySelectorAll('body *')).slice(0, 12000)].filter(Boolean);
  for (const el of els) {
    if (!shown(el)) continue;
    const s = getComputedStyle(el);
    const text = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
    if (text) { tally(fonts, s.fontFamily); tally(sizes, s.fontSize); tally(weights, s.fontWeight); tally(colors, hex(s.color)); }
    if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent') tally(backgrounds, hex(s.backgroundColor));
    for (const k of ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'rowGap', 'columnGap', 'marginTop', 'marginBottom']) { const v = s[k]; if (v && v.endsWith('px') && v !== '0px') tally(spacing, v); }
    if (s.maxWidth.endsWith('px')) tally(maxWidths, s.maxWidth);
    // A pill made with calc(infinity * 1px) comes back clamped as 3.35544e+07px: record it as 9999px (#155).
    if (s.borderRadius && s.borderRadius !== '0px') tally(radii, s.borderRadius.replace(/[\d.]+(?:e\+?\d+)?px/g, n => parseFloat(n) > 9999 ? '9999px' : n));
    if (s.boxShadow && s.boxShadow !== 'none') tally(shadows, s.boxShadow);
    const bi = s.backgroundImage; if (bi && bi !== 'none') for (const m of bi.matchAll(/url\(["']?([^"')]+)["']?\)/g)) tally(bgImages, m[1]);
  }
  const vars = {}, bps = {}; let ruleCount = 0, unreadable = 0;
  const bp = (side, n, unit) => tally(bps, side + '-width ' + Math.round(parseFloat(n) * (unit === 'px' ? 1 : 16)) + 'px');
  const walk = (rules, depth) => {
    if (!rules || depth > 6) return;
    for (const r of Array.from(rules)) {
      if (++ruleCount > 40000) return;
      if (r.selectorText && r.selectorText.includes(':root') && r.style) for (const name of Array.from(r.style)) if (name.startsWith('--') && Object.keys(vars).length < 300) vars[name] = cap(r.style.getPropertyValue(name), 120);
      const media = r.media && r.media.mediaText ? r.media.mediaText : (r.conditionText || '');
      for (const m of media.matchAll(/(min|max)-width\s*:\s*([\d.]+)(px|r?em)/g)) bp(m[1], m[2], m[3]);
      for (const m of media.matchAll(/width\s*(>=?|<=?)\s*([\d.]+)(px|r?em)/g)) bp(m[1][0] === '>' ? 'min' : 'max', m[2], m[3]);
      if (r.cssRules) walk(r.cssRules, depth + 1);
    }
  };
  for (const sheet of Array.from(document.styleSheets)) { let rules; try { rules = sheet.cssRules; } catch (e) { unreadable++; continue; } walk(rules, 0); }
  const breakpoints = Object.entries(bps).map(([query, count]) => ({query, px: parseInt(query.split(' ')[1], 10), count})).sort((a, b) => a.px - b.px).slice(0, 24);
  const PICK = 'header,nav,main,footer,section,article,aside,form,h1,h2,h3,h4,p,ul,ol,button,a,img,picture,video,svg,input,select,textarea,[role]';
  const outline = [];
  for (const el of document.querySelectorAll(PICK)) {
    if (outline.length >= 900) break;
    if (!shown(el)) continue;
    let depth = 0; for (let p = el.parentElement; p; p = p.parentElement) depth++;
    const tag = el.tagName.toLowerCase();
    const item = {tag, depth, box: box(el)};
    const role = el.getAttribute('role'); if (role) item.role = role;
    if (el.id) item.id = cap(el.id, 60);
    const cls = typeof el.className === 'string' ? cap(el.className, 120) : ''; if (cls) item.class = cls;
    if (!['main', 'section', 'article', 'header', 'footer', 'nav', 'aside', 'form', 'ul', 'ol', 'svg', 'picture', 'video'].includes(tag)) { const t = cap(el.innerText, 200); if (t) item.text = t; }
    if (tag === 'a') item.href = el.href || '';
    if (tag === 'img') { item.src = el.currentSrc || el.src || ''; item.alt = cap(el.alt, 120); }
    if (['input', 'select', 'textarea'].includes(tag)) { item.type = el.type || tag; item.name = cap(el.name, 60); item.placeholder = cap(el.placeholder, 80); }
    const s = getComputedStyle(el);
    if (['header', 'nav', 'main', 'footer', 'section', 'article', 'aside', 'form', 'ul', 'ol'].includes(tag)) { item.display = s.display; if (s.display.includes('flex')) item.flex = s.flexDirection; if (s.display.includes('grid')) item.grid = cap(s.gridTemplateColumns, 120); }
    item.font = s.fontSize + ' ' + s.fontWeight; item.color = hex(s.color); if (s.backgroundColor !== 'rgba(0, 0, 0, 0)') item.background = hex(s.backgroundColor);
    outline.push(item);
  }
  const labelFor = el => { if (el.labels && el.labels[0]) return cap(el.labels[0].innerText, 80); return cap(el.getAttribute('aria-label'), 80); };
  const forms = Array.from(document.forms).slice(0, 30).map(f => ({action: f.getAttribute('action') || '', method: (f.method || 'get').toLowerCase(),
    fields: Array.from(f.elements).slice(0, 60).map(e => ({tag: e.tagName.toLowerCase(), type: e.type || '', name: cap(e.name, 60), label: labelFor(e), placeholder: cap(e.placeholder, 80), required: !!e.required}))}));
  const links = Array.from(document.links).slice(0, 400).map(a => ({text: cap(a.innerText || a.getAttribute('aria-label'), 100), href: a.href}));
  const meta = n => { const m = document.querySelector(`meta[name="${n}"],meta[property="${n}"]`); return m ? cap(m.content, 300) : ''; };
  const icons = Array.from(document.querySelectorAll('link[rel~="icon"],link[rel="apple-touch-icon"]')).map(l => l.href).slice(0, 10);
  // What the page loaded, without query strings (they can carry ids).
  const resources = (performance.getEntriesByType ? performance.getEntriesByType('resource') : []).map(e => ({url: String(e.name).split(/[?#]/)[0], type: e.initiatorType, bytes: e.transferSize || 0}));
  // Accessibility at a glance: controls a screen reader can't name, pictures without alt text,
  // the landmarks and the page language.
  const CONTROLS = 'a[href],button,input:not([type="hidden"]),select,textarea,[role="button"],[role="link"],[role="tab"],[role="menuitem"]';
  const named = el => !!(cap(el.innerText, 80) || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title')
    || (el.labels && el.labels.length) || el.getAttribute('placeholder') || (['submit', 'button', 'reset'].includes(el.type) && el.value)
    || el.querySelector('img[alt]:not([alt=""]),svg title,[aria-label]'));
  const unnamed = Array.from(document.querySelectorAll(CONTROLS)).slice(0, 3000).filter(el => shown(el) && !named(el));
  const landmarks = {};
  for (const el of document.querySelectorAll('header,nav,main,footer,aside,form[aria-label],[role="banner"],[role="navigation"],[role="main"],[role="contentinfo"],[role="complementary"],[role="search"]')) {
    if (!shown(el)) continue;
    const role = el.getAttribute('role') || {header: 'banner', nav: 'navigation', main: 'main', footer: 'contentinfo', aside: 'complementary', form: 'form'}[el.tagName.toLowerCase()];
    tally(landmarks, role);
  }
  const a11y = {lang: document.documentElement.lang || '', landmarks, unnamed_controls: unnamed.length,
    unnamed_examples: unnamed.slice(0, 5).map(el => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + cap(el.className, 40).split(' ')[0] : '')),
    images_without_alt: Array.from(document.images).filter(i => shown(i) && !i.hasAttribute('alt')).length};
  const fontFaces = []; try { document.fonts.forEach(f => { if (fontFaces.length < 80) fontFaces.push({family: f.family, weight: f.weight, style: f.style, status: f.status}); }); } catch (e) {}
  return {
    url: location.href, title: document.title, lang: document.documentElement.lang || '',
    viewport: {w: innerWidth, h: innerHeight}, page: {w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight},
    meta: {description: meta('description'), theme_color: meta('theme-color'), og_title: meta('og:title'), og_image: meta('og:image'), icons},
    design: {fonts: top(fonts, 12), font_sizes: top(sizes, 16), font_weights: top(weights, 8), text_colors: top(colors, 16), backgrounds: top(backgrounds, 16), radii: top(radii, 10), shadows: top(shadows, 8), spacing: top(spacing, 24), max_widths: top(maxWidths, 8), css_variables: vars, font_faces: fontFaces},
    breakpoints, unreadable_stylesheets: unreadable, a11y,
    outline, forms, links,
    assets: {
      images: Array.from(document.images).slice(0, 300).map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, alt: cap(i.alt, 120)})),
      background_images: top(bgImages, 60).map(x => x.value),
      stylesheets: Array.from(document.styleSheets).map(s => s.href).filter(Boolean).slice(0, 80),
      scripts: Array.from(document.scripts).map(s => s.src).filter(Boolean).slice(0, 120),
      inline_scripts: Array.from(document.scripts).filter(s => !s.src).length,
      fonts: resources.filter(r => /\.(woff2?|ttf|otf|eot)$/i.test(r.url) || r.url.includes('fonts.googleapis.com')).map(r => r.url).slice(0, 40),
      requests: resources.slice(0, 300)
    },
    headings: Array.from(document.querySelectorAll('h1,h2,h3')).slice(0, 120).map(h => ({level: Number(h.tagName[1]), text: cap(h.innerText, 160)})),
    text: cap(document.body ? document.body.innerText : '', 30000)
  };
})()"#;

/// Scroll through the page as a visitor would, so sections that appear as they come into view and
/// lazy images are there for the full-page picture (#160), then back to the top. At most a few
/// seconds; returns how far it scrolled.
const REVEAL_JS: &str = r#"(async () => {
  const pause = ms => new Promise(r => setTimeout(r, ms));
  const end = Date.now() + 5000;
  const step = Math.max(200, Math.floor(innerHeight * 0.8));
  const bottom = () => Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0) - innerHeight;
  let y = 0;
  while (y < bottom() && Date.now() < end) {
    y = Math.min(y + step, bottom());
    scrollTo(0, y);
    await pause(120);
  }
  for (const img of document.images) if (img.loading === 'lazy') img.loading = 'eager';
  const loading = [...document.images].filter(i => !i.complete).map(i => new Promise(r => { i.addEventListener('load', r, {once: true}); i.addEventListener('error', r, {once: true}); }));
  await Promise.race([Promise.all(loading), pause(Math.max(300, end - Date.now()))]);
  scrollTo(0, 0);
  await pause(200);
  return y;
})()"#;

/// Our read-only layout script, run at every width: the page's width (wider than the window means
/// it scrolls sideways), heading and text sizes, and each landmark and section's padding, gap,
/// background, content column and how many items sit side by side.
const LAYOUT_JS: &str = r#"(() => {
  const cap = (s, n) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const px = v => Math.round(parseFloat(v) || 0);
  const shown = el => { const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const size = sel => { const el = Array.from(document.querySelectorAll(sel)).slice(0, 50).find(shown); return el ? px(getComputedStyle(el).fontSize) : 0; };
  const cv = document.createElement('canvas'); cv.width = cv.height = 1; const g = cv.getContext('2d', {willReadFrequently: true});
  // Computed rgb()/rgba() is read as numbers; a canvas read can be off by one (#154).
  const hex = c => { const h2 = x => x.toString(16).padStart(2, '0'); const m = /^rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)$/.exec(c); if (m) { const a = m[4] === undefined ? 1 : +m[4]; return '#' + h2(+m[1]) + h2(+m[2]) + h2(+m[3]) + (a < 1 ? h2(Math.round(a * 255)) : ''); } if (!g) return c; g.clearRect(0, 0, 1, 1); g.fillStyle = '#000'; g.fillStyle = c; g.fillRect(0, 0, 1, 1); const d = g.getImageData(0, 0, 1, 1).data; return '#' + h2(d[0]) + h2(d[1]) + h2(d[2]) + (d[3] < 255 ? h2(d[3]) : ''); };
  // Items side by side: the most children of one box sharing a top edge, counting only children at
  // least 15% of the block's width (cards and columns, not inline links or logo strips).
  const perRow = (root, width) => {
    let best = 1, seen = 0;
    for (const c of [root, ...root.querySelectorAll('*')]) {
      if (++seen > 400) break;
      if (c.children.length < 2) continue;
      const kids = Array.from(c.children).filter(k => shown(k) && k.getBoundingClientRect().width >= Math.max(40, width * 0.15));
      if (kids.length < 2) continue;
      const top = kids[0].getBoundingClientRect().top;
      best = Math.max(best, kids.filter(k => Math.abs(k.getBoundingClientRect().top - top) <= 2).length);
    }
    return best;
  };
  const blocks = [];
  for (const el of document.querySelectorAll('header,nav,main,footer,section,article,aside')) {
    if (blocks.length >= 60) break;
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect(); if (r.height < 24) continue;
    const s = getComputedStyle(el);
    const b = {tag: el.tagName.toLowerCase(), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height),
      pad: [px(s.paddingTop), px(s.paddingRight), px(s.paddingBottom), px(s.paddingLeft)], per_row: perRow(el, r.width)};
    const head = Array.from(el.querySelectorAll('h1,h2,h3')).slice(0, 20).find(shown); if (head) b.heading = cap(head.innerText, 80);
    const gap = px(s.columnGap) || px(s.rowGap); if (gap) b.gap = gap;
    if (s.backgroundColor !== 'rgba(0, 0, 0, 0)') b.background = hex(s.backgroundColor);
    // The content column: the first box (itself or inside) held to a maximum width in px.
    let n = 0;
    for (const c of [el, ...el.querySelectorAll('*')]) {
      if (++n > 80) break;
      const cs = getComputedStyle(c);
      if (cs.maxWidth.endsWith('px') && !['IMG', 'SVG', 'VIDEO', 'PICTURE'].includes(c.tagName.toUpperCase()) && shown(c)) {
        const cr = c.getBoundingClientRect();
        b.column = {max_w: px(cs.maxWidth), x: Math.round(cr.left), w: Math.round(cr.width), pad: [px(cs.paddingLeft), px(cs.paddingRight)]};
        break;
      }
    }
    blocks.push(b);
  }
  return {page_w: document.documentElement.scrollWidth, page_h: document.documentElement.scrollHeight,
    type: {h1: size('h1'), h2: size('h2'), h3: size('h3'), body: size('p')}, blocks};
})()"#;

fn web_site_capture(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CaptureParams = parse_params(params)?;
    if p.widths.is_empty() || p.widths.len() > 4 || p.widths.iter().any(|w| !(320..=3840).contains(w)) {
        return Err(ToolError::invalid("widths must hold 1..=4 values, each 320..=3840"));
    }
    if !(600..=20_000).contains(&p.max_height) {
        return Err(ToolError::invalid("max_height must be 600..=20000"));
    }
    let mut p = p;
    // Clean room keeps what a visitor sees: never the page's own code.
    let visitor = ctx.session.clean_room();
    p.include_html &= !visitor;
    let dl = deadline(ctx, p.timeout_secs.max(30))?;
    let site = open_site(ctx, &dl)?;
    let mut client = page_client(&site, &dl)?;
    // A site that didn't open leaves the browser on its own error page (or a blank one), which
    // would be captured as if it were the site (#158).
    let here = eval(&mut client, "location.href", &dl).ok().and_then(|v| v.as_str().map(str::to_string)).unwrap_or_default();
    if here.is_empty() || here.starts_with("chrome-error:") || here == "about:blank" {
        cleanup(&mut client, &dl);
        return Err(ToolError::new(ErrorCode::NotFound, "The website didn't open, so there's nothing to capture: the browser is showing its own error page.")
            .with_remediation("Open the site again with web_site_open and make sure it loads."));
    }
    let out = match create_absent_dir(&p.output_directory) {
        Ok(out) => out,
        Err(e) => {
            cleanup(&mut client, &dl);
            return Err(e);
        }
    };
    let r = capture_into(ctx, &mut client, &out, &p, &dl);
    // Leave the page at the first (usually desktop) width for the tools that follow.
    if let Some(w) = p.widths.first() {
        let _ = set_viewport(&mut client, *w, 900, &dl);
    }
    cleanup(&mut client, &dl);
    let (mut blueprint, shots, html) = r?;
    let html_bytes = html.0;
    if visitor {
        visitor_view(&mut blueprint);
    } else if let (Value::Object(b), Ok(h)) = (&mut blueprint, site.health.lock()) {
        b.insert("health".into(), h.clone());
    }

    let url = blueprint.get("url").and_then(Value::as_str).unwrap_or_default().to_string();
    let shown = shown_url(&url);
    let n = |k: &str| blueprint.get(k).and_then(Value::as_array).map_or(0, Vec::len);
    let images = blueprint.pointer("/assets/images").and_then(Value::as_array).map_or(0, Vec::len);
    let readme = readme(&blueprint, &shots, html, visitor);
    write_new_file(&out, &["README.md".into()], readme.as_bytes()).map_err(ToolError::invalid)?;
    let capture_json = serde_json::to_vec_pretty(&blueprint).map_err(|e| ToolError::internal(e.to_string()))?;
    write_new_file(&out, &["capture.json".into()], &capture_json).map_err(ToolError::invalid)?;

    let summary = format!(
        "Captured {shown}: {} screenshot(s), {} outline items, {} headings, {images} images, {} links, {} forms → {}.",
        shots.len(),
        n("outline"),
        n("headings"),
        n("links"),
        n("forms"),
        out.display()
    );
    let browser = site.handle();
    let ev = EvidenceBuilder::new("web_site_capture", Subject { kind: "website".into(), sha256: None, name: Some(shown.clone()) }, browser_env(ctx.session.clean_room(), &browser))
        .params(json!({"widths": p.widths, "max_height": p.max_height, "include_html": p.include_html, "noise_pass": p.noise_pass, "visitor_view": visitor}))
        .result(json!({
            "output_directory": out.display().to_string(),
            "url": url,
            "title": blueprint.get("title"),
            "screenshots": shots,
            "html_bytes": html_bytes,
            "counts": {"outline": n("outline"), "headings": n("headings"), "links": n("links"), "forms": n("forms"), "images": images},
            "design": blueprint.get("design"),
            "files": ["README.md", "capture.json"],
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OurRun)
        .limitation(Limitation::new("one_state", "One state of the page: menus, dialogs and content behind interactions are not opened."))
        .limitation(if visitor {
            Limitation::new("visitor_view", "Clean room: only what a visitor sees was kept (screenshots, visible text, measured layout and styles); not the page's HTML, CSS rules, scripts, requests or errors.")
        } else {
            Limitation::new("cross_origin_css", "CSS custom properties and breakpoints from cross-origin stylesheets can't be read.")
        })
        .limitations(html_cut(html))
        .coverage(Coverage::complete(p.widths.len() as u64))
        .location(Location::new("url", shown))
        .location(Location::new("path", out.display().to_string()))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

/// The blueprint, the screenshots, and the HTML's bytes as (saved, the page's).
type Captured = (Value, Vec<Value>, (usize, usize));

/// When page.html holds only the first part of the page's HTML (#336).
fn html_cut((kept, total): (usize, usize)) -> Option<Limitation> {
    (kept < total).then(|| {
        Limitation::new(
            "html_cut",
            format!("page.html holds the first {kept} of the page's {total} bytes of HTML: it was cut at the {} MiB limit.", MAX_HTML_BYTES >> 20),
        )
    })
}

fn capture_into(ctx: &Ctx<'_>, client: &mut CdpClient, out: &Path, p: &CaptureParams, dl: &Deadline) -> Result<Captured, ToolError> {
    client.call("Page.enable", json!({}), None, dl)?;
    let mut shots = Vec::new();
    let mut blueprint = Value::Null;
    let mut layouts = Vec::new();
    for (i, &w) in p.widths.iter().enumerate() {
        ctx.report(Some(i as f32 / p.widths.len() as f32), format!("Photographing the page at {w} px…"));
        set_viewport(client, w, 900, dl)?;
        settle(client, 900)?;
        // A page that can't be scrolled through is still photographed as it is.
        let _ = eval(client, REVEAL_JS, dl);
        if i == 0 {
            // The blueprint is read at the first width, where the layout is the reference one.
            blueprint = eval(client, BLUEPRINT_JS, dl)?;
        }
        // A page whose layout can't be read is still photographed.
        if let Ok(Value::Object(mut layout)) = eval(client, LAYOUT_JS, dl) {
            layout.insert("width".into(), json!(w));
            layouts.push(Value::Object(layout));
        }
        let height = eval(client, "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)", dl)?
            .as_u64()
            .unwrap_or(900)
            .clamp(320, u64::from(p.max_height));
        let clip = json!({"format": "png", "captureBeyondViewport": true, "clip": {"x": 0, "y": 0, "width": w, "height": height, "scale": 1}});
        let photograph = |client: &mut CdpClient| -> Result<Vec<u8>, ToolError> {
            let shot = client.call("Page.captureScreenshot", clip.clone(), None, dl)?;
            let data =
                shot.get("data").and_then(Value::as_str).ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, "the browser returned no screenshot"))?;
            web_common::b64_decode(data)
        };
        let bytes = photograph(client)?;
        let (pw, ph) = web_common::png_dimensions(&bytes)?;
        let name = format!("screenshot-{w}.png");
        write_new_file(out, std::slice::from_ref(&name), &bytes).map_err(ToolError::invalid)?;
        let mut row = json!({"file": name, "width": pw, "height": ph, "css_width": w, "sha256": sha256_hex(&bytes), "cut": height >= u64::from(p.max_height)});
        if p.noise_pass {
            // The same page twice more, at uneven gaps so something repeating every so often
            // can't look still in both: what changed by itself moves, not the build's fault.
            settle(client, 900)?;
            let second = photograph(client)?;
            settle(client, 1300)?;
            let third = photograph(client)?;
            if let (Ok(a), Ok(b), Ok(c)) = (web_common::decode_png(&bytes), web_common::decode_png(&second), web_common::decode_png(&third)) {
                let mask = web_common::NoiseMask::between(&a, &b, 24).union(&web_common::NoiseMask::between(&a, &c, 24));
                row["noise_tiles"] = json!(mask.count());
                if mask.count() > 0 {
                    let file = format!("noise-{w}.png");
                    write_new_file(out, std::slice::from_ref(&file), &mask.to_png()?).map_err(ToolError::invalid)?;
                    row["noise_file"] = json!(file);
                }
            }
        }
        shots.push(row);
    }
    if let Value::Object(b) = &mut blueprint {
        b.insert("layouts".into(), Value::Array(layouts));
    }
    let mut html_bytes = (0, 0);
    if p.include_html {
        let html = eval(client, "document.documentElement.outerHTML", dl)?;
        let html = html.as_str().unwrap_or_default();
        let kept = truncate_utf8(html, MAX_HTML_BYTES);
        html_bytes = (kept.len(), html.len());
        write_new_file(out, &["page.html".into()], kept.as_bytes()).map_err(ToolError::invalid)?;
    }
    Ok((blueprint, shots, html_bytes))
}

fn truncate_utf8(s: &str, max: usize) -> &str {
    if s.len() <= max {
        return s;
    }
    let mut end = max;
    while !s.is_char_boundary(end) {
        end -= 1;
    }
    s.get(..end).unwrap_or_default()
}

/// Drop everything a visitor can't see: the page's metadata, CSS variables and breakpoints, the
/// stylesheets, scripts, fonts and requests it loaded, where its pictures come from (their sizes
/// stay), its class names, and the query strings (deployment ids, tokens) on the addresses it
/// shows (#156). Screenshots, visible text, the measured layout and styles, links and forms are kept.
fn visitor_view(blueprint: &mut Value) {
    let Value::Object(b) = blueprint else { return };
    for k in ["meta", "breakpoints", "unreadable_stylesheets", "health"] {
        b.remove(k);
    }
    let bare = |v: &mut Value| {
        if let Some(s) = v.as_str() {
            *v = Value::String(s.split(['?', '#']).next().unwrap_or_default().to_string());
        }
    };
    if let Some(Value::Array(items)) = b.get_mut("outline") {
        for item in items.iter_mut().filter_map(Value::as_object_mut) {
            item.remove("class");
            item.get_mut("src").map(bare);
            item.get_mut("href").map(bare);
        }
    }
    if let Some(Value::Array(links)) = b.get_mut("links") {
        links.iter_mut().filter_map(|l| l.get_mut("href")).for_each(bare);
    }
    // "button.btn-primary" → "button": the element, not the page's class for it.
    if let Some(Value::Array(examples)) = b.get_mut("a11y").and_then(|a| a.get_mut("unnamed_examples")) {
        for e in examples.iter_mut() {
            if let Some(s) = e.as_str() {
                *e = Value::String(s.split('.').next().unwrap_or_default().to_string());
            }
        }
    }
    if let Some(Value::Object(d)) = b.get_mut("design") {
        d.remove("css_variables");
        d.remove("font_faces");
    }
    let images: Vec<Value> = b
        .get("assets")
        .and_then(|a| a.get("images"))
        .and_then(Value::as_array)
        .map(|a| a.iter().map(|i| json!({"w": i.get("w"), "h": i.get("h")})).collect())
        .unwrap_or_default();
    b.insert("assets".into(), json!({"images": images}));
}

/// A short human/agent-readable summary of the capture folder.
fn readme(b: &Value, shots: &[Value], (html_bytes, html_total): (usize, usize), visitor: bool) -> String {
    let s = |p: &str| b.pointer(p).and_then(Value::as_str).unwrap_or_default().to_string();
    let top = |p: &str, n: usize| {
        b.pointer(p)
            .and_then(Value::as_array)
            .map(|a| a.iter().take(n).filter_map(|x| x.get("value").and_then(Value::as_str)).map(|v| format!("`{v}`")).collect::<Vec<_>>().join(", "))
            .unwrap_or_default()
    };
    let mut md = format!("# Capture of {}\n\n", shown_url(&s("/url")));
    md.push_str(&format!("- Title: {}\n", s("/title")));
    if !s("/meta/description").is_empty() {
        md.push_str(&format!("- Description: {}\n", s("/meta/description")));
    }
    md.push_str(&format!(
        "- Page size at the first width: {}×{} CSS px\n\n",
        b.pointer("/page/w").and_then(Value::as_u64).unwrap_or(0),
        b.pointer("/page/h").and_then(Value::as_u64).unwrap_or(0)
    ));
    md.push_str("## Files\n\n");
    for sh in shots {
        md.push_str(&format!(
            "- `{}` — {}×{} px screenshot{}\n",
            sh["file"].as_str().unwrap_or_default(),
            sh["width"],
            sh["height"],
            if sh["cut"].as_bool().unwrap_or(false) { " (cut at the height limit)" } else { "" }
        ));
        if let Some(noise) = sh["noise_file"].as_str() {
            md.push_str(&format!(
                "- `{noise}` — the parts that changed by themselves between two photos a moment apart (white, one pixel per 16 px square): carousels, videos, animations. They aren't compared.\n"
            ));
        }
    }
    if html_bytes > 0 {
        let cut = if html_bytes < html_total { format!(": the first part of {html_total}, cut at the size limit") } else { String::new() };
        md.push_str(&format!("- `page.html` — rendered HTML ({html_bytes} bytes{cut})\n"));
    }
    if visitor {
        md.push_str("- `capture.json` — design tokens, the layout at each width (`layouts`), layout outline (positions in CSS px), headings, links, forms, picture sizes and visible text\n\n");
        md.push_str("Clean room: only what a visitor sees was kept. The page's HTML, CSS rules, scripts, requests and errors weren't read.\n\n");
    } else {
        md.push_str("- `capture.json` — design tokens, breakpoints, the layout at each width (`layouts`), layout outline (positions in CSS px), headings, links, forms, assets and visible text\n\n");
    }
    md.push_str("## Design at a glance\n\n");
    md.push_str(&format!("- Fonts: {}\n", top("/design/fonts", 4)));
    md.push_str(&format!("- Text sizes: {}\n", top("/design/font_sizes", 8)));
    md.push_str(&format!("- Text colours: {}\n", top("/design/text_colors", 6)));
    md.push_str(&format!("- Backgrounds: {}\n", top("/design/backgrounds", 6)));
    md.push_str(&format!("- Corner radii: {}\n", top("/design/radii", 5)));
    md.push_str(&format!("- Spacing (padding, gaps, margins): {}\n", top("/design/spacing", 10)));
    md.push_str(&format!("- Content widths: {}\n", top("/design/max_widths", 4)));
    if visitor {
        md.push('\n');
    } else {
        md.push_str(&format!("- Font files: {}\n\n", b.pointer("/assets/fonts").and_then(Value::as_array).map_or(0, Vec::len)));
    }
    md.push_str(&layout_section(b, visitor));
    if !visitor {
        md.push_str(&health_section(b));
    }
    md.push_str("## Headings\n\n");
    for h in b.pointer("/headings").and_then(Value::as_array).into_iter().flatten().take(40) {
        let level = h.get("level").and_then(Value::as_u64).unwrap_or(1) as usize;
        md.push_str(&format!("{}- {}\n", "  ".repeat(level.saturating_sub(1)), h.get("text").and_then(Value::as_str).unwrap_or_default()));
    }
    md
}

/// What went wrong while the page loaded and how it reads to a screen reader, for the README.
fn health_section(b: &Value) -> String {
    let list = |p: &str| b.pointer(p).and_then(Value::as_array).cloned().unwrap_or_default();
    let (errors, failed) = (list("/health/errors"), list("/health/failed_requests"));
    let mut md = String::from("## Page health\n\n");
    if errors.is_empty() && failed.is_empty() {
        md.push_str("It loaded without script errors or failed requests.\n\n");
    } else {
        for e in errors.iter().take(10) {
            md.push_str(&format!("- {} error: {}\n", e["kind"].as_str().unwrap_or("script"), e["text"].as_str().unwrap_or_default()));
        }
        for f in failed.iter().take(10) {
            let why = f["status"].as_u64().map(|s| s.to_string()).or_else(|| f["error"].as_str().map(String::from)).unwrap_or_default();
            md.push_str(&format!("- failed request ({why}): {}\n", f["url"].as_str().unwrap_or_default()));
        }
        md.push('\n');
    }
    if let Some(a) = b.get("a11y") {
        let n = |k: &str| a.get(k).and_then(Value::as_u64).unwrap_or(0);
        let lang = a.get("lang").and_then(Value::as_str).filter(|l| !l.is_empty()).unwrap_or("not set");
        md.push_str(&format!(
            "## Accessibility\n\nLanguage: {lang}. Controls without a name: {}. Pictures without alt text: {}.\n\n",
            n("unnamed_controls"),
            n("images_without_alt")
        ));
    }
    md
}

/// The widths the page's CSS switches layout at, for the README.
fn breakpoints_section(b: &Value) -> String {
    let bps: Vec<String> = b
        .pointer("/breakpoints")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|q| q.get("query").and_then(Value::as_str))
        .map(String::from)
        .collect();
    let unreadable = b.get("unreadable_stylesheets").and_then(Value::as_u64).unwrap_or(0);
    let body = match (bps.is_empty(), unreadable) {
        (true, 0) => "Its CSS has no width breakpoints.\n\n".to_string(),
        (true, u) => format!("None readable: {u} stylesheet(s) from other sites can't be read; compare the screenshots at each width.\n\n"),
        (false, _) => format!("Its CSS switches layout at: {}\n\n", bps.join(", ")),
    };
    format!("## Breakpoints\n\n{body}")
}

/// Breakpoints (not in a visitor's view) and the layout at each width, for the README.
fn layout_section(b: &Value, visitor: bool) -> String {
    let n = |v: &Value, k: &str| v.get(k).and_then(Value::as_u64).unwrap_or(0);
    let mut md = String::new();
    if !visitor {
        md.push_str(&breakpoints_section(b));
    }
    md.push_str("## Layout at each width\n\n");
    for l in b.pointer("/layouts").and_then(Value::as_array).into_iter().flatten() {
        let (w, pw) = (n(l, "width"), n(l, "page_w"));
        let ty = |k: &str| l.pointer(&format!("/type/{k}")).and_then(Value::as_u64).unwrap_or(0);
        let scroll = if pw > w + 1 { format!("page {pw} px wide, so it scrolls sideways") } else { "no sideways scroll".into() };
        md.push_str(&format!("### {w} px ({scroll})\n\nHeadings {}/{}/{} px, text {} px.\n\n", ty("h1"), ty("h2"), ty("h3"), ty("body")));
        for blk in l.get("blocks").and_then(Value::as_array).into_iter().flatten().take(16) {
            md.push_str(&format!("- {}\n", block_line(blk)));
        }
        md.push('\n');
    }
    md
}

/// One section at one width: `section "Pricing": padding 96 32 96 32, gap 24, 3 per row, column 1280 px at x 80`.
fn block_line(blk: &Value) -> String {
    let n = |v: &Value, k: &str| v.get(k).and_then(Value::as_u64).unwrap_or(0);
    let mut s = blk.get("tag").and_then(Value::as_str).unwrap_or("block").to_string();
    if let Some(h) = blk.get("heading").and_then(Value::as_str) {
        s.push_str(&format!(" \"{h}\""));
    }
    let pad: Vec<String> = blk.get("pad").and_then(Value::as_array).into_iter().flatten().map(|p| p.as_u64().unwrap_or(0).to_string()).collect();
    s.push_str(&format!(": padding {}", pad.join(" ")));
    if n(blk, "gap") > 0 {
        s.push_str(&format!(", gap {}", n(blk, "gap")));
    }
    if n(blk, "per_row") > 1 {
        s.push_str(&format!(", {} per row", n(blk, "per_row")));
    }
    if let Some(c) = blk.get("column") {
        s.push_str(&format!(", column {} px at x {}", n(c, "max_w"), n(c, "x")));
    }
    if let Some(bg) = blk.get("background").and_then(Value::as_str) {
        s.push_str(&format!(", background {bg}"));
    }
    s
}

// ---------------------------------------------------------------------------------------------
// web_site_close

#[derive(Debug, Default, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CloseParams {}

fn web_site_close(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let _: CloseParams = parse_params(params)?;
    let closed = ctx.session.ext.remove::<SiteBrowser>().is_some();
    Ok(ToolOutput::Value(json!({"closed": closed})))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_click_is_described_by_what_changed() {
        let before = json!({"expanded": "false", "selected": null, "open": null, "dialogs": 0, "url": "https://a.test/"});
        let menu = json!({"expanded": "true", "selected": null, "open": null, "dialogs": 0, "url": "https://a.test/"});
        assert_eq!(state_change(&before, &menu), vec!["expanded"]);
        let dialog = json!({"expanded": "false", "selected": null, "open": null, "dialogs": 1, "url": "https://a.test/"});
        assert_eq!(state_change(&before, &dialog), vec!["dialog appeared"]);
        let away = json!({"expanded": "false", "selected": null, "open": null, "dialogs": 0, "url": "https://a.test/other"});
        assert_eq!(state_change(&before, &away), vec!["address changed"]);
        let tab = json!({"selected": "true", "url": "https://a.test/"});
        assert_eq!(state_change(&json!({"selected": "false", "url": "https://a.test/"}), &tab), vec!["tab selected"]);
        assert!(state_change(&before, &before).is_empty());
        // The page scripts carry their placeholders.
        assert!(FIND_STATES_JS.contains("__MAX__") && STATE_JS.contains("__I__") && CLICK_STATE_JS.contains("__I__"));
        assert!(REMEMBER_TAB_JS.contains("__I__") && RESELECT_TAB_JS.contains("__I__"));
    }

    #[test]
    fn urls_are_checked() {
        assert!(check_url("https://example.com").is_ok());
        assert!(check_url(" http://a.b/c?d ").is_ok());
        for bad in ["example.com", "file:///etc/passwd", "javascript:alert(1)", "https://", "https:///x", "https://a b.com", "chrome://settings"] {
            assert!(check_url(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn truncation_keeps_char_boundaries() {
        assert_eq!(truncate_utf8("héllo", 2), "h");
        assert_eq!(truncate_utf8("abc", 10), "abc");
    }

    #[test]
    fn readme_lists_files_and_tokens() {
        let b = json!({"url": "https://ex.com/a?secret=1", "title": "Ex", "page": {"w": 1440, "h": 3000},
            "design": {"fonts": [{"value": "Inter", "count": 9}], "font_sizes": [], "text_colors": [], "backgrounds": [], "radii": []},
            "headings": [{"level": 1, "text": "Hello"}, {"level": 2, "text": "World"}]});
        let md = readme(&b, &[json!({"file": "screenshot-1440.png", "width": 1440, "height": 3000, "cut": false})], (10, 10), false);
        assert!(md.contains("screenshot-1440.png") && md.contains("`Inter`") && md.contains("  - World") && md.contains("page.html"));
        assert!(!md.contains("secret=1"), "query strings are not echoed");
        assert!(md.contains("no width breakpoints"), "{md}");
        assert!(!md.contains("cut at the size limit") && html_cut((10, 10)).is_none());
    }

    /// #336: HTML cut at the size limit is said in the evidence and the README.
    #[test]
    fn html_cut_at_the_limit_is_said() {
        let md = readme(&json!({}), &[], (MAX_HTML_BYTES, MAX_HTML_BYTES + 1174), false);
        assert!(md.contains(&format!("rendered HTML ({MAX_HTML_BYTES} bytes: the first part of {}, cut at the size limit)", MAX_HTML_BYTES + 1174)), "{md}");
        let l = html_cut((MAX_HTML_BYTES, MAX_HTML_BYTES + 1174)).unwrap();
        assert_eq!(l.code, "html_cut");
        assert!(l.message.contains("4 MiB"), "{}", l.message);
        assert!(html_cut((0, 0)).is_none());
    }

    #[test]
    fn page_health_keeps_errors_and_failed_requests_without_query_strings() {
        let ev = |method: &str, params: Value| CdpEvent { method: method.into(), params, session_id: None };
        let events = vec![
            ev("Network.requestWillBeSent", json!({"requestId": "7", "request": {"url": "https://ex.com/font.woff2?token=abc"}})),
            ev(
                "Runtime.exceptionThrown",
                json!({"exceptionDetails": {"text": "Uncaught", "url": "https://ex.com/app.js?v=2", "exception": {"description": "TypeError: x is undefined\n    at app.js:1"}}}),
            ),
            ev(
                "Runtime.exceptionThrown",
                json!({"exceptionDetails": {"text": "Uncaught", "exception": {"description": "TypeError: x is undefined\n    at app.js:9"}}}),
            ),
            ev(
                "Runtime.consoleAPICalled",
                json!({"type": "error", "args": [{"type": "string", "value": "Hydration failed"}, {"type": "object", "description": "Error"}]}),
            ),
            ev("Runtime.consoleAPICalled", json!({"type": "log", "args": [{"type": "string", "value": "hello"}]})),
            ev("Log.entryAdded", json!({"entry": {"level": "error", "source": "network", "text": "Failed to load resource: 404"}})),
            ev("Log.entryAdded", json!({"entry": {"level": "error", "source": "security", "text": "Mixed content blocked", "url": "https://ex.com/"}})),
            ev("Network.responseReceived", json!({"type": "Image", "response": {"url": "https://ex.com/logo.png?sig=1", "status": 404}})),
            ev("Network.responseReceived", json!({"type": "Document", "response": {"url": "https://ex.com/", "status": 200}})),
            ev("Network.loadingFailed", json!({"requestId": "7", "type": "Font", "errorText": "net::ERR_NAME_NOT_RESOLVED"})),
            ev("Network.loadingFailed", json!({"requestId": "8", "type": "Media", "errorText": "net::ERR_ABORTED", "canceled": true})),
        ];
        let h = page_health(&events);
        let texts: Vec<&str> = h["errors"].as_array().unwrap().iter().map(|e| e["text"].as_str().unwrap()).collect();
        assert_eq!(texts, ["TypeError: x is undefined", "Hydration failed Error", "Mixed content blocked"], "one line each, once, no network log noise");
        assert_eq!(h["errors"][0]["url"], "https://ex.com/app.js");
        let failed = h["failed_requests"].as_array().unwrap();
        assert_eq!(failed.len(), 2, "a 404 and a failed font; the cancelled load and the 200 aren't failures");
        assert_eq!(failed[0], json!({"url": "https://ex.com/logo.png", "status": 404, "type": "Image"}));
        assert_eq!(failed[1]["url"], "https://ex.com/font.woff2");
        assert!(!h.to_string().contains("token") && !h.to_string().contains("sig="), "no query strings");
        assert_eq!(page_health(&[]), json!({"errors": [], "failed_requests": []}));
        let md = readme(&json!({"health": h, "a11y": {"lang": "en", "unnamed_controls": 2, "images_without_alt": 1}}), &[], (0, 0), false);
        assert!(md.contains("- script error: TypeError: x is undefined") && md.contains("- failed request (404): https://ex.com/logo.png"), "{md}");
        assert!(md.contains("Language: en. Controls without a name: 2. Pictures without alt text: 1."), "{md}");
        assert!(readme(&json!({"health": page_health(&[])}), &[], (0, 0), false).contains("loaded without script errors"));
    }

    #[test]
    fn readme_shows_breakpoints_and_the_layout_at_each_width() {
        let b = json!({"url": "https://ex.com/", "breakpoints": [{"query": "min-width 768px", "px": 768, "count": 3}],
        "design": {"spacing": [{"value": "96px", "count": 20}], "max_widths": [{"value": "1280px", "count": 4}]},
        "assets": {"fonts": ["https://ex.com/f.woff2"]},
        "layouts": [
            {"width": 1440, "page_w": 1440, "type": {"h1": 64, "h2": 40, "h3": 24, "body": 16},
             "blocks": [{"tag": "section", "heading": "Plans", "pad": [96, 32, 96, 32], "gap": 24, "per_row": 3, "column": {"max_w": 1280, "x": 80}, "background": "#12181f"}]},
            {"width": 390, "page_w": 512, "type": {"h1": 40}, "blocks": [{"tag": "header", "pad": [16, 16, 16, 16], "per_row": 1}]}
        ]});
        let md = readme(&b, &[], (0, 0), false);
        assert!(md.contains("switches layout at: min-width 768px") && md.contains("`96px`") && md.contains("`1280px`") && md.contains("Font files: 1"), "{md}");
        assert!(md.contains("### 1440 px (no sideways scroll)") && md.contains("Headings 64/40/24 px, text 16 px"), "{md}");
        assert!(md.contains("- section \"Plans\": padding 96 32 96 32, gap 24, 3 per row, column 1280 px at x 80, background #12181f"), "{md}");
        assert!(md.contains("### 390 px (page 512 px wide, so it scrolls sideways)") && md.contains("- header: padding 16 16 16 16\n"), "{md}");
        let cross = readme(&json!({"unreadable_stylesheets": 2}), &[], (0, 0), false);
        assert!(cross.contains("2 stylesheet(s) from other sites"), "{cross}");
    }

    #[test]
    fn a_visitors_view_keeps_what_shows_and_drops_the_pages_code() {
        let mut b = json!({
            "title": "Plans", "meta": {"description": "hidden"}, "breakpoints": [{"query": "min-width 768px"}], "unreadable_stylesheets": 1,
            "health": {"errors": [{"text": "boom"}]}, "design": {"fonts": [{"value": "Inter", "count": 9}], "css_variables": {"--brand": "#123"}, "font_faces": [{"family": "Inter"}]},
            "assets": {"images": [{"src": "https://cdn.test/a.png", "w": 40, "h": 30, "alt": "logo"}], "scripts": ["https://cdn.test/app.js"], "requests": [{"url": "https://api.test/x"}]},
            "headings": [{"level": 1, "text": "Plans"}], "text": "Plans Pricing", "layouts": [{"width": 1440, "page_w": 1440}],
            "outline": [{"tag": "img", "class": "w-full rounded-xl", "src": "https://cdn.test/hero.webp?dpl=dpl_abc123#x"}, {"tag": "a", "class": "btn", "href": "https://shop.test/plans?ref=sk-test-123"}],
            "links": [{"text": "Plans", "href": "https://shop.test/plans?session=abc"}],
            "a11y": {"unnamed_examples": ["button.icon-btn", "a"]}
        });
        visitor_view(&mut b);
        // #156: the page's class names and the query strings on its addresses aren't a visitor's view.
        assert!(b["outline"].as_array().unwrap().iter().all(|i| i.get("class").is_none()));
        assert_eq!(b["outline"][0]["src"], "https://cdn.test/hero.webp");
        assert_eq!(b["outline"][1]["href"], "https://shop.test/plans");
        assert_eq!(b["links"][0]["href"], "https://shop.test/plans");
        assert_eq!(b["a11y"]["unnamed_examples"], json!(["button", "a"]));
        assert!(!b.to_string().contains("dpl_") && !b.to_string().contains("sk-test"));
        for gone in [
            "/meta",
            "/breakpoints",
            "/unreadable_stylesheets",
            "/health",
            "/design/css_variables",
            "/design/font_faces",
            "/assets/scripts",
            "/assets/requests",
            "/assets/images/0/src",
        ] {
            assert!(b.pointer(gone).is_none(), "{gone} isn't something a visitor sees");
        }
        assert_eq!((b["assets"]["images"][0]["w"].as_u64(), b["text"].as_str()), (Some(40), Some("Plans Pricing")));
        let md = readme(&b, &[], (0, 0), true);
        assert!(
            md.contains("Clean room: only what a visitor sees") && !md.contains("Breakpoints") && !md.contains("Page health") && !md.contains("page.html"),
            "{md}"
        );
        assert!(md.contains("### 1440 px"), "{md}");
    }

    #[test]
    fn capture_without_open_site_is_a_clear_error() {
        let e = crate::Engine::new(crate::testing::session());
        let r = e.call(
            "web_site_capture",
            json!({"output_directory": std::env::temp_dir().join("ca-never-created").display().to_string()}),
            crate::CallOptions::new(crate::Caller::Cli),
        );
        let err = r.err().map(|e| e.message).unwrap_or_default();
        assert!(err.contains("no website is open") || err.contains("Chromium") || err.contains("chromium"), "{err}");
    }

    /// #153: from the CLI, a site opened by an earlier command is gone, and the error says why and
    /// where the steps run together. A stand-in browser path gets past the engine check on any
    /// machine; nothing is started.
    #[test]
    fn a_cli_capture_without_a_site_says_each_command_starts_fresh() {
        let fix = |caller| {
            let mut s = crate::testing::session();
            s.settings.engines.tools.chromium = Some(std::env::current_exe().unwrap());
            let dir = tempfile::tempdir().unwrap();
            let out = dir.path().join("capture");
            let err = crate::Engine::new(s)
                .call("web_site_capture", json!({"output_directory": out.display().to_string()}), crate::CallOptions::new(caller))
                .unwrap_err();
            assert!(err.message.contains("no website is open"), "{err:?}");
            assert!(!out.exists());
            err.remediation.unwrap_or_default()
        };
        assert!(fix(crate::Caller::Cli).contains("Each CLI command starts its own browser") && fix(crate::Caller::Cli).contains("craft-anything-cli mcp"));
        assert_eq!(fix(crate::Caller::Mcp), "Open one first with web_site_open.");
    }

    /// A browser that exits as soon as it starts is reported at once, not after the whole wait,
    /// with what it said. The "browser" is a system program that rejects Chrome's arguments and
    /// exits, so no browser or window starts.
    #[test]
    fn a_browser_that_exits_at_once_is_reported_at_once() {
        let stand_in = if cfg!(windows) {
            std::path::PathBuf::from(std::env::var("SystemRoot").unwrap_or_else(|_| "C:\\Windows".into())).join("System32").join("where.exe")
        } else {
            std::path::PathBuf::from("/bin/false")
        };
        if !stand_in.is_file() {
            return;
        }
        let mut s = crate::testing::session();
        s.settings.engines.tools.chromium = Some(stand_in);
        let e = crate::Engine::new(s);
        let opts = crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted);
        let started = std::time::Instant::now();
        let err = e.call("web_site_open", json!({"url": "https://example.com", "timeout_secs": 60}), opts).err().unwrap();
        assert!(started.elapsed() < std::time::Duration::from_secs(20), "waited {:?}", started.elapsed());
        assert!(err.message.starts_with("Couldn't start the private browser") && err.message.contains("closed after"), "{}", err.message);
        assert!(err.remediation.is_some_and(|r| r.contains("Settings")));
    }

    /// #160: a section that only shows once it's scrolled into view is in the full-page picture.
    /// Live: it needs a Chromium-based browser, so it runs with `--ignored`.
    #[test]
    #[ignore]
    fn sections_shown_on_scroll_are_photographed() {
        use std::io::{Read, Write};
        let page = r#"<!doctype html><html><body style="margin:0">
<div style="height:1400px;background:#fff">Top</div>
<div id="late" style="height:600px;background:#fff">Shown on scroll</div>
<script>new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) e.target.style.background = '#ff0000'; })).observe(document.getElementById('late'));</script>
</body></html>"#;
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let url = format!("http://{}/", listener.local_addr().unwrap());
        std::thread::spawn(move || {
            for mut s in listener.incoming().flatten() {
                let mut buf = [0u8; 4096];
                let _ = s.read(&mut buf);
                let _ = write!(s, "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{page}", page.len());
            }
        });
        // In Clean room, a visitor's view: its evidence says so (#157).
        let mut s = crate::testing::live_session();
        s.settings.deep_mode = false;
        let e = crate::Engine::new(s);
        let cli = || crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted);
        e.call("web_site_open", json!({"url": url}), cli()).unwrap();
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("capture");
        let v = e.call("web_site_capture", json!({"output_directory": out.display().to_string(), "widths": [1440]}), cli()).unwrap().to_json();
        assert_eq!(v["environment"]["clean_room"], true, "{}", v["environment"]);
        let shot = web_common::decode_png(&std::fs::read(out.join("screenshot-1440.png")).unwrap()).unwrap();
        let at = |x: u32, y: u32| shot.rgba.get(((y * shot.width + x) * 4) as usize..((y * shot.width + x) * 4 + 3) as usize).unwrap().to_vec();
        assert_eq!(at(20, 1700), [255, 0, 0], "the section shown on scroll is in the picture");
        assert_eq!(at(20, 200), [255, 255, 255]);
    }

    /// #158: after a site fails to open, a capture refuses instead of photographing the browser's
    /// error page as if it were the site. Live: it needs a Chromium-based browser (`--ignored`).
    #[test]
    #[ignore]
    fn the_browsers_error_page_is_not_captured() {
        let e = crate::Engine::new(crate::testing::live_session());
        let cli = || crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted);
        // Nothing listens on port 1, so the browser shows its own error page.
        let _ = e.call("web_site_open", json!({"url": "http://127.0.0.1:1/"}), cli());
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("capture");
        let err = e.call("web_site_capture", json!({"output_directory": out.display().to_string(), "widths": [1440]}), cli()).unwrap_err();
        assert_eq!(err.code, ErrorCode::NotFound, "{}", err.message);
        assert!(err.message.contains("didn't open"), "{}", err.message);
        assert!(!out.exists(), "no folder is made for a capture that can't happen");
    }

    /// An engine with `page` open in a real browser, served from a local port. Live: it needs a
    /// Chromium-based browser, so it looks for one the way the app does.
    fn serve_and_open(page: &'static str) -> crate::Engine {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let url = format!("http://{}/", listener.local_addr().unwrap());
        std::thread::spawn(move || {
            for mut s in listener.incoming().flatten() {
                let mut buf = [0u8; 4096];
                let _ = s.read(&mut buf);
                let _ = write!(s, "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{page}", page.len());
            }
        });
        let e = crate::Engine::new(crate::testing::live_session());
        e.call("web_site_open", json!({"url": url}), crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted)).unwrap();
        e
    }

    /// #339: states captured at a phone width after a desktop width open the phone's own button,
    /// not the desktop one the earlier capture marked. Live (`--ignored`).
    #[test]
    #[ignore]
    fn states_at_a_second_width_open_that_widths_controls() {
        let e = serve_and_open(
            r#"<!doctype html><html><head><meta name="viewport" content="width=device-width"><style>
body{margin:0} .d{display:none} @media (min-width:800px){.d{display:block} .p{display:none}}
.panel{display:none;position:fixed;top:0;left:0;width:100%;height:200px}
</style></head><body style="padding-top:300px">
<button class="d" aria-expanded="false" data-panel="dp">Desktop options</button>
<button class="p" aria-expanded="false" data-panel="pp">Phone options</button>
<div id="dp" class="panel" style="background:#0000ff"></div><div id="pp" class="panel" style="background:#ff0000"></div>
<script>for (const b of document.querySelectorAll('button')) b.onclick = () => {
  const open = b.getAttribute('aria-expanded') !== 'true';
  b.setAttribute('aria-expanded', String(open));
  document.getElementById(b.dataset.panel).style.display = open ? 'block' : 'none';
};</script></body></html>"#,
        );
        let cli = || crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted);
        let dir = tempfile::tempdir().unwrap();
        let top_colour = |out: &Path| {
            let rows: Value = serde_json::from_str(&std::fs::read_to_string(out.join("states.json")).unwrap()).unwrap();
            let shot = web_common::decode_png(&std::fs::read(out.join("state-1.png")).unwrap()).unwrap();
            let at = shot.rgba.get(((10 * shot.width + 10) * 4) as usize..((10 * shot.width + 10) * 4 + 3) as usize).unwrap().to_vec();
            (rows["states"][0]["label"].as_str().unwrap().to_string(), at)
        };
        for (width, label, colour) in [(1440, "Desktop options", [0, 0, 255]), (390, "Phone options", [255, 0, 0])] {
            let out = dir.path().join(format!("states-{width}"));
            e.call("web_page_states_capture", json!({"output_directory": out.display().to_string(), "width": width, "max_states": 1}), cli()).unwrap();
            assert_eq!(top_colour(&out), (label.to_string(), colour.to_vec()), "at {width} px");
        }
        let _ = e.call("web_site_close", json!({}), cli());
    }

    /// #335: after photographing another tab, the tab that was selected is selected again, so the
    /// next capture finds the page as it was. Live (`--ignored`).
    #[test]
    #[ignore]
    fn the_tab_that_was_selected_is_selected_again() {
        let e = serve_and_open(
            r#"<!doctype html><html><body><div role="tablist">
<button role="tab" aria-selected="true">One</button><button role="tab" aria-selected="false">Two</button></div>
<script>const tabs = document.querySelectorAll('[role="tab"]');
for (const t of tabs) t.onclick = () => tabs.forEach(o => o.setAttribute('aria-selected', String(o === t)));</script></body></html>"#,
        );
        let cli = || crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted);
        let dir = tempfile::tempdir().unwrap();
        // Each capture opens the unselected tab: Two both times when One is selected again.
        for n in 1..=2 {
            let out = dir.path().join(format!("states-{n}"));
            e.call("web_page_states_capture", json!({"output_directory": out.display().to_string(), "max_states": 1}), cli()).unwrap();
            let rows: Value = serde_json::from_str(&std::fs::read_to_string(out.join("states.json")).unwrap()).unwrap();
            assert_eq!(rows["states"][0]["label"], "Two", "capture {n}: {rows}");
            assert_eq!(rows["states"][0]["changed"], json!(["tab selected"]), "capture {n}: {rows}");
        }
        let _ = e.call("web_site_close", json!({}), cli());
    }

    /// `capture.json` of `page`, served from a local port and captured at 1440 px. Live: it needs a
    /// Chromium-based browser.
    fn capture_of(page: &'static str) -> Value {
        let e = serve_and_open(page);
        let cli = || crate::CallOptions::new(crate::Caller::Cli).with_consent(crate::Consent::Granted);
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("capture");
        e.call("web_site_capture", json!({"output_directory": out.display().to_string(), "widths": [1440]}), cli()).unwrap();
        serde_json::from_str(&std::fs::read_to_string(out.join("capture.json")).unwrap()).unwrap()
    }

    /// #155: a pill made with `calc(infinity * 1px)` (Tailwind's `rounded-full`) is recorded as
    /// `9999px`, not the browser's clamped `3.35544e+07px`. Live (`--ignored`).
    #[test]
    #[ignore]
    fn an_endless_corner_radius_is_recorded_as_a_pill() {
        let page = r#"<!doctype html><html><body>
<a style="border-radius:calc(infinity * 1px);background:#1e66f5;padding:8px">One</a>
<a style="border-radius:calc(infinity * 1px) calc(infinity * 1px) 4px 4px;background:#1e66f5;padding:8px">Two</a>
<a style="border-radius:12px;background:#1e66f5;padding:8px">Three</a>
</body></html>"#;
        let capture = capture_of(page);
        let mut radii: Vec<&str> = capture["design"]["radii"].as_array().unwrap().iter().filter_map(|r| r["value"].as_str()).collect();
        radii.sort_unstable();
        assert_eq!(radii, ["12px", "9999px", "9999px 9999px 4px 4px"]);
    }

    /// #154: colours are the page's own CSS values, not a canvas read that can be off by one per
    /// channel; see-through ones keep their alpha. Live (`--ignored`).
    #[test]
    #[ignore]
    fn captured_colours_are_the_css_values() {
        let capture = capture_of(
            r#"<!doctype html><html><body style="background:#F5F2EC;color:#2D2B26"><p>Text</p><p style="background:rgba(30, 102, 245, 0.5)">Half</p></body></html>"#,
        );
        let values = |k: &str| capture["design"][k].as_array().unwrap().iter().filter_map(|c| c["value"].as_str().map(String::from)).collect::<Vec<_>>();
        assert!(values("backgrounds").contains(&"#f5f2ec".to_string()), "{:?}", values("backgrounds"));
        assert!(values("backgrounds").contains(&"#1e66f580".to_string()), "{:?}", values("backgrounds"));
        assert_eq!(values("text_colors"), ["#2d2b26"]);
    }
}
