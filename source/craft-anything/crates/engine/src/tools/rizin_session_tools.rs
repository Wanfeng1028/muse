//! Rizin debug sessions, through [`craft_anything_engines::rizin`]: each session is one owned
//! `rizin -d` process that either started a program (stopped before its first instruction) or
//! attached to a running one. Any Rizin command works in it (`dr`, `db`, `dc`, `ds`, `pd`, `px`…),
//! so starting one and sending commands both need consent. Sessions are kept by id for this run.

use super::native_common::spec;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::rizin::{RizinSession, Target};
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
    let eng = Requires::Engine("rizin");
    let runs = Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS | Effects::EXECUTES_FOREIGN_CODE | Effects::MUTATES_TARGET;
    vec![
        spec(
            "native_rizin_session_begin",
            "Start a Rizin debug session",
            "Start Rizin's debugger (user settings and scripts off, no prompt or colours) on a program (absolute path, optional arguments), which it starts stopped before its first instruction, or attach it to a running process by pid. Returns a session_id for native_rizin_session_command_run, native_rizin_session_show and native_rizin_session_end, plus Rizin's start-up messages. The program's own console output isn't captured. Sessions live in memory for this run; at most 4 at a time. Starting a program or attaching to one asks for consent.",
            "Open a debugger session on a program, paused at its start.",
            Toolset::Runtime,
            runs,
            eng,
            schema_of::<StartParams>,
            native_rizin_session_begin,
        ),
        spec(
            "native_rizin_session_command_run",
            "Rizin debug command",
            "Run one Rizin command line in a debug session (for example `dr` registers, `db main` breakpoint, `dc` continue, `ds` step, `dbt` backtrace, `dm` memory maps, `pd 10 @ rip`, `px 64 @ rsp`; chain with `;`) and return its output and any `ERROR:` lines, waiting up to timeout_seconds. A command still running at the deadline (a `dc` that never stops) keeps running and the next command waits for it. Visual mode isn't available. Commands can run the program and change its memory, so this asks for consent.",
            "Type a command into the debugger.",
            Toolset::Runtime,
            runs,
            eng,
            schema_of::<CommandParams>,
            native_rizin_session_command_run,
        ),
        spec(
            "native_rizin_session_show",
            "Rizin debug session status",
            "Show one Rizin debug session (or all when session_id is omitted): whether Rizin is alive, what it debugs, whether a command is still running, and any output that arrived since the last command.",
            "Check on an open debugger session.",
            Toolset::Runtime,
            Effects::MUTATES_SESSION,
            Requires::Nothing,
            schema_of::<ShowParams>,
            native_rizin_session_show,
        ),
        spec(
            "native_rizin_session_end",
            "Close a Rizin debug session",
            "End a Rizin debug session: ask Rizin to quit (which ends a program it started; an attached process is detached), then stop it and anything it started.",
            "Close a debugger session.",
            Toolset::Runtime,
            Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS,
            Requires::Nothing,
            schema_of::<SessionIdParams>,
            native_rizin_session_end,
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
    /// Absolute path of the program to start under the debugger.
    #[serde(default)]
    pub program: Option<String>,
    /// Arguments the program gets.
    #[serde(default)]
    pub args: Vec<String>,
    /// A running process to attach to instead of starting a program.
    #[serde(default)]
    pub pid: Option<u32>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CommandParams {
    pub session_id: String,
    /// One Rizin command line.
    pub command: String,
    /// Seconds to wait for the command to finish: 1–300, default 10.
    #[serde(default = "d_timeout")]
    pub timeout_seconds: u64,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ShowParams {
    #[serde(default)]
    pub session_id: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SessionIdParams {
    pub session_id: String,
}

struct RizinStore(Mutex<HashMap<String, RizinSession>>);

fn store(ctx: &mut Ctx<'_>) -> Arc<RizinStore> {
    if let Some(s) = ctx.session.ext.get::<RizinStore>() {
        return s;
    }
    let s = Arc::new(RizinStore(Mutex::new(HashMap::new())));
    ctx.session.ext.insert(s.clone());
    s
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn new_id() -> String {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let h = sha256_hex(format!("rizin:{}:{nanos}:{n}", std::process::id()).as_bytes());
    format!("rizin_{}", h.get(..24).unwrap_or(&h))
}

fn unknown_session() -> ToolError {
    ToolError::new(ErrorCode::BadInput, "no Rizin debug session with that id")
        .with_remediation("List sessions with native_rizin_session_show, or start one with native_rizin_session_begin.")
}

fn target(p: &StartParams) -> Result<Target, ToolError> {
    match (&p.program, p.pid) {
        (Some(_), Some(_)) => Err(ToolError::invalid("give a program or a pid, not both")),
        (None, None) => Err(ToolError::invalid("give the program to debug (absolute path) or the pid of a running process")),
        (None, Some(pid)) => {
            if !p.args.is_empty() {
                return Err(ToolError::invalid("args only apply to a program started by the debugger"));
            }
            if pid == 0 {
                return Err(ToolError::invalid("pid 0 isn't a process that can be debugged"));
            }
            Ok(Target::Process { pid })
        }
        (Some(prog), None) => {
            let path = PathBuf::from(prog);
            if !path.is_absolute() {
                return Err(ToolError::invalid(format!("program {prog:?} is not an absolute path")));
            }
            if !path.is_file() {
                return Err(ToolError::invalid(format!("program {prog} is not a file")));
            }
            if p.args.len() > 256 || p.args.iter().any(|a| a.contains(['\n', '\r', '\0'])) {
                return Err(ToolError::invalid("args must be at most 256 single-line strings"));
            }
            Ok(Target::Program { path, args: p.args.clone() })
        }
    }
}

fn locate_rizin(ctx: &Ctx<'_>) -> Result<PathBuf, ToolError> {
    let s = &ctx.session.settings;
    craft_anything_engines::locate("rizin", &s.engines.tools, &s.engine_store_dir())
        .ok_or_else(|| ToolError::unavailable("Rizin is not installed.").with_remediation("Install Rizin and set its path in Settings → Engines."))
}

/// The session's status with its id.
fn status_json(id: &str, s: &mut RizinSession) -> Value {
    let mut v = s.status();
    if let Value::Object(m) = &mut v {
        m.insert("session_id".into(), Value::String(id.to_string()));
    }
    v
}

fn subject(s: &RizinSession) -> Subject {
    let name = match &s.target {
        Target::Program { path, .. } => path.file_name().map(|n| n.to_string_lossy().into_owned()),
        Target::Process { pid } => Some(format!("pid {pid}")),
    };
    Subject { kind: "process".into(), sha256: None, name }
}

// ---------------------------------------------------------------------------------------------
// Tools

fn native_rizin_session_begin(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StartParams = parse_params(params)?;
    let target = target(&p)?;
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    guard.retain(|_, s| !s.is_finished());
    if guard.len() >= MAX_SESSIONS {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{MAX_SESSIONS} Rizin debug sessions are already open"))
            .with_remediation("Close one with native_rizin_session_end."));
    }
    let rizin = locate_rizin(ctx)?;
    ctx.report(None, "Starting Rizin's debugger");
    let cancel = ctx.cancel.clone();
    let (mut s, c) = RizinSession::start(&rizin, target, &|| cancel.is_cancelled())?;
    let id = new_id();
    let mut out = status_json(&id, &mut s);
    if let Value::Object(m) = &mut out {
        m.insert("messages".into(), Value::String(c.output));
        m.insert("continue_with".into(), Value::String("native_rizin_session_command_run".into()));
    }
    guard.insert(id, s);
    Ok(ToolOutput::Value(out))
}

fn native_rizin_session_command_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CommandParams = parse_params(params)?;
    let cmd = craft_anything_engines::rizin::check_command(&p.command)?.to_string();
    if cmd.len() > 4096 {
        return Err(ToolError::invalid("command must be at most 4096 characters"));
    }
    let timeout = Duration::from_secs(p.timeout_seconds.clamp(1, 300));
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    let s = guard.get_mut(&p.session_id).ok_or_else(unknown_session)?;
    ctx.report(None, format!("rizin: {cmd}"));
    let cancel = ctx.cancel.clone();
    let (c, timed_out) = s.command(&cmd, timeout, &|| cancel.is_cancelled())?;
    let status = status_json(&p.session_id, s);
    let mut lims =
        vec![Limitation::new("live_session", "Output reflects this moment in a live debugging session; running the program again can give different results.")];
    if timed_out {
        lims.push(Limitation::new(
            "timed_out",
            "The command had not finished when the wait ended; it keeps running and the next command waits for it. Its later output appears in native_rizin_session_show.",
        ));
    }
    if c.truncated {
        lims.push(Limitation::new("output_capped", "More than 1 MiB of text arrived; the rest was dropped."));
    }
    let alive = status.get("alive").and_then(Value::as_bool).unwrap_or(false);
    let e = EvidenceBuilder::new("native_rizin_session_command_run", subject(s), Environment::builtin(ctx.session.clean_room()))
        .params(json!({"session_id": p.session_id, "command": cmd, "timeout_seconds": timeout.as_secs()}))
        .result(json!({
            "command": cmd,
            "timed_out": timed_out,
            "output": c.output,
            "errors": c.errors,
            "status": status,
        }))
        .summary(format!(
            "rizin `{cmd}`: {} line(s) of output, {} error(s){}.",
            c.output.lines().count(),
            c.errors.len(),
            if timed_out {
                ", still running"
            } else if !alive {
                ", Rizin has exited"
            } else {
                ""
            }
        ))
        .confidence(Confidence::Observed)
        .authority(Authority::OurRun)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn native_rizin_session_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ShowParams = parse_params(params)?;
    let st = store(ctx);
    let mut guard = st.0.lock().unwrap_or_else(PoisonError::into_inner);
    match &p.session_id {
        Some(id) => {
            let s = guard.get_mut(id).ok_or_else(unknown_session)?;
            let (c, dropped) = s.take_output();
            let mut v = status_json(id, s);
            if let Value::Object(m) = &mut v {
                m.insert("new_output".into(), json!({"output": c.output, "errors": c.errors}));
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

fn native_rizin_session_end(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
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

    fn granted() -> CallOptions<'static> {
        let mut o = CallOptions::new(Caller::Mcp);
        o.consent = Consent::Granted;
        o
    }

    #[test]
    fn sessions_need_a_target_consent_and_an_id() {
        let mut s = crate::testing::session();
        // A stand-in path, so the checks below run without Rizin installed.
        let stand_in = craft_anything_testkit::temp_file("rizin.exe", b"");
        s.settings.engines.tools.rizin = Some(stand_in.clone());
        let e = Engine::new(s);
        assert!(e.call("native_rizin_session_begin", json!({"program": stand_in}), CallOptions::new(Caller::Mcp)).is_err(), "asks for consent first");
        for bad in [json!({}), json!({"program": "relative.exe"}), json!({"program": stand_in, "pid": 4}), json!({"pid": 0}), json!({"pid": 4, "args": ["x"]})]
        {
            assert!(e.call("native_rizin_session_begin", bad.clone(), granted()).is_err(), "{bad}");
        }
        assert!(e.call("native_rizin_session_command_run", json!({"session_id": "nope", "command": "dr"}), granted()).is_err());
        assert!(e.call("native_rizin_session_command_run", json!({"session_id": "nope", "command": "dr\nq"}), granted()).is_err());
        let st = e.call("native_rizin_session_show", json!({}), CallOptions::new(Caller::Mcp));
        assert!(matches!(st, Ok(ToolOutput::Value(v)) if v["count"] == 0));
        assert!(e.call("native_rizin_session_end", json!({"session_id": "nope"}), CallOptions::new(Caller::Mcp)).is_err());
    }

    /// A real round trip, only where `CRAFT_ANYTHING_TEST_RIZIN` names a Rizin: start this test
    /// program under the debugger (it never runs past its entry), read registers, close.
    #[test]
    fn live_session_with_rizin() {
        let Some(rizin) = std::env::var_os("CRAFT_ANYTHING_TEST_RIZIN").map(PathBuf::from) else { return };
        let mut s = crate::testing::session();
        s.settings.engines.tools.rizin = Some(rizin);
        let e = Engine::new(s);
        let me = std::env::current_exe().unwrap();
        let Ok(ToolOutput::Value(v)) = e.call("native_rizin_session_begin", json!({"program": me, "args": ["--list"]}), granted()) else {
            panic!("start failed")
        };
        let id = v["session_id"].as_str().unwrap().to_string();
        assert_eq!(v["alive"], true, "{v}");
        let run = |cmd: &str| {
            let Ok(ToolOutput::Evidence(ev)) = e.call("native_rizin_session_command_run", json!({"session_id": id, "command": cmd}), granted()) else {
                panic!("{cmd} failed")
            };
            serde_json::to_value(&*ev).unwrap()["result"].clone()
        };
        let r = run("dr PC");
        assert_eq!(r["timed_out"], false, "{r}");
        assert!(r["output"].as_str().unwrap().contains(" = 0x"), "{r}");
        let r = run("dr nosuchregister");
        assert!(!r["errors"].as_array().unwrap().is_empty(), "{r}");
        let Ok(ToolOutput::Value(c)) = e.call("native_rizin_session_end", json!({"session_id": id}), CallOptions::new(Caller::Mcp)) else {
            panic!("close failed")
        };
        assert_eq!(c["closed"], true);

        // A `dc` that outlasts its wait keeps going, and the next command waits for it.
        if cfg!(windows) {
            let ping = PathBuf::from(std::env::var("SystemRoot").unwrap_or_else(|_| "C:\\Windows".into())).join("System32").join("PING.EXE");
            let Ok(ToolOutput::Value(v)) = e.call("native_rizin_session_begin", json!({"program": ping, "args": ["-n", "4", "127.0.0.1"]}), granted()) else {
                panic!("start failed")
            };
            let id = v["session_id"].as_str().unwrap().to_string();
            let call = |cmd: &str, secs: u64| {
                e.call("native_rizin_session_command_run", json!({"session_id": id, "command": cmd, "timeout_seconds": secs}), granted())
            };
            let mut waited = false;
            for _ in 0..20 {
                let Ok(ToolOutput::Evidence(ev)) = call("dc", 1) else { panic!("dc failed") };
                let r = serde_json::to_value(&*ev).unwrap()["result"].clone();
                if r["timed_out"] == true {
                    waited = true;
                    break;
                }
            }
            assert!(waited, "ping never kept dc busy for a second");
            let Ok(ToolOutput::Value(st)) = e.call("native_rizin_session_show", json!({"session_id": id}), CallOptions::new(Caller::Mcp)) else { panic!() };
            assert_eq!(st["busy"], true, "{st}");
            assert!(call("dr PC", 30).is_ok(), "the next command waits for the running one");
            let _ = e.call("native_rizin_session_end", json!({"session_id": id}), CallOptions::new(Caller::Mcp));
        }
    }
}
