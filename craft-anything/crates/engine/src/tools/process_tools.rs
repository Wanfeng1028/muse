//! Running programs: capture a program under a pseudo-terminal with a scripted timeline, and
//! compare two captures. Capture executes foreign code, so it is consent-gated.

use super::artifact_tools::resolve_evidence_input;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{
    Authority, Confidence, Coverage, CoverageStatus, Environment, EvidenceBuilder, Limitation, Location, Subject, ToolError, host_triple,
};
use craft_anything_platform::capture::{self, Event, EventKind, Limits, SandboxRequest, Sig, Spec, Terminal};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::sync::Arc;
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "runtime_walkthrough_record",
            title: "Run and watch a program",
            summary: "Run a program under a terminal with a scripted timeline of typed input, resizes and signals, then record the terminal screen, exit, and (opt-in) which files changed. Values that change every run (process ids, loopback ports, 10 ms time buckets; optionally paths and literal patterns) are normalised so two runs compare. Bounded by time, output and files; the whole process group is killed on timeout or cancel. Runs code, so it needs your OK.",
            beginner: "Actually run the program in a safe, watched sandbox and see what it does on screen and which files it touches.",
            toolset: Toolset::Runtime,
            // Runs code from the target -> consent-gated.
            effects: Effects::MUTATES_SESSION.union(Effects::WRITES_FILESYSTEM).union(Effects::LAUNCHES_PROCESS).union(Effects::EXECUTES_FOREIGN_CODE),
            requires: Requires::Nothing,
            input_schema: schema_of::<CaptureParams>,
            run: runtime_walkthrough_record,
        },
        ToolSpec {
            id: "runtime_captures_compare",
            title: "Compare two runs",
            summary: "Compare two runtime_walkthrough_record evidence records dimension by dimension (terminal, exit, filesystem, events) and report what changed. Pure; no program is run.",
            beginner: "See what differs between two runs of a program.",
            toolset: Toolset::Runtime,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<CompareParams>,
            run: runtime_captures_compare,
        },
    ]
}

// --------------------------------------------------------------------------------------------
// runtime_walkthrough_record

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CaptureParams {
    /// The program to run (absolute path or a name resolved on PATH).
    pub executable: String,
    #[serde(default)]
    pub arguments: Vec<String>,
    /// Working directory (absolute). Defaults to the program's own default.
    #[serde(default)]
    pub working_directory: Option<String>,
    /// Extra environment variables applied on top of the inherited environment.
    #[serde(default)]
    pub environment: std::collections::BTreeMap<String, String>,
    /// Absolute paths to snapshot before and after (opt-in). File contents are never read; only
    /// path, size and sha256.
    #[serde(default)]
    pub watched_paths: Vec<String>,
    #[serde(default)]
    pub terminal: TerminalParams,
    /// Scripted events, ordered by `at_ms`.
    #[serde(default)]
    pub events: Vec<EventParams>,
    #[serde(default = "d_timeout")]
    pub timeout_ms: u64,
    #[serde(default = "d_timeout")]
    pub idle_timeout_ms: u64,
    #[serde(default = "d_settle")]
    pub settle_ms: u64,
    /// 0 = SIGKILL at the deadline; > 0 = SIGTERM, wait this long, then SIGKILL.
    #[serde(default)]
    pub finish_ms: u64,
    #[serde(default)]
    pub limits: LimitsParams,
    /// Run inside bubblewrap if it is installed (recorded honestly either way).
    #[serde(default)]
    pub sandbox: bool,
    /// Make two runs comparable: replace values that change every run (on by default for process
    /// ids, ports and 10 ms time buckets).
    #[serde(default)]
    pub normalization: NormalizationParams,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields, default)]
pub struct NormalizationParams {
    /// Replace the run's process ids with <pid>.
    pub pids: bool,
    /// Replace ports after localhost, 127.0.0.1, 0.0.0.0 and [::1] with <port>.
    pub ports: bool,
    /// Replace the working directory and the temp folder with <cwd> and <tmp>.
    pub paths: bool,
    /// Literal replacements (no patterns), applied last; at most 100.
    pub patterns: Vec<LiteralRule>,
    /// Round event dispatch times down to this many milliseconds (0 keeps them exact).
    pub time_step_ms: u64,
}

