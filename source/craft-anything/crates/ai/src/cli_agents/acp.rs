//! Agents that speak the Agent Client Protocol (ACP: JSON-RPC 2.0, one message per line on the
//! agent's stdin/stdout) as one more [`Conversation`]. One agent process serves the whole chat:
//! `initialize`, then `session/new` (or `session/load` to continue) with our MCP server, then one
//! `session/prompt` per message; `session/update` notifications become [`AgentEvent`]s and
//! `session/request_permission` becomes [`AgentEvent::ConsentNeeded`].
//!
//! [`AcpCore`] is the protocol alone (lines in, lines and events out) so it's tested without a
//! process; [`AcpConversation`] runs it against the agent through `craft_anything_platform`.

use super::{McpCommand, display_for};
use crate::{AgentEvent, Conversation};
use craft_anything_platform::sync::Mutex;
use craft_anything_platform::{Process, RunningProcess, StdinMode};
use serde_json::{Value, json};
use std::collections::{HashMap, VecDeque};
use std::io::Write;
use std::path::PathBuf;
use std::process::ChildStdin;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, Sender};
use std::sync::{Arc, PoisonError};
use std::time::Duration;

/// Agents known to speak ACP, and the arguments that start them in that mode.
pub const ACP_AGENTS: &[(&str, &[&str])] = &[
    ("gemini-cli", &["--experimental-acp"]),
    ("qwen-code", &["--experimental-acp"]),
    ("opencode", &["acp"]),
    ("goose", &["acp"]),
    ("hermes", &["acp"]),
    ("maki", &["acp"]),
];

/// Agents whose ACP mode takes the backend's model (`cli_model`), and the flag after the ACP
/// arguments that picks it. Others keep the model they're set to.
pub const ACP_MODEL_FLAGS: &[(&str, &str)] = &[("maki", "-m")];

/// The arguments after `agent`'s ACP ones that pick `model`; none when its ACP mode isn't known
/// to take one.
pub fn model_args(agent: &str, model: Option<&str>) -> Vec<String> {
    let flag = ACP_MODEL_FLAGS.iter().find(|(id, _)| *id == agent).map(|(_, f)| *f);
    match (flag, model.map(str::trim).filter(|m| !m.is_empty())) {
        (Some(flag), Some(model)) => vec![flag.to_string(), model.to_string()],
        _ => Vec::new(),
    }
}

/// The ACP version we speak.
const PROTOCOL_VERSION: u64 = 1;

/// The arguments that start `agent` in ACP mode, if it has one.
pub fn acp_args(agent: &str) -> Option<&'static [&'static str]> {
    ACP_AGENTS.iter().find(|(id, _)| *id == agent).map(|(_, a)| *a)
}

/// What the core asks its driver to do.
#[derive(Debug, PartialEq)]
pub enum Out {
    /// Write this line to the agent.
    Send(String),
    Event(AgentEvent),
    /// The current message is answered (or failed); the conversation is free again.
    TurnEnded,
    /// Ask the approver about a permission request (`tool` and `input` in the approval policy's
    /// shape: `Write {file_path}`, `Bash {command}`…), then [`AcpCore::answer`] it.
    Decide {
        call_id: String,
        tool: String,
        input: Value,
    },
}

/// Decides a builder's permission request (`tool`, `input` as in [`Out::Decide`]); may block
/// while the person is asked. True allows it.
pub type Approver = Arc<dyn Fn(&str, &Value) -> bool + Send + Sync>;

