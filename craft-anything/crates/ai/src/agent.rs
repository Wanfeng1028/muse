//! The built-in agent loop: a model, the engine's tools, consent, memory and the journal.
//!
//! Everything here runs on a background worker thread owned by [`ApiConversation`]; the UI only
//! ever calls the non-blocking [`Conversation`] methods.

use crate::anthropic::INVALID_INPUT_KEY;
use crate::context;
use crate::model::{Block, ChatModel, Delta, Effort, Msg, Speaker, Stop, StopReason, ToolDef, TurnRequest, Usage};
use crate::price::{self, Meter};
use crate::prompt;
use crate::{AgentEvent, Conversation};
use craft_anything_engine::{CallOptions, Caller, CancelToken, Consent, Engine, Registry, ToolOutput, Toolset};
use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::sync::Mutex;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, PoisonError};
use std::time::Duration;

/// Byte budget for one tool result sent to the model.
pub const RESULT_BUDGET: usize = 16 * 1024;
/// Default most model turns per user message.
pub const DEFAULT_MAX_TURNS: u32 = 40;
/// Steps one builder message may take (writing, building and fixing a project takes many).
pub const BUILDER_MAX_TURNS: u32 = 400;

/// What the loop needs from the engine (a trait so tests can inject behaviour).
pub trait ToolHost: Send + Sync {
    /// Tool definitions for the enabled toolsets (without the meta-tools).
    fn tools(&self, enabled: &BTreeSet<Toolset>) -> Vec<ToolDef>;
    /// The toolset a tool belongs to, if it exists.
    fn toolset_of(&self, id: &str) -> Option<Toolset>;
    fn call(&self, id: &str, input: Value, consent: bool, cancel: CancelToken) -> Result<ToolOutput, ToolError>;
    fn journal(&self, kind: &str, entry: Value);
    /// `core_investigation_show` as compact JSON text.
    fn investigation(&self) -> String;
    fn clean_room(&self) -> bool;
    /// A tool's title (for consent prompts).
    fn title(&self, id: &str) -> String;
    /// Every toolset in use (built-in and added at run time).
    fn toolsets(&self) -> Vec<Toolset> {
        Toolset::ALL.to_vec()
    }
}

/// The real host: the engine.
pub struct EngineHost(pub Arc<Engine>);

/// Remove keys model APIs dislike at the schema root, and write boolean sub-schemas as objects.
fn clean_schema(mut s: Value) -> Value {
    if let Some(o) = s.as_object_mut() {
        o.remove("$schema");
        o.remove("title");
        if !o.contains_key("type") {
            o.insert("type".into(), json!("object"));
        }
        if !o.contains_key("properties") && o.get("type") == Some(&json!("object")) {
            o.insert("properties".into(), json!({}));
        }
    }
    object_subschemas(&mut s, 0);
    s
}

/// Deepest schema nesting rewritten (run-time tools bring their own schemas).
const MAX_SCHEMA_DEPTH: usize = 64;

/// `true` and `false` as sub-schemas (schemars writes `"items": true` for a list of any JSON) become
/// `{}` and `{"not": {}}`: local servers such as LM Studio refuse anything but an object there.
/// `additionalProperties` stays as it is: a boolean is what every API expects in it.
fn object_subschemas(schema: &mut Value, depth: usize) {
    let Some(o) = schema.as_object_mut().filter(|_| depth < MAX_SCHEMA_DEPTH) else { return };
    for (key, sub) in o.iter_mut() {
        let subs: Vec<&mut Value> = match (key.as_str(), sub) {
            ("items" | "additionalItems" | "contains" | "not" | "if" | "then" | "else", s) => vec![s],
            ("properties" | "patternProperties" | "$defs" | "definitions", Value::Object(m)) => m.values_mut().collect(),
            ("anyOf" | "oneOf" | "allOf" | "prefixItems", Value::Array(a)) => a.iter_mut().collect(),
            _ => Vec::new(),
        };
        for s in subs {
            match s {
                Value::Bool(true) => *s = json!({}),
                Value::Bool(false) => *s = json!({"not": {}}),
                _ => object_subschemas(s, depth + 1),
            }
        }
    }
}

pub fn registry_tools(reg: &Registry, enabled: &BTreeSet<Toolset>) -> Vec<ToolDef> {
    reg.all()
        .iter()
        .filter(|s| enabled.contains(&s.toolset))
        .map(|s| ToolDef { name: s.id.to_string(), description: s.summary.to_string(), schema: clean_schema(reg.input_schema(s)) })
        .collect()
}

impl ToolHost for EngineHost {
    fn tools(&self, enabled: &BTreeSet<Toolset>) -> Vec<ToolDef> {
        // Clean room offers only the tools it runs.
        let clean = self.clean_room();
        registry_tools(self.0.registry(), enabled).into_iter().filter(|t| !clean || craft_anything_engine::clean_room::allows(&t.name)).collect()
    }

    fn toolset_of(&self, id: &str) -> Option<Toolset> {
        self.0.registry().get(id).map(|s| s.toolset)
    }

    fn toolsets(&self) -> Vec<Toolset> {
        self.0.registry().toolsets()
    }

    fn call(&self, id: &str, input: Value, consent: bool, cancel: CancelToken) -> Result<ToolOutput, ToolError> {
        let opts = CallOptions::new(Caller::Agent).with_cancel(cancel).with_consent(if consent { Consent::Granted } else { Consent::NotAsked });
        self.0.call(id, input, opts)
    }

    fn journal(&self, kind: &str, entry: Value) {
        self.0.journal(kind, entry);
    }

    fn investigation(&self) -> String {
        match self.0.call("core_investigation_show", json!({}), CallOptions::new(Caller::Agent)) {
            Ok(o) => {
                let v = o.to_json();
                let inner = v.get("result").cloned().unwrap_or(v);
                truncate_json(&inner, 24 * 1024)
            }
            Err(e) => format!("(couldn't load: {})", e.message),
        }
    }

    fn clean_room(&self) -> bool {
        self.0.try_session().map(|s| s.clean_room()).unwrap_or(true)
    }

    fn title(&self, id: &str) -> String {
        self.0.registry().get(id).map(|s| s.title.to_string()).unwrap_or_else(|| id.to_string())
    }
}

