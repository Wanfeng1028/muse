//! AI backends, the agent loop and crews.
//!
//! The UI talks to this crate only through [`AiHub`] and [`Conversation`]: start a conversation,
//! send a message, then poll [`AgentEvent`]s every frame. All network and subprocess work happens
//! on background threads; nothing here ever blocks the caller (except the explicitly blocking
//! helpers `test_backend`, `list_models` and `check_reachability`, which the UI runs on a worker).
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod agent;
pub mod anthropic;
pub mod cli_agents;
pub mod config;
pub mod context;
pub mod detect;
pub mod failure_log;
pub mod http;
pub mod key_tools;
pub mod keys;
pub mod model;
pub mod openai;
pub mod price;
pub mod prompt;
pub mod rebuild;
pub mod ssh;

pub use config::{AiConfig, BackendEntry, BackendOptions, Price};
pub use keys::KeyStore;
pub use model::Effort;

use crate::agent::{ApiConversation, EngineHost, LoopConfig, ModelSlot};
use crate::model::{ChatModel, Delta, Msg, Stop, TurnRequest, TurnResult};
use craft_anything_engine::{Engine, Settings};
use craft_anything_evidence::{ErrorCode, ToolError};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Kinds of backend. See `plan/05-ai-backends.md`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BackendKind {
    Anthropic,
    Openai,
    Openrouter,
    /// Ollama, LM Studio, llama.cpp, vLLM… (OpenAI-compatible HTTP).
    OpenaiCompatible,
    /// Claude Code, Codex, Gemini CLI, Hermes Agent, OpenCode… run as a subprocess with our MCP server.
    AgentCli,
}

impl BackendKind {
    pub fn title(self) -> &'static str {
        match self {
            BackendKind::Anthropic => "Anthropic (Claude API)",
            BackendKind::Openai => "OpenAI",
            BackendKind::Openrouter => "OpenRouter",
            BackendKind::OpenaiCompatible => "Local / OpenAI-compatible server",
            BackendKind::AgentCli => "Agent app (command line)",
        }
    }

    /// Models offered in a dropdown before a live list is fetched.
    pub fn suggested_models(self) -> &'static [&'static str] {
        match self {
            BackendKind::Anthropic => anthropic::MODELS,
            BackendKind::Openai => &[openai::OPENAI_DEFAULT_MODEL],
            BackendKind::Openrouter => openai::OPENROUTER_MODELS,
            BackendKind::OpenaiCompatible => &[],
            BackendKind::AgentCli => &["claude-code", "codex", "gemini-cli", "opencode", "antigravity", "hermes", "maki"],
        }
    }

    pub fn needs_key(self) -> bool {
        matches!(self, BackendKind::Anthropic | BackendKind::Openai | BackendKind::Openrouter)
    }
}

/// One configured backend (stored in `settings.ai`; secrets live in the OS keychain).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BackendConfig {
    /// User-chosen name, unique: "Claude", "Local Llama", "Codex on studio-mac".
    pub name: String,
    pub kind: BackendKind,
    /// Model id (API backends) or agent id (`claude-code`, `codex`, `gemini-cli`, `antigravity`, `hermes`, `opencode`…).
    pub model: String,
    /// Base URL for API backends (defaults per kind).
    #[serde(default)]
    pub base_url: Option<String>,
    /// SSH host alias for running an agent CLI or reaching a local-LLM server remotely.
    #[serde(default)]
    pub ssh_host: Option<String>,
    #[serde(default = "yes")]
    pub enabled: bool,
}

fn yes() -> bool {
    true
}

/// The effort an AI thinks at, when it can be chosen (Settings → AI): the Claude API and Claude
/// Code, which take every level in [`Effort::ALL`]. `None` for the others, which don't use it.
pub fn effort_in_use(config: &BackendConfig, options: Option<&BackendOptions>) -> Option<Effort> {
    let claude = match config.kind {
        BackendKind::Anthropic => true,
        BackendKind::AgentCli => config.model == "claude-code",
        _ => false,
    };
    claude.then(|| prompt::choose_effort(options.and_then(|o| o.effort)))
}

/// The model an AI uses, when it can be chosen (Settings → AI, #123): an API's own, or the one
/// Claude Code is asked for. `None` for an agent app that picks its own.
pub fn model_in_use(config: &BackendConfig, options: Option<&BackendOptions>) -> Option<String> {
    match config.kind {
        BackendKind::AgentCli if config.model == "claude-code" => {
            Some(options.and_then(|o| o.cli_model.clone()).unwrap_or_else(|| anthropic::DEFAULT_MODEL.to_string()))
        }
        BackendKind::AgentCli => None,
        _ => Some(config.model.clone()),
    }
}

