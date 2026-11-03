//! Agent CLIs (Claude Code, Codex, Gemini CLI, OpenCode, Hermes…) run as owned subprocesses with
//! our MCP server, optionally on another machine over ssh. Their JSON event streams become
//! [`AgentEvent`]s.
//!
//! How each CLI is driven lives in [`adapters`] ([`AgentAdapter`], registered in
//! [`AgentAdapters`]). Flags: Claude Code's were checked against `claude --help`. For the others,
//! the flags we rely on are checked at run time against `<cli> --help`; when they're missing we
//! fall back to the plain adapter (prompt as an argument, stdout streamed as text) and say so,
//! unless the CLI's plain form is interactive (Codex), which keeps its adapter.

pub mod acp;
pub mod adapters;

pub use acp::AcpConversation;
pub use adapters::{AgentAdapter, AgentAdapters, ArgsCx};

use crate::config::BackendOptions;
use crate::model::Stop;
use crate::{AgentEvent, BackendConfig, Conversation};
use craft_anything_engine::CancelToken;
use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::Process;
use craft_anything_platform::sync::Mutex;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, Sender};
use std::sync::{Arc, PoisonError};
use std::time::Duration;

/// Name our MCP server is registered under.
pub const MCP_NAME: &str = "craft-anything";

/// Known agent CLIs: (agent id, program, display name).
pub const KNOWN: &[(&str, &str, &str)] = &[
    ("claude-code", "claude", "Claude Code"),
    ("codex", "codex", "Codex"),
    ("gemini-cli", "gemini", "Gemini CLI"),
    ("antigravity", "agy", "Antigravity"),
    ("opencode", "opencode", "OpenCode"),
    ("hermes", "hermes", "Hermes Agent"),
    ("qwen-code", "qwen", "Qwen Code"),
    ("goose", "goose", "Goose"),
    ("maki", "maki", "Maki"),
    ("aider", "aider", "Aider"),
];

pub fn program_for(agent: &str) -> String {
    KNOWN.iter().find(|(id, _, _)| *id == agent).map(|(_, p, _)| p.to_string()).unwrap_or_else(|| agent.to_string())
}

pub fn display_for(agent: &str) -> String {
    KNOWN.iter().find(|(id, _, _)| *id == agent).map(|(_, _, d)| d.to_string()).unwrap_or_else(|| agent.to_string())
}

/// The built-in adapter for an agent id (the plain one for agents without their own).
pub fn adapter_for(agent: &str) -> Arc<dyn AgentAdapter> {
    AgentAdapters::built_in().for_agent(agent)
}

/// The MCP server command handed to the CLI.
#[derive(Debug, Clone, PartialEq)]
pub struct McpCommand {
    pub command: String,
    pub args: Vec<String>,
    /// Where the person's notes wait for a builder on this computer (`rebuild::notes`), so an
    /// agent with tool hooks can hand them over at its next step. None for remote runs.
    pub notes: Option<PathBuf>,
}

impl McpCommand {
    /// Our installed CLI (`craft-anything-cli mcp [--project <dir>] [--inbox <dir>]`). Remote runs
    /// use the name on the remote PATH and have no local project or inbox.
    pub fn local_or_remote(remote: bool, project: Option<PathBuf>, inbox: Option<PathBuf>) -> McpCommand {
        let command = if remote {
            "craft-anything-cli".to_string()
        } else {
            craft_anything_platform::self_cli_path().map(|p| p.display().to_string()).unwrap_or_else(|| "craft-anything-cli".to_string())
        };
        let mut args = vec!["mcp".to_string()];
        if let Some(p) = project.filter(|_| !remote) {
            args.push("--project".into());
            args.push(p.display().to_string());
        }
        let notes = inbox.as_deref().filter(|_| !remote).map(crate::rebuild::notes::notes_dir);
        if let Some(i) = inbox.filter(|_| !remote) {
            args.push("--inbox".into());
            args.push(i.display().to_string());
        }
        McpCommand { command, args, notes }
    }
}

/// Whether the `craft-anything-cli` a builder's tool server runs from (None: there isn't one) can
/// start. Without it Claude Code stops at its first approval with a stack trace (#91). A check
/// that ran out of time says nothing about the program, so the build goes ahead. Stopping the
/// build ends the check, as `ErrorCode::Cancelled`.
pub fn cli_can_start(cli: Option<&Path>, stop: &CancelToken) -> Result<(), ToolError> {
    const REINSTALL: &str = "Install the latest Craft Anything again: it keeps this helper next to the app. If you built the app yourself, run `cargo build -p craft-anything-cli` too.";
    let Some(cli) = cli else {
        return Err(ToolError::new(ErrorCode::EngineMissing, "Craft Anything's helper program (craft-anything-cli) is missing, so the builder can't start.")
            .with_remediation(REINSTALL));
    };
    let failed = |why: String| {
        ToolError::new(ErrorCode::EngineMissing, format!("Craft Anything's helper program at {} wouldn't start: {why}", cli.display()))
            .with_remediation(REINSTALL)
    };
    let stop = stop.clone();
    match Process::new(cli.as_os_str()).arg("--version").timeout(Duration::from_secs(30)).stdout_cap(64 * 1024).cancel_when(move || stop.is_cancelled()).run() {
        Ok(out) if out.success => Ok(()),
        Ok(out) => Err(failed(out.code.map_or_else(|| "it was stopped by the system".to_string(), |c| format!("it exited with code {c}")))),
        Err(e) if e.code == ErrorCode::TimedOut => Ok(()),
        Err(e) if e.code == ErrorCode::Cancelled => Err(e),
        Err(e) => Err(failed(e.message)),
    }
}

/// Whether a local build by `agent` can have our tool server: over ACP every agent is handed it,
/// else its adapter says.
pub fn check_builder_tools(adapter: &dyn AgentAdapter, agent: &str, options: &BackendOptions, stop: &CancelToken) -> Result<(), ToolError> {
    if options.acp == Some(true) && acp::acp_args(agent).is_some() {
        return cli_can_start(craft_anything_platform::self_cli_path().as_deref(), stop);
    }
    adapter.check_tool_server(stop)
}

fn toml_string(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into())
}

/// The permission-prompt tool a builder run routes its approvals through.
pub const APPROVAL_TOOL: &str = craft_anything_engine::tools::interaction_tools::APPROVE_TOOL;

/// What an agent run may do with files.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Access {
    /// Only analyse: no edits.
    Analyse,
    /// Build: read freely, edit through our approval tool (which asks the person when needed).
    Build,
    /// Build in Clean room: every read and edit goes through our approval tool, which keeps the
    /// original out of reach.
    CleanRoomBuild,
    /// A question about a build: read the project's files, change nothing, keep no session.
    Question,
    /// The same in Clean room: no file tools at all (the answer comes from what it knows and
    /// what the question says), so the original stays out of reach.
    CleanRoomQuestion,
}

/// argv (after the program) for one prompt.
pub fn build_args(
    adapter: &dyn AgentAdapter,
    opts: &BackendOptions,
    prompt: &str,
    preamble: &str,
    mcp: &McpCommand,
    resume: Option<&str>,
    access: Access,
) -> Vec<String> {
    // A leading dash would be read as a flag.
    let prompt = if prompt.starts_with('-') { format!(" {prompt}") } else { prompt.to_string() };
    let builder = matches!(access, Access::Build | Access::CleanRoomBuild);
    let question = matches!(access, Access::Question | Access::CleanRoomQuestion);
    let reads_checked = matches!(access, Access::CleanRoomBuild | Access::CleanRoomQuestion);
    adapter.args(&ArgsCx { options: opts, prompt: &prompt, preamble, mcp, resume, builder, reads_checked, question })
}

/// True when `program`'s help mentions every required flag (10 s limit, stdin closed).
pub fn verify_flags(program: &str, help_args: &[&str], needed: &[&str]) -> bool {
    if needed.is_empty() {
        return true;
    }
    match Process::new(program).args(help_args).timeout(Duration::from_secs(10)).stdout_cap(256 * 1024).run() {
        Ok(out) => {
            let text = format!("{}{}", out.stdout_text(), out.stderr_text());
            needed.iter().all(|f| text.contains(f))
        }
        Err(_) => false,
    }
}

/// The fix for a sign-in failure, in plain words. Sign-in always happens in Claude Code itself;
/// we never see or handle the account.
pub fn sign_in_hint(message: &str) -> Option<String> {
    let m = message.to_ascii_lowercase();
    ["authenticat", "oauth", "log in", "login", "not logged", "api key", "unauthorized"]
        .iter()
        .any(|w| m.contains(w))
        .then(|| "Sign in to Claude Code: open a terminal and run `claude auth login` (or start `claude` and type /login), then try again.".to_string())
}

/// Words in an API's answer when the installed Claude Code is older than the model it was asked
/// to use (#165).
pub const TOO_OLD_FOR_MODEL: &str = "does not support this model";

/// Claude Code's failure in plain words, and its fix when the person can make one: a version too
/// old for the model (#165), or a sign-in.
pub fn claude_code_failure(why: &str) -> (String, Option<String>) {
    if why.to_ascii_lowercase().contains(TOO_OLD_FOR_MODEL) {
        return (
            format!("Claude Code is too old for the model it was asked to use ({}).", why.chars().take(200).collect::<String>()),
            Some(
                "Update the `claude` command-line tool, which is installed and updated apart from the Claude desktop app: open a terminal and run `claude update`, then try again. Or choose another model for Claude Code in Settings → AI."
                    .into(),
            ),
        );
    }
    (format!("Claude Code stopped: {why}"), sign_in_hint(why))
}