/// The engine with only the tools that change nothing: no files written, nothing started, no
/// network, nobody asked (recording evidence in the session is fine). For questions about a build.
pub struct ReadOnlyHost(pub EngineHost);

impl ReadOnlyHost {
    fn changes_nothing(&self, id: &str) -> bool {
        use craft_anything_engine::Effects;
        let harmless = Effects::IDEMPOTENT.union(Effects::MUTATES_SESSION).union(Effects::CARRIES_TARGET_CONTENT);
        self.0.0.registry().get(id).is_some_and(|s| harmless.contains(s.effects))
    }
}

impl ToolHost for ReadOnlyHost {
    fn tools(&self, enabled: &BTreeSet<Toolset>) -> Vec<ToolDef> {
        self.0.tools(enabled).into_iter().filter(|t| self.changes_nothing(&t.name)).collect()
    }
    fn toolset_of(&self, id: &str) -> Option<Toolset> {
        self.0.toolset_of(id)
    }
    fn toolsets(&self) -> Vec<Toolset> {
        self.0.toolsets()
    }
    fn call(&self, id: &str, input: Value, _consent: bool, cancel: CancelToken) -> Result<ToolOutput, ToolError> {
        if !self.changes_nothing(id) {
            return Err(ToolError::new(ErrorCode::NoPermission, format!("{id} changes something, and this is only a question."))
                .with_remediation("Answer from what you can read."));
        }
        // Nothing that needs consent is offered, so none is given.
        self.0.call(id, input, false, cancel)
    }
    fn journal(&self, kind: &str, entry: Value) {
        self.0.journal(kind, entry);
    }
    fn investigation(&self) -> String {
        self.0.investigation()
    }
    fn clean_room(&self) -> bool {
        self.0.clean_room()
    }
    fn title(&self, id: &str) -> String {
        self.0.title(id)
    }
}

/// JSON text no longer than `budget` bytes (cut on a char boundary with a note).
pub fn truncate_json(v: &Value, budget: usize) -> String {
    let s = v.to_string();
    if s.len() <= budget {
        return s;
    }
    let mut cut = budget.saturating_sub(120);
    while cut > 0 && !s.is_char_boundary(cut) {
        cut -= 1;
    }
    format!("{}… [truncated: {} of {} bytes shown; page with offset/limit or fetch the evidence by id]", s.get(..cut).unwrap_or_default(), cut, s.len())
}

/// What the model sees for a tool's output: evidence summary + id + (bounded) result.
pub fn compact(out: &ToolOutput) -> (String, String, Option<String>) {
    match out {
        ToolOutput::Evidence(ev) => {
            let mut v = ev.summary_view();
            let result_text = ev.result.to_string();
            let summary_len = v.to_string().len();
            if let Some(o) = v.as_object_mut() {
                if result_text.len() + summary_len <= RESULT_BUDGET {
                    o.insert("result".into(), ev.result.clone());
                } else {
                    o.insert("result_preview".into(), json!(truncate_json(&ev.result, RESULT_BUDGET.saturating_sub(summary_len).max(512))));
                    o.insert(
                        "note".into(),
                        json!("Result is large: this is a preview. Page with offset/limit, or get the full record with core_evidence_show {evidence_id}."),
                    );
                }
            }
            let summary = if ev.summary.is_empty() { ev.operation.clone() } else { ev.summary.clone() };
            (truncate_json(&v, RESULT_BUDGET + 1024), summary, Some(ev.id.clone()))
        }
        ToolOutput::Value(v) => {
            let text = truncate_json(&out.to_json(), RESULT_BUDGET);
            let summary: String = v.to_string().chars().take(160).collect();
            (text, summary, None)
        }
    }
}

fn error_text(e: &ToolError) -> String {
    serde_json::to_string(&json!({"error": e})).unwrap_or_else(|_| e.message.clone())
}

/// Consent waiters shared between the worker and the UI-facing handle.
type Waiters = Arc<Mutex<HashMap<String, Sender<bool>>>>;

/// One model with its display name (a link in a fallback chain).
pub struct ModelSlot {
    pub name: String,
    pub model: Box<dyn ChatModel>,
    /// Local models cost nothing.
    pub local: bool,
    pub effort: Option<Effort>,
    pub max_turns: u32,
}

/// Settings for one conversation.
#[derive(Default)]
pub struct LoopConfig {
    pub beginner: bool,
    pub prices: BTreeMap<String, crate::config::Price>,
    /// Keep the conversation in this file after every step, and continue it when it's there.
    pub transcript: Option<std::path::PathBuf>,
    /// Input tokens the conversation may grow to before it's trimmed; 0 = by model (local or
    /// cloud, see [`crate::context`]).
    pub context_tokens: u64,
}

/// The state the worker keeps between user messages.
pub struct AgentLoop {
    host: Arc<dyn ToolHost>,
    chain: Vec<ModelSlot>,
    current: usize,
    history: Vec<Msg>,
    system: Option<String>,
    enabled: BTreeSet<Toolset>,
    cfg: LoopConfig,
    events: Sender<AgentEvent>,
    waiters: Waiters,
    stop: Stop,
    cancel: Arc<Mutex<CancelToken>>,
    pub meter: Meter,
    /// The last turn's real input size (tokens), 0 before the first or after making room.
    last_input: u64,
}

impl AgentLoop {
    fn emit(&self, e: AgentEvent) {
        let _ = self.events.send(e);
    }

    fn tool_defs(&self) -> Vec<ToolDef> {
        let mut tools = self.host.tools(&self.enabled);
        tools.push(ToolDef {
            name: "list_toolsets".into(),
            description: "List the groups of tools (toolsets), which are enabled, and what each covers.".into(),
            schema: json!({"type": "object", "properties": {}}),
        });
        tools.push(ToolDef {
            name: "enable_toolset".into(),
            description: "Enable a toolset so its tools become available from the next step on. Use list_toolsets to see the ids.".into(),
            schema: json!({"type": "object", "properties": {"toolset": {"type": "string", "enum": self.host.toolsets().iter().map(|t| t.id()).collect::<Vec<_>>()}}, "required": ["toolset"]}),
        });
        crate::anthropic::sorted(tools)
    }