impl Default for NormalizationParams {
    fn default() -> Self {
        NormalizationParams { pids: true, ports: true, paths: false, patterns: Vec::new(), time_step_ms: 10 }
    }
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct LiteralRule {
    pub pattern: String,
    pub replacement: String,
}

/// Replace `num` where it stands alone (not inside a longer number); returns the count.
fn replace_number(text: &mut String, num: &str, with: &str) -> u64 {
    let mut out = String::with_capacity(text.len());
    let mut rest = text.as_str();
    let mut n = 0;
    while let Some(i) = rest.find(num) {
        let (before, after) = (rest.get(..i).unwrap_or_default(), rest.get(i + num.len()..).unwrap_or_default());
        let alone = !before.ends_with(|c: char| c.is_ascii_digit()) && !after.starts_with(|c: char| c.is_ascii_digit());
        out.push_str(before);
        out.push_str(if alone { with } else { num });
        n += u64::from(alone);
        rest = after;
    }
    out.push_str(rest);
    *text = out;
    n
}

/// Replace the digits after each loopback host with <port>; returns the count.
fn replace_ports(text: &mut String) -> u64 {
    let mut n = 0;
    for host in ["localhost:", "127.0.0.1:", "0.0.0.0:", "[::1]:"] {
        let mut out = String::with_capacity(text.len());
        let mut rest = text.as_str();
        while let Some(i) = rest.find(host) {
            let end = i + host.len();
            out.push_str(rest.get(..end).unwrap_or_default());
            let after = rest.get(end..).unwrap_or_default();
            let digits = after.len() - after.trim_start_matches(|c: char| c.is_ascii_digit()).len();
            if digits > 0 {
                out.push_str("<port>");
                n += 1;
            }
            rest = after.get(digits..).unwrap_or_default();
        }
        out.push_str(rest);
        *text = out;
    }
    n
}

/// Normalise a capture's text and timings in place; returns how many of each were replaced.
fn normalize_capture(result: &mut Value, n: &NormalizationParams, pids: &[u32], paths: &[(String, &str)]) -> Value {
    let mut counts = std::collections::BTreeMap::from([("pids", 0u64), ("ports", 0), ("paths", 0), ("patterns", 0), ("times", 0)]);
    let text = |s: &mut String, counts: &mut std::collections::BTreeMap<&str, u64>| {
        if n.paths {
            for (path, alias) in paths.iter().filter(|(p, _)| !p.is_empty()) {
                let hits = s.matches(path.as_str()).count() as u64;
                if hits > 0 {
                    *s = s.replace(path.as_str(), alias);
                    *counts.entry("paths").or_default() += hits;
                }
            }
        }
        if n.pids {
            for pid in pids {
                *counts.entry("pids").or_default() += replace_number(s, &pid.to_string(), "<pid>");
            }
        }
        if n.ports {
            *counts.entry("ports").or_default() += replace_ports(s);
        }
        for rule in &n.patterns {
            let hits = s.matches(rule.pattern.as_str()).count() as u64;
            if hits > 0 {
                *s = s.replace(rule.pattern.as_str(), &rule.replacement);
                *counts.entry("patterns").or_default() += hits;
            }
        }
    };
    for v in result.pointer_mut("/terminal/lines").and_then(Value::as_array_mut).into_iter().flatten() {
        if let Value::String(s) = v {
            text(s, &mut counts);
        }
    }
    for e in result.get_mut("events").and_then(Value::as_array_mut).into_iter().flatten() {
        if let Some(Value::String(s)) = e.get_mut("detail") {
            text(s, &mut counts);
        }
        if n.time_step_ms > 0
            && let Some(t) = e.get("sent_at_ms").and_then(Value::as_u64)
        {
            e["sent_at_ms"] = json!(t - t % n.time_step_ms);
            *counts.entry("times").or_default() += 1;
        }
    }
    json!(counts)
}

fn d_timeout() -> u64 {
    30_000
}
fn d_settle() -> u64 {
    100
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TerminalParams {
    #[serde(default = "d_cols")]
    pub columns: u16,
    #[serde(default = "d_rows")]
    pub rows: u16,
    #[serde(default = "d_scrollback")]
    pub scrollback: usize,
}

fn d_cols() -> u16 {
    80
}
fn d_rows() -> u16 {
    24
}
fn d_scrollback() -> usize {
    1000
}

impl Default for TerminalParams {
    fn default() -> Self {
        TerminalParams { columns: 80, rows: 24, scrollback: 1000 }
    }
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum EventParams {
    Input {
        at_ms: u64,
        /// Text to type. A trailing newline is not added for you.
        data: String,
        #[serde(default)]
        sensitive: bool,
    },
    Resize {
        at_ms: u64,
        columns: u16,
        rows: u16,
    },
    Signal {
        at_ms: u64,
        signal: SignalParam,
    },
}

#[derive(Debug, Clone, Copy, Deserialize, JsonSchema)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum SignalParam {
    Sigint,
    Sigterm,
    Sigkill,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct LimitsParams {
    #[serde(default = "d_output")]
    pub output_bytes: usize,
    #[serde(default = "d_files")]
    pub files: usize,
    #[serde(default = "d_file_bytes")]
    pub file_bytes: u64,
    #[serde(default = "d_depth")]
    pub watch_depth: usize,
}

fn d_output() -> usize {
    1_000_000
}
fn d_files() -> usize {
    10_000
}
fn d_file_bytes() -> u64 {
    10_000_000
}
fn d_depth() -> usize {
    16
}

impl Default for LimitsParams {
    fn default() -> Self {
        LimitsParams { output_bytes: 1_000_000, files: 10_000, file_bytes: 10_000_000, watch_depth: 16 }
    }
}

/// A sane ceiling so a single capture can never tie the machine up for too long.
const MAX_TIMEOUT_MS: u64 = 600_000;

fn runtime_walkthrough_record(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CaptureParams = parse_params(params)?;
    if p.executable.trim().is_empty() {
        return Err(ToolError::invalid("executable is empty"));
    }
    if p.timeout_ms == 0 || p.timeout_ms > MAX_TIMEOUT_MS {
        return Err(ToolError::invalid(format!("timeout_ms must be 1..={MAX_TIMEOUT_MS}")));
    }
    for k in p.environment.keys() {
        if k == capture::RUN_ID_ENV {
            return Err(ToolError::invalid(format!("{} is reserved for run ownership", capture::RUN_ID_ENV)));
        }
        if k.is_empty() || k.contains('=') || k.contains('\0') {
            return Err(ToolError::invalid(format!("invalid environment name {k:?}")));
        }
    }
    for path in &p.watched_paths {
        if !std::path::Path::new(path).is_absolute() {
            return Err(ToolError::invalid(format!("observation path must be absolute: {path}")));
        }
    }
    if let Some(wd) = &p.working_directory
        && !std::path::Path::new(wd).is_absolute()
    {
        return Err(ToolError::invalid("working_directory must be absolute"));
    }

    if p.normalization.patterns.len() > 100 || p.normalization.patterns.iter().any(|r| r.pattern.is_empty()) {
        return Err(ToolError::invalid("normalization.patterns: at most 100, each with a non-empty pattern"));
    }
    let terminal = Terminal { cols: p.terminal.columns, rows: p.terminal.rows, scrollback: p.terminal.scrollback };
    terminal.validate()?;

    let mut events = Vec::with_capacity(p.events.len());
    let mut last_at = 0u64;
    for ev in &p.events {
        let (at_ms, kind) = match ev {
            EventParams::Input { at_ms, data, sensitive } => (*at_ms, EventKind::Input { data: data.clone().into_bytes(), sensitive: *sensitive }),
            EventParams::Resize { at_ms, columns, rows } => {
                let t = Terminal { cols: *columns, rows: *rows, scrollback: p.terminal.scrollback };
                t.validate()?;
                (*at_ms, EventKind::Resize { cols: *columns, rows: *rows })
            }
            EventParams::Signal { at_ms, signal } => (
                *at_ms,
                EventKind::Signal(match signal {
                    SignalParam::Sigint => Sig::Int,
                    SignalParam::Sigterm => Sig::Term,
                    SignalParam::Sigkill => Sig::Kill,
                }),
            ),
        };
        if at_ms < last_at {
            return Err(ToolError::invalid("events must be ordered by at_ms"));
        }
        if at_ms > p.timeout_ms {
            return Err(ToolError::invalid("an event is scheduled after timeout_ms"));
        }
        last_at = at_ms;
        events.push(Event { at_ms, kind });
    }

    let spec = Spec {
        executable: p.executable.clone().into(),
        args: p.arguments.iter().map(Into::into).collect(),
        cwd: p.working_directory.clone().map(Into::into),
        env: p.environment.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
        terminal,
        events,
        timeout: Duration::from_millis(p.timeout_ms),
        idle_timeout: Duration::from_millis(p.idle_timeout_ms),
        settle: Duration::from_millis(p.settle_ms),
        finalization: Duration::from_millis(p.finish_ms),
        observation_paths: p.watched_paths.iter().map(Into::into).collect(),
        limits: Limits { output_bytes: p.limits.output_bytes, files: p.limits.files, file_bytes: p.limits.file_bytes, watch_depth: p.limits.watch_depth },
        sandbox: if p.sandbox { SandboxRequest::IfAvailable } else { SandboxRequest::Off },
    };

    let ct = ctx.cancel.clone();
    let cancel: craft_anything_platform::process::Cancel = Arc::new(move || ct.is_cancelled());
    ctx.report(Some(0.0), "running the program");
    let cap = capture::capture(spec, cancel)?;

    let mut result = serde_json::to_value(&cap).map_err(|e| ToolError::internal(e.to_string()))?;
    let tmp = std::env::temp_dir().to_string_lossy().trim_end_matches(['/', '\\']).to_string();
    let mut paths = vec![(tmp.replace('\\', "/"), "<tmp>"), (tmp, "<tmp>")];
    if let Some(cwd) = &p.working_directory {
        let cwd = cwd.trim_end_matches(['/', '\\']).to_string();
        paths.insert(0, (cwd.replace('\\', "/"), "<cwd>"));
        paths.insert(0, (cwd, "<cwd>"));
    }
    let pids: Vec<u32> = cap.exit.leader_pid.into_iter().collect();
    let replaced = normalize_capture(&mut result, &p.normalization, &pids, &paths);
    result["normalization"] = json!({"settings": p.normalization, "replacements": replaced});
    let fs_effects = cap.filesystem.as_ref().map(|f| f.effects.len()).unwrap_or(0);
    let summary = format!(
        "Ran {} ({}): {}{}. Terminal {}×{}; {} bytes of output{}.",
        cap.manifest.executable_name,
        cap.exit.reason,
        cap.exit.code.map(|c| format!("exit {c}")).unwrap_or_else(|| "no exit code".into()),
        if cap.manifest.sandbox.used { ", sandboxed" } else { "" },
        cap.terminal.columns,
        cap.terminal.rows,
        cap.terminal.output_bytes,
        if fs_effects > 0 { format!("; {fs_effects} filesystem changes observed") } else { String::new() },
    );

    // Secret-free parameters for the record.
    let safe_params = json!({
        "executable_name": cap.manifest.executable_name,
        "argument_count": p.arguments.len(),
        "event_count": p.events.len(),
        "watched_path_count": p.watched_paths.len(),
        "timeout_ms": p.timeout_ms,
        "sandbox_requested": p.sandbox,
    });

    let env = Environment {
        clean_room: ctx.session.clean_room(),
        engine: "program-runs".into(),
        engine_version: Some(env!("CARGO_PKG_VERSION").into()),
        host: host_triple(),
        language_id: None,
    };
    let subject = Subject { kind: "capture".into(), sha256: cap.manifest.executable_sha256.clone(), name: Some(cap.manifest.executable_name.clone()) };

    let mut b = EvidenceBuilder::new("runtime_walkthrough_record", subject, env)
        .params(safe_params)
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OurRun)
        .limitations(cap.limitations.iter().map(|l| Limitation::new(l.code.clone(), l.message.clone())));
    if cap.truncated {
        b = b.coverage(Coverage { status: CoverageStatus::Partial, examined: None, total: None, next_offset: None });
    } else {
        b = b.coverage(Coverage::complete(1));
    }
    if let Some(pid) = cap.exit.leader_pid {
        b = b.location(Location::new("process", pid.to_string()).with_label("process-group leader"));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// --------------------------------------------------------------------------------------------
// runtime_captures_compare

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CompareParams {
    /// The first run: runtime_walkthrough_record evidence (inline, {"kind":"saved",…} or a bare id).
    pub left: Value,
    /// The second run, in the same forms.
    pub right: Value,
}

#[derive(Debug, Serialize)]
struct Dimension {
    dimension: &'static str,
    status: &'static str,
    detail: Value,
}

fn runtime_captures_compare(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CompareParams = parse_params(params)?;
    let l = resolve_evidence_input(ctx, &p.left, &["runtime_walkthrough_record"])?;
    let r = resolve_evidence_input(ctx, &p.right, &["runtime_walkthrough_record"])?;

    let dims = vec![
        compare_terminal(&l.result, &r.result),
        compare_exit(&l.result, &r.result),
        compare_events(&l.result, &r.result),
        compare_filesystem(&l.result, &r.result),
    ];

    // Overall precedence: changed/added/removed, then unknown, then unchanged.
    let overall = if dims.iter().any(|d| matches!(d.status, "changed" | "added" | "removed")) {
        "changed"
    } else if dims.iter().any(|d| d.status == "unknown") {
        "unknown"
    } else {
        "unchanged"
    };
    let changed: Vec<&str> = dims.iter().filter(|d| d.status != "unchanged").map(|d| d.dimension).collect();

    let summary = if overall == "unchanged" {
        "The two runs match across terminal, exit, events and filesystem.".to_string()
    } else {
        format!("Runs differ ({overall}): {}.", changed.join(", "))
    };

    let b = EvidenceBuilder::new(
        "runtime_captures_compare",
        Subject { kind: "capture-pair".into(), sha256: None, name: Some("two captures".into()) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"left": l.id, "right": r.id}))
    .result(json!({"overall": overall, "dimensions": dims, "changed_dimensions": changed}))
    .summary(summary)
    .confidence(Confidence::Derived)
    .link(l.id.clone())
    .link(r.id.clone());
    Ok(ToolOutput::evidence(b.build()?))
}

fn compare_terminal(l: &Value, r: &Value) -> Dimension {
    let ll = l.pointer("/terminal/lines").and_then(Value::as_array);
    let rl = r.pointer("/terminal/lines").and_then(Value::as_array);
    match (ll, rl) {
        (Some(a), Some(b)) => {
            let status = if a == b { "unchanged" } else { "changed" };
            let text = |v: &[Value]| v.iter().map(|l| l.as_str().unwrap_or_default().to_string()).collect::<Vec<_>>();
            let mut detail = line_changes(&text(a), &text(b));
            detail["left_lines"] = json!(a.len());
            detail["right_lines"] = json!(b.len());
            Dimension { dimension: "terminal", status, detail }
        }
        _ => Dimension { dimension: "terminal", status: "unknown", detail: json!({"reason": "no rendered terminal in one capture"}) },
    }
}

/// Which lines differ: the common start and end are skipped, and what is left on each side is
/// listed with its 1-based line number (at most 200 a side).
fn line_changes(a: &[String], b: &[String]) -> Value {
    const MAX: usize = 200;
    let prefix = a.iter().zip(b).take_while(|(x, y)| x == y).count();
    let suffix = a.iter().rev().zip(b.iter().rev()).take(a.len().min(b.len()).saturating_sub(prefix)).take_while(|(x, y)| x == y).count();
    let side = |v: &[String]| -> Vec<Value> {
        v.iter().enumerate().skip(prefix).take(v.len().saturating_sub(prefix + suffix)).take(MAX).map(|(i, t)| json!({"line": i + 1, "text": t})).collect()
    };
    let (removed, added) = (side(a), side(b));
    let listed_all = removed.len() == a.len().saturating_sub(prefix + suffix) && added.len() == b.len().saturating_sub(prefix + suffix);
    json!({
        "first_changed_line": (prefix < a.len().max(b.len())).then_some(prefix + 1),
        "only_left": removed,
        "only_right": added,
        "complete": listed_all,
    })
}

fn compare_exit(l: &Value, r: &Value) -> Dimension {
    let lc = l.pointer("/exit/code");
    let rc = r.pointer("/exit/code");
    let lr = l.pointer("/exit/reason").and_then(Value::as_str);
    let rr = r.pointer("/exit/reason").and_then(Value::as_str);
    let status = if lc == rc && lr == rr { "unchanged" } else { "changed" };
    Dimension { dimension: "exit", status, detail: json!({"left": {"code": lc, "reason": lr}, "right": {"code": rc, "reason": rr}}) }
}

fn compare_events(l: &Value, r: &Value) -> Dimension {
    let le = l.pointer("/events").and_then(Value::as_array).map(|a| a.len()).unwrap_or(0);
    let re = r.pointer("/events").and_then(Value::as_array).map(|a| a.len()).unwrap_or(0);
    let lo = dispatched(l);
    let ro = dispatched(r);
    let status = if le == re && lo == ro { "unchanged" } else { "changed" };
    Dimension { dimension: "events", status, detail: json!({"left": {"count": le, "dispatched": lo}, "right": {"count": re, "dispatched": ro}}) }
}

fn dispatched(v: &Value) -> usize {
    v.pointer("/events")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter(|e| e.get("outcome").and_then(Value::as_str) == Some("dispatched")).count())
        .unwrap_or(0)
}

fn compare_filesystem(l: &Value, r: &Value) -> Dimension {
    let both_observed = l.pointer("/filesystem").is_some_and(Value::is_object) && r.pointer("/filesystem").is_some_and(Value::is_object);
    if both_observed {
        let lc = changes(l);
        let rc = changes(r);
        let status = if lc == rc { "unchanged" } else { "changed" };
        Dimension { dimension: "filesystem", status, detail: json!({"left_changes": lc.len(), "right_changes": rc.len()}) }
    } else {
        Dimension { dimension: "filesystem", status: "unknown", detail: json!({"reason": "one or both runs did not observe the filesystem"}) }
    }
}

/// Each changed path with how it changed: deleting a file and creating it are different runs (#300).
fn changes(v: &Value) -> std::collections::BTreeSet<(String, String)> {
    v.pointer("/filesystem/effects")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(|e| Some((e.get("path")?.as_str()?.to_string(), e.get("change")?.as_str()?.to_string())))
                .filter(|(_, c)| matches!(c.as_str(), "created" | "deleted" | "modified"))
                .collect()
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use crate::{CallOptions, Caller, Consent, Engine};
    use serde_json::{Value, json};

    fn call_consent(e: &Engine, id: &str, p: Value) -> Result<Value, craft_anything_evidence::ToolError> {
        e.call(id, p, CallOptions::new(Caller::Cli).with_consent(Consent::Granted)).map(|o| o.to_json())
    }

    /// #300: one run deleting a file and the other creating it matched, as only paths were compared.
    #[test]
    fn deleting_and_creating_a_file_differ() {
        let run = |effects: Value| json!({"filesystem": {"effects": effects}});
        let fx = |change: &str, path: &str| json!([{"path": path, "change": change}]);
        let status = |l: Value, r: Value| super::compare_filesystem(&run(l), &run(r)).status;
        assert_eq!(status(fx("deleted", "/w/a"), fx("created", "/w/a")), "changed");
        assert_eq!(status(fx("deleted", "/w/a"), fx("deleted", "/w/a")), "unchanged");
        assert_eq!(status(fx("deleted", "/w/a"), fx("deleted", "/w/b")), "changed");
        assert_eq!(status(fx("unchanged", "/w/a"), json!([])), "unchanged");
    }

    #[test]
    fn capture_needs_consent() {
        let e = Engine::new(crate::testing::session());
        let err = e.call("runtime_walkthrough_record", json!({"executable": "/bin/echo"}), CallOptions::new(Caller::Mcp)).unwrap_err();
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::ConsentRequired);
    }

    #[test]
    #[cfg_attr(not(any(target_os = "linux", target_os = "macos")), ignore)]
    fn capture_and_compare_echo() {
        if craft_anything_platform::which::which("sh").is_none() {
            return;
        }
        let e = Engine::new(crate::testing::session());
        let a = call_consent(
            &e,
            "runtime_walkthrough_record",
            json!({"executable": "/bin/sh", "arguments": ["-c", "echo first"], "timeout_ms": 5000, "settle_ms": 200}),
        )
        .unwrap();
        let ida = a["id"].as_str().unwrap().to_string();
        assert_eq!(a["result"]["exit"]["reason"], "exited");
        assert!(a["result"]["terminal"]["lines"].as_array().unwrap().iter().any(|l| l.as_str().unwrap_or("").contains("first")));

        let b = call_consent(
            &e,
            "runtime_walkthrough_record",
            json!({"executable": "/bin/sh", "arguments": ["-c", "echo second"], "timeout_ms": 5000, "settle_ms": 200}),
        )
        .unwrap();
        let idb = b["id"].as_str().unwrap().to_string();

        let cmp = call_consent(&e, "runtime_captures_compare", json!({"left": ida, "right": idb})).unwrap();
        assert_eq!(cmp["result"]["overall"], "changed");
        assert!(cmp["result"]["changed_dimensions"].as_array().unwrap().iter().any(|d| d == "terminal"));
    }

    #[test]
    fn captures_are_normalised_so_runs_compare() {
        use super::{LiteralRule, NormalizationParams, normalize_capture};
        let mut capture = json!({
            "terminal": {"lines": [
                "pid 4242 started (not 42420)",
                "listening on 127.0.0.1:53817 and localhost:8080/x",
                "wrote /work/dir/save.dat and /tmp/x",
                "build abc-123"
            ]},
            "events": [{"sent_at_ms": 1234, "detail": "sent to 4242"}]
        });
        let n =
            NormalizationParams { paths: true, patterns: vec![LiteralRule { pattern: "abc-123".into(), replacement: "BUILD".into() }], ..Default::default() };
        let counts = normalize_capture(&mut capture, &n, &[4242], &[("/work/dir".into(), "<cwd>"), ("/tmp".into(), "<tmp>")]);
        let lines = &capture["terminal"]["lines"];
        assert_eq!(lines[0], "pid <pid> started (not 42420)");
        assert_eq!(lines[1], "listening on 127.0.0.1:<port> and localhost:<port>/x");
        assert_eq!(lines[2], "wrote <cwd>/save.dat and <tmp>/x");
        assert_eq!(lines[3], "build BUILD");
        assert_eq!(capture["events"][0]["detail"], "sent to <pid>");
        assert_eq!(capture["events"][0]["sent_at_ms"], 1230);
        assert_eq!(counts, json!({"paths": 2, "patterns": 1, "pids": 2, "ports": 2, "times": 1}));

        // Nothing is touched with everything off.
        let mut same = json!({"terminal": {"lines": ["pid 4242 on localhost:80"]}});
        let off = NormalizationParams { pids: false, ports: false, time_step_ms: 0, ..Default::default() };
        normalize_capture(&mut same, &off, &[4242], &[]);
        assert_eq!(same["terminal"]["lines"][0], "pid 4242 on localhost:80");
    }

    #[test]
    fn terminal_comparison_names_the_changed_lines() {
        let lines = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        let d = super::line_changes(&lines(&["$ run", "score: 10", "lives: 3", "bye"]), &lines(&["$ run", "score: 12", "lives: 3", "bonus!", "bye"]));
        assert_eq!(d["first_changed_line"], 2);
        assert_eq!(d["only_left"], json!([{"line": 2, "text": "score: 10"}, {"line": 3, "text": "lives: 3"}]));
        assert_eq!(d["only_right"], json!([{"line": 2, "text": "score: 12"}, {"line": 3, "text": "lives: 3"}, {"line": 4, "text": "bonus!"}]));
        assert_eq!(d["complete"], true);
        let same = super::line_changes(&lines(&["a", "b"]), &lines(&["a", "b"]));
        assert!(same["first_changed_line"].is_null() && same["only_left"] == json!([]));
        let grown = super::line_changes(&lines(&["a"]), &lines(&["a", "b"]));
        assert_eq!(grown["only_right"], json!([{"line": 2, "text": "b"}]));
        assert_eq!(grown["only_left"], json!([]));
    }

    #[test]
    fn reserved_env_is_rejected() {
        let e = Engine::new(crate::testing::session());
        let err =
            call_consent(&e, "runtime_walkthrough_record", json!({"executable": "/bin/echo", "environment": {"CRAFT_ANYTHING_RUN_ID": "x"}})).unwrap_err();
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::BadInput);
    }
}
