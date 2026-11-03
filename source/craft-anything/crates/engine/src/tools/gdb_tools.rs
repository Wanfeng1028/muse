//! GDB sessions over the machine interface (GDB/MI), through [`craft_anything_engines::gdb`]:
//! each session is one owned `gdb` process driven with `-interpreter-exec console`, so any GDB
//! command works while results come back as structured records. Starting a session only loads the
//! program; running it, calling functions or using GDB's shell/python commands happens through
//! native_gdb_command_run, which needs consent. Sessions are kept by id for this run.

use super::native_common::spec;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::gdb::GdbSession;
use craft_anything_evidence::{Authority, Confidence, Coverage, Environment, ErrorCode, EvidenceBuilder, Limitation, Subject, ToolError, sha256_hex};
use craft_anything_platform::sync::Mutex;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, PoisonError};
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    let base = Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS;
    let eng = Requires::Engine("gdb");
    vec![
        spec(
            "native_gdb_session_begin",
            "Start a GDB session",
            "Start GDB (machine-interface mode, no init files, auto-loaded scripts off, pagination off) with a program loaded (absolute path; optional core file and program arguments), or empty. The program is only loaded, not run. Returns a session_id for native_gdb_command_run, native_gdb_session_show and native_gdb_session_end, plus GDB's start-up messages. Sessions live in memory for this run; at most 4 at a time.",
            "Open a debugger session on a program (it doesn't run yet).",
            Toolset::Runtime,
            base,
            eng,
            schema_of::<StartParams>,
            native_gdb_session_begin,
        ),
        spec(
            "native_gdb_command_run",
            "GDB command",
            "Run one GDB command line in a session (for example `info functions`, `disassemble main`, `break main`, `run`, `bt`, `info registers`, `x/16xb $sp`) and return its console output, the result (done, running, error, exit), stop events (reason, frame) and any program output, waiting up to timeout_seconds for a started run to stop. Commands can run the program, call its functions or use GDB's shell and Python, so this asks for consent.",
            "Type a command into the debugger.",
            Toolset::Runtime,
            base | Effects::EXECUTES_FOREIGN_CODE | Effects::MUTATES_TARGET,
            eng,
            schema_of::<ConsoleParams>,
            native_gdb_command_run,
        ),
        spec(
            "native_gdb_session_show",
            "GDB session status",
            "Show one GDB session (or all when session_id is omitted): whether GDB is alive, the last known program state (not started, stopped, running, exited), the last stop event, and any output that arrived since the last command.",
            "Check on an open debugger session.",
            Toolset::Runtime,
            Effects::MUTATES_SESSION,
            Requires::Nothing,
            schema_of::<StatusParams>,
            native_gdb_session_show,
        ),
        spec(
            "native_gdb_session_end",
            "Close a GDB session",
            "End a GDB session: ask GDB to exit, then stop it and anything it started (including a program it is debugging).",
            "Close a debugger session.",
            Toolset::Runtime,
            Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS,
            Requires::Nothing,
            schema_of::<SessionIdParams>,
            native_gdb_session_end,
        ),
    ]
}

const MAX_SESSIONS: usize = 4;