    /// Handle one user message to completion.
    pub fn handle(&mut self, text: &str) {
        self.stop.reset();
        let cancel = CancelToken::default();
        *self.cancel.lock().unwrap_or_else(PoisonError::into_inner) = cancel.clone();
        self.host.journal("user_message", json!({"text": crate::journal_text(text)}));
        if self.system.is_none() {
            self.emit(AgentEvent::Status { text: "Reading the investigation so far…".into() });
            let inv = self.host.investigation();
            self.system = Some(prompt::system_prompt(self.cfg.beginner, self.host.clean_room(), &inv));
        }
        context::push_user_text(&mut self.history, text);
        let configured = self.chain.get(self.current).and_then(|s| s.effort);
        let effort = prompt::choose_effort(configured);
        let max_turns = self.chain.get(self.current).map(|s| s.max_turns).unwrap_or(DEFAULT_MAX_TURNS).max(1);
        let mut msg_usage = Usage::default();
        let mut msg_cost: Option<f64> = Some(0.0);
        let mut turns = 0u32;
        loop {
            if self.stop.is_stopped() {
                self.emit(AgentEvent::Status { text: "Stopped.".into() });
                break;
            }
            if turns >= max_turns {
                self.emit(AgentEvent::Error {
                    message: format!("Stopped after {max_turns} steps without a final answer."),
                    remediation: Some("Ask it to continue, or narrow the question.".into()),
                    log: None,
                });
                break;
            }
            turns += 1;
            let tools = self.tool_defs();
            let system = self.system.clone().unwrap_or_default();
            if let Some((usage, cost)) = self.fit_context(&system) {
                msg_usage.add(usage);
                msg_cost = match (msg_cost, cost) {
                    (Some(a), Some(b)) => Some(a + b),
                    _ => None,
                };
            }
            let Some(result) = self.one_turn(&system, &tools, effort) else { break };
            self.last_input = result.usage.input_tokens + result.usage.cache_read_tokens + result.usage.cache_write_tokens;
            let (slot_name, local, model_id) = match self.chain.get(self.current) {
                Some(s) => (s.name.clone(), s.local, result.model.clone()),
                None => break,
            };
            let cost = price::cost(&model_id, &result.usage, &self.cfg.prices, local);
            self.meter.add(result.usage, cost);
            msg_usage.add(result.usage);
            msg_cost = match (msg_cost, cost) {
                (Some(a), Some(b)) => Some(a + b),
                _ => None,
            };
            self.host.journal(
                "model_turn",
                json!({
                    "backend": slot_name, "model": model_id, "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens, "cache_read_tokens": result.usage.cache_read_tokens,
                    "cache_write_tokens": result.usage.cache_write_tokens, "cost_usd": cost, "stop_reason": result.stop.as_str(),
                    "effort": effort.as_str(),
                }),
            );
            let uses = result.message.tool_uses();
            match result.stop {
                StopReason::Refusal => {
                    self.emit(AgentEvent::Error {
                        message: "The model declined to answer this request.".into(),
                        remediation: Some("Rephrase the question, say why you're examining the software, or try another backend.".into()),
                        log: None,
                    });
                    self.host.journal("error", json!({"kind": "refusal", "backend": slot_name}));
                    // Drop the refused turn so the conversation stays usable.
                    break;
                }
                StopReason::PauseTurn => {
                    self.history.push(result.message);
                    continue;
                }
                StopReason::ToolUse if !uses.is_empty() => {
                    self.history.push(result.message);
                    let results = self.run_tools(&uses);
                    self.history.push(Msg { role: Speaker::User, blocks: results });
                    self.save_transcript();
                }
                StopReason::MaxTokens if !uses.is_empty() => {
                    // Tool input may be cut off: don't run anything, tell the model.
                    self.history.push(result.message);
                    let blocks = uses
                        .iter()
                        .map(|(id, _, _)| Block::ToolResult {
                            tool_use_id: id.clone(),
                            content: "Not run: the reply hit the output limit, so this call may be incomplete. Retry it with smaller input.".into(),
                            is_error: true,
                        })
                        .collect();
                    self.history.push(Msg { role: Speaker::User, blocks });
                }
                StopReason::MaxTokens => {
                    self.history.push(result.message);
                    self.emit(AgentEvent::Status { text: "The answer hit the length limit and was cut off.".into() });
                    break;
                }
                _ => {
                    self.history.push(result.message);
                    break;
                }
            }
        }
        self.save_transcript();
        let backend = self.chain.get(self.current).map(|s| s.name.clone()).unwrap_or_default();
        self.emit(AgentEvent::TurnDone {
            backend,
            input_tokens: msg_usage.input_tokens,
            output_tokens: msg_usage.output_tokens,
            cost_usd: msg_cost,
            cost_is_estimate: false,
        });
    }

    /// Keep the conversation in its transcript file, when it has one.
    fn save_transcript(&self) {
        if let Some(p) = &self.cfg.transcript
            && let Err(e) = context::save(p, &self.history)
        {
            log::warn!("couldn't keep the conversation in {}: {}", p.display(), e.message);
        }
    }

    /// Input tokens the conversation may take before room is made.
    fn context_budget(&self) -> u64 {
        match self.cfg.context_tokens {
            0 if self.chain.get(self.current).is_some_and(|s| s.local) => context::LOCAL_CONTEXT_TOKENS,
            0 => context::CLOUD_CONTEXT_TOKENS,
            n => n,
        }
    }

