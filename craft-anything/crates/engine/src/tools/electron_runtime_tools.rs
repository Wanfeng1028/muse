//! Electron and V8-inspector tools over loopback CDP.
//!
//! Electron apps and Node processes are started by the user (or, for the consent-gated walkthrough,
//! by us) with a remote-debugging / `--inspect` port. We attach to the loopback endpoint, observe
//! passively (the inspector sends exactly two commands), and bound every exchange.

use super::browser_tools::{self, CaptureFlags};
use super::native_common::spec;
use super::web_common::{self, Browser};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::cdp::{self, CdpClient, Deadline, INSPECTOR_MAX_MESSAGE, PAGE_MAX_MESSAGE, WsConn};
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, EvidenceBuilder, Limitation, Location, Subject, ToolError};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "js_electron_pages_list",
            "List Electron pages",
            "List the debuggable targets of an Electron app started with --remote-debugging-port (loopback), labelling renderer pages (file:// or app:// URLs) and other targets. Attach-only discovery over HTTP.",
            "See the windows inside a running Electron desktop app.",
            Toolset::Javascript,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<ElectronListParams>,
            js_electron_pages_list,
        ),
        spec(
            "js_electron_page_show",
            "Inspect an Electron page",
            "Passively inspect one Electron renderer page (a hostless file:// page) over CDP: frame origins, a DOM summary, parsed scripts (optionally their sources) and, opt-in, console entries. Never navigates or evaluates; values are never kept.",
            "Look inside one window of an Electron app without changing it.",
            Toolset::Javascript,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<ElectronInspectParams>,
            js_electron_page_show,
        ),
        spec(
            "js_electron_walkthrough_record",
            "Run a scripted Electron session",
            "Launch an Electron app's own executable with a private profile and a loopback debugging port, run a short script (wait / reload / navigate / click) against its first renderer, capture network request outlines, then terminate the owned process. Executes the app and accesses the network, so it needs your approval.",
            "Start an Electron app, click through a few steps and record what it does, with your permission.",
            Toolset::Javascript,
            Effects::EVIDENCE.union(Effects::EXECUTES_FOREIGN_CODE).union(Effects::ACCESSES_NETWORK).union(Effects::LAUNCHES_PROCESS),
            Requires::Nothing,
            schema_of::<ElectronWalkthroughParams>,
            js_electron_walkthrough_record,
        ),
        spec(
            "js_runtimes_list",
            "List JS runtime targets",
            "List the inspectable targets of a Node or Electron process started with --inspect (loopback V8 inspector endpoint), with their ids and whether another client is attached. Attach-only discovery.",
            "See which JavaScript processes you can observe.",
            Toolset::Javascript,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<RuntimeListParams>,
            js_runtimes_list,
        ),
        spec(
            "js_runtime_watch",
            "Observe a JS runtime",
            "Attach the V8 inspector to one Node/Electron target and observe passively: it sends exactly Runtime.enable and Debugger.enable, then records the scripts parsed (deduplicated and sorted), execution contexts and a parse-failure count. Never resumes a paused (--inspect-brk) target. runtime_kind is taken as given.",
            "Watch which scripts a running JavaScript program loads, without pausing or changing it.",
            Toolset::Javascript,
            Effects::NETWORK_EVIDENCE,
            Requires::Nothing,
            schema_of::<RuntimeObserveParams>,
            js_runtime_watch,
        ),
    ]
}

fn d_timeout() -> u64 {
    60
}

fn attach(ctx: &Ctx<'_>, endpoint: &Option<String>, dl: &Deadline) -> Result<Browser, ToolError> {
    let ep = endpoint.as_deref().map(str::trim).filter(|s| !s.is_empty()).ok_or_else(|| web_common::engine_missing("no CDP endpoint was given"))?;
    Browser::resolve(ctx, Some(ep), &web_common::LaunchOptions { allow_launch: false, ..web_common::LaunchOptions::default() }, dl)
}

/// Resolve a loopback endpoint from an optional field, or a clear EngineMissing.
fn require_endpoint(endpoint: &Option<String>) -> Result<cdp::Endpoint, ToolError> {
    let ep = endpoint.as_deref().map(str::trim).filter(|s| !s.is_empty()).ok_or_else(|| web_common::engine_missing("no CDP endpoint was given"))?;
    cdp::parse_endpoint(ep)
}