/// Variables a Claude Code session sets for its own child processes. When Craft Anything itself
/// runs inside such a session, they'd make the person's `claude` act as part of that session
/// instead of as their own install, so they're removed. The person's own settings (provider
/// choice `CLAUDE_CODE_USE_*`, `CLAUDE_CONFIG_DIR`, `ANTHROPIC_*`) are kept.
pub fn host_session_vars(vars: impl Iterator<Item = String>) -> Vec<String> {
    let all: Vec<String> = vars.collect();
    if !all.iter().any(|k| k == "CLAUDECODE") {
        return Vec::new();
    }
    all.into_iter()
        .filter(|k| {
            matches!(k.as_str(), "CLAUDECODE" | "CLAUDE_PID" | "CLAUDE_EFFORT")
                || k.starts_with("CLAUDE_AGENT_SDK_")
                || k.starts_with("CLAUDE_PREVIEW_")
                || (k.starts_with("CLAUDE_CODE_") && !k.starts_with("CLAUDE_CODE_USE_"))
        })
        .collect()
}

/// `program` as the person's own standalone Claude Code (see [`host_session_vars`]).
fn standalone(program: &str) -> Process {
    host_session_vars(std::env::vars().map(|(k, _)| k)).into_iter().fold(Process::new(program), |p, k| p.env_remove(k))
}

/// Parses one CLI's output stream: the adapter reads each line, this keeps what it learned.
pub struct StreamParser {
    adapter: Arc<dyn AgentAdapter>,
    pub session_id: Option<String>,
    pub tool_names: HashMap<String, String>,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cost_usd: Option<f64>,
    pub saw_result: bool,
    /// The run was asked to continue a saved session the agent doesn't have (it lives on another
    /// computer, or under another folder), so it did nothing.
    pub session_missing: bool,
}

fn short_tool(name: &str) -> String {
    name.strip_prefix(&format!("mcp__{MCP_NAME}__")).or_else(|| name.strip_prefix(&format!("{MCP_NAME}__"))).unwrap_or(name).to_string()
}

fn find_evidence_id(text: &str) -> Option<String> {
    let mut rest = text;
    while let Some(pos) = rest.find("ev_") {
        let cand = rest.get(pos..pos + 67).unwrap_or_default();
        if craft_anything_evidence::is_evidence_id(cand) {
            return Some(cand.to_string());
        }
        rest = rest.get(pos + 3..).unwrap_or_default();
    }
    None
}