/// The backend that builds when none is named: the Builder role's choice while it's on, else an
/// agent app, else an API backend. The same rule as [`AiConfig::backend_for`] for
/// [`Role::Builder`], for a client that holds only the list (the app decides "can it build?"
/// with it, so its warning and Start never disagree).
pub fn default_builder<'a>(backends: &'a [BackendConfig], chosen: Option<&str>) -> Option<&'a BackendConfig> {
    let on = || backends.iter().filter(|b| b.enabled);
    chosen
        .and_then(|n| on().find(|b| b.name == n))
        .or_else(|| on().find(|b| b.kind == BackendKind::AgentCli))
        .or_else(|| on().find(|b| b.kind != BackendKind::AgentCli))
}

/// What a backend does in a crew.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    Lead,
    Worker,
    Reviewer,
    Builder,
    /// Takes the original game's files out after the study, in Deep mode (only when chosen).
    Extractor,
}

/// Something that was found on this machine and can be added with one click.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Detected {
    pub suggestion: BackendConfig,
    /// Plain words: "Found Ollama running with 3 models", "Found ANTHROPIC_API_KEY".
    pub reason: String,
    /// True when a key is still needed before it works.
    pub needs_key: bool,
}

/// Events the UI renders, in order.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgentEvent {
    /// Streaming text from the assistant (append to the current message).
    TextDelta {
        text: String,
    },
    /// A short note on what it's doing ("Looking at the functions that mention 'percent'…").
    Status {
        text: String,
    },
    /// A line a program printed outside the conversation (its stderr), for logs: never part of
    /// the answer.
    Output {
        text: String,
    },
    ToolStarted {
        call_id: String,
        tool: String,
        input: serde_json::Value,
    },
    ToolFinished {
        call_id: String,
        tool: String,
        ok: bool,
        summary: String,
        evidence_id: Option<String>,
    },
    /// The agent wants to run a tool that needs the user's OK. Answer with [`Conversation::answer_consent`].
    ConsentNeeded {
        call_id: String,
        tool: String,
        title: String,
        explanation: String,
    },
    /// One assistant turn finished.
    TurnDone {
        backend: String,
        input_tokens: u64,
        output_tokens: u64,
        cost_usd: Option<f64>,
        /// `cost_usd` is the agent's own guess at API prices, not what a key was charged: a
        /// subscription may cover the whole of it.
        #[serde(default)]
        cost_is_estimate: bool,
    },
    Error {
        message: String,
        remediation: Option<String>,
        /// A log with everything known about the failure, to open and inspect.
        log: Option<std::path::PathBuf>,
    },
}

/// A chat with the agent about the current session.
pub trait Conversation: Send {
    fn send(&mut self, text: &str);
    /// A saved session to continue later, for agents that have one (agent CLIs).
    fn session_id(&self) -> Option<String> {
        None
    }
    /// The saved session the last message was to continue isn't on this computer (the project
    /// was started on another one, or in another folder): that message did nothing, and the next
    /// one starts a new session, which knows nothing of the old.
    fn session_lost(&self) -> bool {
        false
    }
    /// Drain new events (non-blocking).
    fn poll(&mut self) -> Vec<AgentEvent>;
    fn answer_consent(&mut self, call_id: &str, allow: bool);
    fn stop(&mut self);
    fn is_busy(&self) -> bool;
}

/// A conversation tagged with its backend's name (compare mode).
pub type Labeled = (String, Box<dyn Conversation>);

/// Result of a backend test.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TestReport {
    pub backend: String,
    pub model: String,
    pub latency_ms: u64,
    pub reply: String,
    /// Only the coding agent's `--version` ran (`reply` is its first line): it's installed, but
    /// whether it's signed in, has a model and quota shows only when it gets a message (#48).
    #[serde(default)]
    pub version_only: bool,
}

/// Text kept in the journal for a user message (bounded).
pub(crate) fn journal_text(t: &str) -> String {
    t.chars().take(4000).collect()
}

/// A model reached through an ssh tunnel; the tunnel lives as long as the model.
struct Tunneled {
    inner: Box<dyn ChatModel>,
    _tunnel: ssh::Tunnel,
}

impl ChatModel for Tunneled {
    fn turn(&mut self, req: &TurnRequest<'_>, on_delta: &mut dyn FnMut(Delta), stop: &Stop) -> Result<TurnResult, ToolError> {
        self.inner.turn(req, on_delta, stop)
    }

    fn model(&self) -> String {
        self.inner.model()
    }
}

