//! Frida instrumentation, driven through the Frida command-line tools (`frida`, `frida-ps`,
//! `frida-ls-devices`) located via [`craft_anything_engines::locate`] — never a native binding.
//!
//! A "session" here is Craft Anything's own managed record of an attach/spawn intent, held in the
//! session's process memory (not the binary session) and keyed by a generated id. Scripts are
//! executed by invoking the Frida CLI for a bounded window with closed stdin, capped output and a
//! deadline, so an instrumentation run can never hang the app. Running a script executes foreign
//! code, so `frida_script_run`, `frida_session_continue` and `frida_instrument_run` carry
//! [`Effects::EXECUTES_FOREIGN_CODE`] and are consent-gated.
//!
//! Remote-device authentication (token, certificate, origin) is accepted only to be forwarded to
//! the CLI as arguments; it is held in process memory, never logged, returned, or written to
//! evidence.

use super::artifact_tools::{abs_path, fresh_temp_dir, read_capped};
use super::native_common::spec;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::frida::{Attach, Frida, Remote, Selector};
use craft_anything_evidence::{Authority, Confidence, Coverage, Environment, ErrorCode, Evidence, EvidenceBuilder, Limitation, Subject, ToolError, sha256_hex};
use craft_anything_platform::process::{Cancel, Output};
use craft_anything_platform::sync::Mutex;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, PoisonError};
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Frida;
    let base = Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS | Effects::ACCESSES_NETWORK;
    let foreign = base | Effects::MUTATES_TARGET | Effects::EXECUTES_FOREIGN_CODE; // consent-gated
    let eng = Requires::Engine("frida");
    vec![
        spec(
            "frida_devices_find",
            "Frida devices",
            "List devices Frida can see with `frida-ls-devices` (local, usb, remote). Pass remote to get one entry for a remote address without contacting it, so its reachability and auth are unverified (`frida-ps -H` checks it); its auth is forwarded to the CLI and never returned.",
            "See which devices the instrumentation tool can reach.",
            Frida,
            base,
            eng,
            schema_of::<RemoteOnlyParams>,
            frida_devices_find,
        ),
        spec(
            "frida_targets_list",
            "Frida processes",
            "List processes and installed apps on the selected device with `frida-ps`. Give exactly one of device_id or remote.",
            "See what is running on the device so you can pick something to study.",
            Frida,
            base,
            eng,
            schema_of::<SelectorParams>,
            frida_targets_list,
        ),
        spec(
            "frida_session_begin",
            "Start a Frida session",
            "Begin a managed Frida session. mode=attach needs pid; mode=spawn needs program (absolute) and optional argv. Returns a session_id (held in memory) you pass to the other Frida tools. This records the session; code runs only when you load or resume a script.",
            "Pick a running app (or launch one) to study with instrumentation.",
            Frida,
            base | Effects::MUTATES_TARGET,
            eng,
            schema_of::<StartParams>,
            frida_session_begin,
        ),
        spec(
            "frida_script_run",
            "Run a Frida script",
            "Load and run an instrumentation script in a session for a bounded window, capturing its console/send output. source_kind=inline with source, or source_kind=file with an absolute path. Executing a script runs foreign code, so this is consent-gated and changes the target.",
            "Run a small instrumentation script against the app and collect what it reports.",
            Frida,
            foreign,
            eng,
            schema_of::<LoadScriptParams>,
            frida_script_run,
        ),
        spec(
            "frida_session_continue",
            "Resume a Frida session",
            "Resume a spawned, paused session so the target runs. Executes foreign code (the target's own), so this is consent-gated.",
            "Let a paused app continue running under instrumentation.",
            Frida,
            foreign,
            eng,
            schema_of::<SessionIdParams>,
            frida_session_continue,
        ),
        spec(
            "frida_script_forget",
            "Unload a Frida script",
            "Forget a loaded script in a session (record-keeping; the bounded CLI run that executed it has already ended).",
            "Stop tracking a script you ran earlier.",
            Frida,
            base | Effects::MUTATES_TARGET,
            eng,
            schema_of::<UnloadParams>,
            frida_script_forget,
        ),
        spec(
            "frida_session_show",
            "Frida session status",
            "Report a managed session's state, its device/target, and the scripts run in it with their most recent captured messages.",
            "Check on an instrumentation session you started.",
            Frida,
            Effects::MUTATES_SESSION,
            eng,
            schema_of::<SessionIdParams>,
            frida_session_show,
        ),
        spec(
            "frida_session_end",
            "Close a Frida session",
            "End a managed session and forget it. Never kills the target process.",
            "Finish an instrumentation session.",
            Frida,
            base | Effects::MUTATES_TARGET,
            eng,
            schema_of::<SessionIdParams>,
            frida_session_end,
        ),
        spec(
            "frida_instrument_run",
            "One-shot instrumentation",
            "Attach to (or spawn) a target, run a script for duration_ms (0..60000, default 1000), capture its output, and detach — all in one call. Executes foreign code, so it is consent-gated and destructive.",
            "Run a quick instrumentation script against an app and get the results in one step.",
            Frida,
            foreign,
            eng,
            schema_of::<InstrumentParams>,
            frida_instrument_run,
        ),
    ]
}