/// An ACP tool call in the approval policy's shape.
fn policy_action(call: &Value) -> (String, Value) {
    let s = |p: &str| call.pointer(p).and_then(Value::as_str).map(str::to_string);
    let path =
        s("/locations/0/path").or_else(|| s("/rawInput/path")).or_else(|| s("/rawInput/file_path")).or_else(|| s("/rawInput/abs_path")).unwrap_or_default();
    let command = match call.pointer("/rawInput/command") {
        Some(Value::String(c)) => c.clone(),
        Some(Value::Array(parts)) => parts.iter().filter_map(Value::as_str).collect::<Vec<_>>().join(" "),
        _ => s("/title").unwrap_or_default(),
    };
    match call.get("kind").and_then(Value::as_str).unwrap_or("other") {
        "edit" | "delete" | "move" => ("Write".into(), json!({"file_path": path})),
        "execute" => ("Bash".into(), json!({"command": command})),
        "read" | "search" => ("Read".into(), json!({"file_path": path})),
        "fetch" => ("WebFetch".into(), call.get("rawInput").cloned().unwrap_or(Value::Null)),
        "think" | "switch_mode" => ("TodoWrite".into(), Value::Null),
        _ => (s("/title").unwrap_or_else(|| "an unnamed tool".into()), call.get("rawInput").cloned().unwrap_or(Value::Null)),
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Pending {
    Initialize,
    NewSession,
    LoadSession,
    Prompt,
}

/// The ACP protocol for one conversation.
pub struct AcpCore {
    backend: String,
    agent_name: String,
    cwd: PathBuf,
    mcp: McpCommand,
    resume: Option<String>,
    next_id: u64,
    pending: HashMap<u64, Pending>,
    session: Option<String>,
    ready: bool,
    queued: VecDeque<String>,
    /// Permission requests waiting for an answer: our call id → (JSON-RPC id, options).
    asks: HashMap<String, (Value, Vec<Value>)>,
    /// Tool call titles by id, for the finished event.
    tools: HashMap<String, String>,
    /// Permission requests go to an approver ([`Out::Decide`]) instead of the person's chat.
    decides: bool,
}

impl AcpCore {
    pub fn new(backend: &str, agent_name: &str, cwd: PathBuf, mcp: McpCommand, resume: Option<String>) -> Self {
        AcpCore {
            backend: backend.into(),
            agent_name: agent_name.into(),
            cwd,
            mcp,
            resume,
            next_id: 0,
            pending: HashMap::new(),
            session: None,
            ready: false,
            queued: VecDeque::new(),
            asks: HashMap::new(),
            tools: HashMap::new(),
            decides: false,
        }
    }

    /// Send permission requests to an approver (a builder run) instead of the chat.
    pub fn deciding(mut self) -> Self {
        self.decides = true;
        self
    }

    /// The agent's session, once it has one (to continue later with `session/load`).
    pub fn session_id(&self) -> Option<String> {
        self.session.clone()
    }

    fn request(&mut self, method: &str, params: Value, kind: Pending) -> Out {
        self.next_id += 1;
        self.pending.insert(self.next_id, kind);
        Out::Send(json!({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}).to_string())
    }

    /// The first lines to send once the agent is running.
    pub fn start(&mut self) -> Vec<Out> {
        let params = json!({
            "protocolVersion": PROTOCOL_VERSION,
            // The agent reads and writes files and runs commands itself, asking us first.
            "clientCapabilities": {"fs": {"readTextFile": false, "writeTextFile": false}, "terminal": false},
            "clientInfo": {"name": "craft-anything", "version": env!("CARGO_PKG_VERSION")},
        });
        vec![self.request("initialize", params, Pending::Initialize)]
    }

    /// A message from the person: sent now, or once the session is ready.
    pub fn prompt(&mut self, text: &str) -> Vec<Out> {
        self.queued.push_back(text.to_string());
        // A start that failed earlier (an `initialize` error) left nothing under way: start again,
        // or the message would wait for a session that never comes (#271).
        if !self.ready && self.pending.is_empty() {
            return self.start();
        }
        self.flush()
    }

    fn flush(&mut self) -> Vec<Out> {
        let busy = self.pending.values().any(|p| *p == Pending::Prompt);
        let Some(sid) = self.session.clone().filter(|_| self.ready && !busy) else { return Vec::new() };
        let Some(text) = self.queued.pop_front() else { return Vec::new() };
        let params = json!({"sessionId": sid, "prompt": [{"type": "text", "text": text}]});
        vec![self.request("session/prompt", params, Pending::Prompt)]
    }

    fn mcp_servers(&self) -> Value {
        json!([{"name": super::MCP_NAME, "command": self.mcp.command, "args": self.mcp.args, "env": []}])
    }

    /// One line from the agent.
    pub fn line(&mut self, line: &str) -> Vec<Out> {
        let Ok(msg) = serde_json::from_str::<Value>(line.trim()) else { return Vec::new() };
        let method = msg.get("method").and_then(Value::as_str);
        match (method, msg.get("id")) {
            (Some(m), Some(id)) => self.agent_request(m, id.clone(), msg.get("params").unwrap_or(&Value::Null)),
            (Some("session/update"), None) => self.update(msg.get("params").and_then(|p| p.get("update")).unwrap_or(&Value::Null)),
            (Some(_), None) => Vec::new(),
            (None, Some(id)) => self.response(id.as_u64().unwrap_or(0), &msg),
            (None, None) => Vec::new(),
        }
    }

    fn fail(&mut self, message: String, remediation: Option<String>) -> Vec<Out> {
        self.queued.clear();
        vec![Out::Event(AgentEvent::Error { message, remediation, log: None }), self.turn_done(), Out::TurnEnded]
    }

    fn turn_done(&self) -> Out {
        Out::Event(AgentEvent::TurnDone { backend: self.backend.clone(), input_tokens: 0, output_tokens: 0, cost_usd: None, cost_is_estimate: false })
    }

    fn response(&mut self, id: u64, msg: &Value) -> Vec<Out> {
        let Some(kind) = self.pending.remove(&id) else { return Vec::new() };
        if let Some(err) = msg.get("error") {
            let text = err.get("message").and_then(Value::as_str).unwrap_or("an error");
            // A session that can't be continued starts afresh rather than failing the message.
            if kind == Pending::LoadSession {
                self.resume = None;
                let params = json!({"cwd": self.cwd, "mcpServers": self.mcp_servers()});
                return vec![self.request("session/new", params, Pending::NewSession)];
            }
            let fix = matches!(kind, Pending::Initialize | Pending::NewSession)
                .then(|| format!("Check that {} is installed and signed in: run it once in a terminal.", self.agent_name));
            return self.fail(format!("{}: {text}", self.agent_name), fix);
        }
        let result = msg.get("result").unwrap_or(&Value::Null);
        match kind {
            Pending::Initialize => {
                let can_load = result.pointer("/agentCapabilities/loadSession").and_then(Value::as_bool).unwrap_or(false);
                match self.resume.clone().filter(|_| can_load) {
                    Some(sid) => {
                        self.session = Some(sid.clone());
                        let params = json!({"sessionId": sid, "cwd": self.cwd, "mcpServers": self.mcp_servers()});
                        vec![self.request("session/load", params, Pending::LoadSession)]
                    }
                    None => {
                        let params = json!({"cwd": self.cwd, "mcpServers": self.mcp_servers()});
                        vec![self.request("session/new", params, Pending::NewSession)]
                    }
                }
            }
            Pending::NewSession | Pending::LoadSession => {
                if let Some(sid) = result.get("sessionId").and_then(Value::as_str) {
                    self.session = Some(sid.to_string());
                }
                if self.session.is_none() {
                    return self.fail(format!("{} started no session", self.agent_name), None);
                }
                self.ready = true;
                self.flush()
            }
            Pending::Prompt => {
                let mut out = Vec::new();
                match result.get("stopReason").and_then(Value::as_str) {
                    Some("cancelled") => out.push(Out::Event(AgentEvent::Status { text: "Stopped.".into() })),
                    Some("max_tokens" | "max_turn_requests") => {
                        out.push(Out::Event(AgentEvent::Status { text: format!("{} stopped at its length limit.", self.agent_name) }))
                    }
                    Some("refusal") => out.push(Out::Event(AgentEvent::Status { text: format!("{} declined to continue.", self.agent_name) })),
                    _ => {}
                }
                out.extend([self.turn_done(), Out::TurnEnded]);
                out.extend(self.flush());
                out
            }
        }
    }

    fn agent_request(&mut self, method: &str, id: Value, params: &Value) -> Vec<Out> {
        if method != "session/request_permission" {
            // We offer no file system or terminal to the agent; it does its own.
            let err = json!({"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": format!("{method} isn't offered by this client")}});
            return vec![Out::Send(err.to_string())];
        }
        let call = params.get("toolCall").unwrap_or(&Value::Null);
        let s = |k: &str| call.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
        let call_id = format!("acp-perm-{}", id.as_u64().map(|n| n.to_string()).unwrap_or_else(|| id.to_string()));
        let options = params.get("options").and_then(Value::as_array).cloned().unwrap_or_default();
        let title = if s("title").is_empty() { "Use a tool".to_string() } else { s("title") };
        self.asks.insert(call_id.clone(), (id, options));
        if self.decides {
            let (tool, input) = policy_action(call);
            return vec![Out::Decide { call_id, tool, input }];
        }
        vec![Out::Event(AgentEvent::ConsentNeeded {
            call_id,
            tool: if s("kind").is_empty() { "other".into() } else { s("kind") },
            title: title.clone(),
            explanation: format!("{} wants to: {title}", self.agent_name),
        })]
    }

    /// Answer a permission request: the first option of the matching kind, once.
    pub fn answer(&mut self, call_id: &str, allow: bool) -> Vec<Out> {
        let Some((id, options)) = self.asks.remove(call_id) else { return Vec::new() };
        let want = if allow { "allow_once" } else { "reject_once" };
        let pick = options
            .iter()
            .find(|o| o.get("kind").and_then(Value::as_str) == Some(want))
            .or_else(|| options.iter().find(|o| o.get("kind").and_then(Value::as_str).is_some_and(|k| k.starts_with(if allow { "allow" } else { "reject" }))))
            .and_then(|o| o.get("optionId").cloned());
        let outcome = match pick {
            Some(option) => json!({"outcome": "selected", "optionId": option}),
            None => json!({"outcome": "cancelled"}),
        };
        vec![Out::Send(json!({"jsonrpc": "2.0", "id": id, "result": {"outcome": outcome}}).to_string())]
    }

    /// Stop the current message: cancel the prompt and any open permission requests.
    pub fn cancel(&mut self) -> Vec<Out> {
        // A message still waiting for the session has no prompt to cancel: its turn ends here.
        let waiting = !self.queued.is_empty() && !self.pending.values().any(|p| *p == Pending::Prompt);
        self.queued.clear();
        let mut out: Vec<Out> = self
            .asks
            .drain()
            .map(|(_, (id, _))| Out::Send(json!({"jsonrpc": "2.0", "id": id, "result": {"outcome": {"outcome": "cancelled"}}}).to_string()))
            .collect();
        if let Some(sid) = self.session.clone().filter(|_| self.pending.values().any(|p| *p == Pending::Prompt)) {
            out.push(Out::Send(json!({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": sid}}).to_string()));
        }
        if waiting {
            out.extend([self.turn_done(), Out::TurnEnded]);
        }
        out
    }

    fn update(&mut self, u: &Value) -> Vec<Out> {
        let s = |k: &str| u.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
        let text = || u.pointer("/content/text").and_then(Value::as_str).unwrap_or_default().to_string();
        let ev = match s("sessionUpdate").as_str() {
            "agent_message_chunk" => AgentEvent::TextDelta { text: text() },
            "agent_thought_chunk" => AgentEvent::Status { text: text() },
            "plan" => {
                let steps: Vec<String> = u
                    .get("entries")
                    .and_then(Value::as_array)
                    .map(|e| e.iter().filter_map(|x| x.get("content").and_then(Value::as_str)).map(str::to_string).collect())
                    .unwrap_or_default();
                AgentEvent::Status { text: format!("Plan: {}", steps.join("; ")) }
            }
            "tool_call" => {
                let id = s("toolCallId");
                let title = if s("title").is_empty() { s("kind") } else { s("title") };
                self.tools.insert(id.clone(), title.clone());
                let started = AgentEvent::ToolStarted { call_id: id.clone(), tool: title, input: u.get("rawInput").cloned().unwrap_or(Value::Null) };
                return match finished(u, &id, self.tools.get(&id).cloned().unwrap_or_default()) {
                    Some(f) => vec![Out::Event(started), Out::Event(f)],
                    None => vec![Out::Event(started)],
                };
            }
            "tool_call_update" => {
                let id = s("toolCallId");
                let title = self.tools.get(&id).cloned().unwrap_or_else(|| s("title"));
                return finished(u, &id, title).map(|f| vec![Out::Event(f)]).unwrap_or_default();
            }
            _ => return Vec::new(),
        };
        vec![Out::Event(ev)]
    }
}

/// The finished event for a tool call whose status is final.
fn finished(u: &Value, id: &str, tool: String) -> Option<AgentEvent> {
    let ok = match u.get("status").and_then(Value::as_str)? {
        "completed" => true,
        "failed" => false,
        _ => return None,
    };
    let summary: String = u
        .get("content")
        .and_then(Value::as_array)
        .map(|c| c.iter().filter_map(|x| x.pointer("/content/text").and_then(Value::as_str)).collect::<Vec<_>>().join("\n"))
        .unwrap_or_default();
    let summary = summary.chars().take(2000).collect();
    Some(AgentEvent::ToolFinished { call_id: id.to_string(), tool, ok, summary, evidence_id: None })
}

/// The running agent and its protocol state, shared with the output reader.
struct Shared {
    core: AcpCore,
    stdin: Option<ChildStdin>,
    stderr: VecDeque<String>,
    approver: Option<Approver>,
}

type SharedRef = Arc<Mutex<Option<Shared>>>;

impl Shared {
    /// Carry out what the core asked for. A decision runs on its own thread (it may wait for the
    /// person) so the agent's output keeps being read.
    fn apply(&mut self, outs: Vec<Out>, shared: &SharedRef, tx: &Sender<AgentEvent>, busy: &Arc<AtomicBool>) {
        for o in outs {
            match o {
                Out::Send(line) => {
                    let ok = self.stdin.as_mut().is_some_and(|s| s.write_all(format!("{line}\n").as_bytes()).and_then(|_| s.flush()).is_ok());
                    if !ok {
                        self.stdin = None;
                    }
                }
                Out::Event(e) => {
                    let _ = tx.send(e);
                }
                Out::TurnEnded => busy.store(false, Ordering::SeqCst),
                Out::Decide { call_id, tool, input } => {
                    let (sh, tx2, busy2, approver, id) = (shared.clone(), tx.clone(), busy.clone(), self.approver.clone(), call_id.clone());
                    let spawned = std::thread::Builder::new().name("acp-approval".into()).spawn(move || {
                        let allow = approver.is_some_and(|a| a(&tool, &input));
                        let mut g = sh.lock().unwrap_or_else(PoisonError::into_inner);
                        if let Some(s) = g.as_mut() {
                            let outs = s.core.answer(&id, allow);
                            s.apply(outs, &sh, &tx2, &busy2);
                        }
                    });
                    // No thread to ask on: refuse rather than leave the agent waiting.
                    if spawned.is_err() {
                        let outs = self.core.answer(&call_id, false);
                        self.apply(outs, shared, tx, busy);
                    }
                }
            }
        }
    }
}

/// A conversation with an ACP agent running on this computer.
pub struct AcpConversation {
    program: String,
    args: Vec<String>,
    agent: String,
    backend: String,
    cwd: PathBuf,
    mcp: McpCommand,
    resume: Option<String>,
    shared: Arc<Mutex<Option<Shared>>>,
    proc: Option<RunningProcess>,
    tx: Sender<AgentEvent>,
    rx: Receiver<AgentEvent>,
    busy: Arc<AtomicBool>,
    approver: Option<Approver>,
    preamble: String,
    logs: Option<PathBuf>,
}

impl AcpConversation {
    /// Where to write a log if the agent stops unexpectedly ([`crate::failure_log`]).
    pub fn with_logs(mut self, logs: Option<PathBuf>) -> Self {
        self.logs = logs;
        self
    }

    /// Text put before each message, as the CLI runs do (who it works for, how to use our tools).
    pub fn with_preamble(mut self, preamble: String) -> Self {
        self.preamble = preamble;
        self
    }

    /// A builder run: the agent's permission requests are decided by `approver` (the approval
    /// policy), not asked in the chat.
    pub fn with_approver(mut self, approver: Approver) -> Self {
        self.approver = Some(approver);
        self
    }

    /// `program args…` starts the agent in ACP mode; `cwd` is its working folder.
    pub fn new(backend: &str, agent: &str, program: String, args: Vec<String>, cwd: PathBuf, mcp: McpCommand, resume: Option<String>) -> Self {
        let (tx, rx) = std::sync::mpsc::channel();
        AcpConversation {
            program,
            args,
            agent: agent.into(),
            backend: backend.into(),
            cwd,
            mcp,
            resume,
            shared: Arc::default(),
            proc: None,
            tx,
            rx,
            busy: Arc::default(),
            approver: None,
            preamble: String::new(),
            logs: None,
        }
    }

    fn lock(&self) -> craft_anything_platform::sync::MutexGuard<'_, Option<Shared>> {
        self.shared.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Start the agent and send `initialize`.
    fn spawn(&mut self) -> Result<(), craft_anything_evidence::ToolError> {
        let name = display_for(&self.agent);
        let resume = self.lock().as_ref().and_then(|s| s.core.session_id()).or_else(|| self.resume.clone());
        let mut core = AcpCore::new(&self.backend, &name, self.cwd.clone(), self.mcp.clone(), resume);
        if self.approver.is_some() {
            core = core.deciding();
        }
        *self.lock() = Some(Shared { core, stdin: None, stderr: VecDeque::new(), approver: self.approver.clone() });
        let (shared, tx, busy) = (self.shared.clone(), self.tx.clone(), self.busy.clone());
        let shared_err = self.shared.clone();
        let tx_err = tx.clone();
        let mut proc = Process::new(&self.program)
            .args(&self.args)
            .cwd(&self.cwd)
            .stdin(StdinMode::Piped)
            // One process serves the whole chat; a builder turn may take hours.
            .timeout(Duration::from_secs(24 * 3600))
            .stdout_cap(4 << 20)
            .stderr_cap(1 << 20)
            .on_stdout_line(move |l| {
                let mut g = shared.lock().unwrap_or_else(PoisonError::into_inner);
                if let Some(s) = g.as_mut() {
                    let outs = s.core.line(l);
                    s.apply(outs, &shared, &tx, &busy);
                }
            })
            .on_stderr_line(move |l| {
                if !l.trim().is_empty() {
                    let _ = tx_err.send(AgentEvent::Output { text: l.to_string() });
                }
                let mut g = shared_err.lock().unwrap_or_else(PoisonError::into_inner);
                if let Some(s) = g.as_mut() {
                    if s.stderr.len() >= 20 {
                        s.stderr.pop_front();
                    }
                    s.stderr.push_back(l.to_string());
                }
            })
            .label(name.clone())
            .remediation(format!("Install {name}, or choose its program in Settings → AI."))
            .spawn()?;
        let stdin = proc.take_stdin();
        self.proc = Some(proc);
        let mut g = self.lock();
        if let Some(s) = g.as_mut() {
            s.stdin = stdin;
            let outs = s.core.start();
            s.apply(outs, &self.shared, &self.tx, &self.busy);
        }
        Ok(())
    }

    fn with_core(&mut self, f: impl FnOnce(&mut AcpCore) -> Vec<Out>) {
        let mut g = self.lock();
        if let Some(s) = g.as_mut() {
            let outs = f(&mut s.core);
            s.apply(outs, &self.shared, &self.tx, &self.busy);
        }
    }
}

impl Conversation for AcpConversation {
    fn send(&mut self, text: &str) {
        if self.busy.swap(true, Ordering::SeqCst) {
            let _ = self.tx.send(AgentEvent::Error {
                message: "Still working on the last message.".into(),
                remediation: Some("Wait for it to finish or press stop.".into()),
                log: None,
            });
            return;
        }
        let running = self.proc.as_mut().is_some_and(|p| !p.is_finished());
        if !running {
            let _ = self.tx.send(AgentEvent::Status { text: format!("Starting {}…", display_for(&self.agent)) });
            if let Err(e) = self.spawn() {
                self.busy.store(false, Ordering::SeqCst);
                let _ = self.tx.send(AgentEvent::Error { message: e.message, remediation: e.remediation, log: None });
                let _ = self.tx.send(AgentEvent::TurnDone {
                    backend: self.backend.clone(),
                    input_tokens: 0,
                    output_tokens: 0,
                    cost_usd: None,
                    cost_is_estimate: false,
                });
                return;
            }
        }
        let text = format!("{}{text}", self.preamble);
        self.with_core(|c| c.prompt(&text));
    }

    fn session_id(&self) -> Option<String> {
        self.lock().as_ref().and_then(|s| s.core.session_id()).or_else(|| self.resume.clone())
    }

    fn poll(&mut self) -> Vec<AgentEvent> {
        let mut events: Vec<AgentEvent> = self.rx.try_iter().collect();
        // An agent that exits mid-message would otherwise leave the conversation busy forever.
        if self.busy.load(Ordering::SeqCst) && self.proc.as_mut().is_some_and(RunningProcess::is_finished) {
            self.busy.store(false, Ordering::SeqCst);
            let tail = self.lock().as_ref().map(|s| s.stderr.iter().cloned().collect::<Vec<_>>().join("\n")).unwrap_or_default();
            events.extend(self.rx.try_iter());
            let command = craft_anything_platform::process::printable_command(std::ffi::OsStr::new(&self.program), &self.args);
            let check = format!("{} --version", crate::ssh::shell_quote(&self.program));
            let log = self.logs.as_ref().and_then(|dir| {
                let report = crate::failure_log::Report {
                    what: format!("{} ({})", display_for(&self.agent), self.backend),
                    command: command.clone(),
                    check: check.clone(),
                    error: Some("It stopped in the middle of a message.".into()),
                    cwd: Some(self.cwd.clone()),
                    stderr: tail.clone().into_bytes(),
                    ..Default::default()
                };
                crate::failure_log::write(dir, &report).map_err(|e| log::warn!("couldn't write a failure log: {e}")).ok()
            });
            events.push(AgentEvent::Error {
                message: format!("{} stopped unexpectedly.{}", display_for(&self.agent), if tail.is_empty() { String::new() } else { format!("\n{tail}") }),
                remediation: Some(format!(
                    "Check that {} is installed and signed in. To test it, run:\n{check}\n\nWhat ran:\n{command}",
                    display_for(&self.agent)
                )),
                log,
            });
            events.push(AgentEvent::TurnDone { backend: self.backend.clone(), input_tokens: 0, output_tokens: 0, cost_usd: None, cost_is_estimate: false });
        }
        events
    }

    fn answer_consent(&mut self, call_id: &str, allow: bool) {
        self.with_core(|c| c.answer(call_id, allow));
    }

    fn stop(&mut self) {
        self.with_core(AcpCore::cancel);
    }

    fn is_busy(&self) -> bool {
        self.busy.load(Ordering::SeqCst)
    }
}

impl Drop for AcpConversation {
    fn drop(&mut self) {
        if let Some(mut p) = self.proc.take() {
            p.kill_and_wait(Duration::from_secs(3));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn core(resume: Option<&str>) -> AcpCore {
        let mcp = McpCommand { command: "/opt/ca/craft-anything-cli".into(), args: vec!["mcp".into()], notes: None };
        AcpCore::new("Gemini", "Gemini CLI", PathBuf::from("/w/project"), mcp, resume.map(str::to_string))
    }

    fn sent(outs: &[Out]) -> Vec<Value> {
        outs.iter().filter_map(|o| if let Out::Send(l) = o { serde_json::from_str(l).ok() } else { None }).collect()
    }

    fn events(outs: Vec<Out>) -> Vec<AgentEvent> {
        outs.into_iter().filter_map(|o| if let Out::Event(e) = o { Some(e) } else { None }).collect()
    }

    #[test]
    fn a_message_goes_through_initialize_and_a_new_session() {
        let mut c = core(None);
        let init = sent(&c.start());
        assert_eq!(init[0]["method"], "initialize");
        assert_eq!(init[0]["params"]["protocolVersion"], 1);
        assert_eq!(init[0]["params"]["clientCapabilities"]["terminal"], false);
        assert!(c.prompt("What does it do?").is_empty(), "held until the session is ready");
        let new = sent(&c.line(r#"{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1,"agentCapabilities":{"loadSession":true}}}"#));
        assert_eq!(new[0]["method"], "session/new");
        assert_eq!(new[0]["params"]["cwd"], "/w/project");
        assert_eq!(new[0]["params"]["mcpServers"][0]["name"], "craft-anything");
        assert_eq!(new[0]["params"]["mcpServers"][0]["env"], json!([]));
        let prompt = sent(&c.line(r#"{"jsonrpc":"2.0","id":2,"result":{"sessionId":"s-1"}}"#));
        assert_eq!(prompt[0]["method"], "session/prompt");
        assert_eq!(prompt[0]["params"], json!({"sessionId": "s-1", "prompt": [{"type": "text", "text": "What does it do?"}]}));
        assert_eq!(c.session_id().as_deref(), Some("s-1"));

        let ev = events(c.line(r#"{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"s-1","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"It "}}}}"#));
        assert_eq!(ev, [AgentEvent::TextDelta { text: "It ".into() }]);
        let ev = events(c.line(
            r#"{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"s-1","update":{"sessionUpdate":"tool_call","toolCallId":"t1","title":"Read main.rs","kind":"read","status":"pending","rawInput":{"path":"main.rs"}}}}"#,
        ));
        assert!(matches!(&ev[..], [AgentEvent::ToolStarted { call_id, tool, .. }] if call_id == "t1" && tool == "Read main.rs"));
        let ev = events(c.line(
            r#"{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"s-1","update":{"sessionUpdate":"tool_call_update","toolCallId":"t1","status":"completed","content":[{"type":"content","content":{"type":"text","text":"fn main"}}]}}}"#,
        ));
        assert!(matches!(&ev[..], [AgentEvent::ToolFinished { ok: true, summary, tool, .. }] if summary == "fn main" && tool == "Read main.rs"));
        let end = c.line(r#"{"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}"#);
        assert!(end.contains(&Out::TurnEnded));
        assert!(matches!(events(end)[..], [AgentEvent::TurnDone { .. }]));
        // The next message goes straight out on the same session.
        assert_eq!(sent(&c.prompt("And then?"))[0]["params"]["sessionId"], "s-1");
    }

    #[test]
    fn a_saved_session_is_loaded_and_a_lost_one_starts_afresh() {
        let mut c = core(Some("old"));
        c.start();
        let load = sent(&c.line(r#"{"jsonrpc":"2.0","id":1,"result":{"agentCapabilities":{"loadSession":true}}}"#));
        assert_eq!(load[0]["method"], "session/load");
        assert_eq!(load[0]["params"]["sessionId"], "old");
        let new = sent(&c.line(r#"{"jsonrpc":"2.0","id":2,"error":{"code":-32603,"message":"no such session"}}"#));
        assert_eq!(new[0]["method"], "session/new");
        // An agent that can't load sessions gets a new one straight away.
        let mut c = core(Some("old"));
        c.start();
        assert_eq!(sent(&c.line(r#"{"jsonrpc":"2.0","id":1,"result":{}}"#))[0]["method"], "session/new");
    }

    #[test]
    fn permission_requests_become_consent_and_are_answered_once() {
        let mut c = core(None);
        let ev = events(c.line(
            r#"{"jsonrpc":"2.0","id":7,"method":"session/request_permission","params":{"sessionId":"s","toolCall":{"toolCallId":"t2","title":"Run npm test","kind":"execute"},"options":[{"optionId":"yes-always","name":"Always","kind":"allow_always"},{"optionId":"yes","name":"Allow","kind":"allow_once"},{"optionId":"no","name":"Reject","kind":"reject_once"}]}}"#,
        ));
        let Some(AgentEvent::ConsentNeeded { call_id, tool, title, .. }) = ev.first() else { panic!("{ev:?}") };
        assert_eq!((tool.as_str(), title.as_str()), ("execute", "Run npm test"));
        let reply = sent(&c.answer(call_id, true));
        assert_eq!(reply[0], json!({"jsonrpc": "2.0", "id": 7, "result": {"outcome": {"outcome": "selected", "optionId": "yes"}}}));
        assert!(c.answer(call_id, true).is_empty(), "answered once");
    }

    /// #271: after `initialize` failed, the next message waited for a session forever, and Stop
    /// didn't end it.
    #[test]
    fn a_failed_start_is_tried_again_and_stop_ends_a_waiting_message() {
        let mut c = core(None);
        c.start();
        let failed = c.line(r#"{"jsonrpc":"2.0","id":1,"error":{"code":-32603,"message":"not signed in"}}"#);
        assert!(failed.contains(&Out::TurnEnded));
        let again = sent(&c.prompt("Hello"));
        assert_eq!(again[0]["method"], "initialize", "the next message starts the agent's session again");
        let failed = c.line(r#"{"jsonrpc":"2.0","id":2,"error":{"code":-32603,"message":"not signed in"}}"#);
        assert!(failed.contains(&Out::TurnEnded), "a second failure ends that message too");
        c.prompt("Hello");
        let stopped = c.cancel();
        assert!(stopped.contains(&Out::TurnEnded), "Stop ends a message still waiting for the session");
        assert!(sent(&c.line(r#"{"jsonrpc":"2.0","id":3,"result":{}}"#)).iter().all(|m| m["method"] != "session/prompt"));
    }

    #[test]
    fn errors_end_the_turn_and_unoffered_requests_are_refused() {
        let mut c = core(None);
        c.start();
        c.prompt("hi");
        let outs = c.line(r#"{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"Authentication required"}}"#);
        assert!(outs.contains(&Out::TurnEnded));
        assert!(matches!(&events(outs)[0], AgentEvent::Error { message, remediation: Some(_), .. } if message.contains("Authentication required")));
        let refused = sent(&c.line(r#"{"jsonrpc":"2.0","id":9,"method":"fs/read_text_file","params":{"path":"/etc/passwd"}}"#));
        assert_eq!(refused[0]["error"]["code"], -32601);
        assert!(c.line("not json").is_empty());
    }

    #[test]
    fn a_builder_sends_permission_requests_to_the_approval_policy() {
        let mut c = core(None).deciding();
        let outs = c.line(
            r#"{"jsonrpc":"2.0","id":4,"method":"session/request_permission","params":{"toolCall":{"toolCallId":"t","title":"Edit App.tsx","kind":"edit","locations":[{"path":"/w/project/app/src/App.tsx"}]},"options":[{"optionId":"ok","name":"Allow","kind":"allow_once"},{"optionId":"no","name":"Reject","kind":"reject_once"}]}}"#,
        );
        let [Out::Decide { call_id, tool, input }] = &outs[..] else { panic!("{outs:?}") };
        assert_eq!((tool.as_str(), input), ("Write", &json!({"file_path": "/w/project/app/src/App.tsx"})));
        assert_eq!(sent(&c.answer(call_id, false))[0]["result"]["outcome"]["optionId"], "no");

        let run = |kind: &str, raw: Value| policy_action(&json!({"kind": kind, "title": "t", "rawInput": raw}));
        assert_eq!(run("execute", json!({"command": "npm run build"})), ("Bash".to_string(), json!({"command": "npm run build"})));
        assert_eq!(run("execute", json!({"command": ["cargo", "build"]})).1, json!({"command": "cargo build"}));
        assert_eq!(run("read", json!({"path": "/a"})).0, "Read");
        assert_eq!(run("fetch", json!({"url": "https://x"})).0, "WebFetch");
        assert_eq!(run("other", json!({})).0, "t", "unknown kinds are asked about by title");
    }

    #[test]
    fn maki_starts_in_acp_mode_with_the_backends_model() {
        assert_eq!(acp_args("maki"), Some(&["acp"][..]));
        assert_eq!(model_args("maki", Some(" anthropic/claude-sonnet-4-6 ")), ["-m", "anthropic/claude-sonnet-4-6"]);
        assert!(model_args("maki", None).is_empty() && model_args("maki", Some(" ")).is_empty());
        // An agent whose ACP mode isn't known to take a model keeps its own, as before.
        assert!(model_args("opencode", Some("x/y")).is_empty());
    }

    /// `maki -m <model> acp` starts with Maki's default model: the flag only counts after `acp`.
    #[test]
    fn a_maki_backend_runs_acp_then_its_model_after_its_own_args() {
        let config = crate::BackendConfig {
            name: "Maki".into(),
            kind: crate::BackendKind::AgentCli,
            model: "maki".into(),
            base_url: None,
            ssh_host: None,
            enabled: true,
        };
        let options = crate::BackendOptions {
            acp: Some(true),
            cli_model: Some("anthropic/claude-sonnet-4-6".into()),
            args: vec!["--no-plugins".into()],
            ..Default::default()
        };
        let Some(c) = super::super::acp_for(&super::super::CliSpec::new(config, options, false, None)) else { panic!("Maki speaks ACP") };
        assert_eq!((c.program.as_str(), c.args.as_slice()), ("maki", &["--no-plugins", "acp", "-m", "anthropic/claude-sonnet-4-6"].map(String::from)[..]));
    }

    #[test]
    fn stopping_cancels_the_prompt_and_open_questions() {
        let mut c = core(None);
        c.start();
        c.prompt("long task");
        c.line(r#"{"jsonrpc":"2.0","id":1,"result":{}}"#);
        c.line(r#"{"jsonrpc":"2.0","id":2,"result":{"sessionId":"s"}}"#);
        c.line(r#"{"jsonrpc":"2.0","id":5,"method":"session/request_permission","params":{"toolCall":{"title":"Edit"},"options":[]}}"#);
        let out = sent(&c.cancel());
        assert!(out.iter().any(|m| m["id"] == 5 && m["result"]["outcome"]["outcome"] == "cancelled"));
        assert!(out.iter().any(|m| m["method"] == "session/cancel" && m["params"]["sessionId"] == "s"));
    }
}