/// The tools this layer adds to the engine's (rebuild control), for
/// [`craft_anything_engine::Engine::shared`].
pub fn tools() -> Vec<craft_anything_engine::ToolSpec> {
    let mut v = rebuild::tools::specs();
    v.extend(key_tools::specs());
    v
}

/// Entry point for the UI and CLI.
pub struct AiHub {
    pub engine: Arc<Engine>,
    settings_path: Option<PathBuf>,
    keys: KeyStore,
}

impl AiHub {
    pub fn new(engine: Arc<Engine>) -> Self {
        AiHub { engine, settings_path: None, keys: KeyStore::system() }
    }

    /// A hub with explicit settings file and key store (tests, portable installs).
    pub fn with_stores(engine: Arc<Engine>, settings_path: PathBuf, keys: KeyStore) -> Self {
        AiHub { engine, settings_path: Some(settings_path), keys }
    }

    fn settings_path(&self) -> PathBuf {
        self.settings_path.clone().unwrap_or_else(Settings::path)
    }

    /// The current AI configuration. Never blocks on a running tool: if the session is busy the
    /// saved settings file is read instead.
    pub fn config(&self) -> AiConfig {
        match self.engine.try_session() {
            Some(s) => AiConfig::from_settings(&s.settings),
            None => AiConfig::from_settings(&Settings::load_from(&self.settings_path())),
        }
    }

    /// The configuration to change and save back. An [ai] section that can't be read is an error
    /// here, never the empty default, so a change can't save over it (#261).
    fn config_to_change(&self) -> Result<AiConfig, ToolError> {
        match self.engine.try_session() {
            Some(s) => AiConfig::from_table(&s.settings.ai),
            None => AiConfig::from_table(&Settings::load_from(&self.settings_path()).ai),
        }
    }

    /// Save the AI configuration into the settings file, then the session: a save that fails
    /// changes nothing, so the app never shows a backend or role that isn't saved.
    pub fn save_config(&self, cfg: &AiConfig) -> Result<(), ToolError> {
        let table = cfg.to_table()?;
        let mut s = self.engine.session();
        let mut next = s.settings.clone();
        next.ai = table;
        next.save_to(&self.settings_path())?;
        s.settings = next;
        Ok(())
    }

    /// Configured backends.
    pub fn backends(&self) -> Vec<BackendConfig> {
        self.config().backends.into_iter().map(|b| b.config).collect()
    }

    /// Look for keys, local servers and agent CLIs (runs quickly; network probes are bounded).
    /// Things already configured (by name) are left out.
    pub fn detect(&self) -> Vec<Detected> {
        let have: Vec<String> = self.backends().into_iter().map(|b| b.name).collect();
        detect::detect_all().into_iter().filter(|d| !have.contains(&d.suggestion.name)).collect()
    }

    /// Host aliases from `~/.ssh/config`, for the "run on another machine" picker.
    pub fn ssh_hosts(&self) -> Vec<String> {
        ssh::ssh_hosts()
    }

    /// The backend the person chose for `role` in Settings → AI, while it's still enabled.
    pub fn chosen(&self, role: Role) -> Option<String> {
        let cfg = self.config();
        cfg.roles.get(config::role_key(role)).filter(|n| cfg.get(n).is_some_and(|b| b.config.enabled)).cloned()
    }

    /// Choose the backend for `role`; `None` goes back to its default (the builder: an agent app,
    /// else any AI backend; the extractor: none).
    pub fn set_role(&self, role: Role, name: Option<&str>) -> Result<(), ToolError> {
        let mut cfg = self.config_to_change()?;
        let role = config::role_key(role).to_string();
        match name {
            Some(n) if cfg.get(n).is_none() => {
                return Err(
                    ToolError::invalid(format!("No AI backend named {n:?}")).with_remediation("See `craft-anything-cli ai list`, or add one in Settings → AI.")
                );
            }
            Some(n) => {
                cfg.roles.insert(role, n.to_string());
            }
            None => {
                cfg.roles.remove(&role);
            }
        }
        self.save_config(&cfg)
    }

    /// Add (or replace) a backend, storing its key in the keychain when given.
    pub fn add_backend(&self, cfg: BackendConfig, key: Option<String>) -> Result<(), ToolError> {
        self.add_backend_with(BackendEntry { config: cfg, options: BackendOptions::default() }, key)
    }