fn d_timeout() -> u64 {
    10
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StartParams {
    /// Absolute path of the program to load; omit for an empty session.
    #[serde(default)]
    pub program: Option<String>,
    /// Absolute path of a core dump to open with the program.
    #[serde(default)]
    pub core: Option<String>,
    /// Arguments the program gets when it is run.
    #[serde(default)]
    pub args: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ConsoleParams {
    pub session_id: String,
    /// One GDB command line.
    pub command: String,
    /// Seconds to wait for the command (and a started run) to finish: 1–300, default 10.
    #[serde(default = "d_timeout")]
    pub timeout_seconds: u64,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StatusParams {
    #[serde(default)]
    pub session_id: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SessionIdParams {
    pub session_id: String,
}

struct GdbStore(Mutex<HashMap<String, GdbSession>>);

fn store(ctx: &mut Ctx<'_>) -> Arc<GdbStore> {
    if let Some(s) = ctx.session.ext.get::<GdbStore>() {
        return s;
    }
    let s = Arc::new(GdbStore(Mutex::new(HashMap::new())));
    ctx.session.ext.insert(s.clone());
    s
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn new_id() -> String {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let h = sha256_hex(format!("gdb:{}:{nanos}:{n}", std::process::id()).as_bytes());
    format!("gdb_{}", h.get(..24).unwrap_or(&h))
}

fn unknown_session() -> ToolError {
    ToolError::new(ErrorCode::BadInput, "no GDB session with that id")
        .with_remediation("List sessions with native_gdb_session_show, or start one with native_gdb_session_begin.")
}

fn abs_file(p: &str, what: &str) -> Result<PathBuf, ToolError> {
    let pb = PathBuf::from(p);
    if !pb.is_absolute() {
        return Err(ToolError::invalid(format!("{what} {p:?} is not an absolute path")));
    }
    if !pb.is_file() {
        return Err(ToolError::invalid(format!("{what} {p} is not a file")));
    }
    Ok(pb)
}

fn locate_gdb(ctx: &Ctx<'_>) -> Result<PathBuf, ToolError> {
    let s = &ctx.session.settings;
    craft_anything_engines::locate("gdb", &s.engines.tools, &s.engine_store_dir())
        .ok_or_else(|| ToolError::unavailable("GDB is not installed.").with_remediation("Install GDB and set its path in Settings → Engines."))
}

/// The session's status with its id.
fn status_json(id: &str, s: &mut GdbSession) -> Value {
    let mut v = s.status();
    if let Value::Object(m) = &mut v {
        m.insert("session_id".into(), Value::String(id.to_string()));
    }
    v
}

// ---------------------------------------------------------------------------------------------
// Tools

fn native_gdb_session_begin(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StartParams = parse_params(params)?;
    let program = p.program.as_deref().map(|x| abs_file(x, "program")).transpose()?;
    let core = p.core.as_deref().map(|x| abs_file(x, "core")).transpose()?;
    if core.is_some() && program.is_none() {
        return Err(ToolError::invalid("a core file needs the program it came from"));
    }
    if p.args.len() > 256 || p.args.iter().any(|a| a.contains(['\n', '\r', '\0'])) {
        return Err(ToolError::invalid("args must be at most 256 single-line strings"));
    }
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    guard.retain(|_, s| !s.is_finished());
    if guard.len() >= MAX_SESSIONS {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{MAX_SESSIONS} GDB sessions are already open"))
            .with_remediation("Close one with native_gdb_session_end."));
    }
    let gdb = locate_gdb(ctx)?;
    ctx.report(None, "Starting GDB");
    let mut s = GdbSession::start(&gdb, program.as_ref(), core.as_ref(), &p.args)?;
    // A harmless command proves GDB is up and flushes its start-up messages.
    let cancel = ctx.cancel.clone();
    let (c, timed_out) = s.exec("-gdb-version", Duration::from_secs(60), &|| cancel.is_cancelled())?;
    if timed_out || s.is_finished() {
        s.kill();
        return Err(ToolError::new(ErrorCode::ProgramFailed, "GDB did not start answering within 60 seconds")
            .with_details(json!({"log": c.log, "output": c.target_output})));
    }
    let id = new_id();
    // Start-up messages ("Reading symbols…") come before the version banner.
    let version = c.console.lines().find(|l| l.starts_with("GNU gdb")).unwrap_or("").to_string();
    let startup: String = c.console.lines().take_while(|l| !l.starts_with("GNU gdb")).map(|l| format!("{l}\n")).collect();
    let mut out = status_json(&id, &mut s);
    if let Value::Object(m) = &mut out {
        m.insert("gdb_version".into(), Value::String(version));
        m.insert("messages".into(), Value::String(format!("{startup}{}{}", c.log, c.target_output)));
        m.insert("continue_with".into(), Value::String("native_gdb_command_run".into()));
    }
    guard.insert(id, s);
    Ok(ToolOutput::Value(out))
}

fn native_gdb_command_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ConsoleParams = parse_params(params)?;
    let cmd = p.command.trim();
    if cmd.is_empty() || cmd.len() > 4096 || cmd.contains(['\n', '\r', '\0']) {
        return Err(ToolError::invalid("command must be one line of 1–4096 characters"));
    }
    let timeout = Duration::from_secs(p.timeout_seconds.clamp(1, 300));
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    let s = guard.get_mut(&p.session_id).ok_or_else(unknown_session)?;
    ctx.report(None, format!("gdb: {cmd}"));
    let cancel = ctx.cancel.clone();
    let (c, timed_out) = s.console(cmd, timeout, &|| cancel.is_cancelled())?;
    let status = status_json(&p.session_id, s);
    let mut lims =
        vec![Limitation::new("live_session", "Output reflects this moment in a live debugging session; running the program again can give different results.")];
    if timed_out {
        lims.push(Limitation::new(
            "timed_out",
            "The command had not finished when the wait ended; the program may still be running. Check with native_gdb_session_show, or send `interrupt`.",
        ));
    }
    if c.truncated {
        lims.push(Limitation::new("output_capped", "More than 1 MiB of text arrived; the rest was dropped."));
    }
    let subject =
        Subject { kind: "process".into(), sha256: None, name: s.program.as_ref().and_then(|p| p.file_name()).map(|n| n.to_string_lossy().into_owned()) };
    let e = EvidenceBuilder::new("native_gdb_command_run", subject, Environment::builtin(ctx.session.clean_room()))
        .params(json!({"session_id": p.session_id, "command": cmd, "timeout_seconds": timeout.as_secs()}))
        .result(json!({
            "command": cmd,
            "timed_out": timed_out,
            "result": c.result,
            "error": c.error,
            "console": c.console,
            "log": c.log,
            "target_output": c.target_output,
            "events": c.events,
            "status": status,
        }))
        .summary(format!(
            "gdb `{cmd}`: {} line(s) of output, program {}{}.",
            c.console.lines().count(),
            status.get("state").and_then(Value::as_str).unwrap_or("unknown"),
            if timed_out { " (still waiting)" } else { "" }
        ))
        .confidence(Confidence::Observed)
        .authority(Authority::OurRun)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn native_gdb_session_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StatusParams = parse_params(params)?;
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    match &p.session_id {
        Some(id) => {
            let s = guard.get_mut(id).ok_or_else(unknown_session)?;
            let (c, dropped) = s.take_output();
            let mut v = status_json(id, s);
            if let Value::Object(m) = &mut v {
                m.insert("new_output".into(), json!({"console": c.console, "log": c.log, "target_output": c.target_output, "events": c.events}));
                m.insert("dropped_lines".into(), json!(dropped));
            }
            Ok(ToolOutput::Value(v))
        }
        None => {
            let list: Vec<Value> = guard.iter_mut().map(|(id, s)| status_json(id, s)).collect();
            Ok(ToolOutput::Value(json!({"sessions": list, "count": list.len()})))
        }
    }
}

fn native_gdb_session_end(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SessionIdParams = parse_params(params)?;
    let st = store(ctx);
    let s = st.0.lock().unwrap_or_else(PoisonError::into_inner).remove(&p.session_id).ok_or_else(unknown_session)?;
    let graceful = s.close();
    Ok(ToolOutput::Value(json!({"session_id": p.session_id, "closed": true, "graceful_exit": graceful})))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Consent, Engine};

    #[test]
    fn console_needs_consent_and_a_session() {
        let e = Engine::new(crate::testing::session());
        let err = e.call("native_gdb_command_run", json!({"session_id": "nope", "command": "info files"}), CallOptions::new(Caller::Mcp)).err();
        assert!(err.is_some());
        let st = e.call("native_gdb_session_show", json!({}), CallOptions::new(Caller::Mcp));
        assert!(matches!(st, Ok(ToolOutput::Value(v)) if v["count"] == 0));
        assert!(e.call("native_gdb_session_end", json!({"session_id": "nope"}), CallOptions::new(Caller::Mcp)).is_err());
    }

    /// A real round trip when GDB is installed: load a program, query it, never run it.
    #[test]
    fn live_session_when_gdb_is_installed() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("dbg.elf", &craft_anything_testkit::elf64(craft_anything_testkit::ElfArch::X86_64, true).0);
        let Ok(ToolOutput::Value(v)) = e.call("native_gdb_session_begin", json!({"program": p}), CallOptions::new(Caller::Mcp)) else {
            return; // GDB not installed here
        };
        let id = v["session_id"].as_str().unwrap().to_string();
        assert_eq!(v["state"], "not_started");
        let mut opts = CallOptions::new(Caller::Mcp);
        opts.consent = Consent::Granted;
        let out = e.call("native_gdb_command_run", json!({"session_id": id, "command": "info functions main"}), opts).unwrap();
        let ToolOutput::Evidence(ev) = out else { panic!("expected evidence") };
        let r = serde_json::to_value(&*ev).unwrap();
        assert_eq!(r["result"]["timed_out"], false, "{r}");
        assert_eq!(r["result"]["result"], "done", "{r}");
        let mut opts = CallOptions::new(Caller::Mcp);
        opts.consent = Consent::Granted;
        let out = e.call("native_gdb_command_run", json!({"session_id": id, "command": "definitely-not-a-command"}), opts).unwrap();
        let ToolOutput::Evidence(ev) = out else { panic!("expected evidence") };
        let r = serde_json::to_value(&*ev).unwrap();
        assert_eq!(r["result"]["result"], "error", "{r}");
        assert!(r["result"]["error"].as_str().unwrap().contains("Undefined command"), "{r}");
        let Ok(ToolOutput::Value(c)) = e.call("native_gdb_session_end", json!({"session_id": id}), CallOptions::new(Caller::Mcp)) else {
            panic!("close failed")
        };
        assert_eq!(c["closed"], true);
    }
}