    /// Make room when the conversation has outgrown its budget: trim old tool results first; when
    /// that isn't enough, replace the oldest part with a summary the model writes. Return the
    /// successful summary call's usage so the message and build account for it too.
    fn fit_context(&mut self, system: &str) -> Option<(Usage, Option<f64>)> {
        let budget = self.context_budget();
        let estimate = context::estimate_tokens(&self.history).max(1);
        let size = if self.last_input > 0 { self.last_input } else { estimate };
        if size <= budget {
            return None;
        }
        // Real tokens per estimated token, to judge the trimmed size before the next turn.
        let scale = size as f64 / estimate as f64;
        let trimmed = context::trim_old(&mut self.history);
        let after = (context::estimate_tokens(&self.history) as f64 * scale) as u64;
        self.last_input = 0;
        self.host.journal("context", json!({"action": "trim", "blocks": trimmed, "tokens_before": size, "tokens_after": after, "budget": budget}));
        if trimmed > 0 && after <= budget * 3 / 4 {
            return None;
        }
        let cut = context::cut_point(&self.history)?;
        self.emit(AgentEvent::Status { text: "Making room: summarising the earlier work…".into() });
        let messages = context::with_summary_request(&self.history[..cut]);
        let req = TurnRequest { system, messages: &messages, tools: &[], effort: Effort::Low, max_tokens: crate::anthropic::MAX_TOKENS };
        let stop = self.stop.clone();
        let summary = self.chain.get_mut(self.current).map(|slot| slot.model.turn(&req, &mut |_| {}, &stop));
        let mut accounted = None;
        let text = match summary {
            Some(Ok(r)) => {
                let local = self.chain.get(self.current).is_some_and(|s| s.local);
                let backend = self.chain.get(self.current).map(|s| s.name.as_str()).unwrap_or_default();
                let cost = price::cost(&r.model, &r.usage, &self.cfg.prices, local);
                self.meter.add(r.usage, cost);
                accounted = Some((r.usage, cost));
                self.host.journal(
                    "model_turn",
                    json!({
                        "backend": backend, "model": r.model, "input_tokens": r.usage.input_tokens,
                        "output_tokens": r.usage.output_tokens, "cache_read_tokens": r.usage.cache_read_tokens,
                        "cache_write_tokens": r.usage.cache_write_tokens, "cost_usd": cost, "stop_reason": r.stop.as_str(),
                        "effort": Effort::Low.as_str(), "purpose": "context_summary",
                    }),
                );
                r.message.text()
            }
            Some(Err(e)) => {
                self.host.journal("error", json!({"kind": "summary", "message": e.message}));
                String::new()
            }
            None => String::new(),
        };
        let text = if text.trim().is_empty() {
            "A summary of the earlier work couldn't be made. Look at the project's files (build_files_list) to see what's done.".to_string()
        } else {
            text
        };
        let before = self.history.len();
        self.history = context::summarised(&self.history, cut, &text);
        self.host.journal("context", json!({"action": "summary", "messages_before": before, "messages_after": self.history.len()}));
        self.save_transcript();
        accounted
    }

    /// One model call, falling back along the chain when a backend fails before producing output.
    fn one_turn(&mut self, system: &str, tools: &[ToolDef], effort: Effort) -> Option<crate::model::TurnResult> {
        loop {
            let events = self.events.clone();
            let mut produced = false;
            let stop = self.stop.clone();
            let req = TurnRequest { system, messages: &self.history, tools, effort, max_tokens: crate::anthropic::MAX_TOKENS };
            let slot = self.chain.get_mut(self.current)?;
            let r = slot.model.turn(
                &req,
                &mut |d| {
                    if let Delta::Text(t) = d {
                        produced = true;
                        let _ = events.send(AgentEvent::TextDelta { text: t });
                    }
                },
                &stop,
            );
            match r {
                Ok(r) => return Some(r),
                Err(e) if e.code == ErrorCode::Cancelled => {
                    self.emit(AgentEvent::Status { text: "Stopped.".into() });
                    return None;
                }
                Err(e) => {
                    let name = slot.name.clone();
                    self.host.journal("error", json!({"backend": name, "code": e.code, "message": e.message}));
                    if !produced && self.current + 1 < self.chain.len() {
                        self.current += 1;
                        let next = self.chain.get(self.current).map(|s| s.name.clone()).unwrap_or_default();
                        self.emit(AgentEvent::Status { text: format!("{name} failed ({}). Trying {next}…", e.message) });
                        continue;
                    }
                    self.emit(AgentEvent::Error { message: format!("{name}: {}", e.message), remediation: e.remediation, log: None });
                    return None;
                }
            }
        }
    }

    /// Run every tool call of one assistant message; all results go back in one user message.
    fn run_tools(&mut self, uses: &[(String, String, Value)]) -> Vec<Block> {
        let mut out = Vec::with_capacity(uses.len());
        for (id, name, input) in uses {
            if self.stop.is_stopped() {
                out.push(Block::ToolResult { tool_use_id: id.clone(), content: "Not run: the user pressed stop.".into(), is_error: true });
                continue;
            }
            self.emit(AgentEvent::ToolStarted { call_id: id.clone(), tool: name.clone(), input: input.clone() });
            let (content, ok, summary, evidence_id) = self.run_one(id, name, input.clone());
            self.emit(AgentEvent::ToolFinished { call_id: id.clone(), tool: name.clone(), ok, summary, evidence_id });
            out.push(Block::ToolResult { tool_use_id: id.clone(), content, is_error: !ok });
        }
        out
    }

    fn run_one(&mut self, call_id: &str, name: &str, input: Value) -> (String, bool, String, Option<String>) {
        if input.get(INVALID_INPUT_KEY).is_some() {
            let e = ToolError::invalid("INVALID_JSON: the tool input wasn't valid JSON (it may have been cut off). Send the call again with complete input.");
            return (error_text(&e), false, e.message, None);
        }
        match name {
            "list_toolsets" => {
                let list: Vec<Value> = self
                    .host
                    .toolsets()
                    .iter()
                    .map(|t| json!({"id": t.id(), "title": t.title(), "enabled": self.enabled.contains(t), "tools": self.host.tools(&BTreeSet::from([*t])).len()}))
                    .collect();
                let text = json!({"toolsets": list}).to_string();
                return (text, true, "Listed toolsets".into(), None);
            }
            "enable_toolset" => {
                let id = input.get("toolset").and_then(Value::as_str).unwrap_or_default();
                return match self.host.toolsets().into_iter().find(|t| t.id() == id) {
                    Some(t) => {
                        self.enabled.insert(t);
                        let n = self.host.tools(&BTreeSet::from([t])).len();
                        (json!({"enabled": id, "tools_added": n}).to_string(), true, format!("Enabled {}", t.title()), None)
                    }
                    None => {
                        let e = ToolError::invalid(format!("No toolset {id:?}")).with_remediation("Call list_toolsets for the ids.");
                        (error_text(&e), false, e.message, None)
                    }
                };
            }
            _ => {}
        }
        match self.host.toolset_of(name) {
            None => {
                let e = ToolError::invalid(format!("No tool named {name}"));
                return (error_text(&e), false, e.message, None);
            }
            Some(t) if !self.enabled.contains(&t) => {
                let e = ToolError::invalid(format!("{name} is in the {} toolset, which isn't enabled.", t.id()))
                    .with_remediation(format!("Call enable_toolset with toolset={} first.", t.id()));
                return (error_text(&e), false, e.message, None);
            }
            Some(_) => {}
        }
        let cancel = self.cancel.lock().unwrap_or_else(PoisonError::into_inner).clone();
        let mut r = self.host.call(name, input.clone(), false, cancel.clone());
        if let Err(e) = &r
            && e.code == ErrorCode::ConsentRequired
        {
            r = match self.ask_consent(call_id, name, &e.message) {
                Some(true) => self.host.call(name, input, true, cancel),
                Some(false) => Err(ToolError::new(ErrorCode::ConsentRequired, "The user said no to running this tool.")
                    .with_remediation("Find another way that doesn't run code or change a device, or explain why it's needed.")),
                None => Err(ToolError::cancelled()),
            };
        }
        match r {
            Ok(out) => {
                let (text, summary, ev) = compact(&out);
                (text, true, summary, ev)
            }
            Err(e) => (error_text(&e), false, e.message.clone(), None),
        }
    }