    /// Add an OpenAI-compatible server by its address: Ollama or LM Studio on another computer, or
    /// a hosted service with its key. It's added only when it answers with its models; without a
    /// model, the first one it lists that can chat is used. Returns the model.
    pub fn add_server(&self, name: &str, address: &str, model: Option<&str>, key: Option<String>) -> Result<String, ToolError> {
        let name = name.trim();
        let address = address.trim().trim_end_matches('/');
        if name.is_empty() {
            return Err(ToolError::invalid("A backend needs a name."));
        }
        if !(address.starts_with("http://") || address.starts_with("https://")) {
            return Err(ToolError::invalid(format!("{address:?} isn't a web address."))
                .with_remediation("Give the server's address, like http://192.168.1.20:11434/v1."));
        }
        let key = key.map(|k| k.trim().to_string()).filter(|k| !k.is_empty());
        let models = openai::OpenAi::compatible(name, address, key.clone(), "").list_models(Duration::from_secs(10)).map_err(|e| {
            let why = e.message.clone();
            e.with_remediation(format!(
                "Check the address (it usually ends in /v1), that the server is running and can be reached from this computer, and its key if it needs one. ({why})"
            ))
        })?;
        let model = match model.map(str::trim).filter(|m| !m.is_empty()) {
            Some(m) => m.to_string(),
            None => detect::chat_model(&models).ok_or_else(|| {
                ToolError::new(ErrorCode::NotFound, format!("{address} has no models yet.")).with_remediation("Add a model on the server first, or name one.")
            })?,
        };
        let config = BackendConfig {
            name: name.to_string(),
            kind: BackendKind::OpenaiCompatible,
            model: model.clone(),
            base_url: Some(address.to_string()),
            ssh_host: None,
            enabled: true,
        };
        self.add_backend(config, key)?;
        Ok(model)
    }

    /// Like [`AiHub::add_backend`], with options.
    pub fn add_backend_with(&self, entry: BackendEntry, key: Option<String>) -> Result<(), ToolError> {
        if entry.config.name.trim().is_empty() {
            return Err(ToolError::invalid("A backend needs a name."));
        }
        let mut cfg = self.config_to_change()?;
        if let Some(k) = key.filter(|k| !k.trim().is_empty()) {
            self.keys.set(&entry.config.name, k.trim())?;
        }
        cfg.upsert(entry);
        self.save_config(&cfg)
    }

    /// Turn a backend on or off; it keeps its settings and key. Returns false when there was no
    /// such backend.
    pub fn set_enabled(&self, name: &str, on: bool) -> Result<bool, ToolError> {
        let mut cfg = self.config_to_change()?;
        let Some(b) = cfg.backends.iter_mut().find(|b| b.config.name == name) else { return Ok(false) };
        b.config.enabled = on;
        self.save_config(&cfg)?;
        Ok(true)
    }

    /// The program an agent app runs (`None` or empty: found by its usual name, on PATH and in the
    /// usual install folders). Returns false when there was no such backend.
    pub fn set_command(&self, name: &str, command: Option<&str>) -> Result<bool, ToolError> {
        let mut cfg = self.config_to_change()?;
        let Some(b) = cfg.backends.iter_mut().find(|b| b.config.name == name) else { return Ok(false) };
        b.options.command = command.map(str::trim).filter(|c| !c.is_empty()).map(str::to_string);
        self.save_config(&cfg)?;
        Ok(true)
    }

    /// Each backend's options (an agent app's program and model…), by name.
    pub fn options(&self) -> std::collections::BTreeMap<String, BackendOptions> {
        self.config().backends.into_iter().map(|b| (b.config.name, b.options)).collect()
    }

    /// The model a backend uses: an API's model, or the one Claude Code is asked for. Returns
    /// false when there was no such backend.
    pub fn set_model(&self, name: &str, model: &str) -> Result<bool, ToolError> {
        let model = model.trim();
        if model.is_empty() {
            return Err(ToolError::invalid("Name a model."));
        }
        let mut cfg = self.config_to_change()?;
        let Some(b) = cfg.backends.iter_mut().find(|b| b.config.name == name) else { return Ok(false) };
        match b.config.kind {
            BackendKind::AgentCli => b.options.cli_model = Some(model.to_string()),
            _ => b.config.model = model.to_string(),
        }
        self.save_config(&cfg)?;
        Ok(true)
    }

    /// How hard a backend thinks (`None`: the usual level again). Only the Claude API and Claude
    /// Code take one ([`effort_in_use`]). Returns false when there was no such backend.
    pub fn set_effort(&self, name: &str, effort: Option<Effort>) -> Result<bool, ToolError> {
        let mut cfg = self.config_to_change()?;
        let Some(b) = cfg.backends.iter_mut().find(|b| b.config.name == name) else { return Ok(false) };
        if effort.is_some() && effort_in_use(&b.config, Some(&b.options)).is_none() {
            return Err(ToolError::invalid(format!("{name} doesn't take an effort level.")).with_remediation("Effort is for the Claude API and Claude Code."));
        }
        b.options.effort = effort;
        self.save_config(&cfg)?;
        Ok(true)
    }