fn content_text(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Array(a) => a.iter().filter_map(|b| b.get("text").and_then(Value::as_str)).collect::<Vec<_>>().join(""),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn summary_of(s: &str) -> String {
    s.chars().take(200).collect()
}

impl StreamParser {
    /// A parser for one run, reading lines the way `adapter` says.
    pub fn new(adapter: Arc<dyn AgentAdapter>) -> Self {
        StreamParser {
            adapter,
            session_id: None,
            tool_names: HashMap::new(),
            input_tokens: 0,
            output_tokens: 0,
            cost_usd: None,
            saw_result: false,
            session_missing: false,
        }
    }

    /// Events for one output line.
    pub fn line(&mut self, line: &str) -> Vec<AgentEvent> {
        if !self.adapter.streams_json() {
            return vec![AgentEvent::TextDelta { text: format!("{line}\n") }];
        }
        let Ok(v) = serde_json::from_str::<Value>(line.trim()) else {
            // Non-JSON lines (warnings, banners) are shown as status, not answer text.
            let t = line.trim();
            return if t.is_empty() { Vec::new() } else { vec![AgentEvent::Status { text: summary_of(t) }] };
        };
        let adapter = self.adapter.clone();
        adapter.parse(self, &v)
    }

    /// A tool call began (adapters call this from `parse`).
    pub fn started(&mut self, id: &str, name: &str, input: Value) -> AgentEvent {
        let tool = short_tool(name);
        self.tool_names.insert(id.to_string(), tool.clone());
        AgentEvent::ToolStarted { call_id: id.to_string(), tool, input }
    }

    /// A tool call ended.
    pub fn finished(&mut self, id: &str, ok: bool, text: &str) -> AgentEvent {
        let tool = self.tool_names.get(id).cloned().unwrap_or_default();
        AgentEvent::ToolFinished { call_id: id.to_string(), tool, ok, summary: summary_of(text), evidence_id: find_evidence_id(text) }
    }
}

/// Everything needed to run one CLI backend.
#[derive(Debug, Clone)]
pub struct CliSpec {
    pub config: BackendConfig,
    pub options: BackendOptions,
    pub beginner: bool,
    /// The working folder (and, without `builder`, the investigation handed to our MCP server).
    pub project: Option<PathBuf>,
    /// Build mode: the agent may edit files in the working folder.
    pub builder: Option<Builder>,
    /// A saved agent session to continue.
    pub resume: Option<String>,
    /// Deep mode: our MCP server runs in it, and a builder sees every tool and may read files
    /// anywhere. In Clean room a builder sees only Clean room's tools, and every file it reads
    /// goes through the approval policy.
    pub deep: bool,
    /// Replaces the default analysis preamble.
    pub preamble: Option<String>,
    /// How each agent CLI is driven.
    pub adapters: AgentAdapters,
    /// A question about a build: read-only, and a resumed session is forked and not kept, so the
    /// builder's own session is never changed. Only adapters that
    /// [answer questions](adapters::AgentAdapter::answers_questions) take it.
    pub question: bool,
    /// Where a failed run writes what's known about it ([`crate::failure_log`]). None writes no log.
    pub logs: Option<PathBuf>,
}

/// What a building run needs besides the working folder.
#[derive(Debug, Clone)]
pub struct Builder {
    /// The investigation project our MCP server keeps evidence in.
    pub investigation: Option<PathBuf>,
    /// Where questions and approvals for the person go.
    pub inbox: PathBuf,
}

/// Our MCP server for `spec`, in the run's mode whatever the saved settings say; a builder's lists
/// every tool in Deep mode.
fn mcp_for(spec: &CliSpec, remote: bool) -> McpCommand {
    let mut mcp = match &spec.builder {
        Some(b) => McpCommand::local_or_remote(remote, b.investigation.clone(), Some(b.inbox.clone())),
        None => McpCommand::local_or_remote(remote, spec.project.clone(), None),
    };
    mcp.args.push(if spec.deep { "--deep" } else { "--clean-room" }.into());
    if spec.deep && spec.builder.is_some() {
        mcp.args.push("--all-tools".into());
    }
    mcp
}

impl CliSpec {
    pub fn new(config: BackendConfig, options: BackendOptions, beginner: bool, project: Option<PathBuf>) -> Self {
        CliSpec {
            config,
            options,
            beginner,
            project,
            builder: None,
            resume: None,
            deep: false,
            preamble: None,
            logs: None,
            adapters: AgentAdapters::built_in(),
            question: false,
        }
    }
}

/// The conversation for a chat with an agent CLI: over ACP when the backend asks for it and the
/// agent speaks it (a local, non-building run), else one CLI run per message.
pub fn conversation(spec: CliSpec) -> Box<dyn Conversation> {
    match acp_for(&spec).filter(|_| spec.builder.is_none()) {
        Some(c) => Box::new(c),
        None => Box::new(CliConversation::new(spec)),
    }
}

/// The conversation for a builder run: over ACP (permission requests decided by `approver`, the
/// approval policy) when the backend asks for it and the agent speaks it, else one CLI run per
/// message (approvals through our approval tool).
pub fn builder_conversation(spec: CliSpec, approver: acp::Approver) -> Box<dyn Conversation> {
    match acp_for(&spec) {
        Some(c) => Box::new(c.with_approver(approver)),
        None => Box::new(CliConversation::new(spec)),
    }
}

/// An ACP conversation for `spec`, when its backend asks for ACP (`acp = true`), runs locally
/// and its agent speaks ACP.
fn acp_for(spec: &CliSpec) -> Option<AcpConversation> {
    let agent = spec.config.model.clone();
    let local = spec.config.ssh_host.as_deref().is_none_or(|h| h.trim().is_empty());
    let acp_args = acp::acp_args(&agent).filter(|_| spec.options.acp == Some(true) && local)?;
    let program = spec.options.command.clone().unwrap_or_else(|| program_for(&agent));
    let mut args = spec.options.args.clone();
    args.extend(acp_args.iter().map(|a| a.to_string()));
    args.extend(acp::model_args(&agent, spec.options.cli_model.as_deref()));
    let cwd = spec.project.clone().or_else(|| std::env::current_dir().ok()).unwrap_or_else(std::env::temp_dir);
    let mcp = mcp_for(spec, false);
    let preamble = spec.preamble.clone().unwrap_or_else(|| crate::prompt::cli_preamble(spec.beginner));
    Some(AcpConversation::new(&spec.config.name, &agent, program, args, cwd, mcp, spec.resume.clone()).with_preamble(preamble).with_logs(spec.logs.clone()))
}

/// A conversation backed by an agent CLI. Each message is one CLI run; Claude Code runs resume
/// the previous session.
pub struct CliConversation {
    spec: CliSpec,
    tx: Sender<AgentEvent>,
    rx: Receiver<AgentEvent>,
    busy: Arc<AtomicBool>,
    stop: Stop,
    session: Arc<Mutex<Option<String>>>,
    verified: Arc<Mutex<Option<bool>>>,
    /// The last run's saved session wasn't there (see [`Conversation::session_lost`]).
    lost: Arc<AtomicBool>,
}

impl CliConversation {
    /// A conversation run as `spec` says; with `spec.resume`, its first message continues that
    /// saved session.
    pub fn new(spec: CliSpec) -> Self {
        let (tx, rx) = std::sync::mpsc::channel();
        let session = Arc::new(Mutex::new(spec.resume.clone()));
        CliConversation { spec, tx, rx, busy: Arc::default(), stop: Stop::default(), session, verified: Arc::default(), lost: Arc::default() }
    }

    /// The agent's session id once a run has reported it (to continue later).
    pub fn session_id(&self) -> Option<String> {
        self.session.lock().unwrap_or_else(PoisonError::into_inner).clone()
    }
}

/// The environment an agent program runs with: Claude Code's limits raised for a long build, and
/// the effort it thinks with. Other agents ignore these names.
fn agent_env(builder: bool, effort: Option<crate::model::Effort>) -> Vec<(&'static str, String)> {
    let (tool, shell) = if builder { (24 * 3600, 8 * 3600) } else { (40 * 60, 10 * 60) };
    let ms = |secs: u64| (secs * 1000).to_string();
    vec![
        ("MCP_TOOL_TIMEOUT", ms(tool)),
        // Progress updates keep a long tool call alive; this also covers one that sends none.
        ("CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT", "0".into()),
        // A builder waits for every tool result (Ghidra above all) instead of carrying on without it.
        ("CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS", if builder { "0" } else { "120000" }.into()),
        ("BASH_DEFAULT_TIMEOUT_MS", ms(shell / 2)),
        ("BASH_MAX_TIMEOUT_MS", ms(shell)),
        // High effort for Claude Code unless chosen. An environment variable rather than
        // `--effort`: it ranks highest, and an older Claude Code that doesn't know it ignores it.
        ("CLAUDE_CODE_EFFORT_LEVEL", crate::prompt::choose_effort(effort).as_str().into()),
    ]
}

/// The command run on another computer over SSH. ssh passes on none of our environment, so it is
/// set there with `env`.
fn remote_command(program: &str, args: Vec<String>, env: &[(&'static str, String)]) -> Vec<String> {
    let mut cmd = vec!["env".to_string()];
    cmd.extend(env.iter().map(|(k, v)| format!("{k}={v}")));
    cmd.push(program.to_string());
    cmd.extend(args);
    cmd
}

/// The run's shared state: the session it continues and reports, whether the agent's flags were
/// checked, and whether the session it was to continue was missing.
struct RunState {
    session: Arc<Mutex<Option<String>>>,
    verified: Arc<Mutex<Option<bool>>>,
    lost: Arc<AtomicBool>,
}

/// End a turn: take the next message first, then say the turn is done (`send(done)`), since
/// whoever reads `TurnDone` may send the next message at once. The other order refuses it ("Still
/// working") with no `TurnDone`, and the caller waits forever.
fn end_turn(busy: &AtomicBool, done: AgentEvent, send: impl FnOnce(AgentEvent)) {
    busy.store(false, Ordering::SeqCst);
    send(done);
}

/// The `TurnDone` that ends a turn of `backend` with no usage to report.
fn nothing_done(backend: &str) -> AgentEvent {
    AgentEvent::TurnDone { backend: backend.to_string(), input_tokens: 0, output_tokens: 0, cost_usd: None, cost_is_estimate: false }
}

/// One message as one run of the agent's program (here or over SSH), its events sent on `tx`
/// as they come. Returns the `TurnDone` that ends the turn, whatever happened, for the caller to
/// send once the conversation can take the next message. The session it reports is kept for the
/// next message; one it was asked to continue but doesn't have is forgotten and flagged in
/// `state.lost` before the error that says so is sent.
fn run_cli(spec: &CliSpec, text: &str, tx: &Sender<AgentEvent>, stop: &Stop, state: &RunState) -> AgentEvent {
    let RunState { session, verified, lost } = state;
    let name = spec.config.name.clone();
    let agent = spec.config.model.clone();
    let program = spec.options.command.clone().unwrap_or_else(|| program_for(&agent));
    let remote = spec.config.ssh_host.clone().filter(|h| !h.trim().is_empty());
    let mut adapter = spec.adapters.for_agent(&agent);
    let (help, needed) = adapter.required_flags();
    if !needed.is_empty() {
        let ok = match remote {
            Some(_) => true, // can't cheaply check a remote CLI; its errors are streamed back
            None => {
                let mut v = verified.lock().unwrap_or_else(PoisonError::into_inner);
                *v.get_or_insert_with(|| verify_flags(&program, help, needed))
            }
        };
        if !ok && adapter.plain_fallback() {
            let _ = tx.send(AgentEvent::Status {
                text: format!("{program}'s help doesn't list {} here, so it runs with the plain adapter (prompt in, text out).", needed.join(" / ")),
            });
            adapter = Arc::new(adapters::Plain);
        } else if !ok {
            let _ = tx.send(AgentEvent::Status { text: format!("Couldn't confirm that {program} has {}; trying it anyway.", needed.join(" / ")) });
        }
    }
    let preamble = spec.preamble.clone().unwrap_or_else(|| crate::prompt::cli_preamble(spec.beginner));
    let mcp = mcp_for(spec, remote.is_some());
    let resume = session.lock().unwrap_or_else(PoisonError::into_inner).clone();
    let builder = spec.builder.is_some();
    // A question goes only to an agent that can be held to reading (a fallback adapter can't).
    if spec.question && !adapter.answers_questions() {
        let _ = tx.send(AgentEvent::Error {
            message: format!("{name} can't be kept to only reading here, so it isn't asked questions about a build."),
            remediation: Some("Ask with Claude Code, or with an AI that has an API key.".into()),
            log: None,
        });
        return nothing_done(&name);
    }
    let access = match (&spec.builder, spec.deep, spec.question) {
        (_, true, true) => Access::Question,
        (_, false, true) => Access::CleanRoomQuestion,
        (Some(_), true, false) => Access::Build,
        (Some(_), false, false) => Access::CleanRoomBuild,
        (None, _, false) => Access::Analyse,
    };
    let args = build_args(adapter.as_ref(), &spec.options, text, &preamble, &mcp, if adapter.resumes() { resume.as_deref() } else { None }, access);
    let shown = FailureContext::new(&program, &args, text, remote.as_deref(), spec);
    // A builder turn may take hours and sit silent for long stretches: Ghidra's first look at a big
    // game, an engine build, or the person answering a question. Claude Code's own limits are
    // raised to match, so nothing cuts a long clone short (its defaults stop a quiet tool call at
    // 30 minutes and a background build at 10).
    let (turn, quiet) = if builder { (24 * 3600, 8 * 3600) } else { (30 * 60, 15 * 60) };
    let env = agent_env(builder, spec.options.effort);
    let (prog, argv) = match &remote {
        Some(host) => ("ssh".to_string(), crate::ssh::ssh_args(host, &remote_command(&program, args, &env))),
        None => (program.clone(), args),
    };
    let _ =
        tx.send(AgentEvent::Status { text: format!("Asking {}{}…", display_for(&agent), remote.as_ref().map(|h| format!(" on {h}")).unwrap_or_default()) });
    let parser = Arc::new(Mutex::new(StreamParser::new(adapter.clone())));
    let (p2, tx2, tx_err, lost2) = (parser.clone(), tx.clone(), tx.clone(), lost.clone());
    let stop2 = stop.clone();
    let mut proc = (if remote.is_none() { adapter.process(&prog) } else { Process::new(&prog) })
        .args(&argv)
        .timeout(Duration::from_secs(spec.options.timeout_secs.unwrap_or(turn)))
        .idle_timeout(Duration::from_secs(quiet));
    for (k, v) in &env {
        proc = proc.env(k, v.as_str());
    }
    let mut proc = proc
        .stdout_cap(4 * 1024 * 1024)
        .cancel_when(move || stop2.is_stopped())
        .on_stdout_line(move |l| {
            let mut p = p2.lock().unwrap_or_else(PoisonError::into_inner);
            let events = p.line(l);
            // Said before the error that follows it, so whoever reads the error can tell.
            if p.session_missing {
                lost2.store(true, Ordering::SeqCst);
            }
            for e in events {
                let _ = tx2.send(e);
            }
        })
        .on_stderr_line(move |l| {
            if !l.trim().is_empty() {
                let _ = tx_err.send(AgentEvent::Output { text: l.to_string() });
            }
        })
        .remediation(format!("Install {}, or choose its program in Settings → AI.", display_for(&agent)));
    if let Some(p) = spec.project.as_ref().filter(|_| remote.is_none()) {
        proc = proc.cwd(p);
    }
    if adapter.prompt_on_stdin() {
        proc = proc.stdin_bytes(text);
    }
    let result = proc.run();
    let p = parser.lock().unwrap_or_else(PoisonError::into_inner);
    if p.session_missing {
        // The id it reported is the one it couldn't find: the next message starts a new session.
        *session.lock().unwrap_or_else(PoisonError::into_inner) = None;
    } else if let Some(id) = &p.session_id {
        *session.lock().unwrap_or_else(PoisonError::into_inner) = Some(id.clone());
    }
    match result {
        // It said why already, and there's nothing more in its output to keep.
        Ok(_) if p.session_missing => {}
        Ok(out) if !out.success && !p.saw_result => {
            let _ = tx.send(shown.exit_event(&agent, &out));
        }
        Ok(out) if !out.success => {
            // The agent already said what went wrong; keep the rest for anyone looking into it.
            if let Some(path) = shown.save(&agent, Some(&out), None).0 {
                let _ = tx.send(AgentEvent::Status { text: format!("The details are in {}", path.display()) });
            }
        }
        Ok(_) => {}
        Err(e) if e.code == craft_anything_evidence::ErrorCode::Cancelled => {
            let _ = tx.send(AgentEvent::Status { text: "Stopped.".into() });
        }
        Err(e) => {
            let _ = tx.send(shown.error_event(&agent, e));
        }
    }
    AgentEvent::TurnDone { backend: name, input_tokens: p.input_tokens, output_tokens: p.output_tokens, cost_usd: p.cost_usd, cost_is_estimate: true }
}

/// What's needed to explain a failed CLI run: the command with the person's message left out, and
/// where to write the log.
struct FailureContext {
    command: String,
    check: String,
    program: String,
    host: Option<String>,
    backend: String,
    cwd: Option<PathBuf>,
    logs: Option<PathBuf>,
}

impl FailureContext {
    fn new(program: &str, args: &[String], message: &str, host: Option<&str>, spec: &CliSpec) -> Self {
        use craft_anything_platform::process::printable_command;
        let message = message.trim();
        let args: Vec<String> = args
            .iter()
            .map(|a| if !message.is_empty() && a.contains(message) { format!("[your message, {} characters]", message.chars().count()) } else { a.clone() })
            .collect();
        let local = printable_command(OsStr::new(program), &args);
        let (command, check) = match host {
            Some(h) => {
                let options = crate::ssh::SSH_OPTIONS.join(" ");
                (format!("ssh {options} -T {} -- {local}", crate::ssh::shell_quote(h)), crate::ssh::check_command(h, program))
            }
            None => (local, format!("{} --version", crate::ssh::shell_quote(program))),
        };
        FailureContext {
            command,
            check,
            program: program.to_string(),
            host: host.map(str::to_string),
            backend: spec.config.name.clone(),
            cwd: spec.project.clone().filter(|_| host.is_none()),
            logs: spec.logs.clone(),
        }
    }

    /// Why this run failed, when it was ssh (or the remote computer) that says so.
    fn ssh_failure(&self, out: &craft_anything_platform::Output) -> Option<crate::ssh::SshFailure> {
        let host = self.host.as_deref()?;
        crate::ssh::diagnose(host, &self.program, crate::ssh::is_git_server(host), out.code, &out.stderr_text())
    }

    /// Write the log. Returns its path, or what to tell the person when it couldn't be written.
    fn save(&self, agent: &str, out: Option<&craft_anything_platform::Output>, diagnosis: Option<&str>) -> (Option<PathBuf>, Option<String>) {
        self.save_with(agent, out, diagnosis, None)
    }

    fn save_with(
        &self,
        agent: &str,
        out: Option<&craft_anything_platform::Output>,
        diagnosis: Option<&str>,
        error: Option<&str>,
    ) -> (Option<PathBuf>, Option<String>) {
        let Some(dir) = &self.logs else { return (None, None) };
        let report = crate::failure_log::Report {
            what: format!("{} ({})", display_for(agent), self.backend),
            command: self.command.clone(),
            check: self.check.clone(),
            diagnosis: diagnosis.map(str::to_string),
            error: error.map(str::to_string),
            cwd: self.cwd.clone(),
            exit_code: out.and_then(|o| o.code),
            duration: out.map(|o| o.duration),
            stdout: out.map(|o| o.stdout.clone()).unwrap_or_default(),
            stderr: out.map(|o| o.stderr.clone()).unwrap_or_default(),
        };
        match crate::failure_log::write(dir, &report) {
            Ok(path) => {
                log::warn!("{} failed; details in {}", display_for(agent), path.display());
                (Some(path), None)
            }
            Err(e) => {
                log::warn!("couldn't write a failure log: {e}");
                (None, Some(format!("The details couldn't be saved: {e}")))
            }
        }
    }

    fn exit_event(&self, agent: &str, out: &craft_anything_platform::Output) -> AgentEvent {
        let name = display_for(agent);
        let plain = craft_anything_platform::process::nonzero_error_with(&name, out, Some(&self.command));
        let excerpt = craft_anything_platform::process::output_excerpt(&String::from_utf8_lossy(if out.stderr.is_empty() { &out.stdout } else { &out.stderr }));
        let (message, mut remediation) = match self.ssh_failure(out) {
            Some(f) => {
                let host = self.host.as_deref().unwrap_or_default();
                let said = if excerpt.is_empty() { String::new() } else { format!("\n\nssh printed:\n{excerpt}") };
                (format!("Couldn't run {name} on {host}: {}.", f.what), format!("{}{said}\n\nTo test it yourself, run:\n{}", f.fix, self.check))
            }
            None => (plain.message, plain.remediation.unwrap_or_default()),
        };
        let (log, unsaved) = self.save(agent, Some(out), Some(&message));
        if let Some(u) = unsaved {
            remediation.push_str(&format!("\n\n{u}"));
        }
        AgentEvent::Error { message, remediation: Some(remediation), log }
    }

    fn error_event(&self, agent: &str, e: ToolError) -> AgentEvent {
        let details = e.details.as_ref().map(ToString::to_string);
        let text = match details {
            Some(d) => format!("{}\n{d}", e.message),
            None => e.message.clone(),
        };
        let (log, unsaved) = self.save_with(agent, None, None, Some(&text));
        let remediation = match (e.remediation, unsaved) {
            (Some(r), Some(u)) => Some(format!("{r}\n\n{u}")),
            (r, u) => r.or(u),
        };
        AgentEvent::Error { message: e.message, remediation, log }
    }
}

impl Conversation for CliConversation {
    fn session_id(&self) -> Option<String> {
        CliConversation::session_id(self)
    }

    /// Set by the last run (see `run_cli`) and cleared when the next message is sent.
    fn session_lost(&self) -> bool {
        self.lost.load(Ordering::SeqCst)
    }

    /// Runs the message on a thread of its own; a message while one is running is refused with an
    /// error event. Every turn ends with `TurnDone`, a runner that panics or can't start included,
    /// and the conversation takes the next message before that's sent: whoever reads it may send
    /// the next message at once (a session that wasn't there is followed by a fresh start).
    fn send(&mut self, text: &str) {
        if self.busy.swap(true, Ordering::SeqCst) {
            let _ = self.tx.send(AgentEvent::Error {
                message: "Still working on the last message.".into(),
                remediation: Some("Wait for it to finish or press stop.".into()),
                log: None,
            });
            return;
        }
        self.stop.reset();
        self.lost.store(false, Ordering::SeqCst);
        let (spec, tx, stop, busy) = (self.spec.clone(), self.tx.clone(), self.stop.clone(), self.busy.clone());
        let state = RunState { session: self.session.clone(), verified: self.verified.clone(), lost: self.lost.clone() };
        let text = text.to_string();
        let spawned = std::thread::Builder::new().name("ai-cli".into()).spawn(move || {
            let done = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| run_cli(&spec, &text, &tx, &stop, &state))).unwrap_or_else(|_| {
                let _ = tx.send(AgentEvent::Error { message: "The agent runner hit a bug and stopped safely.".into(), remediation: None, log: None });
                nothing_done(&spec.config.name)
            });
            end_turn(&busy, done, |e| {
                let _ = tx.send(e);
            });
        });
        if spawned.is_err() {
            let _ = self.tx.send(AgentEvent::Error { message: "Couldn't start a worker thread.".into(), remediation: None, log: None });
            end_turn(&self.busy, nothing_done(&self.spec.config.name), |e| {
                let _ = self.tx.send(e);
            });
        }
    }

    fn poll(&mut self) -> Vec<AgentEvent> {
        self.rx.try_iter().collect()
    }

    /// Agent CLIs ask for approval through their own UI; our MCP server refuses consent-gated
    /// tools unless it was started with `--allow-run`.
    fn answer_consent(&mut self, _call_id: &str, _allow: bool) {}

    fn stop(&mut self) {
        self.stop.stop();
    }

    fn is_busy(&self) -> bool {
        self.busy.load(Ordering::SeqCst)
    }
}

impl Drop for CliConversation {
    fn drop(&mut self) {
        self.stop.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Over SSH our environment doesn't reach the other computer, so the chosen effort (and Claude
    /// Code's raised limits) go in the remote command itself.
    #[test]
    fn an_agent_over_ssh_gets_its_effort_on_the_other_computer() {
        let env = agent_env(true, Some(crate::model::Effort::Max));
        assert!(env.contains(&("CLAUDE_CODE_EFFORT_LEVEL", "max".to_string())));
        assert!(env.contains(&("CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS", "0".to_string())));
        let cmd = remote_command("claude", vec!["-p".into(), "hi".into()], &env);
        assert_eq!(cmd.first().map(String::as_str), Some("env"));
        assert!(cmd.contains(&"CLAUDE_CODE_EFFORT_LEVEL=max".to_string()));
        assert_eq!(cmd[cmd.len() - 3..], ["claude", "-p", "hi"]);
        let line = crate::ssh::ssh_args("box", &cmd).pop().unwrap_or_default();
        assert!(line.starts_with("env ") && line.contains("CLAUDE_CODE_EFFORT_LEVEL=max") && line.ends_with("claude -p hi"), "{line}");
        assert!(agent_env(false, None).contains(&("CLAUDE_CODE_EFFORT_LEVEL", "high".to_string())), "high unless chosen");
    }
    use crate::BackendKind;

    fn mcp() -> McpCommand {
        McpCommand { command: "/opt/ca/craft-anything-cli".into(), args: vec!["mcp".into(), "--project".into(), "/p/x.cany".into()], notes: None }
    }

    #[test]
    fn claude_args() {
        let a = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "-what?", "PRE", &mcp(), Some("sess-1"), Access::Analyse);
        assert_eq!(a[0], "-p");
        // #402: the message goes in on stdin, so a long one can't pass Windows' command-line limit.
        assert!(adapter_for("claude-code").prompt_on_stdin() && !a.iter().any(|x| x.contains("what?")), "{a:?}");
        let pos = |f: &str| a.iter().position(|x| x == f).unwrap();
        assert_eq!(a[pos("--output-format") + 1], "stream-json");
        assert!(a.contains(&"--verbose".to_string()));
        assert_eq!(a[pos("--resume") + 1], "sess-1");
        assert_eq!(a[pos("--allowedTools") + 1], "mcp__craft-anything__*");
        assert_eq!(a[pos("--model") + 1], "claude-opus-5-5", "Opus 5.5 unless configured otherwise");
        let o = BackendOptions { cli_model: Some("opus".into()), ..Default::default() };
        let b = build_args(adapter_for("claude-code").as_ref(), &o, "q", "PRE", &mcp(), None, Access::Analyse);
        assert_eq!(b[b.iter().position(|x| x == "--model").unwrap() + 1], "opus");
        let cfg: Value = serde_json::from_str(&a[pos("--mcp-config") + 1]).unwrap();
        assert_eq!(cfg["mcpServers"]["craft-anything"]["args"][0], "mcp");
        // variadic flags come last: nothing after them is read as one of their values
        assert!(pos("--mcp-config") > pos("--resume"));
    }

    #[test]
    fn codex_and_gemini_args() {
        let a = build_args(adapter_for("codex").as_ref(), &BackendOptions::default(), "q", "P:", &mcp(), None, Access::Analyse);
        assert_eq!(&a[..2], &["exec".to_string(), "--json".to_string()]);
        // #69: project folders aren't git repositories; the flag comes once, also when the
        // backend's own args already have it.
        let skip = |a: &[String]| a.iter().filter(|x| *x == "--skip-git-repo-check").count();
        assert_eq!(skip(&a), 1);
        let o = BackendOptions { args: vec!["--skip-git-repo-check".into()], ..Default::default() };
        assert_eq!(skip(&build_args(adapter_for("codex").as_ref(), &o, "q", "P:", &mcp(), None, Access::Build)), 1);
        assert!(a.contains(&"mcp_servers.craft-anything.command=\"/opt/ca/craft-anything-cli\"".to_string()));
        assert!(a.contains(&"mcp_servers.craft-anything.args=[\"mcp\", \"--project\", \"/p/x.cany\"]".to_string()));
        assert_eq!(a.last().unwrap(), "P:q");
        let g = build_args(adapter_for("gemini-cli").as_ref(), &BackendOptions::default(), "q", "", &mcp(), None, Access::Analyse);
        assert!(g.windows(2).any(|w| w[0] == "--output-format" && w[1] == "stream-json"));
        let o = BackendOptions { args: vec!["run".into()], ..Default::default() };
        assert_eq!(build_args(adapter_for("aider").as_ref(), &o, "q", "", &mcp(), None, Access::Analyse), vec!["run".to_string(), "q".to_string()]);
    }

    #[test]
    fn nested_session_variables_are_dropped_but_user_settings_kept() {
        let v = |names: &[&str]| names.iter().map(|s| s.to_string()).collect::<Vec<_>>().into_iter();
        assert!(host_session_vars(v(&["CLAUDE_CODE_ENTRYPOINT", "PATH"])).is_empty(), "outside a session nothing is touched");
        let mut dropped = host_session_vars(v(&[
            "CLAUDECODE",
            "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH",
            "CLAUDE_CODE_SESSION_ID",
            "CLAUDE_AGENT_SDK_VERSION",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CONFIG_DIR",
            "ANTHROPIC_API_KEY",
            "PATH",
        ]));
        dropped.sort();
        assert_eq!(dropped, ["CLAUDECODE", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH", "CLAUDE_CODE_SESSION_ID"]);
    }

    fn failed(code: i32, stderr: &str) -> craft_anything_platform::Output {
        craft_anything_platform::Output {
            code: Some(code),
            success: false,
            stdout: Vec::new(),
            stderr: stderr.as_bytes().to_vec(),
            stdout_truncated: false,
            stderr_truncated: false,
            duration: Duration::from_millis(400),
        }
    }

    fn context(host: Option<&str>, logs: Option<PathBuf>) -> FailureContext {
        let config = BackendConfig {
            name: "Mine".into(),
            kind: BackendKind::AgentCli,
            model: "claude-code".into(),
            base_url: None,
            ssh_host: host.map(str::to_string),
            enabled: true,
        };
        let spec = CliSpec { logs, ..CliSpec::new(config, BackendOptions::default(), false, None) };
        let args = ["-p".to_string(), "PRE private plans for my app".to_string(), "--verbose".to_string()];
        FailureContext::new("claude", &args, "private plans for my app", host, &spec)
    }

    #[test]
    fn a_failed_ssh_run_says_what_happened_and_saves_a_log() {
        let dir = tempfile::tempdir().unwrap();
        let ev = context(Some("github.com"), Some(dir.path().to_path_buf())).exit_event("claude-code", &failed(255, "exec request failed on channel 0\n"));
        let AgentEvent::Error { message, remediation, log } = ev else { panic!("not an error") };
        let help = remediation.unwrap();
        assert!(message.contains("Couldn't run Claude Code on github.com: github.com is a git server"), "{message}");
        assert!(help.contains("exec request failed on channel 0") && help.contains("ssh -o BatchMode=yes -T github.com -- claude --version"), "{help}");
        assert!(!help.contains("by hand") && !help.contains("below"), "{help}");
        let text = std::fs::read_to_string(log.unwrap()).unwrap();
        for part in ["Exit code: 255", "exec request failed on channel 0", "git server", "claude --version", "--verbose", "[your message, 24 characters]"] {
            assert!(text.contains(part), "{part} is missing from:\n{text}");
        }
        assert!(!text.contains("private plans"), "the message stays out of the log:\n{text}");
    }

    #[test]
    fn a_failed_local_run_shows_its_output_and_command() {
        let dir = tempfile::tempdir().unwrap();
        let ev = context(None, Some(dir.path().to_path_buf())).exit_event("claude-code", &failed(3, "first\nreal reason\n"));
        let AgentEvent::Error { message, remediation, log } = ev else { panic!("not an error") };
        let help = remediation.unwrap();
        assert!(message.contains("exit code 3: real reason"), "{message}");
        assert!(help.contains("first\nreal reason") && help.contains("claude -p '[your message, 24 characters]' --verbose"), "{help}");
        assert!(log.is_some());
    }

    #[test]
    fn without_a_log_folder_nothing_is_written_and_a_failed_write_is_reported() {
        let ev = context(None, None).exit_event("claude-code", &failed(1, "x"));
        assert!(matches!(ev, AgentEvent::Error { log: None, .. }));
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("a-file");
        std::fs::write(&file, "").unwrap();
        let AgentEvent::Error { remediation, log, .. } = context(None, Some(file)).exit_event("claude-code", &failed(1, "x")) else { panic!("not an error") };
        assert!(log.is_none());
        assert!(remediation.unwrap().contains("The details couldn't be saved"));
    }

    #[test]
    fn sign_in_failures_get_a_plain_fix() {
        let mut p = StreamParser::new(adapter_for("claude-code"));
        let ev = p.line(&json!({"type":"result","subtype":"success","is_error":true,"result":"Failed to authenticate: OAuth session expired"}).to_string());
        match &ev[0] {
            AgentEvent::Error { message, remediation, .. } => {
                assert_eq!(message, "Claude Code stopped: Failed to authenticate: OAuth session expired");
                assert!(remediation.as_deref().unwrap_or_default().contains("claude auth login"));
            }
            other => panic!("{other:?}"),
        }
        assert!(sign_in_hint("rate limited").is_none());
        // #165: an install too old for the model says so, and how to update it.
        let raw =
            r#"API Error: 400 {"type":"error","error":{"type":"invalid_request_error","message":"Claude Code 2.1.81 does not support this model; version 2"}}"#;
        let (message, fix) = claude_code_failure(raw);
        assert!(message.starts_with("Claude Code is too old for the model it was asked to use") && message.contains("2.1.81"), "{message}");
        let fix = fix.unwrap_or_default();
        assert!(fix.contains("claude update") && fix.contains("desktop app") && fix.contains("Settings → AI"), "{fix}");
        assert_eq!(claude_code_failure("rate limited"), ("Claude Code stopped: rate limited".to_string(), None));
    }

    #[test]
    fn builder_args_route_permissions_and_questions_to_us() {
        let a = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "build it", "PRE", &mcp(), None, Access::Build);
        let pos = |f: &str| a.iter().position(|x| x == f).unwrap();
        assert_eq!(a[pos("--permission-prompt-tool") + 1], "mcp__craft-anything__core_action_approve");
        assert_eq!(a[pos("--disallowedTools") + 1], "AskUserQuestion");
        assert!(a[pos("--allowedTools")..].contains(&"Read".to_string()));
        assert!(!a.iter().any(|x| x == "Write" || x == "Bash"), "writes and commands always go through the approval tool");
        let analysis = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "q", "PRE", &mcp(), None, Access::Analyse);
        assert!(!analysis.contains(&"--permission-prompt-tool".to_string()));
        // A local builder gets the hook that hands over notes at its next step; analysis runs don't.
        assert!(!a.contains(&"--settings".to_string()), "no notes folder, no hook");
        let local = McpCommand { notes: Some(PathBuf::from(r"C:\p\inbox\notes")), ..mcp() };
        let b = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "build it", "PRE", &local, None, Access::Build);
        let settings: serde_json::Value = serde_json::from_str(&b[b.iter().position(|x| x == "--settings").unwrap() + 1]).unwrap();
        let hook = &settings["hooks"]["PostToolUse"][0];
        assert_eq!(hook["matcher"], "*");
        assert_eq!(hook["hooks"][0]["command"], "\"/opt/ca/craft-anything-cli\" builder-notes \"C:/p/inbox/notes\"");
        let no_hook = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "q", "PRE", &local, None, Access::Analyse);
        assert!(!no_hook.contains(&"--settings".to_string()));
        assert!(McpCommand::local_or_remote(true, None, Some(PathBuf::from("/p/inbox"))).notes.is_none(), "a remote builder can't reach this computer's files");
        let m = McpCommand::local_or_remote(false, Some("/p/inv.cany".into()), Some("/p/inbox".into()));
        assert!(m.args.windows(2).any(|w| w[0] == "--inbox" && w[1] == "/p/inbox"));
        assert!(!McpCommand::local_or_remote(true, None, Some("/p/inbox".into())).args.contains(&"--inbox".to_string()));
    }

    #[test]
    fn a_question_reads_a_copy_of_the_builders_session_and_changes_nothing() {
        let q = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "where?", "PRE", &mcp(), Some("sess-1"), Access::Question);
        let has = |a: &[String], x: &str| a.iter().any(|y| y == x);
        assert!(q.windows(3).any(|w| w[0] == "--resume" && w[1] == "sess-1" && w[2] == "--fork-session"), "a copy, never the session itself: {q:?}");
        assert!(has(&q, "--no-session-persistence") && has(&q, "--strict-mcp-config"));
        assert!(!has(&q, "--mcp-config") && !has(&q, "--permission-prompt-tool"), "no tool server: {q:?}");
        let refused = &q[q.iter().position(|x| x == "--disallowedTools").unwrap()..];
        for t in ["Write", "Edit", "Bash", "PowerShell", "WebFetch"] {
            assert!(has(refused, t), "{t} is refused");
        }
        let allowed = &q[q.iter().position(|x| x == "--allowedTools").unwrap()..];
        assert_eq!(&allowed[1..], ["Read", "Glob", "Grep"]);
        // Clean room: no file tools at all; no session: a fresh one, still not kept.
        let clean = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "where?", "PRE", &mcp(), None, Access::CleanRoomQuestion);
        assert!(!has(&clean, "--allowedTools") && !has(&clean, "--fork-session") && has(&clean, "--no-session-persistence"));
        // Only agents that can be held to reading are asked.
        assert!(adapter_for("claude-code").answers_questions());
        assert!(!adapter_for("codex").answers_questions() && !adapter_for("gemini-cli").answers_questions() && !adapter_for("aider").answers_questions());
    }

    #[test]
    fn a_clean_room_builder_reads_through_us_and_a_deep_one_sees_every_tool() {
        let clean = build_args(adapter_for("claude-code").as_ref(), &BackendOptions::default(), "build it", "PRE", &mcp(), None, Access::CleanRoomBuild);
        let allowed = &clean[clean.iter().position(|x| x == "--allowedTools").unwrap()..];
        assert!(allowed.contains(&"TodoWrite".to_string()));
        assert!(!["Read", "Glob", "Grep"].iter().any(|t| allowed.contains(&t.to_string())), "every read goes through the approval tool: {allowed:?}");
        let spec = |deep, builder: bool| CliSpec {
            deep,
            builder: builder.then(|| Builder { investigation: None, inbox: PathBuf::from("/p/inbox") }),
            ..CliSpec::new(
                BackendConfig {
                    name: "Claude".into(),
                    kind: BackendKind::AgentCli,
                    model: "claude-code".into(),
                    base_url: None,
                    ssh_host: None,
                    enabled: true,
                },
                BackendOptions::default(),
                false,
                None,
            )
        };
        let args = |deep, builder| mcp_for(&spec(deep, builder), false).args;
        assert!(args(true, true).contains(&"--all-tools".to_string()) && args(true, true).contains(&"--deep".to_string()));
        assert!(!args(false, true).contains(&"--all-tools".to_string()) && args(false, true).contains(&"--clean-room".to_string()));
        // A chat's server runs in the chat's mode too, whatever was saved.
        assert!(args(true, false).contains(&"--deep".to_string()) && !args(true, false).contains(&"--all-tools".to_string()));
        assert!(args(false, false).contains(&"--clean-room".to_string()));
    }

    #[test]
    fn parses_claude_stream() {
        let ev = format!("ev_{}", "a".repeat(64));
        let lines = [
            json!({"type":"system","subtype":"init","session_id":"s1"}).to_string(),
            json!({"type":"assistant","message":{"content":[{"type":"text","text":"Looking"},{"type":"tool_use","id":"t1","name":"mcp__craft-anything__core_session_show","input":{}}]}}).to_string(),
            json!({"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"text","text":format!("{{\"evidence_id\":\"{ev}\"}}")}]}]}}).to_string(),
            json!({"type":"result","subtype":"success","is_error":false,"total_cost_usd":0.12,"usage":{"input_tokens":5,"cache_read_input_tokens":5,"output_tokens":7}}).to_string(),
            "not json warning".to_string(),
        ];
        let mut p = StreamParser::new(adapter_for("claude-code"));
        let events: Vec<AgentEvent> = lines.iter().flat_map(|l| p.line(l)).collect();
        assert_eq!(p.session_id.as_deref(), Some("s1"));
        assert!(matches!(&events[0], AgentEvent::TextDelta { text } if text == "Looking"));
        assert!(matches!(&events[1], AgentEvent::ToolStarted { tool, .. } if tool == "core_session_show"));
        assert!(matches!(&events[2], AgentEvent::ToolFinished { tool, ok: true, evidence_id: Some(id), .. } if tool == "core_session_show" && *id == ev));
        assert!(matches!(&events[3], AgentEvent::Status { .. }));
        assert_eq!((p.input_tokens, p.output_tokens, p.cost_usd), (10, 7, Some(0.12)));
    }

    /// #446: a project copied from another computer names a session this one doesn't have. The
    /// result line is Claude Code 2.1's own.
    #[test]
    fn a_session_that_is_not_on_this_computer_is_told_apart() {
        let missing = json!({"type":"result","subtype":"error_during_execution","is_error":true,"num_turns":0,"session_id":"39b5b312-5678-1234-961c-32112666ffab","total_cost_usd":0,"errors":["No conversation found with session ID: 39b5b312-5678-1234-961c-32112666ffab"]});
        let mut p = StreamParser::new(adapter_for("claude-code"));
        let events = p.line(&missing.to_string());
        assert!(p.session_missing);
        let [AgentEvent::Error { message, remediation: Some(fix), .. }] = events.as_slice() else { panic!("{events:?}") };
        assert!(message.contains("isn't on this computer") && fix.contains("Ask again"), "{message} / {fix}");
        // Any other failure is still that failure.
        let other = json!({"type":"result","subtype":"error_during_execution","is_error":true,"num_turns":3,"errors":["Something else"]});
        let mut p = StreamParser::new(adapter_for("claude-code"));
        let events = p.line(&other.to_string());
        assert!(!p.session_missing);
        assert!(matches!(events.as_slice(), [AgentEvent::Error { message, .. }] if message.contains("error_during_execution")), "{events:?}");
    }

    /// #451: Claude Code's session is found wherever it ran, and only by a real id.
    #[test]
    fn a_claude_code_session_is_found_by_its_id_alone() {
        let config = tempfile::tempdir().unwrap();
        let folder = config.path().join("projects").join("-Users-someone-Documents-Craft-Anything-notes");
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::write(folder.join("0e4a6b1c-1111-4222-8333-944455556666.jsonl"), "{}\n").unwrap();
        std::fs::write(config.path().join("projects").join("stray.jsonl"), "{}\n").unwrap();
        let found = adapters::claude_session_file(config.path(), "0e4a6b1c-1111-4222-8333-944455556666");
        assert_eq!(found, Some(folder.join("0e4a6b1c-1111-4222-8333-944455556666.jsonl")));
        assert_eq!(adapters::claude_session_file(config.path(), "1b70e5c4-0000-0000-0000-000000000000"), None);
        for bad in ["", "../stray", "a/b", &"a".repeat(65)] {
            assert_eq!(adapters::claude_session_file(config.path(), bad), None, "{bad:?}");
        }
        assert_eq!(adapters::claude_session_file(&config.path().join("nowhere"), "0e4a6b1c-1111-4222-8333-944455556666"), None);
    }

    /// #451: a session kept in the project is put back where Claude Code finds it, once, and
    /// only as the session it was.
    #[test]
    fn a_kept_claude_code_session_is_put_back_on_another_computer() {
        let config = tempfile::tempdir().unwrap();
        let id = "0e4a6b1c-1111-4222-8333-944455556666";
        let saved = format!("{{\"type\":\"user\",\"sessionId\":\"{id}\",\"message\":{{\"content\":\"Make a notes app.\"}}}}\n");
        let cwd = Path::new("/home/someone/Craft Anything/notes.app");
        assert!(adapters::claude_restore(config.path(), id, saved.as_bytes(), cwd).unwrap());
        let put = config.path().join("projects").join("-home-someone-Craft-Anything-notes-app").join(format!("{id}.jsonl"));
        assert_eq!(std::fs::read_to_string(&put).unwrap(), saved);
        assert_eq!(adapters::claude_session_file(config.path(), id), Some(put.clone()), "Claude Code finds it by its id");
        // There already: left as it is (it may have moved on since the copy was kept).
        std::fs::write(&put, "newer").unwrap();
        assert!(!adapters::claude_restore(config.path(), id, saved.as_bytes(), cwd).unwrap());
        assert_eq!(std::fs::read_to_string(&put).unwrap(), "newer");
        // A copy of another session, or an id that isn't one, puts nothing back.
        let other = "1b70e5c4-0000-0000-0000-000000000000";
        assert!(adapters::claude_restore(config.path(), other, saved.as_bytes(), cwd).unwrap_err().message.contains("another session"));
        assert!(adapters::claude_restore(config.path(), "../../x", saved.as_bytes(), cwd).is_err());
        assert_eq!(adapters::claude_session_file(config.path(), other), None);
        assert!(!adapter_for("codex").restore_session(id, saved.as_bytes(), cwd).unwrap());
    }

    /// #451: a kept session read back as a handoff: what was asked and answered, nothing else.
    /// The line shapes are Claude Code 2.1's.
    #[test]
    fn a_kept_claude_code_session_reads_back_as_its_requests_and_replies() {
        let lines = [
            json!({"type":"queue-operation","operation":"enqueue","content":"queued copy"}),
            json!({"type":"user","isSidechain":false,"message":{"role":"user","content":"Make a notes app."}}),
            json!({"type":"assistant","isSidechain":false,"message":{"content":[{"type":"thinking","thinking":"secret plan"}]}}),
            json!({"type":"assistant","isSidechain":false,"message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"ls"}}]}}),
            json!({"type":"user","isSidechain":false,"message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"app/"}]}}),
            json!({"type":"assistant","isSidechain":true,"message":{"content":[{"type":"text","text":"side task"}]}}),
            json!({"type":"assistant","isSidechain":false,"message":{"content":[{"type":"text","text":"Built a notes app with a sidebar."}]}}),
            json!({"type":"assistant","isSidechain":false,"message":{"content":[{"type":"text","text":"No response requested."}]}}),
            json!({"type":"user","isSidechain":false,"message":{"content":"The person asks: \"make it blue\""}}),
            json!({"type":"assistant","isSidechain":false,"message":{"content":[{"type":"text","text":"Made it blue."}]}}),
        ];
        let saved = lines.iter().map(Value::to_string).collect::<Vec<_>>().join("\n") + "\nnot json\n";
        let all = adapters::claude_handoff(&saved, 10_000).unwrap();
        assert_eq!(
            all,
            "Craft Anything asked you: Make a notes app.\n\nYou answered: Built a notes app with a sidebar.\n\nCraft Anything asked you: The person asks: \"make it blue\"\n\nYou answered: Made it blue."
        );
        // Short of room, the newest is kept.
        let short = adapters::claude_handoff(&saved, 80).unwrap();
        assert!(short.ends_with("You answered: Made it blue.") && !short.contains("notes app"), "{short}");
        // A first brief runs long: it's cut short.
        let long = json!({"type":"user","message":{"content":"x".repeat(10_000)}}).to_string();
        assert!(adapters::claude_handoff(&long, 10_000).unwrap().chars().count() < 1600);
        assert_eq!(adapters::claude_handoff("", 10_000), None);
        assert_eq!(adapters::claude_handoff("\u{0}garbage", 10_000), None);
        assert!(adapter_for("claude-code").handoff(&saved, 10_000).is_some() && adapter_for("codex").handoff(&saved, 10_000).is_none());
    }

    #[test]
    fn parses_codex_and_gemini_streams() {
        let mut p = StreamParser::new(adapter_for("codex"));
        let mut ev = Vec::new();
        for l in [
            json!({"type":"thread.started","thread_id":"th"}),
            json!({"type":"item.started","item":{"id":"i1","type":"mcp_tool_call","server":"craft-anything","tool":"core_target_open","arguments":{"path":"/bin/ls"}}}),
            json!({"type":"item.completed","item":{"id":"i1","type":"mcp_tool_call","tool":"core_target_open","status":"completed","result":{"ok":true}}}),
            json!({"type":"item.completed","item":{"id":"i2","type":"agent_message","text":"It lists files."}}),
            json!({"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":4}}),
        ] {
            ev.extend(p.line(&l.to_string()));
        }
        assert!(matches!(&ev[0], AgentEvent::ToolStarted { tool, .. } if tool == "core_target_open"));
        assert!(matches!(&ev[1], AgentEvent::ToolFinished { ok: true, .. }));
        assert!(matches!(&ev[2], AgentEvent::TextDelta { text } if text.starts_with("It lists")));
        assert!(p.saw_result && p.output_tokens == 4);
        let mut g = StreamParser::new(adapter_for("gemini-cli"));
        let ev: Vec<_> = [
            json!({"type":"message","role":"assistant","content":"Hi","delta":true}),
            json!({"type":"tool_use","tool_name":"craft-anything__core_targets_list","tool_id":"x","parameters":{}}),
            json!({"type":"tool_result","tool_id":"x","status":"error","output":"boom"}),
        ]
        .iter()
        .flat_map(|l| g.line(&l.to_string()))
        .collect();
        assert!(matches!(&ev[1], AgentEvent::ToolStarted { tool, .. } if tool == "core_targets_list"));
        assert!(matches!(&ev[2], AgentEvent::ToolFinished { ok: false, .. }));
    }

    #[cfg(unix)]
    #[test]
    fn generic_cli_runs_through_owned_process_and_streams_text() {
        // `echo` stands in for an unknown agent CLI: prompt via argv, stdout as text.
        let spec = CliSpec::new(
            BackendConfig { name: "Echo".into(), kind: BackendKind::AgentCli, model: "echo".into(), base_url: None, ssh_host: None, enabled: true },
            BackendOptions::default(),
            true,
            None,
        );
        let mut c = CliConversation::new(spec);
        c.send("hello there");
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        let mut all = Vec::new();
        while std::time::Instant::now() < deadline && !all.iter().any(|e| matches!(e, AgentEvent::TurnDone { .. })) {
            all.extend(c.poll());
            std::thread::sleep(Duration::from_millis(10));
        }
        let text: String = all.iter().filter_map(|e| if let AgentEvent::TextDelta { text } = e { Some(text.clone()) } else { None }).collect();
        assert!(text.contains("hello there"), "{all:?}");
        assert!(text.contains("Request"), "preamble is passed too");
    }

    /// #402: a 34,641-character message in argv passed Windows' command-line limit (os error 206);
    /// Claude Code reads it from stdin instead.
    #[cfg(unix)]
    #[test]
    fn claude_code_reads_a_long_message_on_stdin() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let program = dir.path().join("claude");
        let reply = r#"{"type":"assistant","message":{"content":[{"type":"text","text":"read %s bytes"}]}}\n"#;
        std::fs::write(&program, format!("#!/bin/sh\nn=$(wc -c)\nprintf '{reply}' $n\n")).unwrap();
        std::fs::set_permissions(&program, std::fs::Permissions::from_mode(0o755)).unwrap();
        let config =
            BackendConfig { name: "Claude".into(), kind: BackendKind::AgentCli, model: "claude-code".into(), base_url: None, ssh_host: None, enabled: true };
        let options = BackendOptions { command: Some(program.display().to_string()), ..Default::default() };
        let mut c = CliConversation::new(CliSpec::new(config, options, false, None));
        c.send(&"a".repeat(40_000));
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        let mut all = Vec::new();
        while std::time::Instant::now() < deadline && !all.iter().any(|e| matches!(e, AgentEvent::TurnDone { .. })) {
            all.extend(c.poll());
            std::thread::sleep(Duration::from_millis(10));
        }
        let text: String = all.iter().filter_map(|e| if let AgentEvent::TextDelta { text } = e { Some(text.clone()) } else { None }).collect();
        assert_eq!(text, "read 40000 bytes", "{all:?}");
    }

    /// Whoever reads `TurnDone` may send the next message at once (a session that wasn't there is
    /// followed by a fresh start), so the conversation takes it before the turn is said to be
    /// done. The race this prevents lasts nanoseconds, too short to catch from outside, so the
    /// order is checked where it's made.
    #[test]
    fn a_turn_is_said_to_be_done_only_once_the_next_message_can_be_taken() {
        let busy = AtomicBool::new(true);
        let mut sent = None;
        end_turn(&busy, nothing_done("Claude"), |e| {
            assert!(!busy.load(Ordering::SeqCst), "TurnDone sent while still busy");
            sent = Some(e);
        });
        assert!(matches!(sent, Some(AgentEvent::TurnDone { .. })));
    }

    /// Message after message, each turn ends with `TurnDone`, with nothing refused as "still
    /// working" when the next is sent the moment the last is done.
    #[cfg(unix)]
    #[test]
    fn the_next_message_is_taken_as_soon_as_a_turn_is_done() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let program = dir.path().join("claude");
        let reply = r#"{"type":"result","subtype":"success","is_error":false,"num_turns":1,"session_id":"s1"}"#;
        std::fs::write(&program, format!("#!/bin/sh\ncat >/dev/null\necho '{reply}'\n")).unwrap();
        std::fs::set_permissions(&program, std::fs::Permissions::from_mode(0o755)).unwrap();
        let config =
            BackendConfig { name: "Claude".into(), kind: BackendKind::AgentCli, model: "claude-code".into(), base_url: None, ssh_host: None, enabled: true };
        let options = BackendOptions { command: Some(program.display().to_string()), ..Default::default() };
        let mut c = CliConversation::new(CliSpec::new(config, options, false, None));
        for round in 0..25 {
            c.send("go");
            let deadline = std::time::Instant::now() + Duration::from_secs(10);
            let mut events = Vec::new();
            loop {
                let got = c.poll();
                let done = got.iter().any(|e| matches!(e, AgentEvent::TurnDone { .. }));
                events.extend(got);
                if done {
                    assert!(!c.is_busy(), "round {round}: the turn was said to be done while still busy");
                    break;
                }
                assert!(std::time::Instant::now() < deadline, "round {round}: no TurnDone: {events:?}");
                std::hint::spin_loop();
            }
            assert!(!events.iter().any(|e| matches!(e, AgentEvent::Error { .. })), "round {round}: {events:?}");
        }
    }

    /// #91: a Mac app with no CLI beside it reached Claude Code, which stopped with a stack trace.
    #[test]
    fn a_missing_or_broken_helper_is_said_plainly() {
        let stop = CancelToken::default();
        let none = cli_can_start(None, &stop).unwrap_err();
        assert!(none.message.contains("craft-anything-cli") && none.message.contains("missing"), "{none:?}");
        assert!(none.remediation.as_deref().is_some_and(|r| r.contains("Install the latest")), "{none:?}");

        let dir = tempfile::tempdir().unwrap();
        let gone = cli_can_start(Some(&dir.path().join("craft-anything-cli")), &stop).unwrap_err();
        assert!(gone.message.contains("wouldn't start"), "{gone:?}");
        assert!(gone.remediation.is_some());
    }

    #[cfg(unix)]
    #[test]
    fn a_helper_is_judged_by_whether_it_runs() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let helper = |name: &str, script: &str| {
            let p = dir.path().join(name);
            std::fs::write(&p, script).unwrap();
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o755)).unwrap();
            p
        };
        let stop = CancelToken::default();
        assert!(cli_can_start(Some(&helper("good", "#!/bin/sh\necho 1.0\n")), &stop).is_ok());
        let bad = cli_can_start(Some(&helper("bad", "#!/bin/sh\nexit 3\n")), &stop).unwrap_err();
        assert!(bad.message.contains("exited with code 3"), "{bad:?}");
    }

    /// Stopping a build doesn't wait for a helper that hangs, and reads as stopped, not as broken.
    #[cfg(unix)]
    #[test]
    fn stopping_ends_the_check_of_a_hung_helper() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let hung = dir.path().join("hung");
        std::fs::write(&hung, "#!/bin/sh\nexec sleep 25\n").unwrap();
        std::fs::set_permissions(&hung, std::fs::Permissions::from_mode(0o755)).unwrap();
        let stop = CancelToken::default();
        let stopper = stop.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(200));
            stopper.cancel();
        });
        let began = std::time::Instant::now();
        let e = cli_can_start(Some(&hung), &stop).unwrap_err();
        assert_eq!(e.code, ErrorCode::Cancelled, "{e:?}");
        assert!(began.elapsed() < Duration::from_secs(10), "it waited for the helper: {:?}", began.elapsed());
    }

    /// Agents that are never handed the tool server build without the helper.
    #[test]
    fn only_agents_handed_the_tool_server_need_the_helper() {
        for agent in ["gemini-cli", "aider", "no-such-agent"] {
            assert!(check_builder_tools(adapter_for(agent).as_ref(), agent, &BackendOptions::default(), &CancelToken::default()).is_ok(), "{agent}");
        }
    }

    #[test]
    fn missing_cli_is_a_clear_error() {
        let spec = CliSpec::new(
            BackendConfig {
                name: "Nope".into(),
                kind: BackendKind::AgentCli,
                model: "no-such-agent-cli-xyz".into(),
                base_url: None,
                ssh_host: None,
                enabled: true,
            },
            BackendOptions::default(),
            false,
            None,
        );
        let mut c = CliConversation::new(spec);
        c.send("x");
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        let mut all = Vec::new();
        while std::time::Instant::now() < deadline && !all.iter().any(|e| matches!(e, AgentEvent::TurnDone { .. })) {
            all.extend(c.poll());
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(all.iter().any(|e| matches!(e, AgentEvent::Error { message, .. } if message.contains("isn't installed"))), "{all:?}");
    }

    /// #199: plain `codex <prompt>` is its interactive TUI ("stdin is not a terminal"), so a
    /// failed check of `codex exec --help` keeps Codex's own adapter.
    #[test]
    fn codex_is_never_run_plain() {
        assert!(!adapter_for("codex").plain_fallback() && adapters::Plain.plain_fallback());
        let options = BackendOptions { command: Some("no-such-codex-xyz".into()), ..Default::default() };
        let config = BackendConfig { name: "Codex".into(), kind: BackendKind::AgentCli, model: "codex".into(), base_url: None, ssh_host: None, enabled: true };
        let mut c = CliConversation::new(CliSpec::new(config, options, false, None));
        c.send("What does this program do?");
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        let mut all = Vec::new();
        while std::time::Instant::now() < deadline && !all.iter().any(|e| matches!(e, AgentEvent::TurnDone { .. })) {
            all.extend(c.poll());
            std::thread::sleep(Duration::from_millis(10));
        }
        let said = |w: &str| all.iter().any(|e| matches!(e, AgentEvent::Status { text } if text.contains(w)));
        assert!(said("trying it anyway") && !said("plain adapter"), "{all:?}");
    }

    /// A fork's own agent: JSON lines of `{"say": …}`, registered under its id.
    struct EchoAgent;
    impl AgentAdapter for EchoAgent {
        fn ids(&self) -> &'static [&'static str] {
            &["echo-agent"]
        }
        fn args(&self, cx: &ArgsCx) -> Vec<String> {
            vec!["--json".into(), cx.prompt.to_string()]
        }
        fn parse(&self, _p: &mut StreamParser, v: &Value) -> Vec<AgentEvent> {
            v.get("say").and_then(Value::as_str).map(|t| AgentEvent::TextDelta { text: t.into() }).into_iter().collect()
        }
    }

    #[test]
    fn a_registered_adapter_drives_its_agent_and_unknown_ones_get_plain() {
        let mut reg = AgentAdapters::built_in();
        reg.register(Arc::new(EchoAgent));
        let echo = reg.for_agent("echo-agent");
        assert_eq!(build_args(echo.as_ref(), &BackendOptions::default(), "hi", "", &mcp(), None, Access::Analyse), ["--json", "hi"]);
        let mut p = StreamParser::new(echo);
        assert!(matches!(p.line(r#"{"say":"hello"}"#).as_slice(), [AgentEvent::TextDelta { text }] if text == "hello"));
        // Unknown agents stream their output as text; the built-ins keep their own adapters.
        assert!(!reg.for_agent("aider").streams_json());
        assert!(reg.for_agent("claude").resumes() && !reg.for_agent("codex").resumes() && reg.for_agent("antigravity").resumes());
        // Registering an adapter for an existing id replaces that one.
        reg.register(Arc::new(EchoAgent));
        assert_eq!(format!("{reg:?}"), r#"["claude-code", "codex", "gemini-cli", "opencode", "antigravity", "hermes", "maki", "echo-agent"]"#);
    }
}