    /// Ask the UI and wait (this worker thread only) for the answer; `None` when stopped.
    fn ask_consent(&mut self, call_id: &str, tool: &str, explanation: &str) -> Option<bool> {
        let (tx, rx) = std::sync::mpsc::channel();
        self.waiters.lock().unwrap_or_else(PoisonError::into_inner).insert(call_id.to_string(), tx);
        self.emit(AgentEvent::ConsentNeeded {
            call_id: call_id.to_string(),
            tool: tool.to_string(),
            title: self.host.title(tool),
            explanation: explanation.to_string(),
        });
        self.host.journal("consent", json!({"tool": tool, "call_id": call_id, "state": "asked"}));
        let answer = wait_answer(&rx, &self.stop);
        self.waiters.lock().unwrap_or_else(PoisonError::into_inner).remove(call_id);
        self.host.journal(
            "consent",
            json!({"tool": tool, "call_id": call_id, "state": match answer { Some(true) => "allowed", Some(false) => "declined", None => "stopped" }}),
        );
        answer
    }
}

fn wait_answer(rx: &Receiver<bool>, stop: &Stop) -> Option<bool> {
    loop {
        match rx.recv_timeout(Duration::from_millis(100)) {
            Ok(a) => return Some(a),
            Err(RecvTimeoutError::Timeout) if !stop.is_stopped() => {}
            _ => return None,
        }
    }
}

/// A conversation with an API backend: a worker thread runs [`AgentLoop`].
pub struct ApiConversation {
    to_worker: Sender<String>,
    events: Receiver<AgentEvent>,
    busy: Arc<AtomicBool>,
    stop: Stop,
    cancel: Arc<Mutex<CancelToken>>,
    waiters: Waiters,
    queued: Vec<AgentEvent>,
    resumed: bool,
}

impl ApiConversation {
    pub fn start(host: Arc<dyn ToolHost>, chain: Vec<ModelSlot>, cfg: LoopConfig) -> Result<ApiConversation, ToolError> {
        ApiConversation::start_with(host, chain, cfg, BTreeSet::from([Toolset::Core]))
    }

    /// [`ApiConversation::start`] with these toolsets enabled from the start.
    pub fn start_with(host: Arc<dyn ToolHost>, chain: Vec<ModelSlot>, cfg: LoopConfig, enabled: BTreeSet<Toolset>) -> Result<ApiConversation, ToolError> {
        if chain.is_empty() {
            return Err(ToolError::unavailable("No AI backend could be started.").with_remediation("Add one in Settings → AI."));
        }
        let (etx, erx) = std::sync::mpsc::channel();
        let (wtx, wrx) = std::sync::mpsc::channel::<String>();
        let busy = Arc::new(AtomicBool::new(false));
        let stop = Stop::default();
        let cancel = Arc::new(Mutex::new(CancelToken::default()));
        let waiters: Waiters = Arc::default();
        // A kept conversation continues where it stopped.
        let history = cfg.transcript.as_deref().and_then(context::load).unwrap_or_default();
        let resumed = !history.is_empty();
        let mut agent = AgentLoop {
            host,
            chain,
            current: 0,
            history,
            system: None,
            enabled,
            cfg,
            events: etx.clone(),
            waiters: waiters.clone(),
            stop: stop.clone(),
            cancel: cancel.clone(),
            meter: Meter::default(),
            last_input: 0,
        };
        let busy2 = busy.clone();
        std::thread::Builder::new()
            .name("ai-agent".into())
            .spawn(move || {
                while let Ok(text) = wrx.recv() {
                    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| agent.handle(&text)));
                    if r.is_err() {
                        let _ = etx.send(AgentEvent::Error {
                            message: "The assistant hit a bug and stopped safely.".into(),
                            remediation: Some("Start a new chat.".into()),
                            log: None,
                        });
                    }
                    busy2.store(false, Ordering::SeqCst);
                }
            })
            .map_err(|e| ToolError::internal(format!("couldn't start the AI worker: {e}")))?;
        Ok(ApiConversation { to_worker: wtx, events: erx, busy, stop, cancel, waiters, queued: Vec::new(), resumed })
    }

    /// It continues a conversation kept in its transcript file.
    pub fn resumed(&self) -> bool {
        self.resumed
    }
}

impl Conversation for ApiConversation {
    fn send(&mut self, text: &str) {
        self.busy.store(true, Ordering::SeqCst);
        if self.to_worker.send(text.to_string()).is_err() {
            self.busy.store(false, Ordering::SeqCst);
            self.queued.push(AgentEvent::Error {
                message: "The assistant isn't running any more.".into(),
                remediation: Some("Start a new chat.".into()),
                log: None,
            });
        }
    }

    fn poll(&mut self) -> Vec<AgentEvent> {
        let mut v = std::mem::take(&mut self.queued);
        v.extend(self.events.try_iter());
        v
    }

    fn answer_consent(&mut self, call_id: &str, allow: bool) {
        if let Some(tx) = self.waiters.lock().unwrap_or_else(PoisonError::into_inner).remove(call_id) {
            let _ = tx.send(allow);
        }
    }

    fn stop(&mut self) {
        self.stop.stop();
        self.cancel.lock().unwrap_or_else(PoisonError::into_inner).cancel();
    }