    /// The models a backend can be set to (#123): the API's own list, or Claude's models for Claude
    /// Code. Empty for an agent app that picks its own. Blocking (bounded); run it off the UI thread.
    pub fn model_choices(&self, name: &str) -> Result<Vec<String>, ToolError> {
        let e = self.entry(name)?;
        match (e.config.kind, model_in_use(&e.config, Some(&e.options))) {
            (_, None) => Ok(Vec::new()),
            (BackendKind::AgentCli, Some(_)) => Ok(anthropic::MODELS.iter().map(|m| m.to_string()).collect()),
            _ => self.list_models(name),
        }
    }

    /// Remove a backend and its stored key. Returns false when there was no such backend.
    pub fn remove_backend(&self, name: &str) -> Result<bool, ToolError> {
        let mut cfg = self.config_to_change()?;
        let removed = cfg.remove(name);
        if removed {
            self.save_config(&cfg)?;
            self.keys.delete(name)?;
        }
        Ok(removed)
    }

    /// Some built-in asset provider has a key, so builds can generate assets.
    pub fn has_asset_keys(&self) -> bool {
        let providers = craft_anything_engines::assets::AssetProviders::built_in();
        providers.ids().into_iter().any(|id| self.has_asset_key(&providers, id))
    }

    /// Save an asset provider's key (keychain first). Returns where it went.
    pub fn set_asset_key(&self, provider: &str, key: &str) -> Result<&'static str, ToolError> {
        self.keys.set(&keys::asset_key_name(provider), key.trim())
    }

    pub fn remove_asset_key(&self, provider: &str) -> Result<(), ToolError> {
        self.keys.delete(&keys::asset_key_name(provider))
    }

    /// The provider's key is stored or in its environment variable.
    pub fn has_asset_key(&self, providers: &craft_anything_engines::assets::AssetProviders, provider: &str) -> bool {
        providers.get(provider).is_some_and(|p| keys::asset_key(&self.keys, p.as_ref()).is_some())
    }

    /// True when a key is stored or in the environment (keys themselves are never returned).
    pub fn has_key(&self, name: &str) -> bool {
        self.config().get(name).is_some_and(|b| !b.config.kind.needs_key() || self.keys.resolve(name, b.config.kind).is_some())
    }

    fn entry(&self, name: &str) -> Result<BackendEntry, ToolError> {
        self.config().get(name).cloned().ok_or_else(|| {
            ToolError::invalid(format!("No AI backend named {name:?}")).with_remediation("See `craft-anything-cli ai list`, or add one in Settings → AI.")
        })
    }

    fn key_for(&self, e: &BackendEntry) -> Result<String, ToolError> {
        self.keys.resolve(&e.config.name, e.config.kind).ok_or_else(|| {
            let var = keys::env_var(e.config.kind).unwrap_or("an API key");
            ToolError::new(ErrorCode::BadSettings, format!("{} has no API key.", e.config.name))
                .with_remediation(format!("Add the key in Settings → AI, or set {var}."))
        })
    }

    /// Build the model for an API backend (not agent CLIs).
    pub fn build_model(&self, e: &BackendEntry) -> Result<ModelSlot, ToolError> {
        let c = &e.config;
        let base = c.base_url.as_deref().filter(|b| !b.trim().is_empty());
        let mut tunnel = None;
        // Over ssh: forward a local port to the server as seen from the remote host.
        let tunneled_base = match (&c.ssh_host, c.kind) {
            (Some(host), BackendKind::OpenaiCompatible) if !host.trim().is_empty() => {
                let b = base.unwrap_or("http://127.0.0.1:11434/v1");
                let after = b.split("://").nth(1).unwrap_or(b);
                let hostport = after.split('/').next().unwrap_or_default();
                let path = after.get(hostport.len()..).unwrap_or("/v1");
                let (rh, rp) = hostport.rsplit_once(':').unwrap_or((hostport, "80"));
                let rp: u16 = rp.parse().map_err(|_| ToolError::invalid(format!("Bad port in {b}")))?;
                let t = ssh::open_tunnel(host, rh, rp)?;
                let url = format!("http://127.0.0.1:{}{path}", t.local_port);
                tunnel = Some(t);
                Some(url)
            }
            _ => None,
        };
        let base = tunneled_base.as_deref().or(base);
        // A server on this computer or its network (Ollama, LM Studio, one reached over ssh) costs
        // nothing and gets the small context budget; a remote OpenAI-compatible service has a
        // large context and a bill, as any other cloud API (#374).
        let local = c.kind == BackendKind::OpenaiCompatible && base.is_none_or(detect::on_this_network);
        let model: Box<dyn ChatModel> = match c.kind {
            BackendKind::Anthropic => {
                let mut a = anthropic::Anthropic::new(base, self.key_for(e)?, &c.model);
                a.fallbacks = e.options.fallbacks_enabled.unwrap_or(true);
                Box::new(a)
            }
            BackendKind::Openai => Box::new(openai::OpenAi::official(base, self.key_for(e)?, &c.model)),
            BackendKind::Openrouter => Box::new(openai::OpenAi::openrouter(base, self.key_for(e)?, &c.model)),
            BackendKind::OpenaiCompatible => {
                let mut o = openai::OpenAi::compatible(&c.name, base.unwrap_or("http://127.0.0.1:11434/v1"), self.keys.get(&c.name), &c.model);
                o.react = e.options.react_fallback.unwrap_or(false);
                Box::new(o)
            }
            BackendKind::AgentCli => return Err(ToolError::invalid(format!("{} is an agent app, not an API backend.", c.name))),
        };
        let model = match tunnel {
            Some(t) => Box::new(Tunneled { inner: model, _tunnel: t }) as Box<dyn ChatModel>,
            None => model,
        };
        Ok(ModelSlot { name: c.name.clone(), model, local, effort: e.options.effort, max_turns: e.options.max_turns.unwrap_or(agent::DEFAULT_MAX_TURNS) })
    }

    fn project_root(&self) -> Option<PathBuf> {
        self.engine.try_session().and_then(|s| s.project.as_ref().map(|p| p.root.clone()))
    }

    /// Start a conversation with the lead backend (or the named one).
    pub fn start(&self, backend: Option<&str>, beginner: bool) -> Result<Box<dyn Conversation>, ToolError> {
        let cfg = self.config();
        let first = match backend {
            Some(n) => self.entry(n)?,
            None => cfg
                .backend_for(Role::Lead)
                .cloned()
                .ok_or_else(|| ToolError::unavailable("No AI is set up yet.").with_remediation("Add one in Settings → AI."))?,
        };
        if first.config.kind == BackendKind::AgentCli {
            let spec = cli_agents::CliSpec::new(first.config.clone(), first.options.clone(), beginner, self.project_root());
            let (deep, logs) = {
                let session = self.engine.session();
                (!session.clean_room(), failure_log::dir_in(&session.config_dir()))
            };
            return Ok(cli_agents::conversation(cli_agents::CliSpec { deep, logs: Some(logs), ..spec }));
        }
        let mut chain = vec![self.build_model(&first)?];
        for name in cfg.chain_from(&first.config.name).into_iter().skip(1) {
            if let Some(e) = cfg.get(&name).filter(|e| e.config.kind != BackendKind::AgentCli) {
                match self.build_model(e) {
                    Ok(slot) => chain.push(slot),
                    Err(err) => log::info!("fallback {name} skipped: {}", err.message),
                }
            }
        }
        let host = Arc::new(EngineHost(self.engine.clone()));
        let conv = ApiConversation::start(host, chain, LoopConfig { beginner, prices: cfg.prices.clone(), ..LoopConfig::default() })?;
        Ok(Box::new(conv))
    }

    /// A builder conversation on an API backend: our agent loop with the Build toolset (files and
    /// commands in the project) enabled from the start, and room for a long build. In Deep mode
    /// every toolset is enabled, so it can look inside the original with all of them.
    /// `transcript`: where the conversation is kept, and resumed from when it's there.
    pub fn start_builder(&self, entry: &BackendEntry, beginner: bool, transcript: Option<PathBuf>) -> Result<ApiConversation, ToolError> {
        use craft_anything_engine::Toolset;
        let deep = !self.engine.session().clean_room();
        let toolsets = if deep { self.engine.registry().toolsets() } else { vec![Toolset::Core, Toolset::Build] };
        self.start_loop(entry, beginner, transcript, &toolsets)
    }

    /// Start the asset extractor: our agent loop with the Build tools and the game archive tools.
    pub fn start_extractor(&self, entry: &BackendEntry, beginner: bool, transcript: Option<PathBuf>) -> Result<ApiConversation, ToolError> {
        use craft_anything_engine::Toolset;
        self.start_loop(entry, beginner, transcript, &[Toolset::Core, Toolset::Build, Toolset::Formats])
    }

    fn start_loop(
        &self,
        entry: &BackendEntry,
        beginner: bool,
        transcript: Option<PathBuf>,
        toolsets: &[craft_anything_engine::Toolset],
    ) -> Result<ApiConversation, ToolError> {
        let mut slot = self.build_model(entry)?;
        slot.max_turns = slot.max_turns.max(agent::BUILDER_MAX_TURNS);
        let host = Arc::new(EngineHost(self.engine.clone()));
        ApiConversation::start_with(
            host,
            vec![slot],
            LoopConfig { beginner, prices: self.config().prices.clone(), transcript, ..LoopConfig::default() },
            toolsets.iter().copied().collect(),
        )
    }

    /// Start a conversation with whichever backend fills `role` in the crew.
    pub fn start_role(&self, role: Role, beginner: bool) -> Result<Box<dyn Conversation>, ToolError> {
        let cfg = self.config();
        let e = cfg.backend_for(role).ok_or_else(|| {
            ToolError::unavailable(format!("No backend is set for the {} role.", config::role_key(role)))
                .with_remediation("Choose one in Settings → AI → Roles.")
        })?;
        self.start(Some(&e.config.name), beginner)
    }

    /// Compare mode: the same question to two backends. Returns one conversation per backend,
    /// tagged by name; the caller sends the same text to both and shows them side by side.
    pub fn compare(&self, a: &str, b: &str, beginner: bool) -> Result<Vec<Labeled>, ToolError> {
        if a == b {
            return Err(ToolError::invalid("Pick two different backends to compare."));
        }
        Ok(vec![(a.to_string(), self.start(Some(a), beginner)?), (b.to_string(), self.start(Some(b), beginner)?)])
    }

    /// Live model list for a backend. Blocking (bounded); run it off the UI thread.
    pub fn list_models(&self, name: &str) -> Result<Vec<String>, ToolError> {
        let e = self.entry(name)?;
        let base = e.config.base_url.as_deref().filter(|b| !b.trim().is_empty());
        let t = Duration::from_secs(10);
        match e.config.kind {
            BackendKind::Anthropic => anthropic::Anthropic::new(base, self.key_for(&e)?, &e.config.model).list_models(t),
            BackendKind::Openai => openai::OpenAi::official(base, self.key_for(&e)?, &e.config.model).list_models(t),
            BackendKind::Openrouter => openai::OpenAi::openrouter(base, self.key_for(&e)?, &e.config.model).list_models(t),
            BackendKind::OpenaiCompatible => {
                if e.config.ssh_host.as_deref().is_some_and(|h| !h.trim().is_empty()) {
                    return Err(ToolError::unavailable("Listing models on a remote server isn't supported yet.").with_remediation("Type the model name."));
                }
                openai::OpenAi::compatible(&e.config.name, base.unwrap_or("http://127.0.0.1:11434/v1"), self.keys.get(&e.config.name), "").list_models(t)
            }
            BackendKind::AgentCli => Ok(BackendKind::AgentCli.suggested_models().iter().map(|s| s.to_string()).collect()),
        }
    }

    /// Send a tiny request and time it; a coding agent only runs `--version`, so its report says
    /// `version_only`. Blocking (bounded); run it off the UI thread.
    pub fn test_backend(&self, name: &str) -> Result<TestReport, ToolError> {
        let e = self.entry(name)?;
        let start = Instant::now();
        if e.config.kind == BackendKind::AgentCli {
            let program = e.options.command.clone().unwrap_or_else(|| cli_agents::program_for(&e.config.model));
            let p = match e.config.ssh_host.as_deref().filter(|h| !h.trim().is_empty()) {
                Some(h) => craft_anything_platform::Process::new("ssh").args(ssh::ssh_args(h, &[program.clone(), "--version".into()])),
                None => craft_anything_platform::Process::new(&program).arg("--version"),
            };
            let out = p.timeout(Duration::from_secs(15)).run_checked()?;
            return Ok(TestReport {
                backend: e.config.name.clone(),
                model: e.config.model.clone(),
                latency_ms: start.elapsed().as_millis() as u64,
                reply: out.stdout_text().lines().next().unwrap_or_default().trim().to_string(),
                version_only: true,
            });
        }
        let mut slot = self.build_model(&e)?;
        let stop = Stop::default();
        let (tx, rx) = std::sync::mpsc::channel();
        // A hard bound even if the server trickles bytes forever.
        std::thread::Builder::new()
            .name("ai-test".into())
            .spawn(move || {
                let msgs = req_parts();
                let r = slot.model.turn(&req_owned(&msgs), &mut |_| {}, &stop).map(|r| (r, slot.model.model()));
                let _ = tx.send(r);
            })
            .map_err(|e| ToolError::internal(e.to_string()))?;
        let (r, model) =
            rx.recv_timeout(Duration::from_secs(60)).map_err(|_| ToolError::new(ErrorCode::TimedOut, format!("{name} didn't answer within 60 s.")))??;
        Ok(TestReport {
            backend: e.config.name.clone(),
            model: if r.model.is_empty() { model } else { r.model },
            latency_ms: start.elapsed().as_millis() as u64,
            reply: r.message.text().trim().to_string(),
            version_only: false,
        })
    }

    /// For `doctor`: is each enabled backend reachable? `(name, Ok(latency ms) | Err(reason))`.
    /// Probes run in parallel; the whole check is bounded to about 12 s.
    pub fn check_reachability(&self) -> Vec<(String, Result<u64, String>)> {
        let entries: Vec<BackendEntry> = self.config().enabled().cloned().collect();
        let (tx, rx) = std::sync::mpsc::channel();
        for (i, e) in entries.iter().enumerate() {
            let e = e.clone();
            let key = self.keys.resolve(&e.config.name, e.config.kind);
            let tx = tx.clone();
            let _ = std::thread::Builder::new().name("ai-reach".into()).spawn(move || {
                let _ = tx.send((i, reach(&e, key)));
            });
        }
        drop(tx);
        let deadline = Instant::now() + Duration::from_secs(12);
        let mut results: Vec<Option<Result<u64, String>>> = vec![None; entries.len()];
        while results.iter().any(Option::is_none) {
            match rx.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
                Ok((i, r)) => {
                    if let Some(slot) = results.get_mut(i) {
                        *slot = Some(r);
                    }
                }
                Err(_) => break,
            }
        }
        entries.into_iter().zip(results).map(|(e, r)| (e.config.name, r.unwrap_or_else(|| Err("no answer in time".into())))).collect()
    }
}