fn deadline(ctx: &Ctx<'_>, timeout_secs: u64) -> Result<Deadline, ToolError> {
    if !(1..=600).contains(&timeout_secs) {
        return Err(ToolError::invalid("timeout_secs must be 1..=600"));
    }
    Ok(Deadline::new(Duration::from_secs(timeout_secs), ctx.cancel.clone()))
}

// ---------------------------------------------------------------------------------------------
// js_electron_pages_list

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ElectronListParams {
    /// Loopback CDP endpoint of the Electron app (it must be started with --remote-debugging-port).
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn is_electron_renderer(url: &str) -> bool {
    url.starts_with("file://") || url.starts_with("app://") || url.starts_with("chrome-extension://")
}

fn js_electron_pages_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ElectronListParams = parse_params(params)?;
    let dl = deadline(ctx, p.timeout_secs)?;
    let browser = attach(ctx, &p.cdp_endpoint, &dl)?;
    let targets = cdp::json_list(&browser.endpoint, &dl)?;
    let runtime = web_common::runtime_of(&browser.product, &browser.user_agent);
    // A plain browser's file:// tabs aren't an app's renderer pages.
    let browser_only = matches!(runtime, "edge" | "chrome");
    let rows: Vec<Value> = targets
        .iter()
        .take(2000)
        .map(|t| {
            let url = t.get("url").and_then(Value::as_str).unwrap_or_default();
            json!({
                "id": t.get("id").and_then(Value::as_str).unwrap_or_default(),
                "type": t.get("type").and_then(Value::as_str).unwrap_or_default(),
                "url": web_common::sanitize_url(url),
                "title": t.get("title").and_then(Value::as_str).unwrap_or_default(),
                "is_renderer": !browser_only && is_electron_renderer(url),
                "has_debugger": t.get("webSocketDebuggerUrl").is_some(),
            })
        })
        .collect();
    let renderers = rows.iter().filter(|r| r["is_renderer"] == true).count();
    let summary = if browser_only {
        format!("{} target(s) at {}, but it is a plain {} browser ({}), not an Electron app.", rows.len(), browser.endpoint.origin, runtime, browser.product)
    } else {
        format!("{} Electron target(s) at {} ({renderers} renderer page(s)).", rows.len(), browser.endpoint.origin)
    };
    let ev = EvidenceBuilder::new(
        "js_electron_pages_list",
        Subject { kind: "electron".into(), sha256: None, name: Some(browser.endpoint.origin.clone()) },
        web_common::cdp_env(ctx.session.clean_room(), Some(browser.version.clone())),
    )
    .params(json!({"cdp_endpoint": browser.endpoint.origin}))
    .result(json!({"endpoint": browser.endpoint.origin, "product": browser.product, "runtime": runtime, "targets": rows}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OutsideService)
    .coverage(Coverage::complete(rows.len() as u64))
    .location(Location::new("url", browser.endpoint.origin.clone()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// js_electron_page_show

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ElectronInspectParams {
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    /// The renderer target id (from js_electron_pages_list); the first renderer otherwise.
    #[serde(default)]
    pub target_id: Option<String>,
    #[serde(default = "d_window")]
    pub watch_ms: u64,
    #[serde(default)]
    pub with_script_text: bool,
    #[serde(default)]
    pub with_console_text: bool,
    #[serde(default)]
    pub hidden_values: Vec<String>,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn d_window() -> u64 {
    100
}

fn js_electron_page_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ElectronInspectParams = parse_params(params)?;
    let dl = deadline(ctx, p.timeout_secs)?;
    let browser = attach(ctx, &p.cdp_endpoint, &dl)?;
    let targets = cdp::json_list(&browser.endpoint, &dl)?;
    // Pick a renderer: the requested id, else the first file://-like page.
    let target = match &p.target_id {
        Some(id) => web_common::pick_target(&targets, Some(id), None)?,
        None => targets
            .iter()
            .find(|t| t.get("type").and_then(Value::as_str) == Some("page") && is_electron_renderer(t.get("url").and_then(Value::as_str).unwrap_or_default()))
            .ok_or_else(|| {
                ToolError::new(craft_anything_evidence::ErrorCode::NotFound, "no Electron renderer page (file://) was found")
                    .with_remediation("Open a window in the app, or pass an explicit target_id.")
            })?,
    };
    let url = target.get("url").and_then(Value::as_str).unwrap_or_default();
    if !is_electron_renderer(url) {
        return Err(ToolError::new(
            craft_anything_evidence::ErrorCode::NotSupported,
            format!("target {} is not a local renderer page", web_common::sanitize_url(url)),
        )
        .with_remediation("js_electron_page_show only inspects hostless file:// / app:// renderer pages."));
    }
    let page_url = web_common::sanitize_url(url);
    let mut client = web_common::connect_target(&browser, target, PAGE_MAX_MESSAGE, &dl)?;
    let flags = CaptureFlags { script_sources: p.with_script_text, console: true, console_text: p.with_console_text, network: true, ..CaptureFlags::default() };
    let mut secrets = web_common::Secrets::new(&p.hidden_values);
    let cap = browser_tools::capture_page(&mut client, &page_url, flags, p.watch_ms, &mut secrets, ctx, &dl);
    browser_tools::cleanup(&mut client, &dl);
    let cap = cap?;
    let scripts_n = cap.result["scripts"].as_array().map_or(0, Vec::len);
    let summary = format!("Inspected Electron page {page_url}: {scripts_n} script(s).");
    let ev = EvidenceBuilder::new(
        "js_electron_page_show",
        Subject { kind: "electron".into(), sha256: None, name: Some(page_url.clone()) },
        web_common::cdp_env(ctx.session.clean_room(), Some(browser.version.clone())),
    )
    .params(json!({"endpoint": browser.endpoint.origin, "target_id": p.target_id, "sensitive_value_declarations": p.hidden_values.len()}))
    .result(cap.result)
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::EarlierRecord)
    .limitation(Limitation::new("passive_snapshot", "A passive look at one renderer window; the main process and IPC are not observed here."))
    .limitation(Limitation::new("values_not_kept", "Cookies, auth headers and storage values are never kept; declared secrets are redacted."))
    .coverage(Coverage { status: CoverageStatus::Partial, examined: None, total: None, next_offset: None })
    .location(Location::new("url", page_url))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// js_electron_walkthrough_record (active, consent-gated)

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case", tag = "kind")]
pub enum ElectronAction {
    Wait { ms: u64 },
    Reload,
    Navigate { url: String },
    Click { selector: String },
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ElectronWalkthroughParams {
    /// Absolute path of the Electron app's executable to launch.
    pub application_executable: String,
    /// Extra arguments passed to the app after the debugging flags.
    #[serde(default)]
    pub args: Vec<String>,
    /// The scripted actions (1..=100).
    pub actions: Vec<ElectronAction>,
    #[serde(default = "yes")]
    pub capture_network: bool,
    #[serde(default)]
    pub hidden_values: Vec<String>,
    #[serde(default = "d_action_ms")]
    pub action_timeout_ms: u64,
    /// Seconds to wait for the app to start its debugging port.
    #[serde(default = "d_startup")]
    pub startup_secs: u64,
    #[serde(default = "d_walkthrough_timeout")]
    pub timeout_secs: u64,
}

fn yes() -> bool {
    true
}
fn d_action_ms() -> u64 {
    15_000
}
fn d_startup() -> u64 {
    60
}
fn d_walkthrough_timeout() -> u64 {
    180
}

fn js_electron_walkthrough_record(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ElectronWalkthroughParams = parse_params(params)?;
    if p.actions.is_empty() || p.actions.len() > 100 {
        return Err(ToolError::invalid("actions must be 1..=100"));
    }
    let exe = super::artifact_tools::abs_path(&p.application_executable, "application_executable")?;
    let dl = deadline(ctx, p.timeout_secs)?;
    let browser = Browser::launch_app(ctx, &exe, &p.args, p.startup_secs, &dl)?;
    // Find the first renderer page.
    let targets = cdp::json_list(&browser.endpoint, &dl)?;
    let target = targets
        .iter()
        .find(|t| t.get("type").and_then(Value::as_str) == Some("page"))
        .ok_or_else(|| ToolError::new(craft_anything_evidence::ErrorCode::NotFound, "the launched app exposed no renderer page"))?;
    let start_url = web_common::sanitize_url(target.get("url").and_then(Value::as_str).unwrap_or_default());
    let mut client = web_common::connect_target(&browser, target, PAGE_MAX_MESSAGE, &dl)?;
    let mut secrets = web_common::Secrets::new(&p.hidden_values);
    let _ = client.call("Page.enable", json!({}), None, &dl);
    let _ = client.call("DOM.enable", json!({}), None, &dl);
    if p.capture_network {
        let _ = client.call("Network.enable", json!({}), None, &dl);
    }
    let mut steps: Vec<Value> = Vec::new();
    let mut aborted: Option<String> = None;
    for (i, action) in p.actions.iter().enumerate() {
        if dl.expired() {
            aborted = Some("the overall deadline passed".into());
            break;
        }
        ctx.report(Some(i as f32 / p.actions.len() as f32), format!("electron step {}", i + 1));
        let step_dl = Deadline::new(Duration::from_millis(p.action_timeout_ms.clamp(1, 120_000)), ctx.cancel.clone());
        let outcome = run_electron_action(&mut client, action, &step_dl);
        let mut step = json!({"index": i, "action": electron_action_name(action), "status": if outcome.is_ok() { "ok" } else { "error" }});
        if let Err(e) = &outcome {
            step["error"] = json!(e.message);
            aborted = Some(format!("step {} failed", i + 1));
        }
        steps.push(step);
        if outcome.is_err() {
            break;
        }
    }
    let network = if p.capture_network {
        let events = client.take_events();
        let mut dropped = 0u64;
        browser_tools::collect_network(&mut client, &events, false, browser_tools::NetworkContent::default(), &mut secrets, &dl, &mut dropped)
    } else {
        Value::Null
    };
    browser_tools::cleanup(&mut client, &dl);
    let ok_steps = steps.iter().filter(|s| s["status"] == "ok").count();
    let summary =
        format!("Ran {} of {} step(s) in the Electron app{}.", ok_steps, p.actions.len(), aborted.as_ref().map(|a| format!(" ({a})")).unwrap_or_default());
    let ev = EvidenceBuilder::new(
        "js_electron_walkthrough_record",
        Subject { kind: "electron".into(), sha256: None, name: exe.file_name().map(|n| n.to_string_lossy().into_owned()) },
        web_common::cdp_env(ctx.session.clean_room(), Some(browser.version.clone())),
    )
    .params(json!({"application_executable": p.application_executable, "action_count": p.actions.len(), "sensitive_value_declarations": p.hidden_values.len()}))
    .result(json!({
        "browser": {"started_by": "craft-anything", "cleanup": "closed", "product": browser.product},
        "start_url": start_url,
        "steps": steps,
        "network": network,
        "aborted": aborted,
        "secret_redactions": secrets.redactions,
    }))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OurRun)
    .limitation(Limitation::new("controlled_run", "One controlled run of scripted steps against a launched copy of the app."))
    .limitation(Limitation::new("renderer_only", "Only the first renderer window is driven; the main process and IPC are not captured here."))
    .coverage(Coverage::complete(p.actions.len() as u64))
    .location(Location::new("path", p.application_executable))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn electron_action_name(a: &ElectronAction) -> &'static str {
    match a {
        ElectronAction::Wait { .. } => "wait",
        ElectronAction::Reload => "reload",
        ElectronAction::Navigate { .. } => "navigate",
        ElectronAction::Click { .. } => "click",
    }
}

fn run_electron_action(client: &mut CdpClient, action: &ElectronAction, dl: &Deadline) -> Result<(), ToolError> {
    match action {
        ElectronAction::Wait { ms } => {
            let settle = Deadline::new(Duration::from_millis((*ms).min(120_000)), crate::tool::CancelToken::default());
            let _ = client.pump_until(&settle);
            Ok(())
        }
        ElectronAction::Reload => client.call("Page.reload", json!({}), None, dl).map(|_| ()),
        ElectronAction::Navigate { url } => {
            if !(url.starts_with("http://") || url.starts_with("https://") || url.starts_with("file://") || url.starts_with("app://")) {
                return Err(ToolError::invalid("navigate url must be http(s), file or app"));
            }
            client.call("Page.navigate", json!({"url": url}), None, dl).map(|_| ())
        }
        ElectronAction::Click { selector } => {
            let (x, y) = browser_tools::element_center(client, selector, dl)?;
            browser_tools::click_at(client, x, y, dl)
        }
    }
}

// ---------------------------------------------------------------------------------------------
// js_runtimes_list

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RuntimeListParams {
    /// Loopback V8 inspector endpoint, e.g. http://127.0.0.1:9229 (node --inspect=127.0.0.1:9229).
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn js_runtimes_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RuntimeListParams = parse_params(params)?;
    let dl = deadline(ctx, p.timeout_secs)?;
    let endpoint = require_endpoint(&p.cdp_endpoint)?;
    let targets = cdp::json_list(&endpoint, &dl)?;
    let rows: Vec<Value> = targets
        .iter()
        .take(500)
        .map(|t| {
            json!({
                "id": t.get("id").and_then(Value::as_str).unwrap_or_default(),
                "type": t.get("type").and_then(Value::as_str).unwrap_or_default(),
                "url": web_common::sanitize_url(t.get("url").and_then(Value::as_str).unwrap_or_default()),
                // Node omits `attached`; store null (unknown) rather than inventing a value.
                "attached": t.get("attached").cloned().unwrap_or(Value::Null),
                "has_debugger": t.get("webSocketDebuggerUrl").is_some(),
            })
        })
        .collect();
    let summary = format!("{} JavaScript runtime target(s) at {}.", rows.len(), endpoint.origin);
    let ev = EvidenceBuilder::new(
        "js_runtimes_list",
        Subject { kind: "javascript-runtime".into(), sha256: None, name: Some(endpoint.origin.clone()) },
        web_common::cdp_env(ctx.session.clean_room(), None),
    )
    .params(json!({"cdp_endpoint": endpoint.origin}))
    .result(json!({"endpoint": endpoint.origin, "targets": rows}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OutsideService)
    .coverage(Coverage::complete(rows.len() as u64))
    .location(Location::new("url", endpoint.origin.clone()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// js_runtime_watch (V8 inspector)

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum RuntimeKind {
    Node,
    ElectronMain,
    ElectronPreload,
    ElectronRenderer,
    Unknown,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RuntimeObserveParams {
    #[serde(default)]
    pub cdp_endpoint: Option<String>,
    /// The target id to observe (from js_runtimes_list); the first otherwise.
    #[serde(default)]
    pub target_id: Option<String>,
    /// The kind of runtime, as given (not checked).
    #[serde(default = "unknown_kind")]
    pub runtime_kind: RuntimeKind,
    #[serde(default = "d_window")]
    pub watch_ms: u64,
    #[serde(default = "d_timeout")]
    pub timeout_secs: u64,
}

fn unknown_kind() -> RuntimeKind {
    RuntimeKind::Unknown
}

fn kind_str(k: RuntimeKind) -> &'static str {
    match k {
        RuntimeKind::Node => "node",
        RuntimeKind::ElectronMain => "electron-main",
        RuntimeKind::ElectronPreload => "electron-preload",
        RuntimeKind::ElectronRenderer => "electron-renderer",
        RuntimeKind::Unknown => "unknown",
    }
}

fn js_runtime_watch(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RuntimeObserveParams = parse_params(params)?;
    let dl = deadline(ctx, p.timeout_secs)?;
    let endpoint = require_endpoint(&p.cdp_endpoint)?;
    let targets = cdp::json_list(&endpoint, &dl)?;
    let target = web_common::pick_target(&targets, p.target_id.as_deref(), None)?;
    if target.get("attached").and_then(Value::as_bool) == Some(true) {
        return Err(ToolError::new(craft_anything_evidence::ErrorCode::EngineMissing, "another debugger is already attached to this target")
            .with_remediation("Detach the other client, or pick a target with attached:false."));
    }
    let ws_url = target
        .get("webSocketDebuggerUrl")
        .and_then(Value::as_str)
        .ok_or_else(|| ToolError::new(craft_anything_evidence::ErrorCode::EngineMissing, "the target has no inspector WebSocket URL"))?;
    let wt = cdp::ws_target(ws_url, &endpoint)?;
    let conn = WsConn::connect(&wt, INSPECTOR_MAX_MESSAGE, &dl)?;
    let mut client = CdpClient::new(conn);
    // Exactly two commands. Never Runtime.runIfWaitingForDebugger.
    let _ = client.call("Runtime.enable", json!({}), None, &dl)?;
    let _ = client.call("Debugger.enable", json!({}), None, &dl)?;
    let window = browser_tools::window_deadline(ctx, p.watch_ms, &dl);
    client.pump_until(&window)?;
    let events = client.take_events();
    client.close(&dl);

    // Deterministic output: dedup + sort scripts by url; exclude protocol ids and timestamps.
    let mut scripts: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    let mut unresolved: Vec<Value> = Vec::new();
    let mut contexts: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    let mut parse_failures = 0u64;
    for ev in &events {
        match ev.method.as_str() {
            "Debugger.scriptParsed" => {
                let url = ev.params.get("url").and_then(Value::as_str).unwrap_or_default();
                if url.is_empty() {
                    continue;
                }
                if is_unresolvable_file_url(url) {
                    unresolved.push(json!({"kind": "unresolved", "reported_url": web_common::sanitize_url(url), "reason": "file-url-unchecked"}));
                } else {
                    scripts.insert(web_common::sanitize_url(url));
                }
            }
            "Debugger.scriptFailedToParse" => parse_failures += 1,
            "Runtime.executionContextCreated" => {
                if let Some(name) = ev.params.pointer("/context/name").and_then(Value::as_str) {
                    contexts.insert(name.to_string());
                }
            }
            _ => {}
        }
    }
    let scripts: Vec<String> = scripts.into_iter().take(50_000).collect();
    unresolved.sort_by(|a, b| a["reported_url"].as_str().unwrap_or("").cmp(b["reported_url"].as_str().unwrap_or("")));
    let kind = kind_str(p.runtime_kind).to_string();
    let summary = format!(
        "Observed a {kind} runtime at {}: {} script(s), {} context(s), {parse_failures} parse failure(s).",
        endpoint.origin,
        scripts.len(),
        contexts.len()
    );
    let ev = EvidenceBuilder::new(
        "js_runtime_watch",
        Subject { kind: "javascript-runtime".into(), sha256: None, name: Some(endpoint.origin.clone()) },
        web_common::cdp_env(ctx.session.clean_room(), None),
    )
    .params(json!({"cdp_endpoint": endpoint.origin, "runtime_kind": kind, "watch_ms": p.watch_ms}))
    .result(json!({
        "endpoint": endpoint.origin,
        "runtime_kind": kind,
        "kind_source": "as-given",
        "scripts": scripts,
        "unresolved_scripts": unresolved,
        "execution_contexts": contexts.into_iter().collect::<Vec<_>>(),
        "parse_failures": parse_failures,
        "dropped_events": client.dropped_events(),
    }))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::EarlierRecord)
    .limitation(Limitation::new(
        "two_commands_only",
        "Only Runtime.enable and Debugger.enable were sent; a paused (--inspect-brk) target is never resumed, so it may report nothing.",
    ))
    .limitation(Limitation::new("runtime_kind_unverified", "runtime_kind is what the caller declared; it is not verified against the process."))
    .coverage(Coverage { status: CoverageStatus::Partial, examined: Some(scripts.len() as u64), total: None, next_offset: None })
    .location(Location::new("url", endpoint.origin.clone()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

/// Node file URLs that cannot be mapped to a verifiable location (Windows paths, ambiguous).
fn is_unresolvable_file_url(url: &str) -> bool {
    url.starts_with("file://") && (url.contains(":\\") || url.contains("%5C"))
}