    fn is_busy(&self) -> bool {
        self.busy.load(Ordering::SeqCst)
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::model::TurnResult;
    use std::collections::VecDeque;

    /// Paths of boolean sub-schemas in `v`.
    fn boolean_subschemas(v: &Value, path: &str, out: &mut Vec<String>) {
        let Value::Object(o) = v else { return };
        for (k, sub) in o {
            let subs: Vec<(String, &Value)> = match (k.as_str(), sub) {
                ("properties" | "$defs" | "definitions", Value::Object(m)) => m.iter().map(|(n, s)| (format!("{path}/{k}/{n}"), s)).collect(),
                ("anyOf" | "oneOf" | "allOf" | "prefixItems", Value::Array(a)) => a.iter().enumerate().map(|(i, s)| (format!("{path}/{k}/{i}"), s)).collect(),
                ("items" | "not", s) => vec![(format!("{path}/{k}"), s)],
                _ => Vec::new(),
            };
            for (p, s) in subs {
                if s.is_boolean() {
                    out.push(p);
                } else {
                    boolean_subschemas(s, &p, out);
                }
            }
        }
    }

    /// Every place a schema can sit holds an object, as LM Studio requires (#17).
    #[test]
    fn tool_schemas_have_only_object_subschemas() {
        let reg = Registry::with_all_tools();
        let all: BTreeSet<Toolset> = reg.toolsets().into_iter().collect();
        let raw = reg.get("app_call_path_find").map(|s| reg.input_schema(s)).unwrap_or_default();
        assert!(raw.to_string().contains("\"items\":true"), "the case from #17 is still covered");
        let mut bad = Vec::new();
        for t in registry_tools(&reg, &all) {
            boolean_subschemas(&t.schema, &t.name, &mut bad);
        }
        assert!(bad.is_empty(), "boolean sub-schemas left: {bad:?}");
    }

    #[test]
    fn boolean_subschemas_become_objects() {
        let s = clean_schema(json!({
            "type": "object", "additionalProperties": false,
            "properties": {"functions": {"type": "array", "items": true}, "never": false, "pick": {"anyOf": [true, {"items": false}]}}
        }));
        assert_eq!(s["properties"]["functions"]["items"], json!({}));
        assert_eq!(s["properties"]["never"], json!({"not": {}}));
        assert_eq!(s["properties"]["pick"]["anyOf"], json!([{}, {"items": {"not": {}}}]));
        assert_eq!(s["additionalProperties"], json!(false), "left as APIs expect");
        // Deeper than the limit: the rest is left as it is.
        let mut deep = json!(true);
        for _ in 0..(MAX_SCHEMA_DEPTH + 10) {
            deep = json!({"items": deep});
        }
        let mut bad = Vec::new();
        boolean_subschemas(&clean_schema(deep), "", &mut bad);
        assert_eq!(bad.len(), 1);
    }

    /// A scripted model: returns canned turns and records requests.
    pub struct Scripted {
        pub turns: VecDeque<Result<TurnResult, ToolError>>,
        pub seen: Arc<Mutex<Vec<Vec<Msg>>>>,
    }

    impl ChatModel for Scripted {
        fn turn(&mut self, req: &TurnRequest<'_>, on_delta: &mut dyn FnMut(Delta), _stop: &Stop) -> Result<TurnResult, ToolError> {
            self.seen.lock().unwrap().push(req.messages.to_vec());
            let r = self.turns.pop_front().unwrap_or_else(|| Err(ToolError::internal("script ended")));
            if let Ok(t) = &r {
                let text = t.message.text();
                if !text.is_empty() {
                    on_delta(Delta::Text(text));
                }
            }
            r
        }
        fn model(&self) -> String {
            "scripted".into()
        }
    }

    pub fn turn(blocks: Vec<Block>, stop: StopReason) -> Result<TurnResult, ToolError> {
        Ok(TurnResult {
            message: Msg { role: Speaker::Assistant, blocks },
            stop,
            usage: Usage { input_tokens: 10, output_tokens: 5, ..Default::default() },
            model: "claude-opus-5-5".into(),
        })
    }

    /// A host whose `danger` tool needs consent.
    struct FakeHost {
        calls: Mutex<Vec<(String, bool)>>,
        journal: Mutex<Vec<(String, Value)>>,
    }

    impl ToolHost for FakeHost {
        fn tools(&self, enabled: &BTreeSet<Toolset>) -> Vec<ToolDef> {
            let mut v = Vec::new();
            if enabled.contains(&Toolset::Core) {
                v.push(ToolDef { name: "look".into(), description: "d".into(), schema: json!({"type":"object"}) });
            }
            if enabled.contains(&Toolset::Runtime) {
                v.push(ToolDef { name: "danger".into(), description: "d".into(), schema: json!({"type":"object"}) });
            }
            v
        }
        fn toolset_of(&self, id: &str) -> Option<Toolset> {
            match id {
                "look" => Some(Toolset::Core),
                "danger" => Some(Toolset::Runtime),
                _ => None,
            }
        }
        fn call(&self, id: &str, _input: Value, consent: bool, _c: CancelToken) -> Result<ToolOutput, ToolError> {
            self.calls.lock().unwrap().push((id.to_string(), consent));
            if id == "danger" && !consent {
                return Err(ToolError::new(ErrorCode::ConsentRequired, "needs your OK"));
            }
            Ok(ToolOutput::Value(json!({"ran": id})))
        }
        fn journal(&self, kind: &str, entry: Value) {
            self.journal.lock().unwrap().push((kind.to_string(), entry));
        }
        fn investigation(&self) -> String {
            "{}".into()
        }
        fn clean_room(&self) -> bool {
            true
        }
        fn title(&self, id: &str) -> String {
            id.into()
        }
    }

    fn drain_until_done(c: &mut ApiConversation, mut on: impl FnMut(&AgentEvent, &mut ApiConversation)) -> Vec<AgentEvent> {
        let mut all = Vec::new();
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        while std::time::Instant::now() < deadline {
            for e in c.poll() {
                on(&e, c);
                let done = matches!(e, AgentEvent::TurnDone { .. });
                all.push(e);
                if done {
                    return all;
                }
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        panic!("timed out: {all:?}");
    }

    #[test]
    fn consent_toolsets_and_one_result_message() {
        let host = Arc::new(FakeHost { calls: Mutex::default(), journal: Mutex::default() });
        let seen = Arc::new(Mutex::new(Vec::new()));
        let script = Scripted {
            turns: VecDeque::from([
                turn(vec![Block::ToolUse { id: "a".into(), name: "danger".into(), input: json!({}) }], StopReason::ToolUse),
                turn(
                    vec![
                        Block::ToolUse { id: "b".into(), name: "enable_toolset".into(), input: json!({"toolset": "runtime"}) },
                        Block::ToolUse { id: "c".into(), name: "look".into(), input: json!({}) },
                        Block::ToolUse { id: "d".into(), name: "look".into(), input: json!({"__invalid_json_input": "{"}) },
                    ],
                    StopReason::ToolUse,
                ),
                turn(vec![Block::ToolUse { id: "e".into(), name: "danger".into(), input: json!({}) }], StopReason::ToolUse),
                turn(vec![Block::ToolUse { id: "f".into(), name: "danger".into(), input: json!({}) }], StopReason::ToolUse),
                turn(vec![Block::Text { text: "done".into() }], StopReason::EndTurn),
            ]),
            seen: seen.clone(),
        };
        let slot = ModelSlot { name: "Fake".into(), model: Box::new(script), local: false, effort: None, max_turns: 10 };
        let mut c = ApiConversation::start(host.clone(), vec![slot], LoopConfig { beginner: true, ..LoopConfig::default() }).unwrap();
        c.send("How does it work?");
        assert!(c.is_busy());
        let mut asked = 0;
        let events = drain_until_done(&mut c, |e, c| {
            if let AgentEvent::ConsentNeeded { call_id, .. } = e {
                asked += 1;
                c.answer_consent(call_id, call_id == "e");
            }
        });
        assert_eq!(asked, 2);
        let seen = seen.lock().unwrap();
        // turn 1: danger not enabled → error, no consent asked
        let r1 = seen[1].last().unwrap();
        assert!(matches!(&r1.blocks[0], Block::ToolResult { is_error: true, content, .. } if content.contains("enable_toolset")));
        // turn 2: three results in ONE user message
        let r2 = seen[2].last().unwrap();
        assert_eq!(r2.role, Speaker::User);
        assert_eq!(r2.blocks.len(), 3);
        assert!(matches!(&r2.blocks[2], Block::ToolResult { is_error: true, content, .. } if content.contains("INVALID_JSON")));
        // turn 3 allowed, turn 4 declined
        assert!(matches!(&seen[3].last().unwrap().blocks[0], Block::ToolResult { is_error: false, .. }));
        assert!(matches!(&seen[4].last().unwrap().blocks[0], Block::ToolResult { is_error: true, content, .. } if content.contains("said no")));
        let calls = host.calls.lock().unwrap().clone();
        assert!(calls.contains(&("danger".into(), true)));
        assert!(events.iter().any(|e| matches!(e, AgentEvent::TextDelta { text } if text == "done")));
        let j = host.journal.lock().unwrap().clone();
        for kind in ["user_message", "model_turn", "consent"] {
            assert!(j.iter().any(|(k, _)| k == kind));
        }
        assert!(matches!(events.last(), Some(AgentEvent::TurnDone { input_tokens: 50, .. })));
        // cost known for the priced model id
        assert!(matches!(events.last(), Some(AgentEvent::TurnDone { cost_usd: Some(_), .. })));
    }

    #[test]
    fn a_long_conversation_is_summarised_kept_and_resumed() {
        let d = tempfile::tempdir().unwrap();
        let path = d.path().join("transcript.json");
        let host = Arc::new(FakeHost { calls: Mutex::default(), journal: Mutex::default() });
        let seen = Arc::new(Mutex::new(Vec::new()));
        let look = |id: &str| turn(vec![Block::ToolUse { id: id.into(), name: "look".into(), input: json!({}) }], StopReason::ToolUse);
        let mut summary = turn(vec![Block::Text { text: "Made index.html; the menu is left.".into() }], StopReason::EndTurn).unwrap();
        summary.usage = Usage { input_tokens: 30, output_tokens: 4, cache_read_tokens: 7, cache_write_tokens: 3 };
        let script = Scripted {
            turns: VecDeque::from([look("a"), look("b"), Ok(summary), turn(vec![Block::Text { text: "done".into() }], StopReason::EndTurn)]),
            seen: seen.clone(),
        };
        let slot = ModelSlot { name: "Fake".into(), model: Box::new(script), local: false, effort: None, max_turns: 10 };
        // Ordinary turns report 10 input tokens, over this budget, so room is made before the third.
        let cfg = || LoopConfig {
            transcript: Some(path.clone()),
            context_tokens: 5,
            prices: BTreeMap::from([(
                "claude-opus-5-5".into(),
                crate::config::Price { input_per_mtok: 1.0, output_per_mtok: 2.0, cache_read_per_mtok: Some(0.25), cache_write_per_mtok: Some(0.5) },
            )]),
            ..LoopConfig::default()
        };
        let mut c = ApiConversation::start(host.clone(), vec![slot], cfg()).unwrap();
        assert!(!c.resumed());
        c.send("Build it");
        let events = drain_until_done(&mut c, |_, _| {});
        assert!(events.iter().any(|e| matches!(e, AgentEvent::TextDelta { text } if text == "done")));
        {
            let seen = seen.lock().unwrap();
            assert_eq!(seen.len(), 4, "two steps, the summary, the last step");
            assert!(seen[2].last().unwrap().text().contains("summary of the work so far"), "the summary request");
            assert!(seen[3][0].text().contains("Made index.html"), "the summary replaced the oldest part");
            assert!(seen[3].len() < seen[1].len() + 2);
        }
        assert!(
            matches!(events.last(), Some(AgentEvent::TurnDone { input_tokens: 60, output_tokens: 19, cost_usd: Some(cost), .. }) if (cost - 0.00010125).abs() < 1e-12),
            "{events:?}"
        );
        {
            let journal = host.journal.lock().unwrap();
            assert!(journal.iter().any(|(kind, _)| kind == "context"));
            let turns: Vec<_> = journal.iter().filter(|(kind, _)| kind == "model_turn").map(|(_, entry)| entry).collect();
            assert_eq!(turns.len(), 4, "all model calls, including the summary, are journaled");
            let summary = turns.iter().find(|entry| entry["purpose"] == "context_summary").unwrap();
            assert_eq!(summary["input_tokens"], 30);
            assert_eq!(summary["output_tokens"], 4);
            assert_eq!(summary["cache_read_tokens"], 7);
            assert_eq!(summary["cache_write_tokens"], 3);
            assert_eq!(summary["effort"], "low");
            assert!((turns.iter().map(|entry| entry["cost_usd"].as_f64().unwrap()).sum::<f64>() - 0.00010125).abs() < 1e-12);
        }
        // A new conversation with the same file continues it.
        let seen2 = Arc::new(Mutex::new(Vec::new()));
        let script = Scripted { turns: VecDeque::from([turn(vec![Block::Text { text: "blue now".into() }], StopReason::EndTurn)]), seen: seen2.clone() };
        let slot = ModelSlot { name: "Fake".into(), model: Box::new(script), local: false, effort: None, max_turns: 10 };
        let mut c = ApiConversation::start(host, vec![slot], LoopConfig { transcript: Some(path.clone()), ..LoopConfig::default() }).unwrap();
        assert!(c.resumed());
        c.send("Make it blue");
        drain_until_done(&mut c, |_, _| {});
        let seen2 = seen2.lock().unwrap();
        assert!(seen2[0][0].text().contains("Made index.html") && seen2[0].last().unwrap().text().contains("Make it blue"));
        assert!(crate::context::load(&path).unwrap().last().unwrap().text().contains("blue now"), "kept after every message");
    }

    #[test]
    fn summary_accounting_keeps_unknown_prices_and_failed_calls_distinct() {
        for (local, failed) in [(false, false), (true, false), (false, true)] {
            let host = Arc::new(FakeHost { calls: Mutex::default(), journal: Mutex::default() });
            let seen = Arc::new(Mutex::new(Vec::new()));
            let look = |id: &str| turn(vec![Block::ToolUse { id: id.into(), name: "look".into(), input: json!({}) }], StopReason::ToolUse);
            let summary = if failed {
                Err(ToolError::internal("summary unavailable"))
            } else {
                let mut result = turn(vec![Block::Text { text: String::new() }], StopReason::EndTurn).unwrap();
                result.model = "unpriced-fixture-model".into();
                Ok(result)
            };
            let script = Scripted {
                turns: VecDeque::from([look("a"), look("b"), summary, turn(vec![Block::Text { text: "done".into() }], StopReason::EndTurn)]),
                seen: seen.clone(),
            };
            let slot = ModelSlot { name: "Fake".into(), model: Box::new(script), local, effort: None, max_turns: 10 };
            let mut c = ApiConversation::start(host.clone(), vec![slot], LoopConfig { context_tokens: 5, ..LoopConfig::default() }).unwrap();
            c.send("Build it");
            let events = drain_until_done(&mut c, |_, _| {});
            assert_eq!(seen.lock().unwrap().len(), 4, "the summary was attempted");
            let Some(AgentEvent::TurnDone { input_tokens, output_tokens, cost_usd, .. }) = events.last() else { panic!("{events:?}") };
            assert_eq!((*input_tokens, *output_tokens), if failed { (30, 15) } else { (40, 20) });
            if local {
                assert_eq!(*cost_usd, Some(0.0));
            } else if failed {
                assert!(cost_usd.is_some(), "a failed call supplies no usage or unknown price");
            } else {
                assert_eq!(*cost_usd, None, "the successful summary's unknown price makes the total unknown");
            }
            let journal = host.journal.lock().unwrap();
            assert_eq!(journal.iter().filter(|(kind, _)| kind == "model_turn").count(), if failed { 3 } else { 4 });
        }
    }

    #[test]
    fn fallback_chain_and_refusal() {
        let host = Arc::new(FakeHost { calls: Mutex::default(), journal: Mutex::default() });
        let failing = Scripted { turns: VecDeque::from([Err(ToolError::new(ErrorCode::EngineMissing, "down"))]), seen: Arc::default() };
        let refusing = Scripted {
            turns: VecDeque::from([turn(vec![], StopReason::Refusal), turn(vec![Block::Text { text: "ok".into() }], StopReason::EndTurn)]),
            seen: Arc::default(),
        };
        let chain = vec![
            ModelSlot { name: "A".into(), model: Box::new(failing), local: false, effort: None, max_turns: 5 },
            ModelSlot { name: "B".into(), model: Box::new(refusing), local: true, effort: None, max_turns: 5 },
        ];
        let mut c = ApiConversation::start(host, chain, LoopConfig::default()).unwrap();
        c.send("q");
        let ev = drain_until_done(&mut c, |_, _| {});
        assert!(ev.iter().any(|e| matches!(e, AgentEvent::Status { text } if text.contains("Trying B"))));
        assert!(ev.iter().any(|e| matches!(e, AgentEvent::Error { message, .. } if message.contains("declined"))));
        assert!(matches!(ev.last(), Some(AgentEvent::TurnDone { backend, .. }) if backend == "B"));
        c.send("again");
        let ev = drain_until_done(&mut c, |_, _| {});
        assert!(ev.iter().any(|e| matches!(e, AgentEvent::TextDelta { text } if text == "ok")));
        assert!(!c.is_busy() || c.poll().is_empty());
    }

    #[test]
    fn compaction_keeps_small_results_and_previews_large_ones() {
        use craft_anything_evidence::{Environment, EvidenceBuilder, Subject};
        let small = EvidenceBuilder::new("op", Subject::default(), Environment::builtin(true)).result(json!({"a": 1})).summary("small").build().unwrap();
        let (text, summary, id) = compact(&ToolOutput::evidence(small.clone()));
        assert!(text.contains("\"result\":{\"a\":1}"));
        assert_eq!(summary, "small");
        assert_eq!(id, Some(small.id));
        let big = EvidenceBuilder::new("op", Subject::default(), Environment::builtin(true)).result(json!({"s": "x".repeat(100_000)})).build().unwrap();
        let (text, _, _) = compact(&ToolOutput::evidence(big));
        assert!(text.len() < RESULT_BUDGET + 2048);
        assert!(text.contains("result_preview"));
        let (text, _, id) = compact(&ToolOutput::Value(json!({"k": "v"})));
        assert!(text.contains("\"k\""));
        assert!(id.is_none());
        assert!(truncate_json(&json!("é".repeat(50_000)), 1000).len() < 1100);
    }
}