fn req_parts() -> Vec<Msg> {
    vec![Msg::user_text("Reply with the single word: ready")]
}

fn req_owned(msgs: &[Msg]) -> TurnRequest<'_> {
    TurnRequest { system: "You are a connectivity check. Answer in one word.", messages: msgs, tools: &[], effort: Effort::High, max_tokens: 2048 }
}

fn reach(e: &BackendEntry, key: Option<String>) -> Result<u64, String> {
    let start = Instant::now();
    let t = Duration::from_secs(8);
    let base = e.config.base_url.as_deref().filter(|b| !b.trim().is_empty());
    let need =
        |k: Option<String>| k.ok_or_else(|| format!("no API key (set it in Settings → AI or {})", keys::env_var(e.config.kind).unwrap_or("the environment")));
    let r: Result<(), String> = match e.config.kind {
        BackendKind::Anthropic => anthropic::Anthropic::new(base, need(key)?, &e.config.model).list_models(t).map(|_| ()).map_err(|x| x.message),
        BackendKind::Openai => openai::OpenAi::official(base, need(key)?, &e.config.model).list_models(t).map(|_| ()).map_err(|x| x.message),
        BackendKind::Openrouter => openai::OpenAi::openrouter(base, need(key)?, &e.config.model).list_models(t).map(|_| ()).map_err(|x| x.message),
        BackendKind::OpenaiCompatible | BackendKind::AgentCli if e.config.ssh_host.as_deref().is_some_and(|h| !h.trim().is_empty()) => {
            let host = e.config.ssh_host.clone().unwrap_or_default();
            craft_anything_platform::Process::new("ssh")
                .args(ssh::ssh_args(&host, &["true".to_string()]))
                .timeout(Duration::from_secs(10))
                .run_checked()
                .map(|_| ())
                .map_err(|x| x.message)
        }
        BackendKind::OpenaiCompatible => {
            let b = base.unwrap_or("http://127.0.0.1:11434/v1");
            if !detect::port_open(b, Duration::from_millis(500)) {
                Err(format!("nothing is listening at {b}"))
            } else {
                // An open port isn't a model server: another program may hold it (#37).
                openai::OpenAi::compatible(&e.config.name, b, key, &e.config.model).list_models(t).map(|_| ()).map_err(|x| x.message)
            }
        }
        BackendKind::AgentCli => {
            let program = e.options.command.clone().unwrap_or_else(|| cli_agents::program_for(&e.config.model));
            craft_anything_platform::which(&program).map(|_| ()).ok_or_else(|| format!("{program} isn't on PATH"))
        }
    };
    r.map(|_| start.elapsed().as_millis() as u64)
}

#[cfg(test)]
mod tests;