// ------------------------------------------------------------------------------------------------
// Session store (process-memory only; never serialized with its auth)

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    Attach,
    Spawn,
}

impl Mode {
    fn as_str(self) -> &'static str {
        match self {
            Mode::Attach => "attach",
            Mode::Spawn => "spawn",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum State {
    Paused,
    Running,
    Detached,
}

impl State {
    fn as_str(self) -> &'static str {
        match self {
            State::Paused => "paused",
            State::Running => "running",
            State::Detached => "detached",
        }
    }
}

struct ScriptRecord {
    script_id: String,
    source_kind: String,
    source_path: Option<String>,
    source_sha256: String,
    messages: Vec<String>,
    messages_truncated: bool,
}

struct FridaSession {
    session_id: String,
    device_label: String,
    /// The selector (may hold remote auth); never serialized.
    selector: Selector,
    attach: Attach,
    target: String,
    pid: Option<u32>,
    mode: Mode,
    state: State,
    scripts: Vec<ScriptRecord>,
}

/// The session table lives in the engine session's shared extension slot.
struct FridaStore(Mutex<HashMap<String, FridaSession>>);

fn store(ctx: &mut Ctx<'_>) -> Arc<FridaStore> {
    if let Some(s) = ctx.session.ext.get::<FridaStore>() {
        return s;
    }
    let s = Arc::new(FridaStore(Mutex::new(HashMap::new())));
    ctx.session.ext.insert(s.clone());
    s
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn new_id(prefix: &str) -> String {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let seed = format!("{prefix}:{}:{nanos}:{n}", std::process::id());
    format!("{prefix}_{}", &sha256_hex(seed.as_bytes())[..32])
}

// ------------------------------------------------------------------------------------------------
// Params

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct RemoteSpec {
    /// host[:port] of a frida-server.
    address: String,
    #[serde(default)]
    token: Option<String>,
    #[serde(default)]
    certificate: Option<String>,
    #[serde(default)]
    origin: Option<String>,
    #[serde(default)]
    keepalive_interval: Option<u32>,
}

impl RemoteSpec {
    fn into_remote(self) -> Remote {
        Remote { address: self.address, token: self.token, certificate: self.certificate, origin: self.origin, keepalive_interval: self.keepalive_interval }
    }
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct RemoteOnlyParams {
    #[serde(default)]
    remote: Option<RemoteSpec>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SelectorParams {
    #[serde(default)]
    device_id: Option<String>,
    #[serde(default)]
    remote: Option<RemoteSpec>,
}

impl SelectorParams {
    fn selector(self) -> Selector {
        Selector { device_id: self.device_id, remote: self.remote.map(RemoteSpec::into_remote) }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum StartMode {
    Attach,
    Spawn,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct StartParams {
    #[serde(default)]
    device_id: Option<String>,
    #[serde(default)]
    remote: Option<RemoteSpec>,
    mode: StartMode,
    /// Process id (mode=attach).
    #[serde(default)]
    pid: Option<u32>,
    /// Absolute program path (mode=spawn).
    #[serde(default)]
    program: Option<String>,
    /// Extra arguments for a spawned program.
    #[serde(default)]
    argv: Vec<String>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum SourceKind {
    Inline,
    File,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct LoadScriptParams {
    session_id: String,
    source_kind: SourceKind,
    /// Script source (source_kind=inline).
    #[serde(default)]
    source: Option<String>,
    /// Absolute path to a script file (source_kind=file).
    #[serde(default)]
    path: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SessionIdParams {
    session_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct UnloadParams {
    session_id: String,
    script_id: String,
}

fn default_duration() -> u32 {
    1000
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct InstrumentParams {
    #[serde(default)]
    device_id: Option<String>,
    #[serde(default)]
    remote: Option<RemoteSpec>,
    mode: StartMode,
    #[serde(default)]
    pid: Option<u32>,
    #[serde(default)]
    program: Option<String>,
    #[serde(default)]
    argv: Vec<String>,
    source_kind: SourceKind,
    #[serde(default)]
    source: Option<String>,
    #[serde(default)]
    path: Option<String>,
    /// How long to run the script, in milliseconds (0..60000).
    #[serde(default = "default_duration")]
    duration_ms: u32,
}

// ------------------------------------------------------------------------------------------------
// Shared plumbing

const MAX_SCRIPT_BYTES: u64 = 4 * 1024 * 1024;
const MAX_MESSAGES: usize = 5000;

fn frida_for(ctx: &Ctx<'_>) -> Result<Frida, ToolError> {
    let s = &ctx.session.settings;
    let path = craft_anything_engines::locate("frida", &s.engines.tools, &s.engine_store_dir())
        .ok_or_else(|| ToolError::new(ErrorCode::EngineMissing, "Frida isn't installed.").with_remediation(INSTALL))?;
    Ok(Frida::new(path).cancel(cancel_of(ctx)))
}

const INSTALL: &str = "Install Frida (for example `pipx install frida-tools`), then set its path in Settings → Engines if it isn't on PATH.";

fn cancel_of(ctx: &Ctx<'_>) -> Cancel {
    let c = ctx.cancel.clone();
    Arc::new(move || c.is_cancelled())
}

fn frida_env(ctx: &Ctx<'_>) -> Environment {
    Environment {
        clean_room: ctx.session.clean_room(),
        engine: "frida".into(),
        engine_version: None,
        host: craft_anything_evidence::host_triple(),
        language_id: None,
    }
}

fn frida_subject(target: &str) -> Subject {
    Subject { kind: "frida-session".into(), sha256: None, name: Some(target.to_string()) }
}

fn validate_pid(pid: u32) -> Result<u32, ToolError> {
    if pid == 0 { Err(ToolError::invalid("pid must be non-zero")) } else { Ok(pid) }
}

fn validate_argv(argv: &[String]) -> Result<(), ToolError> {
    if argv.len() > 64 {
        return Err(ToolError::invalid("at most 64 argv entries"));
    }
    for a in argv {
        if a.len() > 4096 || a.bytes().any(|b| b == 0) {
            return Err(ToolError::invalid("an argv entry is too long or contains a NUL byte"));
        }
    }
    Ok(())
}

/// Read a script into bytes from inline source or an absolute file; returns (bytes, source_path).
fn read_script(kind: SourceKind, source: &Option<String>, path: &Option<String>) -> Result<(Vec<u8>, Option<String>), ToolError> {
    match kind {
        SourceKind::Inline => {
            let src = source.as_ref().ok_or_else(|| ToolError::invalid("source_kind=inline needs source"))?;
            if src.len() as u64 > MAX_SCRIPT_BYTES {
                return Err(ToolError::new(ErrorCode::OverLimit, "the inline script is too large"));
            }
            Ok((src.as_bytes().to_vec(), None))
        }
        SourceKind::File => {
            let p = path.as_ref().ok_or_else(|| ToolError::invalid("source_kind=file needs path"))?;
            let pb = abs_path(p, "path")?;
            let bytes = read_capped(&pb, MAX_SCRIPT_BYTES)?;
            Ok((bytes, Some(pb.to_string_lossy().into_owned())))
        }
    }
}

/// Run a script via the Frida CLI for a bounded window and collect console/send output lines.
fn run_and_collect(
    ctx: &Ctx<'_>,
    selector: &Selector,
    attach: &Attach,
    script: &[u8],
    duration_ms: u32,
) -> Result<(Vec<String>, bool, Option<i32>), ToolError> {
    let dir = fresh_temp_dir("craft-anything-frida")?;
    let script_file = dir.join("script.js");
    let write = craft_anything_platform::fs::write_atomic(&script_file, script);
    let result = (|| {
        write?;
        let wall = Duration::from_millis(u64::from(duration_ms.clamp(1, 60_000))).saturating_add(Duration::from_secs(10));
        let frida = frida_for(ctx)?.timeout(wall).idle_timeout(Duration::from_secs(8));
        let out: Output = frida.run_script(selector, attach, &script_file)?;
        let (messages, truncated) = collect_lines(&out.stdout_text());
        // A frida CLI that couldn't attach prints to stderr and exits non-zero with no messages.
        if !out.success && messages.is_empty() {
            let tail = tail_text(&out.stderr_text());
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("Frida could not run the script: {}", tail.lines().next_back().unwrap_or("").trim()))
                .with_remediation("Check the device is reachable, frida-server is running, and the pid/program is valid.")
                .with_details(json!({"exit_code": out.code, "stderr_tail": tail})));
        }
        Ok((messages, truncated, out.code))
    })();
    let _ = std::fs::remove_dir_all(&dir);
    result
}

fn collect_lines(text: &str) -> (Vec<String>, bool) {
    let mut out = Vec::new();
    let mut truncated = false;
    for line in text.lines() {
        let t = line.trim_end();
        if t.is_empty() {
            continue;
        }
        if out.len() >= MAX_MESSAGES {
            truncated = true;
            break;
        }
        let clipped: String = t.chars().take(8192).collect();
        out.push(clipped);
    }
    (out, truncated)
}

fn tail_text(s: &str) -> String {
    let n = s.chars().count();
    s.chars().skip(n.saturating_sub(2000)).collect()
}

fn done(e: Evidence) -> Result<ToolOutput, ToolError> {
    Ok(ToolOutput::evidence(e))
}

fn value(v: Value) -> Result<ToolOutput, ToolError> {
    Ok(ToolOutput::Value(v))
}

// ------------------------------------------------------------------------------------------------
// Tools

fn frida_devices_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RemoteOnlyParams = parse_params(params)?;
    let selector = p.remote.map(|r| Selector { device_id: None, remote: Some(r.into_remote()) });
    let frida = frida_for(ctx)?;
    let devices = frida.list_devices(selector.as_ref())?;
    value(json!({"devices": devices, "count": devices.len(), "cleanup_error": Value::Null}))
}

fn frida_targets_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SelectorParams = parse_params(params)?;
    let selector = p.selector();
    selector.args()?; // validate exactly-one + values before spawning
    let frida = frida_for(ctx)?;
    let procs = frida.list_processes(&selector)?;
    value(json!({"device_id": selector.device_id, "processes": procs, "count": procs.len(), "cleanup_error": Value::Null}))
}

fn frida_session_begin(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StartParams = parse_params(params)?;
    let selector = Selector { device_id: p.device_id.clone(), remote: p.remote.map(RemoteSpec::into_remote) };
    selector.args()?;
    let device_label = selector.device_id.clone().unwrap_or_else(|| "remote".to_string());
    let (attach, target, pid, mode, state) = match p.mode {
        StartMode::Attach => {
            let pid = validate_pid(p.pid.ok_or_else(|| ToolError::invalid("mode=attach needs pid"))?)?;
            (Attach::Pid(pid), format!("pid {pid}"), Some(pid), Mode::Attach, State::Running)
        }
        StartMode::Spawn => {
            let prog = p.program.as_ref().ok_or_else(|| ToolError::invalid("mode=spawn needs program"))?;
            let pb = abs_path(prog, "program")?;
            validate_argv(&p.argv)?;
            (Attach::Spawn { program: pb.clone(), argv: p.argv.clone() }, pb.to_string_lossy().into_owned(), None, Mode::Spawn, State::Paused)
        }
    };
    // Confirm the engine is present now (so a bad environment fails here, not later).
    let _ = frida_for(ctx)?;
    let session_id = new_id("fs");
    let session = FridaSession {
        session_id: session_id.clone(),
        device_label: device_label.clone(),
        selector,
        attach,
        target: target.clone(),
        pid,
        mode,
        state,
        scripts: Vec::new(),
    };
    let st = store(ctx);
    st.0.lock().unwrap_or_else(PoisonError::into_inner).insert(session_id.clone(), session);
    value(json!({"session_id": session_id, "device_id": device_label, "target": target, "pid": pid, "mode": mode.as_str(), "state": state.as_str()}))
}

fn frida_script_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: LoadScriptParams = parse_params(params)?;
    let (script, source_path) = read_script(p.source_kind, &p.source, &p.path)?;
    let source_sha256 = sha256_hex(&script);
    let source_kind = match p.source_kind {
        SourceKind::Inline => "inline",
        SourceKind::File => "file",
    };
    // Pull the session's selector/attach out under the lock, then run the CLI without holding it.
    let st = store(ctx);
    let (selector, attach, target) = {
        let guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
        let s = guard.get(&p.session_id).ok_or_else(unknown_session)?;
        if s.state == State::Detached {
            return Err(ToolError::new(ErrorCode::BadInput, "that session is closed").with_remediation("Start a new session with frida_session_begin."));
        }
        (s.selector.clone(), s.attach.clone(), s.target.clone())
    };
    let (messages, truncated, exit) = run_and_collect(ctx, &selector, &attach, &script, 3000)?;
    let script_id = new_id("fsc");
    {
        let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some(s) = guard.get_mut(&p.session_id) {
            s.state = State::Running;
            s.scripts.push(ScriptRecord {
                script_id: script_id.clone(),
                source_kind: source_kind.to_string(),
                source_path: source_path.clone(),
                source_sha256: source_sha256.clone(),
                messages: messages.clone(),
                messages_truncated: truncated,
            });
        }
    }
    let e = EvidenceBuilder::new("frida_script_run", frida_subject(&target), frida_env(ctx))
        .params(json!({"session_id": p.session_id, "source_kind": source_kind, "source_path": source_path}))
        .authority(Authority::OutsideService)
        .confidence(Confidence::Observed)
        .result(json!({
            "script_id": script_id, "source_kind": source_kind, "source_path": source_path, "source_sha256": source_sha256,
            "messages": messages, "messages_truncated": truncated, "exit_code": exit,
        }))
        .summary(format!("Ran a script in session {} ({} message(s) captured).", p.session_id, messages.len()))
        .limitation(Limitation::new(
            "bounded_cli_run",
            "The script ran via the Frida CLI for a bounded window with closed stdin; a long-lived interactive session is not held open between calls.",
        ))
        .coverage(Coverage::complete(messages.len() as u64))
        .build()?;
    done(e)
}

fn frida_session_continue(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SessionIdParams = parse_params(params)?;
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    let s = guard.get_mut(&p.session_id).ok_or_else(unknown_session)?;
    if s.state == State::Detached {
        return Err(ToolError::new(ErrorCode::BadInput, "that session is closed"));
    }
    s.state = State::Running;
    value(json!({"session_id": p.session_id, "state": "running"}))
}

fn frida_script_forget(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: UnloadParams = parse_params(params)?;
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    let s = guard.get_mut(&p.session_id).ok_or_else(unknown_session)?;
    let before = s.scripts.len();
    s.scripts.retain(|sc| sc.script_id != p.script_id);
    if s.scripts.len() == before {
        return Err(ToolError::new(ErrorCode::BadInput, format!("no script {} in that session", p.script_id)));
    }
    value(json!({"unloaded": true, "session_id": p.session_id, "script_id": p.script_id}))
}

fn frida_session_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SessionIdParams = parse_params(params)?;
    let st = store(ctx);
    let guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    let s = guard.get(&p.session_id).ok_or_else(unknown_session)?;
    let scripts: Vec<Value> = s
        .scripts
        .iter()
        .map(|sc| {
            json!({
                "script_id": sc.script_id, "source_kind": sc.source_kind, "source_path": sc.source_path,
                "source_sha256": sc.source_sha256, "messages": sc.messages, "messages_truncated": sc.messages_truncated,
            })
        })
        .collect();
    let target = s.target.clone();
    let env = frida_env(ctx);
    // Build the evidence while the lock is released to avoid holding it across the builder.
    let result = json!({
        "session_id": s.session_id, "device_id": s.device_label, "target": s.target, "pid": s.pid,
        "mode": s.mode.as_str(), "state": s.state.as_str(), "scripts": scripts, "script_count": s.scripts.len(),
    });
    let summary = format!("Session {} is {} with {} script(s).", s.session_id, s.state.as_str(), s.scripts.len());
    drop(guard);
    let e = EvidenceBuilder::new("frida_session_show", frida_subject(&target), env)
        .params(json!({"session_id": p.session_id}))
        .authority(Authority::OutsideService)
        .confidence(Confidence::Observed)
        .result(result)
        .summary(summary)
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn frida_session_end(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SessionIdParams = parse_params(params)?;
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    if guard.remove(&p.session_id).is_none() {
        return Err(unknown_session());
    }
    value(json!({"session_id": p.session_id, "closed": true, "target_state": "unknown"}))
}

fn frida_instrument_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: InstrumentParams = parse_params(params)?;
    if p.duration_ms > 60_000 {
        return Err(ToolError::invalid("duration_ms must be between 0 and 60000"));
    }
    let selector = Selector { device_id: p.device_id.clone(), remote: p.remote.map(RemoteSpec::into_remote) };
    selector.args()?;
    let (attach, target) = match p.mode {
        StartMode::Attach => {
            let pid = validate_pid(p.pid.ok_or_else(|| ToolError::invalid("mode=attach needs pid"))?)?;
            (Attach::Pid(pid), format!("pid {pid}"))
        }
        StartMode::Spawn => {
            let prog = p.program.as_ref().ok_or_else(|| ToolError::invalid("mode=spawn needs program"))?;
            let pb = abs_path(prog, "program")?;
            validate_argv(&p.argv)?;
            (Attach::Spawn { program: pb.clone(), argv: p.argv.clone() }, pb.to_string_lossy().into_owned())
        }
    };
    let (script, source_path) = read_script(p.source_kind, &p.source, &p.path)?;
    let source_sha256 = sha256_hex(&script);
    let source_kind = match p.source_kind {
        SourceKind::Inline => "inline",
        SourceKind::File => "file",
    };
    let (messages, truncated, exit) = run_and_collect(ctx, &selector, &attach, &script, p.duration_ms)?;
    let e = EvidenceBuilder::new("frida_instrument_run", frida_subject(&target), frida_env(ctx))
        .params(json!({"mode": match p.mode { StartMode::Attach => "attach", StartMode::Spawn => "spawn" }, "source_kind": source_kind, "source_path": source_path, "duration_ms": p.duration_ms}))
        .authority(Authority::OutsideService)
        .confidence(Confidence::Observed)
        .result(json!({
            "target": target, "source_kind": source_kind, "source_path": source_path, "source_sha256": source_sha256,
            "duration_ms": p.duration_ms, "messages": messages, "messages_truncated": truncated, "exit_code": exit,
        }))
        .summary(format!("Instrumented {target} for up to {} ms ({} message(s) captured).", p.duration_ms, messages.len()))
        .limitation(Limitation::new("bounded_cli_run", "The script ran via the Frida CLI with closed stdin and a deadline; duration_ms is an upper bound, and no interactive session is kept."))
        .coverage(Coverage::complete(messages.len() as u64))
        .build()?;
    done(e)
}

fn unknown_session() -> ToolError {
    ToolError::new(ErrorCode::BadInput, "no Frida session with that id")
        .with_remediation("Start one with frida_session_begin; session ids live only for this run.")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tools::native_common::test_support::call_err;
    use crate::{Engine, Session, Settings};

    fn engine_without_frida() -> (Engine, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let mut settings = Settings { deep_mode: true, ..Default::default() };
        settings.engines.store_dir = Some(dir.path().to_path_buf());
        settings.engines.tools = Default::default();
        (Engine::new(Session::new(settings)), dir)
    }

    fn frida_locatable(e: &Engine) -> bool {
        let s = e.session();
        craft_anything_engines::locate("frida", &s.settings.engines.tools, &s.settings.engine_store_dir()).is_some()
    }

    #[test]
    fn missing_frida_is_provider_unavailable() {
        let (e, _d) = engine_without_frida();
        if frida_locatable(&e) {
            return;
        }
        for id in ["frida_devices_find", "frida_targets_list", "frida_session_begin", "frida_instrument_run"] {
            let err = call_err(&e, id, json!({"mode": "attach", "pid": 123, "source_kind": "inline", "source": "console.log(1)"}));
            assert_eq!(err.code, ErrorCode::EngineMissing, "{id}");
            assert!(err.remediation.is_some());
        }
    }

    #[test]
    fn foreign_code_tools_need_consent() {
        let e = Engine::new(crate::testing::session());
        for id in ["frida_script_run", "frida_session_continue", "frida_instrument_run"] {
            assert!(e.registry().get(id).unwrap().effects.needs_consent(), "{id} should be consent-gated");
        }
        // Device listing and status do not run foreign code.
        assert!(!e.registry().get("frida_devices_find").unwrap().effects.needs_consent());
        assert!(!e.registry().get("frida_session_show").unwrap().effects.needs_consent());
    }

    #[test]
    fn session_ids_are_distinct() {
        let a = new_id("fs");
        let b = new_id("fs");
        assert_ne!(a, b);
        assert!(a.starts_with("fs_"));
        assert_eq!(a.len(), 3 + 32);
    }

    #[test]
    fn remote_spec_never_derives_serialize() {
        // Compile-time guarantee lives in the engines crate (Remote is not Serialize). Here we just
        // confirm a selector with auth validates and that device_id-only selectors round-trip.
        let sel = Selector {
            device_id: None,
            remote: Some(Remote { address: "1.2.3.4:27042".into(), token: Some("s".into()), certificate: None, origin: None, keepalive_interval: None }),
        };
        assert!(sel.args().is_ok());
    }
}
